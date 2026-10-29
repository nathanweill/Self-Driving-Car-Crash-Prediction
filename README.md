# Spatiotemporal crash prediction for autonomous vehicles in San Francisco

Code and data for the paper *Spatiotemporal Crash Prediction for Autonomous Vehicle
Deployment: A Case Study in San Francisco*.

The repository builds a panel of 65 San Francisco zones observed from 2021 to 2025,
fits a joint Poisson model of autonomous-vehicle (AV) and human-driven-vehicle (HV)
crash counts with covariates chosen by forward selection with the BIC, evaluates it
on temporal and spatial holdouts, and quantifies uncertainty with zone-level random
weighting. Running it regenerates every number, table and figure of the paper that
comes from the analysis, except the Street View comparison (see "Data").

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m avcrash all          # about 10 minutes; writes results/ (the paper's numbers)
python -m pytest               # about 1 minute; checks a rerun against results/
```

`results/` is committed, so the outputs can be inspected without running anything.
`results/` was produced on Linux with Python 3.13, numpy 2.5.3, pandas 3.0.5, scipy 1.18.1,
shapely 2.2.0, geopandas 1.2.0, pyproj 3.8.0 and scikit-learn 1.9.1, where `pytest` reproduces
it exactly. On other platforms, floating-point differences of about 1e-8 in the zone areas
can break exact ties between equivalent HV fatality variables (`fatal_crash_share` and
`collision_severity_fatal_share` are identical in the data), so a few setups may select a
different but equivalent variable and a few reproduction tests fail.

## Repository layout

```
config/paper.yaml      every setting used in the paper (years, thresholds, seeds, ...)
config/sensitivity_*.yaml  the two N_A sensitivity runs (low, high)
data/                  inputs (see "Data")
data/mileage/          tables behind the AV mileage N_A (see "AV mileage")
mileage/               scripts that compute N_A from the DMV and NHTSA files
research/              additional mileage, crash-location and activity data
avcrash/
  io.py                readers and parsing of the raw files
  zones.py             the zones: saved assignment, or Ward clustering and island removal
  features.py          zone-year panel: crash counts, exposure, covariates
  geosplit.py          east/west split for the spatial holdouts
  pool.py              candidate pool: screening, log(1+x), correlation pruning
  model.py             profiled joint Poisson model
  selection.py         forward selection with the BIC and strong heredity
  metrics.py           R2, MAE, Kendall tau-b, Poisson deviance (and weighted versions)
  uncertainty.py       zone random weighting (P1), Poisson simulation (P2), test-zone weighting (P3)
  pipeline.py          one evaluation setup end to end
  diagnostics.py       selection frequency, residual dependence, Street View comparison
  figures.py, tables.py  paper figures and LaTeX table bodies
  cli.py               python -m avcrash <command>
