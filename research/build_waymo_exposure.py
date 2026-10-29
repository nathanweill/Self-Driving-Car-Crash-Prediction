"""Audit published Waymo snapshots; allocate S2 exposures with explicit assumptions.

Run from the repository: research/.venv/bin/python research/build_waymo_exposure.py
No network access. Inputs remain immutable. Outputs are research products, not
replacement baseline exposures. Missing published cells are NEVER filled with 0.
"""
import json
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from s2sphere import Cell, CellId, LatLng
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
VARS = ["HPMS Yearly Vehicle Miles Traveled", "Waymo RO Miles"]


def sf_rows(df):
    col = "county_name" if "county_name" in df else "Location"
    return df[df[col].str.casefold().str.replace("_", " ").eq("san francisco")].copy()


def unique_exposure(df):
    df = sf_rows(df)
    if df.groupby("S2 Cell")[VARS].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Inconsistent exposure across outcomes")
    if df[VARS].isna().any().any() or (df[VARS] < 0).any().any():
        raise ValueError("Invalid or missing mileage")
    return df.drop_duplicates("S2 Cell")[["S2 Cell"] + VARS].copy()


def s2_polygon(cell_id):
    cid = CellId(int(cell_id))
    if not cid.is_valid() or cid.level() != 13:
        raise ValueError(f"Invalid level-13 S2 ID: {cell_id}")
    cell = Cell(cid)
    ll = [LatLng.from_point(cell.get_vertex(k)) for k in range(4)]
    return Polygon([(p.lng().degrees, p.lat().degrees) for p in ll])


def difference(a, b):
    """Outer join: revisions and missing endpoints survive in output."""
    d = a[["S2 Cell", "Waymo RO Miles"]].merge(
        b[["S2 Cell", "Waymo RO Miles"]], on="S2 Cell", how="outer",
        suffixes=("_start", "_end"), indicator=True)
    d["waymo_miles_increment"] = d["Waymo RO Miles_end"] - d["Waymo RO Miles_start"]
    d["status"] = np.select(
        [d._merge.eq("left_only"), d._merge.eq("right_only"), d.waymo_miles_increment.lt(-1e-6)],
        ["missing_end_snapshot", "missing_start_snapshot", "negative_revision"], default="matched_nonnegative")
    return d.drop(columns="_merge")


