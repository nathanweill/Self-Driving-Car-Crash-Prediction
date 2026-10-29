"""Map SFCTA's published modeled daily segment volumes into the paper's zones.

This yields partial-network VMT proxies, NOT observed complete-zone human mileage.
AM and PM rows carry duplicate daily volume; count each segment-month only once.
Dates, not the constant source 'year' field, identify the observation month.
"""
import json
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"


def deduplicate_daily_volumes(df):
    keys = ["cmp_segid", "date"]
    if df.duplicated(keys + ["period"]).any():
        raise ValueError("Repeated segment/date/period observation")
    counts = df.groupby(keys).imp_vol.nunique(dropna=False)
    if counts.gt(1).any():
        raise ValueError("AM and PM contain conflicting daily volumes; review before combining")
    if df.imp_vol.isna().any() or df.imp_vol.lt(0).any():
        raise ValueError("Missing/negative volume")
    return df.drop_duplicates(keys).copy()


def main():
    OUT.mkdir(exist_ok=True)
    records = json.loads((ROOT / "raw/sfcta/segments.json").read_text())
    segments = gpd.GeoDataFrame([{k: v for k, v in r.items() if k != "geometry"} for r in records],
                               geometry=[shape(json.loads(r["geometry"])) for r in records], crs=4326).to_crs(26910)
    assert not segments.cmp_segid.duplicated().any()
    segments["full_geom_m"] = segments.geometry.length
    zones = gpd.read_file(ROOT.parent / "results/zones.geojson").to_crs(26910)
    intersections = gpd.overlay(segments, zones[["superzone_id", "geometry"]], how="intersection", keep_geom_type=True)
    intersections["length_fraction"] = intersections.geometry.length / intersections.full_geom_m
    assert intersections.groupby("cmp_segid").length_fraction.sum().max() <= 1.0001
    intersections["allocated_source_length_miles"] = intersections["length"] * intersections.length_fraction
    intersections.drop(columns="geometry").to_csv(OUT / "sfcta_segment_to_zone.csv", index=False)
    segments.to_crs(4326).to_file(OUT / "sfcta_segments.geojson", driver="GeoJSON")
    observations = pd.DataFrame(json.loads((ROOT / "raw/sfcta/monthly_volumes_2021_2025.json").read_text()))
    daily = deduplicate_daily_volumes(observations)
    assert daily.date.nunique() == 60 and daily.date.min() == "2021-01" and daily.date.max() == "2025-12"
    assert set(daily.cmp_segid) <= set(segments.cmp_segid)
    daily["days_in_month"] = pd.to_datetime(daily.date).dt.days_in_month
    joined = daily.merge(intersections[["cmp_segid", "superzone_id", "allocated_source_length_miles"]], on="cmp_segid")
    joined["partial_network_daily_vmt_proxy"] = joined.imp_vol * joined.allocated_source_length_miles
    joined["partial_network_month_vmt_proxy"] = joined.partial_network_daily_vmt_proxy * joined.days_in_month
    m = joined.groupby(["superzone_id", "date"]).agg(
        partial_network_daily_vmt_proxy=("partial_network_daily_vmt_proxy", "sum"),
        partial_network_month_vmt_proxy=("partial_network_month_vmt_proxy", "sum"),
        observed_directed_segment_count=("cmp_segid", "nunique"),
        observed_directed_length_miles=("allocated_source_length_miles", "sum")).reset_index()
    full_index = pd.MultiIndex.from_product([sorted(zones.superzone_id), sorted(daily.date.unique())], names=["superzone_id", "date"])
    m = m.set_index(["superzone_id", "date"]).reindex(full_index).reset_index()
    m["observation_status"] = np.where(m.partial_network_month_vmt_proxy.isna(), "no_segment_data", "partial_network_proxy")
    m.to_csv(OUT / "sfcta_zone_month_vmt_proxy.csv", index=False)
    m["calendar_year"] = m.date.str[:4].astype(int)
    annual = m.groupby(["superzone_id", "calendar_year"]).agg(
        partial_network_annual_vmt_proxy=("partial_network_month_vmt_proxy", lambda s: s.sum(min_count=1)),
        months_with_data=("partial_network_month_vmt_proxy", "count"),
        min_directed_segment_count=("observed_directed_segment_count", "min"),
        max_directed_segment_count=("observed_directed_segment_count", "max")).reset_index()

    # Coverage diagnostic: official surface-street length within 20m of the CMP
    # geometry, not percentage of VMT covered. OSM-style direction duplication
    # is removed geometrically before computing the corridor coverage metric.
    streets = gpd.read_file(ROOT / "raw/sf/streets.geojson").to_crs(26910)
    surface_layers = ["STREETS", "PARKS", "PARKS_NPS_PRESIDIO", "PARKS_NPS_FTMASON", "PRIVATE", "STREETS_TI", "STREETS_YBI", "STREETS_HUNTERSP"]
    streets = streets[streets.active.eq(True) & streets.layer.isin(surface_layers)]
    observed_segments = segments[segments.cmp_segid.isin(daily.cmp_segid)]
    corridor = observed_segments.geometry.union_all().buffer(20)
    coverage = []
    for _, z in zones.iterrows():
        near = streets.iloc[streets.sindex.query(z.geometry, predicate="intersects")]
        street_geom = near.geometry.intersection(z.geometry).union_all()
        coverage.append({"superzone_id": int(z.superzone_id), "official_surface_centerline_m": street_geom.length,
                         "surface_centerline_within_20m_cmp_m": street_geom.intersection(corridor).length,
                         "surface_centerline_coverage_fraction": street_geom.intersection(corridor).length / street_geom.length if street_geom.length else np.nan})
    coverage = pd.DataFrame(coverage)
    coverage.to_csv(OUT / "sfcta_zone_road_coverage.csv", index=False)
    annual = annual.merge(coverage, on="superzone_id")
    annual["approved_as_complete_human_exposure"] = False
    annual.to_csv(OUT / "sfcta_zone_year_vmt_proxy.csv", index=False)

    aggregate = pd.DataFrame(json.loads((ROOT / "raw/sfcta/citywide_vmt.json").read_text()))
    aggregate = aggregate[aggregate.fac_typ.eq("Citywide") & aggregate.date.between("2021-01", "2025-12")]
    assert aggregate.groupby("date").metric.nunique().max() == 1
    aggregate = aggregate.drop_duplicates("date").copy()
    aggregate["calendar_year"] = aggregate.date.str[:4].astype(int)
    aggregate["days_in_month"] = pd.to_datetime(aggregate.date).dt.days_in_month
    aggregate["monthly_vmt_millions_proxy"] = aggregate.metric * aggregate.days_in_month
    city = aggregate.groupby("calendar_year").agg(sfcta_annual_vmt_millions_proxy=("monthly_vmt_millions_proxy", "sum"), months=("date", "count")).reset_index()
    city.to_csv(OUT / "sfcta_citywide_year_vmt_proxy.csv", index=False)
    summary = {"source_observation_rows": len(observations), "unique_segment_months": len(daily),
               "source_geometry_segments": len(segments), "observed_segments": daily.cmp_segid.nunique(), "months": daily.date.nunique(),
               "zone_year_rows": len(annual), "zone_years_without_segment_data": int(annual.partial_network_annual_vmt_proxy.isna().sum()),
               "minimum_zone_centerline_coverage": coverage.surface_centerline_coverage_fraction.min(),
               "median_zone_centerline_coverage": coverage.surface_centerline_coverage_fraction.median(),
               "maximum_zone_centerline_coverage": coverage.surface_centerline_coverage_fraction.max(),
               "note": "Volumes are imputed from INRIX speeds/VDFs. Daily estimates multiplied by calendar days are proxies. Coverage is road length, not VMT. Source 'year'=2020 is not observation year. AM/PM daily volumes counted once. No missing road exposure imputed."}
    (OUT / "sfcta_exposure_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
