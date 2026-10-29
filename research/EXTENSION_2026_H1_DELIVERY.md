# January–June 2026 extension

**Other operators:** [Recovered pilot mileage and SF sensitivity range](OTHER_OPERATORS_2026.md). Zoox H1 monthly mileage and 17 mapped SF crash reports are now available; matching passenger-service exposure/outcome scope remains unresolved. See [current status](CATEGORY_3_STATUS.md).

A **Waymo rider-only / city-street reference** panel for all 65 study zones,
January 1-June 30, 2026 (181 days). Waymo rider-only includes driverless testing
and commercial service. A matched all-operator exposure/outcome panel is not
available from the verified inputs.

## Files to use

`outputs/extension_2026_h1/all_candidates.csv` contains four alternatives (260 rows).
Each separate CSV contains 65 zones:

- `sfcta_expanded_point.csv`: contemporary traffic expansion; point crash locations.
- `hpms_static_point.csv`: fixed 2022 HPMS shares; point crash locations.
- `sfcta_expanded_fractional_candidates.csv`: traffic expansion; fractional locations.
- `hpms_static_fractional_candidates.csv`: fixed HPMS shares; fractional locations.

Choose one alternative; do not stack them as independent observations. The
fractional outcome is an allocation sensitivity, not an integer observed count;
it cannot be inserted unchanged into a model requiring integer count responses.

## Mileage processing

Reference city exposure is **1,713.492773 million miles**: sum SFCTA's modeled daily
city VMT × calendar days for each of the six months. AM/PM duplicate daily values
are counted once. All city miles are allocated among the 65 study zones, following
the human-mileage method; mileage is not verified human-only and geographic scope is approximate.

SFCTA spatial shares use segment daily traffic × segment miles within a zone ×
month days. The 101 missing segment-months use that segment's mean daily traffic
across its available H1 months. Road coverage is recomputed for the H1 observed
network using the same official surface-street layers and 20-metre corridor.
Missing roads receive half the blended local/pooled traffic density, with the
the human-mileage shrinkage length (3672.70082944 metres). Normalize expanded estimates
to the H1 city total. The second alternative uses the fixed 2022 HPMS
centerline-allocated spatial shares, scaled to that same H1 city total.

Waymo exposure is **19.790413 million rider-only miles**: subtract fitted December
2025 cumulative S2-cell mileage from June 2026 cumulative mileage, using the
AV-mileage county reconciliation and monotone-fit audit. Allocate increments by surface
road centerline weights. The retained zone allocation before normalization is
19,776,482.466 miles; normalize to the full SF total and blend 99% Waymo shares
with 1% of the selected reference shares, as in the AV-mileage reconstruction. Rider-only includes
both driverless testing and commercial operation. Other operators are not set to
zero; they are outside this dataset's scope.

## Crash processing and limits

The Waymo source has 158 H1 rows / 157 distinct SGO report IDs. Event attributes
must agree before duplicate IDs are removed. Of 14 injury events, **8** also meet
police-reported, in-transport, and surface-street filters; these are the selected
outcome. All eight have candidate point zones. Point allocation counts one per
point zone. The sensitivity splits one event equally across zones intersecting
the geocoder's assumed uncertainty radius; these weights are not probabilities.

SFDPH/SFPD reference data has **1,578** distinct H1 injury/fatality cases:
**1,559** uniquely assigned, 15 missing coordinates, and 4 ambiguous/outside.
All cases remain in the event audit; only unique assignments enter zone counts.
Do not treat unassigned cases as zero crashes. The reference is not reliably
human-only, may include AV cases, excludes highways, and differs from the original
TIMS source. Both counts and mileage are labeled reference rather than verified
human-only. The outcome filters improve comparability but do not establish equal
reporting/ascertainment. These files alone do not support a causal safety claim.

## Evidence, code, and reproduction

Builder: `build_2026_extension.py`; tests: `test_2026_extension.py`.
Run `research/.venv/bin/python research/reproduce.py` from the repository root.
Raw source hashes and retrieval URLs are in `sources.json`; the new source is
`sfcta/monthly_volumes_2026_h1.json`. Existing Waymo CSV2/CSV4 snapshots, SF injury
records, SFCTA city totals, road geometries, and the human/AV mileage artifacts are reused.
The output folder includes monthly traffic, city totals, road expansion, S2-cell
increments, both crash-event audits, and a validation summary.

Public availability checked 2026-10-29:
[DMV permit resources](https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/autonomous-vehicles-program-permit-resources/)
and [DMV AV homepage](https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/)
did not yield a verified downloadable all-operator H1 deployment-mileage dataset.
Reporting requirements/templates are not submitted mileage observations.
[CPUC quarterly reports](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting)
are a separate source; the existing CPUC audit documents public/redacted-field
limitations. This search result is not proof that no further records exist.

The four datasets are inputs for model comparison; no fitted results are included.
