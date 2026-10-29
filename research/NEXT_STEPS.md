# Remaining work and precise data requests

**Category 5 update, 2026-10-29:** [Service/activity covariates](SERVICE_ACTIVITY_DELIVERY.md) complete the local estimated-data handoff. Nathan can compare allocated historical passenger trips, two recent-trip estimates, Waymo activity/intensity, general traffic, and authority-event dates. Exact historical service polygons and ride requests remain potential source refinements; they do not block this handoff. Strict prospective modeling requires release-aware re-estimation because the current covariates are retrospective.

**Category 4 update, 2026-10-29:** [Refined location handoff](GEOCODING_DELIVERY.md) now provides 749/757 candidate point locations. Of the original 48 unresolved rows, 40 have point estimates, one has multiple junction candidates, one is a confirmed Atlanta/SF source conflict, and six remain unresolved. Original audit findings below are historical.

**Category 3 update, 2026-10-29:** [January–June 2026 extension](EXTENSION_2026_H1_DELIVERY.md) provides four matched-window, 65-zone Waymo/reference candidates. The Waymo-only handoff is complete; all-operator DMV deployment coverage remains unfilled.

**Category 2 update, 2026-10-29:** [AV-mileage alternatives](AV_MILEAGE_DELIVERY.md) now complete the local estimated-data deliverable. Requests below concerning exact Waymo history, original commercial code, and operator routes are refinements/reproduction tasks; they do not block handing off the explicit estimates.

**2026-10-29 update:** Human-mileage acquisition/processing is complete for candidate-model testing; see [the delivered estimates](HUMAN_MILEAGE_DELIVERY.md). The SFCTA request below is now an optional refinement, not a blocking task for Category 1.

No requests below have been sent. They identify the evidence required to move from local candidates to an approved modeling panel.

## 1. Recover the original commercial assembly from Nathan

Request the scripts and source manifests for `appendix_commercial.tex`, specifically:

- Waymo row-to-coordinate/zone crosswalk, including unresolved descriptions and original source-row IDs.
- DMV–Waymo duplicate crosswalk supporting the 57/59 overlap claim.
- Cruise CPUC tables, reporting-quarter interpretation, tract-vintage mapping, and mileage series.
- Monthly allocations used to divide cumulative Waymo mileage, including exact 2025 cutoff dates and revisions.
- Commercial model configuration, final panel, and results underlying the appendix table and R² values.

Once obtained, join by source record/report ID, compare original and new geocodes, inspect changed zones, and reconcile counts before refitting. A current centerline approximation should not silently replace a previously verified historical location.

## 2. Request complete road-based human exposure from SFCTA

Target: the [Model & Data Service Bureau](https://www.sfcta.org/model-data-service-bureau).

Explain the research: predict spatial distribution of reported AV crashes in 65 SF superzones during 2021–2025. Request:

- Link-level daily traffic/VMT and link geometry for validated historical model years or the nearest available base years, with passenger vehicle / heavy vehicle / transit distinctions if available.
- The traffic count, speed-to-volume, and citywide expansion procedures needed to extend the public CMP dashboard beyond its selected road network.
- Units, directionality, roadway classes, dates, weekday/day-of-year weighting, network versions, and any known 2023 measurement changes.
- Availability of uncertainty or validation errors and appropriate citation/redistribution terms.

Supply the local `results/zones.geojson` only if the request is authorized for sending. Ask for road-based VMT within polygons, not household-origin travel or resident VMT per person. Confirm whether traffic includes AV miles and how that would affect a human-only denominator.

## 3. Reconcile Waymo snapshots before annualizing

- Explain the operational-area-to-county conversion and get a consistent SF County back-series.
- Resolve the two absent December 2025 cells and seven negative interval differences across the audited releases.
- Reconcile December 2024 CSV1 versus CSV4 totals (30,406.7 miles).
- Obtain comparable pre-July-2024 spatial mileage if available. Current public release evidence does not recover 2021–2023.
- Clarify anomalous SF county labels and the event/vehicle counting unit for repeated SGO IDs.

The cached `outputs/waymo_s2_intervals.csv` contains the exact cell IDs/values. Do not clip negative differences or treat missing entries as zero.

## 4. Establish an admissible extension protocol

Choose a single operator/mode/geography/outcome/window before the next fit. A limited Waymo-only study can be considered separately from an all-operator commercial extension, but it would answer a narrower question and needs its own stated scope.

For 2026, determine whether actual DMV deployment reports can be obtained and whether SF mileage can be established independently. Harmonize SFDPH/SFPD injury data against TIMS on overlapping dates; exclude or model the highway-scope difference, address missing coordinates, and define human-versus-AV involvement. The prepared January–June 2026 table is a starting point, not a drop-in replacement.

For geocoding, the original 48-row queue has been processed; see GEOCODING_DELIVERY.md for the six remaining unresolved locations, one multi-junction case, 15 public/source coordinate conflicts, and delivered deterministic allocation sensitivities. For service/demand, use the completed SERVICE_ACTIVITY_DELIVERY.md package: older numeric CPUC trips are allocated to zones, recent redactions have two estimated alternatives, and mileage provides activity/intensity proxies. Redacted tract-list membership still does not establish positive trips or service availability.

## 5. Validation before changing reported results

Freeze a source manifest and a coherent observation window. Confirm outcome counts and mileage cover the same fleet and roads. Quantify excluded records and exposure coverage. Reproduce the original commercial results first, then compare exposure/allocation alternatives with the same folds and covariate selection. Report uncertainty arising from exposure imputation separately from model-fitting uncertainty.