tests/                 unit tests of the model and a reproduction test
results/               outputs of config/paper.yaml (see "Outputs")
results_sensitivity_{low,high}/  outputs of the two sensitivity runs
```

## Data

| File | Content | Source |
|---|---|---|
| `TAZ981.*` | 981 transportation analysis zones (TAZ) of San Francisco | SFCTA, [TNCs Today](https://www.sfcta.org/projects/tncs-today-2017) |
| `Uber_pickup_dropoff.csv` | Estimated pickups and dropoffs of Uber and Lyft (transportation network companies, TNCs) per TAZ, day of week and hour (2016 sample). Despite the file and column names (`uber_*`), the counts cover both companies | SFCTA, TNCs Today |
| `land_use.csv.gz` | Parcel land use (floor area by use, intersection density), 155,135 parcels | [DataSF, San Francisco Land Use - 2023 (archived)](https://data.sf.gov/Geographic-Locations-and-Boundaries/-ARCHIVED-San-Francisco-Land-Use-2023/fdfd-xptc/about_data), public domain |
| `taz_to_zone.csv` | Assignment of the 969 mainland TAZs to the 65 zones used in the paper (the output of method step 1) | this study |
| `sf_hv_14_25.csv` | Police-reported HV injury and fatal crashes in San Francisco, 2014-2025, one row per crash. Crash-level export of the SWITRS Query & Map tool of TIMS (downloaded April 2026), with the columns renamed; crashes without a TIMS geocode are excluded. The 2025 records are provisional | California Highway Patrol ([CCRS](https://data.ca.gov/@california-highway-patrol/ccrs)), geocoded and distributed by [TIMS, UC Berkeley SafeTREC](https://tims.berkeley.edu/) |
| `sf_av_combined_2025.csv` | AV collision reports (form OL 316) of DMV testing-permit holders in San Francisco, 2016-2025, one row per report: date, time, location and driving mode (`av_mode` = AM autonomous, CM conventional) extracted from the PDF reports, with the reported locations geocoded; reports whose location could not be geocoded are excluded. Only crashes in autonomous mode are used | California DMV collision reports ([archived page, 25 Feb 2026](https://web.archive.org/web/20260225190800/https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/autonomous-vehicle-collision-reports/)); the same reports are compiled in the DMV spreadsheet [DMV AV Testing Collisions Data](https://docs.google.com/spreadsheets/d/1Ml2AOMWtRo2E-SrNZjA7JkpHP3-C2kFzgVsiIOF_lkU) |
| `mileage/dmv_testing_monthly.csv` | Autonomous-mode miles per manufacturer and month, testing with a safety driver and driverless testing, 2020-2025 | California DMV Autonomous Vehicle Mileage and Disengagement Reports, 2015-2025, released 20 February 2026 ([DMV news release](https://www.dmv.ca.gov/portal/news-and-media/autonomous-vehicle-permit-holders-in-california-logged-more-than-9-million-test-miles-between-december-1-2024-and-november-30-2025/)) |
| `mileage/sgo_ca_incidents.csv` | California crashes with the automated driving system engaged, one row per incident (operator, year, San Francisco or not, someone on board or not) | [NHTSA Standing General Order](https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting), ADS incident reports: [archive file](https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/Archive-2021-2025/SGO-2021-01_Incident_Reports_ADS.csv) and [file under the third amendment](https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Incident_Reports_ADS.csv) |

**Street View labels (not included).** The zones and the Street View comparison also use
`consensus_segments_wkt.csv.gz`: 16,137 OpenStreetMap road segments (extracted April 2026)
with streetscape labels (lanes, bus and bike lanes, crosswalks, ...) extracted from Google
Street View images by Qwen3.5-27B. The Google Maps Platform terms do not allow redistributing
content derived from Street View imagery, so this file is not in the repository. It is needed
only to rebuild the zones from scratch (its bus-lane share is one of the clustering
descriptors) and to rerun the Street View comparison. The repository instead ships the
resulting zone assignment (`data/taz_to_zone.csv`) and the comparison's output
(`results/streetview_comparison.csv`), so every other result can be reproduced.

The land-use file is gzip-compressed (pandas reads it directly). Fleet
mileage is in `config/paper.yaml` (`exposure`), in million miles: `N_H` is the annual HV
vehicle miles traveled in San Francisco ([SFCTA congestion dashboard](https://congestion.sfcta.org/), accessed April 2026)
and `N_A` the annual autonomous testing miles in San Francisco (next section).

**Scope.** The AV crashes and `N_A` both cover autonomous *testing* under the DMV
testing permits, with a safety driver or driverless. Commercial driverless service (deployment
permits) is not included: its operators did not report collisions or mileage to the DMV
before April 2026. The HV crashes are police-reported injury crashes (TIMS contains no
property-damage-only crashes; severity code 4 is "complaint of pain"), whereas every AV
collision is reported. This difference shifts the intercept of the AV-to-HV risk ratio; the
ratio is not a comparison of safety.

## AV mileage

The DMV mileage reports give each test vehicle's autonomous miles per month, statewide.
`mileage/sf_testing_miles.py` attributes each operator's miles to San Francisco with the share
of its California SGO crashes (testing with someone on board) that occurred in San Francisco:
by year for Waymo, pooled over 2021-2025 for the other operators; operators without any
California SGO crash get no San Francisco miles. Waymo's driverless miles cannot be separated
from its commercial service in the SGO data, so three cases are computed: `low` (none in San
Francisco), `mid` (the San Francisco share of Waymo's driverless SGO crashes; `config/paper.yaml`)
and `high` (all in San Francisco; `config/sensitivity_{low,high}.yaml`). Years are DMV report
years (December to November).

```
python mileage/sf_testing_miles.py     # prints N_A for the three cases from data/mileage/
# rebuild the two input tables from the raw downloads (not included in the repository):
#   DMV report folder = the 2015-2025 mileage and disengagement release of 20 February 2026
#   SGO folder = the two NHTSA ADS incident files linked in the Data table
python mileage/build_dmv_monthly.py <DMV report folder> data/mileage/dmv_testing_monthly.csv
python mileage/build_sgo_ca.py <SGO folder> sgo_ca_incidents.csv   # see the note in the script
```

## Method, step by step

All settings below are read from `config/paper.yaml`.

1. **Zones** (`zones.py`). Each TAZ is described by its residential land-use share,
   mean parcel intersection density, share of road segments with a bus lane, and the
   coordinates of its representative point. Missing values are replaced by the mean
   over TAZs and the descriptors are standardized. Starting from one cluster per TAZ,
   the pair of adjacent clusters (polygons within 5 m) with the smallest Ward cost is
   merged until 70 clusters remain. Clusters not connected to the mainland are
   dropped, which leaves 65 zones. The repository ships the result as
   `data/taz_to_zone.csv` and reads it by default (`zones.from_assignment: true` in the
   config), because the bus-lane share comes from the Street View labels, which are not
   included (see "Data"). With `from_assignment: false` and the segment file, the zones
   are rebuilt; this reproduces `data/taz_to_zone.csv` exactly.
2. **Panel** (`features.py`). For each zone and year 2021-2025: the AV crashes in
   autonomous mode (`n_av`), the HV crashes (`n_hv`), the fleet mileages `N_A` and
   `N_H`, and the 41 covariates of the paper's feature table (land-use shares,
   ride-hailing densities, composition and severity shares of the HV crashes, three
   products). Crashes are assigned to zones by their coordinates.
3. **Setups**. Temporal holdouts train on 2021-2023 (test 2024) or 2021-2024
   (test 2025) over all zones. Spatial holdouts split the zones by a line at 135°
   through the city center (36 western and 29 eastern zones), train on one side and
   test on the other side in the test year.
4. **Candidate pool** (`pool.py`), using only the covariates of the training-region
   zones in the initial training years (2021-2022 for test 2024, 2021-2023 for test
   2025): removal of the TNC total `uber_total` (the sum of pickups and dropoffs); support
   and variance screening of the zone means; `log(1+x)` for nonnegative variables
   with a maximum above 1 (columns ending in `__lg`); pruning of pairs with
   |correlation| > 0.9.
5. **Forward selection** (`selection.py`) with the BIC of the profiled Poisson
   likelihood on the full training window; a product of two variables is eligible
   only after both of its factors are selected.
6. **Model** (`model.py`). With x the selected covariates plus an intercept,
   the HV crash rate is profiled out and β minimizes
   Σ (n_A + n_H) log(N_H + N_A e^{β'x}) − n_A β'x (L-BFGS-B on standardized
   covariates). The predicted AV count is μ = n_H (N_A / N_H) e^{β'x}. The
   intercept-only model is the benchmark.
7. **Uncertainty** (`uncertainty.py`, 200 draws each).
   * P1, *TrainZone-Mean*: each training zone receives a weight Gamma(4)/mean
     (shared across its years), the model is refitted, and the draws are rescaled
     around the unweighted fit (β* = β̂ + 2(β_w − β̂), μ* = μ̂ (μ_w/μ̂)²). Reported:
     the predicted test total and the coefficient intervals. Seed 7, the same
     weights for the full and intercept-only models.
   * P2, *Poisson-Pred*: Poisson counts simulated from the fitted test means; reported: the total.
   * P3, *TestZone-Metric*: R², MAE, Kendall τb and deviance recomputed with
     Dirichlet(4) weights over test zones, rescaled as m* = m̂ + 2(m_w − m̂).
8. **Diagnostics** (`diagnostics.py`): selection frequency of each feature when the
   forward selection is repeated with Exp(1) zone weights; lag-one correlation and
   intra-class correlation of the training Pearson residuals with a permutation test;
   the six setups plus three 2023 backtests (the same temporal and two spatial designs with
   training years 2021-2022 and test year 2023; window `test_2023` in `config/paper.yaml`),
   nine evaluations in all, rerun with the 18 Street View covariates added to the pool
   (needs the segment file; the saved output is `results/streetview_comparison.csv`).

## Commands and outputs

```
python -m avcrash panel                # results/panel.csv, zones.geojson, taz_to_zone.csv
python -m avcrash run                  # results/runs/<setup>/
python -m avcrash selection-frequency  # results/selection_frequency/<setup>.json  (~8 min)
python -m avcrash residuals            # results/residual_dependence.json
python -m avcrash streetview           # results/streetview_comparison.csv (needs the Street View file; skipped by all)
python -m avcrash figures              # results/figures/
python -m avcrash tables               # results/tables/*.tex and numbers.json
python -m avcrash tables --paper PATH  # also writes the table bodies into the LaTeX sources

