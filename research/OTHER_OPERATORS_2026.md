# Other operators in January-June 2026

In the CPUC H1 reporting index inspected on 2026-10-29, deployment reports list
only Waymo. Other operators appear under the **pilot** program. These reports
cover passenger-program activity; mileage from other testing operations requires
separate sources.

## Recovered mileage

Public California CPUC pilot reports disclose the following passenger-program
mileage. These are statewide/program totals, not verified SF-only autonomous-mode
miles. They do not cover all testing outside passenger service.

| Operator | Mode | Available period | Reported miles |
|---|---|---|---:|
| Zoox | Driverless | January–June 2026 | 302,254.90 |
| Zoox | Drivered | January–June 2026 | 30,498.83 |
| WeRide | Driverless | January–June 2026 | 251.80 |
| WeRide | Drivered | January–June 2026 | 0.00 |
| Tensor | Drivered | January–June 2026 | 105.00 |
| Nuro | Drivered | May 7–June 30, 2026 | 65.66 |

Aurora attests to zero Q1 passenger trips; that does not establish zero testing
mileage. Aurora Q2 and Nuro Q1 are absent from these archives and remain unknown.
Nuro's workbook says June 31; the signed cover letter specifies June 30 and the
May 7 permit start, which are used here. Simple report totals are taken once from
the Total column, not added to their per-vehicle breakdowns. Zoox mileage sums
periods 1, 2, and 3; monthly rows are checked against the archive quarter.

## SF mileage allocation

Zoox monthly mileage is recovered. SF geography is redacted in both quarters,
including trip pickup/dropoff/request tracts. A transparent sensitivity grid
allocates 0%, 25%, 50%, 75%, or 100% of disclosed driverless pilot mileage to SF:
0; 75,563.72; 151,127.45; 226,691.17; or 302,254.90 miles. These are assumptions,
not five competing measurements or a preferred midpoint estimate. The range is
only a bound for this disclosed pilot component, not for all Zoox testing miles.

The current DMV permit table lists Nuro deployment in San Mateo/Santa Clara and
Mercedes-Benz deployment on highways. Neither describes the study's SF surface
street deployment scope. This is a current scope check, not reconstructed H1
permit history or proof of no testing in SF. Zoox is listed under driverless
testing, including SF, rather than deployment.

## Crash records recovered through another public source

The NHTSA ADS release contains 17 distinct Zoox SF H1 reports/incident IDs.
All 17 match the same report versions in the public DMV-linked TIMS dashboard,
which supplies coordinates even though the NHTSA CSV location fields are redacted.
All 17 points map uniquely to study zones. Thirteen reports state no injury, two
report minor injury, and two have unknown severity. Both injury points fall in
zone 36. The crosswalk preserves source report IDs, source severity labels,
unknowns, and zones intersecting an assumed 20-metre location-sensitivity buffer.
That buffer is not a measured positional error bound.

Only incident month/year is used: the TIMS codebook defines month precision and
some stored dates are the first of the month. Do not treat those as known exact
incident days. The dashboard explains that earlier mapped records are supplemented
from DMV collision reports, while reports from April 28 onward come directly from
manufacturer reports to DMV. Codebook wording and populated earlier coordinates
are therefore not taken as proof of exact source precision.

## What still prevents a matched all-operator crash panel

The two injury reports do not establish a police report or CPUC passenger-pilot
operation. CPUC mileage is passenger-program mileage; the NHTSA/TIMS crash set
covers ADS operations more broadly. Consequently, dividing these crashes by
recovered pilot miles would use mismatched populations. These diagnostic crash
counts remain separate from the Waymo police-reported injury panel.

CPUC's own Zoox collision tables redact geography, and both Q2 files label their
rows Q1. That source discrepancy remains flagged, but no longer blocks locating
the independently recovered NHTSA/TIMS reports. Verified SF pilot mileage and
matching service-mode crash outcomes still require another source/operator
records. See [current completion and infeasibility report](CATEGORY_3_STATUS.md).

## Files and reproduction

- `outputs/other_operators_2026/zoox_monthly_mileage.csv`: twelve mode/month records.
- `outputs/other_operators_2026/pilot_quarterly_totals.json`: source member, sheet,
  and cell for disclosed totals.
- `outputs/other_operators_2026/summary.json`: recovered totals and SF scenarios.
- `outputs/other_operators_2026/zoox_source_audit.json`: member hashes, period
  checks, redactions, and collision-use restrictions.
- `outputs/other_operators_2026/zoox_sf_h1_crash_crosswalk.csv`: 17 joined and mapped reports.
- `outputs/other_operators_2026/zoox_sf_h1_zone_crash_diagnostics.csv`: 65-zone diagnostic counts.
- `build_other_operator_crash_crosswalk.py`: joins NHTSA/TIMS by report ID/version and maps coordinates.
- `audit_other_operators_2026.py`: reproducible extraction, integrated into
  `reproduce.py`; `test_other_operators_2026.py` checks conservation and flags.

The two downloaded archives are pinned in `sources.json` under `cpuc_pilot/`.
Read-only XLSX extraction uses pandas/openpyxl; source workbooks are unchanged.

Sources: [CPUC reporting index](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting),
[Q1 archive](https://www.cpuc.ca.gov/-/media/cpuc-website/divisions/consumer-protection-and-enforcement-division/documents/tlab/av-programs/av-pilot-2026q1.zip),
[Q2 archive](https://www.cpuc.ca.gov/-/media/cpuc-website/divisions/consumer-protection-and-enforcement-division/documents/tlab/av-programs/av-pilot-2026q2.zip),
[DMV current permit scope](https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/autonomous-vehicle-testing-permit-holders/).

Additional sources: [NHTSA SGO](https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting), [DMV-linked TIMS dashboard and source definitions](https://tims.berkeley.edu/tools/avsafety.php). All retrieved CSV/configuration/layer responses are pinned in `sources.json`.