def main():
    OUT.mkdir(exist_ok=True)
    snaps, audits = {}, []
    for p in sorted((ROOT / "raw/waymo").glob("*_csv4.csv")):
        stamp = p.stem[:6]
        raw = pd.read_csv(p, dtype={"S2 Cell": str})
        d = unique_exposure(raw)
        snaps[stamp] = d
        totals = pd.read_csv(p.with_name(f"{stamp}_csv1.csv"))
        name_col = totals.columns[0]
        reported = totals.loc[totals[name_col].str.casefold().str.replace("_", " ").eq("san francisco"), totals.columns[1]]
        assert len(reported) == 1
        a = dict(snapshot=stamp, sf_cells=len(d), waymo_cumulative_miles=d[VARS[1]].sum(),
                 human_vmt_2022_benchmark=d[VARS[0]].sum(), csv1_million_miles=float(reported.iloc[0]))
        a["csv4_minus_csv1_miles"] = a["waymo_cumulative_miles"] - a["csv1_million_miles"] * 1e6
        # CSV1 is rounded to .001 million miles. Preserve larger discrepancies
        # for review instead of silently forcing spatial totals to agree.
        a["agrees_with_csv1_within_display_precision"] = abs(a["csv4_minus_csv1_miles"]) <= 1001
        a["geography_label"] = "county" if "county_name" in raw else "operational_location"
        audits.append(a)
    pd.DataFrame(audits).to_csv(OUT / "waymo_snapshot_audit.csv", index=False)
    long = pd.concat([d.assign(snapshot=k) for k, d in snaps.items()], ignore_index=True)
    long.to_csv(OUT / "waymo_s2_snapshots_sf.csv", index=False)
    intervals = []
    for start, end in zip(list(snaps)[:-1], list(snaps)[1:]):
        intervals.append(difference(snaps[start], snaps[end]).assign(start_snapshot=start, end_snapshot=end,
                         geography_definition_changed=(start < '202512' <= end)))
    annual = difference(snaps["202412"], snaps["202512"]).assign(start_snapshot="202412", end_snapshot="202512", geography_definition_changed=True,
                        approved_as_annual_exposure=False)
    pd.concat(intervals).to_csv(OUT / "waymo_s2_intervals.csv", index=False)
    annual.to_csv(OUT / "waymo_s2_calendar_2025.csv", index=False)

    zones = gpd.read_file(ROOT.parent / "results/zones.geojson").to_crs(26910)
    ids = sorted(long["S2 Cell"].unique())
    cells = gpd.GeoDataFrame({"S2 Cell": ids}, geometry=[s2_polygon(c) for c in ids], crs=4326).to_crs(26910)
    cells["cell_area_m2"] = cells.area
    cells.to_crs(4326).to_file(OUT / "waymo_s2_cells.geojson", driver="GeoJSON")
    overlaps = gpd.overlay(cells, zones[["superzone_id", "geometry"]], how="intersection", keep_geom_type=True)
    overlaps["area_weight"] = overlaps.area / overlaps.cell_area_m2

    streets = gpd.read_file(ROOT / "raw/sf/streets.geojson").to_crs(26910)
    # Exclude paper streets, freeways, pedestrian-only and inactive records.
    # These are geometric sensitivity weights, not measured traffic volumes.
    layers = ["STREETS", "PARKS", "PARKS_NPS_PRESIDIO", "PARKS_NPS_FTMASON", "PRIVATE", "STREETS_TI", "STREETS_YBI", "STREETS_HUNTERSP"]
    streets = streets[streets.active.eq(True) & streets.layer.isin(layers)]
    def road_length(poly):
        near = streets.iloc[streets.sindex.query(poly, predicate="intersects")]
        return near.geometry.intersection(poly).union_all().length if len(near) else 0.0
    denominators = {r["S2 Cell"]: road_length(r.geometry) for _, r in cells.iterrows()}
    overlaps["cell_surface_centerline_m"] = overlaps["S2 Cell"].map(denominators)
    overlaps["zone_cell_surface_centerline_m"] = overlaps.geometry.map(road_length)
    overlaps["centerline_weight"] = overlaps.zone_cell_surface_centerline_m / overlaps.cell_surface_centerline_m.replace(0, np.nan)
    # Road centerlines exactly on zone boundaries may be in both geometries.
    # Normalize only those sums exceeding one; document affected cells.
    wsum = overlaps.groupby("S2 Cell").centerline_weight.sum()
    overlaps["boundary_road_normalization"] = overlaps["S2 Cell"].map(wsum).clip(lower=1)
    overlaps["centerline_weight"] /= overlaps.boundary_road_normalization
    weights = pd.DataFrame(overlaps.drop(columns="geometry"))
    weights.to_csv(OUT / "s2_to_superzone_weights.csv", index=False)
    assert weights.groupby("S2 Cell").area_weight.sum().max() <= 1.00001
    assert weights.groupby("S2 Cell").centerline_weight.sum().max() <= 1.00001

    products = []
    for mode in ["area", "centerline"]:
        merged = long.merge(weights[["S2 Cell", "superzone_id", f"{mode}_weight"]], on="S2 Cell", how="left")
        for source, target in [(VARS[0], "human_vmt_2022_benchmark_allocated"), (VARS[1], "waymo_cumulative_miles_allocated")]:
            merged[target] = merged[source] * merged[f"{mode}_weight"]
        g = merged.groupby(["snapshot", "superzone_id"])[["human_vmt_2022_benchmark_allocated", "waymo_cumulative_miles_allocated"]].sum(min_count=1).reset_index()
        g["allocation"] = mode
        products.append(g)
    pd.concat(products).to_csv(OUT / "waymo_human_zone_snapshot_exposure.csv", index=False)
    summary = {"snapshots": len(snaps), "union_sf_cells": len(cells), "zones": len(zones),
               "2025_csv4_sum_difference_miles": float(snaps["202512"][VARS[1]].sum() - snaps["202412"][VARS[1]].sum()),
               "2025_csv1_total_difference_miles_rounded": float((next(a for a in audits if a['snapshot']=='202512')['csv1_million_miles'] - next(a for a in audits if a['snapshot']=='202412')['csv1_million_miles']) * 1e6),
               "snapshots_with_total_discrepancies": [a['snapshot'] for a in audits if not a['agrees_with_csv1_within_display_precision']],
               "2025_cell_status_counts": annual.status.value_counts().to_dict(),
               "boundary_road_normalized_cells": int((wsum > 1 + 1e-6).sum()),
               "interpretation": "Spatial allocation is assumed. Human VMT is a 2022 benchmark in published cells, never a measured 2021-2025 series. Missing snapshot endpoints stay missing. 2025 year-end subtraction crosses an operational-location to county definition change and is diagnostic, NOT approved annual mileage."}
    (OUT / "waymo_exposure_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