# N_A sensitivity runs
python -m avcrash all --config config/sensitivity_low.yaml  --results results_sensitivity_low
python -m avcrash all --config config/sensitivity_high.yaml --results results_sensitivity_high
```

`--setups citywide_2025 geo_w2e_2025` restricts `run` and `selection-frequency`
to some setups; `--results DIR` writes elsewhere. The six setups are
`citywide_2024`, `citywide_2025` (temporal holdouts), `geo_w2e_2024`,
`geo_w2e_2025` (train west, test east) and `geo_e2w_2024`, `geo_e2w_2025`
(train east, test west).

Each `results/runs/<setup>/` contains:

| File | Content |
|---|---|
| `observed_metrics.json` | selected features, coefficients, test metrics of the selected and intercept-only models |
| `candidate_pool.json` | screened variables, log-transformed variables, variables removed by correlation pruning, final pool |
| `selection_trace.csv` | accepted steps of the forward selection with their BIC |
| `test_predictions.csv` | observed and predicted AV crashes per test zone |
| `{full,null}_p1.csv`, `_p2.csv`, `_p3.csv` | interval summaries of P1, P2 and P3 |
| `coefficient_draws.csv`, `null_coefficient_draws.csv` | the 200 P1 coefficient draws |

In the interval summaries (`*_p1.csv`, `*_p2.csv`, `*_p3.csv`), `observed` is the value on the
actual data; `Mean`, `STD` and `MAD (scaled)` (1.4826 times the median absolute deviation)
summarize the 200 draws; `P2.5`, `P5`, ..., `P97.5` are their 2.5th to 97.5th percentiles (not
pipeline names); `within_95` says whether `observed` lies between `P2.5` and `P97.5`.

Paper tables and figures:

| Paper | Output |
|---|---|
| Temporal holdout tables (2024, 2025) | `tables/tab_rolling_2024.tex`, `tab_rolling_2025.tex` |
| Spatial holdout tables | `tables/tab_geo_2024.tex`, `tab_geo_2025.tex` |
| Predicted totals with P1 intervals | `tables/tab_p1.tex` |
| Feature pool, BIC path, AV crash sparsity | `tables/tab_preproc.tex`, `tab_bic_trace.tex`, `tab_sparsity.tex` |
| Coefficients and selection frequencies; intercept-only coefficient | `tables/tab_supp_coef.tex`, `tab_supp_null_coef.tex` |
| Percentiles of P3 metrics and P1/P2 totals | `tables/tab_supp_q_{r2,tau,mae,dev,p1,p2}.tex` |
| Street View comparison | `tables/tab_vlm.tex` |
| Residual dependence (supplement text) | `residual_dependence.json` |
| Zone map, spatial split | `figures/superzone_map.png`, `figures/geosplit.png` |
| Prediction maps | `figures/heatmap24.png`, `heatmap25.png`, `geoheatmap24.png`, `geoheatmap25.png` |
| Sparsity figures | `figures/sparsity/sparsity_<year>.png` |

## Commercial-service data

Additional data for the commercial-service analysis are in
[`research/`](research/README.md): zone-level mileage estimates for 2021-2025,
a Waymo/reference panel for January-June 2026, refined crash locations and
monthly activity covariates. The derived tables, source records and reproduction
instructions are included; the estimates and coverage limits are described in
the method notes. These inputs have not been incorporated into the fitted results
in `results/`.

## License

The code is released under the MIT License (see `LICENSE`). The files in `data/` come from the
sources listed in "Data" and remain subject to their terms of use. The DataSF land-use data are in
the U.S. public domain. The road segments used for the zones and the Street View comparison (not
included) are derived from OpenStreetMap data, © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).

## Citation

If you use this code or data, please cite the paper (reference to be added on publication)
and the original data sources listed in "Data".
