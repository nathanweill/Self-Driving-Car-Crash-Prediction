# AV mileage by zone and year

Two primary alternatives and three sensitivity variants cover **65 zones × five
years (2021-2025)**. Each contains separate testing, Waymo rider-only and Cruise
commercial components. Operator totals and spatial allocations are estimated
under the assumptions below.

## Download and use

| Candidate | Full calendar years | All streams end June 15 in 2025 |
|---|---|---|
| **Hybrid + HPMS**: Waymo-specific spatial information; other streams use HPMS human-mileage shares | [CSV](outputs/av_mileage_candidates/hybrid_hpms_calendar_year.csv) | [CSV](outputs/av_mileage_candidates/hybrid_hpms_through_june15_2025.csv) |
| **Hybrid + SFCTA**: same Waymo reconstruction; other streams use time-varying SFCTA human-mileage shares | [CSV](outputs/av_mileage_candidates/hybrid_sfcta_calendar_year.csv) | [CSV](outputs/av_mileage_candidates/hybrid_sfcta_through_june15_2025.csv) |
| Fixed Waymo footprint: first available footprint used in every year | [CSV](outputs/av_mileage_candidates/fixed_waymo_footprint_calendar_year.csv) | [CSV](outputs/av_mileage_candidates/fixed_waymo_footprint_through_june15_2025.csv) |
| Legacy-geography sensitivity: omit the historical county-fraction adjustment | [CSV](outputs/av_mileage_candidates/legacy_geography_sensitivity_calendar_year.csv) | [CSV](outputs/av_mileage_candidates/legacy_geography_sensitivity_through_june15_2025.csv) |
| Testing SF upper scenario: assign all reported California testing miles to SF | [CSV](outputs/av_mileage_candidates/testing_sf_upper_calendar_year.csv) | [CSV](outputs/av_mileage_candidates/testing_sf_upper_through_june15_2025.csv) |

The upper scenario is a deliberately broad screening case, not a confidence bound or a bound on unreported/omitted operations. The June-15 files retain full years in 2021–2024 and cover January 1–June 15 only in 2025. Their `window_start`, `window_end`, and `scope` columns make that distinction explicit.

Each file has 325 unique `superzone_id, year` keys. `av_mileage_million_miles` matches the original model’s mileage units; the three stream columns and `av_mileage_miles` are in **miles**. Choose one candidate and one scope before joining. [A wide comparison table](outputs/av_mileage_candidates/candidate_comparison_million_miles.csv) and [all operator/mode allocations, compressed CSV](outputs/av_mileage_candidates/operator_zone_year_all_candidates.csv.gz) are also provided. The latter has 46 operator/mode pairs, including pairs assigned zero SF mileage by the estimation rule.

## Precisely how the components are processed

### 1. Testing: calendar-month DMV data, excluding Waymo driverless

- Read the repository’s monthly California DMV mileage, retaining each operator and testing mode.
- Convert statewide to SF mileage using the original paper’s SGO-based allocation logic: calendar-year shares for Waymo with a safety driver; pooled 2021–2025 shares for other fleets. For a driverless fleet without driverless SGO records, use its drivered share. With no SGO evidence, the primary estimate assigns zero SF mileage and flags that assumption.
- Group actual calendar months, rather than labeling December–November reporting totals as calendar years. The input ends in November 2025. **December 2025 is estimated separately for each operator/mode as the mean of September–November 2025 statewide mileage**, then multiplied by its SF share. This contributes about **228,017 estimated SF miles** to the primary full-year total.
- Allocate each resulting SF operator total across zones using the HPMS or SFCTA shares from the human-mileage estimates. These are proxy spatial distributions, not observed testing routes.
- **Remove every Waymo driverless-testing row before aggregation.** Those miles belong to the Waymo rider-only component. Retain Waymo drivered testing.

The [monthly audit](outputs/av_mileage_candidates/testing_operator_monthly_estimates.csv) distinguishes source months, December estimates, and assumed-zero absent rows. [Excluded Waymo rows](outputs/av_mileage_candidates/excluded_waymo_driverless_testing.csv) make overlap removal inspectable. SGO-derived allocation is outcome-dependent and retrospective; it must not be represented as independent measured exposure or a prospective forecast input.

### 2. Waymo: reconcile snapshots, retain early total anchors, estimate spatial shares

The spatial source is nine cached Waymo CSV4 snapshots ending July 2024–June 2026. Repeated outcome rows are counted once per cell.

**Reconcile geography and revisions:**

1. Earlier releases label an operational area; later releases label counties. For each cell, calculate `SF county mileage / mileage across all counties` in the June 2026 release. Multiply each earlier operational-area value by this fraction. Holding that within-cell fraction fixed historically is an assumption, not a recovered historical county boundary allocation.
2. Fit a nondecreasing cumulative-mileage curve independently for each cell using equal-weight least-squares isotonic regression (the code implements the pool-adjacent-violators algorithm). This adjusts inconsistent cumulative values rather than silently dropping negative increments.
3. Fill missing interior snapshots by interpolation in actual elapsed days. Before a cell’s first reported snapshot, assume zero; this is flagged as an estimation assumption, not an observed zero. Interpolate within reporting intervals uniformly in time to evaluate January 1, June 16, and January 1 of the following year.

The primary audit records **six adjusted observed entries**, **16,810.27 total absolute miles of monotonicity adjustment**, and **96 missing cell/snapshot entries**. County-fraction adjustments are recorded separately from monotonicity adjustments. The legacy-geography variant reruns the fit without step 1. See [county-adjusted audit](outputs/av_mileage_candidates/waymo_cumulative_audit_county_adjusted.csv) and [legacy audit](outputs/av_mileage_candidates/waymo_cumulative_audit_legacy_labels.csv).

