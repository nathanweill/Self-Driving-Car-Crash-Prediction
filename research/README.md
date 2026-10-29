# Data for the commercial AV analysis

Additional mileage, crash-location and activity data for the 65 San Francisco
zones used in the paper. The scripts produce alternative HV and AV mileage
estimates for 2021-2025, a Waymo/reference panel for January-June 2026, refined
Waymo crash locations, and monthly traffic and passenger-activity covariates.

The derived tables are included in `outputs/` and can be inspected directly.
They are inputs for evaluating a commercial-service extension; the paper's
testing-only panel and fitted results remain in `results/`.

## Quick start

From the repository root, using Python 3.12:

```bash
python3.12 -m venv research/.venv
research/.venv/bin/python -m pip install -r research/requirements-research.txt
research/.venv/bin/python research/download_recorded_sources.py  # restore raw/ if absent
research/.venv/bin/python research/reproduce.py                 # rebuild outputs/ and run tests
```

The raw downloads and virtual environment are excluded from Git. `sources.json`
records the source URLs, retrieval dates, response metadata and SHA-256 hashes.
Downloads are checked against those hashes. If a source has changed, use the
pinned cache or add an explicitly versioned source. Rebuilding from a populated
cache requires no network access.

Tested with Python 3.12.14 and the versions in `requirements-research.txt`.
The full run verifies 79 source files, runs 13 builders and passes 50 tests.
An independent run starting without derived outputs reproduced 127 output files
byte for byte in the same environment. [validation.json](validation.json)
records the input and output hashes.

## Directory layout

```
build_*.py, audit_*.py    source extraction and derived tables
geocode_waymo.py          initial street-centerline geocoder
refine_waymo_geocoding.py refined locations and allocation sensitivities
reproduce.py             source verification, builders and tests
download_recorded_sources.py  restore the pinned public downloads
requirements-research.txt Python dependencies
sources.json             download URLs, dates and hashes
inputs/                  source extracts and explicit interpretation rules
outputs/                 derived tables and diagnostics
test_*.py                integrity and conservation checks
audits/                  verification records
```

## Data and outputs

Paths below are relative to `outputs/`. Each method note lists the individual
files, units, allocation assumptions and source limitations.

| Folder | Content | Method |
|---|---|---|
| `human_mileage_candidates/` | Five HV mileage alternatives, each 65 zones × 2021-2025: expanded SFCTA traffic or fixed HPMS spatial shares | [Human mileage](HUMAN_MILEAGE_DELIVERY.md) |
| `av_mileage_candidates/` | Five AV mileage alternatives with testing, Waymo rider-only and Cruise components; calendar-year and June-15-2025 cutoff versions, each 325 rows | [AV mileage](AV_MILEAGE_DELIVERY.md) |
| `extension_2026_h1/` | Four 65-zone Waymo/reference datasets for January-June 2026; two reference-mileage methods × two crash-location allocations | [2026 H1 panel](EXTENSION_2026_H1_DELIVERY.md) |
| `other_operators_2026/` | Disclosed pilot mileage, SF allocation scenarios and 17 located Zoox SF crash reports; separate from the matched Waymo panel | [Other operators](OTHER_OPERATORS_2026.md) |
| `geocoding_refined/` | All 757 Waymo source rows, including 749 candidate point locations, uncertainty weights and unresolved cases | [Crash locations](GEOCODING_DELIVERY.md) |
| `service_activity/` | Monthly traffic, historical passenger trips, two recent-trip estimates, Waymo activity and authority-event dates; 4,290 monthly rows, 325 annual rows and 65 H1 rows per spatial allocation | [Activity covariates](SERVICE_ACTIVITY_DELIVERY.md) |

The main HV alternatives are `sfcta_expanded.csv` and `hpms_2022_static.csv`.
The main AV alternatives are `hybrid_hpms_calendar_year.csv` and
`hybrid_sfcta_calendar_year.csv`; the June-15 versions and sensitivity files
are listed in the AV mileage note. For activity covariates, start with
`zone_month_covariates_centerline.csv` or `zone_year_covariates_centerline.csv`;
the area versions test spatial-allocation sensitivity.

Top-level output files contain the underlying source audits and spatial
crosswalks. `outputs/waymo_sf_geocoding.csv` is the initial geocoding result;
`outputs/geocoding_refined/waymo_sf_geocoding_refined.csv` is the refined version.

## Sources

