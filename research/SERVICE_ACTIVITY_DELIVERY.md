# AV activity and passenger-trip covariates

Retrospective covariates for the 65 study zones: reported passenger-trip counts
allocated to zones, two recent-trip estimates, changing Waymo driving activity,
monthly traffic and dated service-authority events. No crash outcomes were used
to fit these covariates.

## Files to use

All tables below are in [outputs/service_activity/](outputs/service_activity/).

| File | Rows and use |
|---|---|
| [zone_month_covariates_centerline.csv](outputs/service_activity/zone_month_covariates_centerline.csv) | Main table: 65 zones × 66 months, January 2021–June 2026; 4,290 rows |
| [zone_month_covariates_area.csv](outputs/service_activity/zone_month_covariates_area.csv) | Same keys; polygon-area spatial-allocation sensitivity |
| [zone_year_covariates_centerline.csv](outputs/service_activity/zone_year_covariates_centerline.csv) | 325 zone/year rows for joining to the 2021–2025 paper panel |
| [zone_year_covariates_area.csv](outputs/service_activity/zone_year_covariates_area.csv) | Corresponding annual spatial sensitivity |
| [zone_2026_h1_covariates_centerline.csv](outputs/service_activity/zone_2026_h1_covariates_centerline.csv) | 65 rows for the January–June 2026 extension; area version also supplied |
| [validation.json](outputs/service_activity/validation.json) | Coverage, input hashes, and unavailable quantities |

Join monthly tables on `superzone_id,date` (`date` is `YYYY-MM`); annual tables
on `superzone_id,year`. Use one allocation version at a time. Empty numeric fields
are unavailable observations, not zero. Annual sums explicitly say
`sum_available_months`, with companion `available_months` counts. Means are
weighted by days actually covered and have companion `available_days` counts.
For example, 2024 Waymo driving activity covers **five months / 153 days**, not
the full year. Neither annual table silently fills that gap.

## 1. Historical passenger-trip activity

The [CPUC quarterly archives](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting)
contain usable SF tract-level trip starts and ends in older reports:

| Operator | Numeric SF tract counts | Other coverage |
|---|---|---|
| Waymo | March 2022–May 2023 and August 2023–December 2024: **32 months** | June/July 2023 unavailable in the extracted tract series; January 2025–June 2026 tract counts redacted |
| Cruise | June 2022–October 2023: **17 months** | Later missing tract records remain missing, including after the suspension |

The builder reads the **Year/Month fields inside each CSV**, including nested ZIP
archives. It preserves original count strings, numeric values, mode labels,
source paths, and member hashes. Earlier reports do not identify the deployment
mode in the path, so they retain `deployment_mode_unspecified`; they are not
reclassified as driverless. Later Waymo files explicitly identify driverless
deployment. California-wide `TotalTrips` is a separate monthly series and is
never mislabeled as SF trips.

