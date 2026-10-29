"""Prepare a clearly labeled, provisional SF injury-crash candidate for 2026.

Source is SFDPH/SFPD (TransBASE), not the original TIMS extract. Highways are
excluded and AV involvement cannot be separated from these supplied fields.
No counts are merged into the paper's baseline panel.
"""
import json
from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"


def main():
    OUT.mkdir(exist_ok=True)
    df = pd.DataFrame(json.loads((ROOT / "raw/sf/injury_crashes_2025_2026.json").read_text()))
    duplicates = df[df.case_id_pkey.duplicated(False)].copy()
    for _, group in duplicates.groupby("case_id_pkey"):
        if len(group.drop(columns="unique_id").drop_duplicates()) > 1:
            raise ValueError("Conflicting duplicate case IDs need manual resolution")
    duplicates.to_csv(OUT / "sf_injury_duplicate_cases.csv", index=False)
    df = df.drop_duplicates("case_id_pkey").copy()
    df["date"] = pd.to_datetime(df.collision_date)
    df["longitude"] = pd.to_numeric(df.tb_longitude, errors="coerce")
    df["latitude"] = pd.to_numeric(df.tb_latitude, errors="coerce")
    zones = gpd.read_file(ROOT.parent / "results/zones.geojson").to_crs(4326)
    points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs=4326)
    rows = []
    for _, row in points.iterrows():
        ids = zones.loc[zones.geometry.covers(row.geometry), "superzone_id"].tolist() if pd.notna(row.longitude) and pd.notna(row.latitude) else []
        r = row.drop(labels="geometry").to_dict()
        r["zone_candidates"] = ";".join(map(str, ids))
        r["superzone_id"] = ids[0] if len(ids) == 1 else None
        r["geographic_status"] = "unique_zone" if len(ids) == 1 else "missing_coordinates" if pd.isna(row.longitude) else "ambiguous_or_outside_study"
        rows.append(r)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "sf_injury_2025_2026_geocoded_candidate.csv", index=False)
    summaries = []
    for label, start, end in [("2025_calendar", "2025-01-01", "2025-12-31"), ("2026_h1", "2026-01-01", "2026-06-30"), ("2026_published_ytd", "2026-01-01", "2026-08-31")]:
        subset = result[result.date.between(start, end)]
        counts = subset[subset.geographic_status.eq("unique_zone")].groupby("superzone_id").size()
        panel = pd.DataFrame({"superzone_id": sorted(zones.superzone_id)})
        panel["recorded_injury_crashes_in_unique_zone"] = panel.superzone_id.map(counts).fillna(0).astype(int)
        panel["window"] = label
        panel["window_start"] = start
        panel["window_end"] = end
        panel["source"] = "SFDPH/SFPD TransBASE; city streets; not confirmed human-only"
        panel.to_csv(OUT / f"sf_injury_zone_counts_{label}.csv", index=False)
        summaries.append({"window": label, "distinct_cases": len(subset), "geographic_status_counts": subset.geographic_status.value_counts().to_dict()})
    audit = {"raw_rows": len(df) + len(duplicates) - duplicates.case_id_pkey.nunique(), "distinct_case_ids": len(df),
             "duplicated_case_ids": duplicates.case_id_pkey.nunique(), "latest_record_date": str(df.date.max().date()), "windows": summaries,
             "limitations": "Provisional city-street injury/fatality records; highways excluded; no reliable ADS/human distinction in selected fields; missing-coordinate cases retained in audit, not treated as no crashes. Count zeros mean no assigned records, not proven complete surveillance. Source and scope differ from baseline TIMS."}
    (OUT / "sf_injury_candidate_summary.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__": main()
