"""Verify cached evidence, rebuild local outputs, then run integrity tests."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    sources = json.loads((ROOT / "sources.json").read_text())
    errors = []
    for name, record in sources.items():
        file = ROOT / "raw" / name
        if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest() != record["sha256"]:
            errors.append(name)
    if errors: raise SystemExit("Missing or changed cached inputs: " + ", ".join(errors))
    for script in ["build_waymo_exposure.py", "build_sfcta_exposure.py", "geocode_waymo.py", "refine_waymo_geocoding.py", "audit_cpuc.py", "build_2026_crash_candidate.py", "build_human_mileage_candidates.py", "build_av_mileage_candidates.py", "build_2026_extension.py", "audit_other_operators_2026.py", "build_other_operator_crash_crosswalk.py", "build_cpuc_trip_activity.py", "build_service_activity.py"]:
        subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT.parent, check=True)
    subprocess.run([sys.executable, "-m", "pytest", str(ROOT / "test_data_integrity.py"), str(ROOT / "test_geocoding_refinement.py"), str(ROOT / "test_human_mileage_candidates.py"), str(ROOT / "test_av_mileage_candidates.py"), str(ROOT / "test_2026_extension.py"), str(ROOT / "test_other_operators_2026.py"), str(ROOT / "test_other_operator_crash_crosswalk.py"), str(ROOT / "test_service_activity.py"), "-q"], check=True)
    print(f"Verified {len(sources)} downloaded source hashes; all rebuilds and tests passed.")


if __name__ == "__main__": main()