Tract identifiers are padded to 11 digits and restricted to SF county `06075`.
The applicable tract vintage is identified against official
[2010](https://data.sf.gov/api/geospatial/n6fe-r6rd?method=export&format=GeoJSON)
and [2020](https://data.sf.gov/api/geospatial/tmph-tgz9?method=export&format=GeoJSON)
boundaries. Every retained SF identifier matches the selected vintage; no
ambiguous vintage selections or unmatched identifiers remain. In these files,
Waymo uses 2020 tracts through November 2022, 2010 tracts during December
2022–December 2024, and 2020 tracts from January 2025. Cruise uses 2020 tracts.

For tract `t` and zone `z`, allocate each count by either:

- **Centerline:** surface-road length in `t ∩ z` / surface-road length in `t`.
- **Area:** polygon area of `t ∩ z` / polygon area of `t`.

Centerline allocation uses the same pinned official surface-road inventory as
the mileage work. Where a tract has no mapped road, it falls back to area and
flags this. If boundary-road duplication pushes a tract's weight sum above one,
that sum is normalized to one. Otherwise, outside-study geography is retained
as unallocated; counts are not forced into the 65 zones. The area version can
lose more counts to water/outside-study portions of large tracts, so it is a
deliberately coarse sensitivity, not a preferred trip-location model.

These are **reported tract counts with estimated within-tract locations**.
Starts and ends remain separate; adding them would double-count many trips.
Sparse tract lists do not establish that unlisted locations had no service.
A zero means no positive count was allocated from the reported tracts. Redacted
counts stay missing. Fulfilled passenger activity is a demand proxy, not a
measurement of requests, rejected requests, or unmet demand.

Audit files: `cpuc_sf_tract_month_records.csv.gz`, `cpuc_member_audit.json`,
`cpuc_california_monthly_trips.csv`, `tract_to_zone_weights.csv`,
`cpuc_zone_month_trip_activity.csv`, and `cpuc_monthly_coverage.csv`.

## 2. Changing Waymo driving activity / footprint proxy

Use the nine previously recovered [Waymo spatial mileage releases](https://waymo.com/safety/impact/)
ending July 2024–June 2026, with the AV-mileage reconstruction's county adjustment, monotone
reconciliation, and missing-endpoint interpolation. Difference the fitted
cumulative cell values across **eight intervals**, allocate cell miles by
centerline or area weights, and divide each interval uniformly by calendar days.
This produces **23 monthly periods, August 2024–June 2026**. Monthly changes
within an interval are a constant-daily-rate assumption, not separate monthly
measurements. No human-share regularization is added to create positive activity.

`waymo_ro_month_miles` and `waymo_ro_daily_miles` describe allocated rider-only
driving mileage. Rider-only does not mean a paying passenger is present;
empty driving and applicable non-passenger operations can contribute.
Crosswalk losses remain in `waymo_activity_interval_audit.csv`.

Three footprint/intensity sensitivities describe the fraction of a zone's
**road length mapped by the S2 crosswalk** lying in cells with:

- Positive reconstructed interval mileage.
- At least **100 reconstructed miles/day per cell**, an explicit sensitivity
  threshold rather than a legal or operational cutoff.
- Positive published endpoint differences, excluding missing or monotone-adjusted
  endpoints; this is the more conservative support diagnostic.

A positive cell does not imply every road in that cell was driven. The
denominator is mapped road length, not a full legal service polygon. Missing
and revised endpoints have separate road-fraction flags. Zero reconstructed
increment is not proof that the operator was prohibited or unavailable.

The positive-mileage fraction changes over time in 12 of 65 zones; the
100-mile/day sensitivity changes in 26. Daily mileage retains more intensity
variation than a simple active/inactive flag. Comparable pre-August-2024 spatial
increments were not recovered and remain missing.

Audit files: `waymo_cell_activity_intervals.csv`,
`waymo_zone_activity_intervals.csv`, `waymo_activity_interval_audit.csv`, and
`waymo_zone_month_activity.csv`.

## 3. Two recent-trip alternatives, January 2025–June 2026

Both alternatives estimate **trip starts in the 65 study zones**. Neither
relabels the redacted source counts as observed. Let `C_m` be reported Waymo
California monthly trips, `D_z` allocated December 2024 SF starts in zone `z`,
`M_m` reconstructed SF county rider-only miles in month `m`, and `w_zm` the
current zone's share of allocated study-zone miles.

1. **California growth with fixed SF pattern**
   (`waymo_trips_estimate_ca_scaled_static`):
   `T_zm = C_m × D_z / C_Dec2024`.
   This preserves December 2024's study-area share of California trips and its
   spatial distribution. The centerline calibration is **400,652.096 allocated
   starts / 541,378 California trips = 0.7400598**. It assumes that share stays
   constant despite expansion elsewhere in California.
2. **SF mileage growth with changing spatial pattern**
   (`waymo_trips_estimate_ro_scaled_dynamic`):
   `T_zm = M_m × r × w_zm`, where
   `r = sum(allocated starts, Aug–Dec 2024) / sum(SF RO miles, Aug–Dec 2024)`.
   The centerline calibration is **1,728,535.036 / 8,810,869.556 = 0.1961821
   study-area trips per SF RO mile**. This allows zone shares to change, but
   assumes a stable trips-per-mile ratio and uses driving intensity to locate
   passenger starts. Longer trips, empty miles, and testing can change that ratio.

Each spatial version has its own calibration. The exact constants and windows
are in `trip_estimation_calibration.json`. `waymo_recent_trip_estimates.csv`
contains the two alternatives side by side. They should be compared in the
model, not summed: the centerline versions imply about **7.75m vs 6.31m** study
trip starts for 2025 and **6.01m vs 3.88m** for H1 2026. This difference reflects
the assumptions, not an empirically established uncertainty interval.

## 4. Monthly traffic context and authority dates

`traffic_vmt_estimate` applies the human-mileage network expansion monthly: missing
roads receive half the covered-road traffic density, blending local and pooled
density with weight `C/(C + 3672.70082944m)`, where `C` is covered road length.
A wholly unobserved zone uses pooled density. Calibrate each month's zone
estimates to the SFCTA citywide daily VMT anchor × calendar days. AM/PM duplicate
daily metrics count once. The H1 2026 segment audit supplies explicitly flagged
missing-segment imputations. Weekday-derived traffic applied to calendar days
remains an annualization assumption.

The resulting series covers all **66 months**. `traffic_daily_index_2024_mean`
divides each zone's estimated daily VMT by its day-weighted 2024 mean. This is
general traffic context; it does not isolate human driving or ride-hailing.

`inputs/service_authority_events.json` records four sourced events:

- [June 2, 2022: restricted Cruise paid driverless authority](https://www.cpuc.ca.gov/news-and-updates/all-news/cpuc-issues-first-driverless-autonomous-vehicle-passenger-service-deployment-permit), on select SF streets during limited hours.
- [August 10, 2023: expanded Waymo and Cruise paid driverless authority](https://www.cpuc.ca.gov/news-and-updates/all-news/cpuc-approves-permits-for-cruise-and-waymo-to-charge-fares-for-passenger-service-in-sf-2023), two operator events.
- [October 24, 2023: Cruise deployment and driverless-testing suspension](https://www.dmv.ca.gov/portal/news-and-media/dmv-statement-on-cruise-llc-suspension/), with drivered testing unaffected.

Monthly calendar fields record fractions of days in these historical windows,
at day resolution. They are city-level event covariates repeated across zones,
not per-zone availability flags or a current permit registry. A post-event
indicator alone does not prove continuous operations or permission afterward.

## Remaining source limits and model use

The following observations are unavailable in the verified sources; the
substitutes and coverage limits are explicit:

- Historical zone-by-date authorized service polygons: use activity support and
  city-level event dates as separate proxies.
- Observed January 2025–June 2026 SF tract trips: use the two estimated alternatives.
- Uber/Lyft/all-operator ride requests, rejected requests, and unmet demand:
  the delivered passenger-activity and general-traffic variables do not measure
  these quantities. No comparable zone series for additional operators is claimed.
- Comparable pre-August-2024 Waymo spatial mileage increments: early interval
  mileage remains missing; historical passenger-trip activity is available for
  the months specified above.

For retrospective explanatory models, select variables and availability windows
explicitly. Do not drop missing years or fill them with zero silently. For
prospective prediction, this package needs **release-aware re-estimation**:
county conversion and monotone fitting use later releases, interval splitting
uses an ending snapshot, and reports become public after their observation
period. A simple one-month shift does not remove all look-ahead information.
Mileage-derived covariates also share information with the exposure denominator;
their predictive contribution is not established by preparing these tables.
No model fitting or performance claims are included.

## Reproduction

Builders: [build_cpuc_trip_activity.py](build_cpuc_trip_activity.py) and
[build_service_activity.py](build_service_activity.py).
Twelve focused tests in [test_service_activity.py](test_service_activity.py)
check source benchmarks, tract vintages, spatial and temporal conservation,
redaction handling, estimates, event dates, and partial-period coverage.

From `av-crash-analysis`, run:

```sh
research/.venv/bin/python research/reproduce.py
```

The complete pipeline verifies **79 downloaded source hashes**, runs **13
builders**, and executes **50 tests**. Source URLs, response metadata, and byte
hashes are pinned in `sources.json`; the public raw cache can be restored with
`download_recorded_sources.py`. The failed obsolete 2010 map-view export is
logged in `inputs/retrieval_failures.json`, excluded from inputs, and replaced
by the valid underlying 2010 layer.

The source manifest, authored inputs, builders, tests and derived tables are
included in `research/`. Raw ZIPs and the virtual environment are excluded
from Git.