**Choose annual totals and spatial weights:**

- **2021–2024 totals:** retain the original supplement’s rounded Waymo rider-only estimates: **0, 0.06, 2.28, and 12.94 million miles**. These remain author estimates, not independently reconstructed exact annual totals. The zero in 2021 inherits the paper’s reporting precision. A [pinned extract with source lines/hash](inputs/paper_commercial_mileage_anchors.csv) makes the build independent of the private Overleaf checkout.
- **2025 total:** difference the fitted cumulative cell values over the selected period. The primary reconstruction gives about **32.186 million miles** for the full calendar year, or **12.663 million** through June 15. These are reconciled estimates and are not the rejected naive subtraction of differently defined published totals.
- **2021–2023 spatial allocation:** backcast the first available July 2024 cumulative footprint.
- **2024 spatial allocation:** use the August–December 2024 increment footprint as a proxy for the full year.
- **2025 spatial allocation:** use the fitted increment footprint over the selected 2025 window.
- Map cells to zones using the existing surface-centerline crosswalk. Normalize retained mileage into shares; then blend **99% Waymo shares + 1% human-mileage shares** to avoid accidental structural-zero zones caused by incomplete spatial coverage. Multiply by the selected annual/partial-year total. The fixed-footprint sensitivity uses July 2024 shares for every year instead.

Spatial retention fractions, time windows, and regularization are recorded in [the allocation audit](outputs/av_mileage_candidates/waymo_spatial_allocation_audit.csv). Early footprints and the 1% blend are modeling choices for testing, not reconstructed vehicle trajectories. Use retrospective evaluation language because some reconciliation inputs come from later releases.

### 3. Cruise: recovered commercial monthly reports

Downloaded seven [official CPUC deployment archives](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting) covering June 2022–February 2024. Extract only Cruise’s commercial driverless monthly CSVs; do not add the separate drivered workbooks.

Sum `TotalVMTPeriod1 + TotalVMTPeriod2 + TotalVMTPeriod3`, which includes the three passenger-service activity periods rather than passenger miles alone. The recovered numeric totals are **51,702.38 miles in 2022** and **373,929.73 miles in 2023**, consistent with the supplement’s rounded 0.05 and 0.37 million miles.

Treat these fleet miles as SF mileage, following the draft’s service scope. Months before June 2022 and after the stated October 2023 cessation are assigned zero under that service-history assumption. The December 2023–February 2024 source fields are **blank**, and stay blank in the evidence table; zero in the modeled panel is not presented as an observed numeric report. Then allocate the totals using the chosen human-mileage spatial shares. Cruise testing remains a separate DMV component.

The [monthly evidence](outputs/av_mileage_candidates/cruise_public_monthly_evidence.csv) records exact archive/member paths and hashes. No trip or crash counts are used to create Cruise’s spatial weights.

## Primary calendar-year totals

Million miles; both primary spatial alternatives have the same fleet totals.

| Year | Testing, excluding Waymo driverless | Waymo rider-only | Cruise commercial | Combined |
|---|---:|---:|---:|---:|
| 2021 | 3.618463 | 0.000000 | 0.000000 | 3.618463 |
| 2022 | 4.893362 | 0.060000 | 0.051702 | 5.005064 |
| 2023 | 5.588350 | 2.280000 | 0.373930 | 8.242280 |
| 2024 | 2.646341 | 12.940000 | 0.000000 | 15.586341 |
| 2025 | 2.288972 | 32.186090 | 0.000000 | 34.475062 |

The common January 1–June 15, 2025 window totals approximately **13.584549 million miles** (0.921245 testing + 12.663304 Waymo). The script’s full-precision [totals and windows](outputs/av_mileage_candidates/stream_totals_and_windows.csv) are authoritative. The original mixed-window 2025 table is not reused as a common-year total.

Calendar-month reconstruction and allocation choices need not reproduce the original supplement’s testing totals exactly. Do not replace its reported results without rerunning the corresponding crash assembly and model. In particular, a full-year 2025 fit must address the June SGO reporting change; a June-15 fit must truncate crash counts and human exposure to the same window. The human-mileage files contain full-year estimates and cannot be joined unchanged to partial-year outcomes/exposure.

## Reproduce, audit and scope

Run from `av-crash-analysis`:

```sh
research/.venv/bin/python research/build_av_mileage_candidates.py
research/.venv/bin/python -m pytest research/test_av_mileage_candidates.py -q
```

The builder is [here](build_av_mileage_candidates.py); [validation](outputs/av_mileage_candidates/validation.json) records assumptions, input hashes, and conservation errors. Raw downloads are pinned in `sources.json`; `download_recorded_sources.py` restores them and rejects changed bytes. The full research rebuild includes the new builder and tests.

The seven focused tests cover monotone fitting, full zone/year coverage, operator-total conservation, overlap removal, December estimation versus the June cutoff, blank Cruise evidence, and the testing upper scenario. Current full-pipeline verification is recorded in [README.md](README.md) and [validation.json](validation.json). Allocation errors are below one millionth of a mile per operator/period.

The fleet scope is the published project's testing roster plus Waymo rider-only
and Cruise commercial service. It is not an independently verified census of all
SF AV activity or unreported/new deployment fleets. These tables are alternative
inputs for subsequent model fitting and selection.
