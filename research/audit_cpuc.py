"""Audit small public CPUC tables directly inside archives; no huge extraction.

Redaction is field-specific; collision totals are not missing just because trip
counts are redacted. Tract IDs are strings padded to 11 digits before SF filtering.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs/cpuc"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    audit = []
    for archive in sorted((ROOT / "raw/cpuc").glob("*.zip")):
        with zipfile.ZipFile(archive) as z:
            for member in z.namelist():
                stem = re.sub(r"[ _-]", "", Path(member).name).casefold()
                if not stem.endswith(".csv") or not any(key in stem for key in ["monthlytract", "monthlevel", "avmonthpart", "incidentslocation"]):
                    continue
                data = z.read(member)
                import io
                d = pd.read_csv(io.BytesIO(data), dtype=str)
                if "Tract" in d:
                    d["tract_geoid"] = d.Tract.str.strip().str.zfill(11)
                    sf = d[d.tract_geoid.str.startswith("06075")].copy()
                else:
                    sf = d.copy()  # explicitly labeled statewide/month-level below
                kind = "tract_collision" if "incidentslocation" in stem else "tract_trips" if "monthlytract" in stem else "statewide_month"
                output = OUT / f"{archive.stem}_{kind}.csv"
                sf.to_csv(output, index=False)
                item = {"archive": archive.name, "member": member, "member_sha256": hashlib.sha256(data).hexdigest(),
                        "kind": kind, "total_rows": len(d), "sf_rows": len(sf) if "Tract" in d else None,
                        "fields": {c: {"redacted": int(d[c].fillna("").str.casefold().eq("redacted").sum()), "blank": int(d[c].isna().sum())} for c in d.columns}}
                if "CollisionsAll" in sf:
                    counts = pd.to_numeric(sf.CollisionsAll.str.replace(",", ""), errors="coerce")
                    item["sf_collision_count_sum"] = float(counts.sum())
                    item["sf_collision_count_non_numeric_rows"] = int(counts.isna().sum())
                    item["sf_tracts_with_positive_counts"] = int(counts.gt(0).sum())
                audit.append(item)
    (ROOT / "outputs/cpuc_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps([{k:v for k,v in a.items() if k != 'fields'} for a in audit], indent=2))


if __name__ == "__main__": main()
