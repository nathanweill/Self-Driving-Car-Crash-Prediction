# Review-ready manuscript corrections

Updated 2026-10-29. These are proposed edits against Overleaf commit `43757e8`,
not replacements for the empirical results. They have not been pushed or applied
to the manuscript. Current deliverables and evidence are linked in [README.md](README.md);
[REPORT.md](REPORT.md) retains the initial audit and later updates.

## `sec_data.tex`: descriptor count

In “Superzone formation,” replace **“Clustering uses the four descriptors”** with **“Clustering uses the three descriptors.”** The preceding paragraph and `config/paper.yaml` list residential share, intersection density, and bus-lane share, with coordinates appended separately.

## `appendix_commercial.tex`: CPUC availability

Replace the categorical sentence saying trip-level, incident-level, and 2025 tract-level files are fully redacted with a field-specific statement:

> CPUC public reports contain redactions that vary by table and field. Numeric SF tract trip starts and ends were recovered for Waymo during March 2022–May 2023 and August 2023–December 2024, and for Cruise during June 2022–October 2023. Waymo SF tract trips are redacted in the inspected January 2025–June 2026 reports, while California monthly trip totals remain public. In the separately audited 2025 Q1 and 2026 Q2 archives, tract collision counts and fleet mileage are also public. The fleet tables do not identify SF mileage separately.

Keep the trip-count audit separate from the collision-field audit. Avoid
describing an entire incident-level archive as fully redacted without a field
audit. Do not add CPUC Waymo collision totals to Data Hub records; they may overlap.
The delivered tract-to-zone trip allocations and recent-trip estimates are
documented in [Category 5](SERVICE_ACTIVITY_DELIVERY.md).

## Timing of mileage: distinguish original assembly from new evidence

Preserve the description of which files the exploratory run actually used. Append or replace the availability conclusion with:

> A subsequent source audit recovered spatial mileage releases ending in July, September and December 2024; March, June, September and December 2025; and March and June 2026. Earlier files use operational-location labels, whereas the December 2025 and later releases use county labels. Some cumulative cell values decrease or disappear across releases, so direct differencing requires geographic reconciliation. The newly recovered files have not yet been incorporated into the reported exploratory results.

Do not replace the 2025 mileage table with 31.874 or 31.904 million miles. Those raw year-end differences span a geography-definition change and use a different time window from the table. The December 2024 spatial sum also differs from the location total by 30,406.7 miles.

## Human exposure: qualify “not available”

Suggested addition to “Where the fleets drive” / “Data that would help”:

> Two public spatial exposure candidates are available for further assessment: the 2022 HPMS benchmark VMT supplied in Waymo’s S2-cell downloads, and monthly modeled traffic volumes for selected SFCTA roadway segments. The former is static and limited to published cells; the latter does not cover the entire road network. Neither is a complete observed human-only mileage panel for the 65 zones over 2021–2025.

The follow-up processing supplies full-zone estimates by expanding SFCTA traffic
to missing roads or scaling fixed HPMS spatial shares to annual city totals, with
three additional sensitivity variants. See [Category 1](HUMAN_MILEAGE_DELIVERY.md).
Do not state that the published model already uses them. Road-based travel belongs
in an exposure denominator; residential-origin VMT per person is a different
quantity and should not be substituted.

## Crash locations: counting unit and unvalidated new crosswalk

Change “757 Waymo crashes” to “757 Waymo source records” pending a consistent event-versus-vehicle definition. The CSV contains 755 distinct SGO IDs. The release notes explain that one repeated ID represents two Waymo vehicles. Preserve rows for the vehicle-level interpretation; deduplicate only after choosing the outcome definition and retaining any different injury flags.

Keep the original 704-geocoded count attached to the original geocoder. The new
pipeline first located 709 source rows and now supplies **749 candidate point
locations** after street/address refinement and compatible public-coordinate
matching. Of its initial 48 unresolved rows, 40 have point estimates, one retains
multiple junction candidates, one is excluded for a confirmed city conflict,
and six remain unresolved. Fifteen source-coordinate conflicts and boundary
sensitivities are retained for review. This has not been matched row by row
against Nathan's original crosswalk; 749 versus 704 is not a verified net gain
of 45 correct locations. See [Category 4](GEOCODING_DELIVERY.md).

## Time-varying covariates

The new data handoff supplies historical tract trips allocated to zones, changing
Waymo driving-activity measures, two estimated alternatives for recent redacted
trips, monthly traffic, and service-authority dates. These are retrospective
covariates; activity support is not an authorized service polygon, and completed
trips are not ride requests or unmet demand. Annual summaries report feature
coverage rather than treating partial periods as full years. Do not claim a
predictive improvement before evaluating them.

## 2026 deployment reporting

Replace “which should provide consistent data for all operators from 2026” with:

> The April 2026 rules extend reporting to deployment permit holders, but the published VMT template does not require geographic disaggregation. Public availability, observation periods, geographic allocation and collision definitions still need to be verified before the reports can support a consistent multi-operator extension.

The audited DMV memo is AVIM 2026–001A. Check the bibliography/version and distinguish the April 28 effective date from the later monthly/quarterly reporting rollout. New collision requirements align with the SGO; the old testing definition should not be projected into 2026 unchanged.

The delivered H1 extension is explicitly Waymo/reference, with four 65-zone
alternatives. Recovered other-operator pilot mileage and 17 located Zoox SF
reports are a separate supplement; their population and reporting criteria do
not establish a matched all-operator rate panel. See [Category 3 status](CATEGORY_3_STATUS.md).

## June 2025 reporting break

The SGO exception for a subject vehicle striking another vehicle/object or being the only vehicle involved is supported by the order. Do not remove it as an error. The phrase “less than $1,000 and no injury” is incomplete: serious-outcome triggers include tow-away, airbag deployment, vulnerable-road-user strike and hospital transport. A police report alone is not a reporting trigger under the order. Prefer a short exact reference to Requests 1–2 and a defined, justified common outcome instead of promising that all police-reported cases form a stable series.

## Submission scope

Retain the testing-only main analysis while these extension issues are reviewed. No new comparative safety conclusion, R², or coefficient estimate follows from this data audit. The 2025 combined table still mixes observation windows and must remain explicitly exploratory.