Public sources were retrieved on October 27-29, 2026. Exact retrieval times and
file versions are in `sources.json`.

| Source | Use |
|---|---|
| [SFCTA congestion dashboard](https://congestion.sfcta.org/) | Monthly segment traffic estimates and citywide VMT anchors |
| [Waymo Safety Impact Data Hub](https://waymo.com/safety/impact/) | Nine spatial mileage releases, the 2022 HPMS benchmark, and rider-only crash descriptions |
| [CPUC quarterly reports](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting) | Deployment/pilot mileage, historical tract trips and California monthly trip totals |
| [DataSF street centerlines](https://data.sf.gov/Geographic-Locations-and-Boundaries/San-Francisco-Basemap-Street-Centerlines/3psu-pn9h), [2010 tracts](https://data.sf.gov/api/geospatial/n6fe-r6rd?method=export&format=GeoJSON), [2020 tracts](https://data.sf.gov/api/geospatial/tmph-tgz9?method=export&format=GeoJSON) | Road coverage, geocoding and spatial allocation |
| [SFDPH/SFPD injury crashes](https://data.sf.gov/Public-Safety/Traffic-Crashes-Resulting-in-Injury/ubvf-ztfx) | Provisional city-street reference injury crashes for the 2026 extension |
| [NHTSA SGO](https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting) and [DMV-linked TIMS data](https://tims.berkeley.edu/tools/avsafety.php) | Report identity, crash attributes and public-coordinate crosswalks |

The builders also read four files already in the repository:
`results/panel.csv`, `results/zones.geojson`,
`data/mileage/dmv_testing_monthly.csv` and `data/mileage/sgo_ca_incidents.csv`.
Their hashes are recorded in `validation.json`. These inputs are unchanged
between the tested baseline `fed7e5a` and the inspected `main` commit `2c3ceac`.
The research builders use the saved zones and do not require the Street View
segment labels.

## Units, joins and scope

Annual mileage files join on `superzone_id,year`. The `*_million_miles` fields
use the model's exposure units; the corresponding `*_miles` fields are also
supplied. Choose one method and time scope. The HV files cover calendar years;
using the AV June-15 cutoff also requires human exposure and crash outcomes
for the same period.

The 2026 H1 table is keyed by `reference_method`, `waymo_location_allocation`
and `superzone_id`. Select one alternative per fit. Fractional crash allocations
are sensitivity weights and require a compatible response model. The H1 table
retains its original geocoding allocation. The refined geocoder leaves its eight
selected point-event zones unchanged; changes to fractional allocations are in
[h1_injury_allocation_comparison.csv](outputs/geocoding_refined/h1_injury_allocation_comparison.csv).

Monthly covariates join on `superzone_id,date`, where `date` is `YYYY-MM`.
Annual summaries include per-feature coverage counts. Redacted or unavailable
observations remain missing; a partial-year sum is labeled accordingly.

**Scope.** Mileage allocations and recent-trip estimates depend on the assumptions
in the method notes. The matched 2026 panel covers Waymo rider-only operation and
city-street reference injury crashes; other operators' pilot miles and crash
reports do not establish matching exposure/outcome populations. Reference traffic
and crashes are not verified human-only. Six Waymo descriptions remain unresolved,
one has multiple junction candidates, and one is excluded for a city conflict.
Activity measures describe driving or fulfilled trips, not authorized service
polygons, ride requests or unmet demand.

These are retrospective inputs. Some AV allocations use SGO crash shares and
some reconstructions use later releases. Prospective tests require appropriately
dated inputs and re-estimation. The alternative datasets have not been selected
using model performance.

## Method notes and verification

The method notes linked above describe the current datasets. [CATEGORY_3_STATUS.md](CATEGORY_3_STATUS.md)
summarizes the unresolved all-operator exposure/outcome match.
[MANUSCRIPT_NOTES.md](MANUSCRIPT_NOTES.md) contains proposed source/data wording;
[REPORT.md](REPORT.md) preserves the initial audit and subsequent updates.
[NEXT_STEPS.md](NEXT_STEPS.md) lists source refinements and checks before refitting.

To regenerate the road-coverage figure separately:

```bash
research/.venv/bin/python research/plot_coverage.py
```

Code follows the repository's license. Source data and derived tables retain
their source-specific terms and attribution. Cite the paper and the original
data sources, following the repository's `CITATION.cff` and README.
