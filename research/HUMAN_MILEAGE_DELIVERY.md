# Human mileage by zone

Five estimated datasets provide annual mileage for the paper's 65 zones in
2021-2025. Two are primary alternatives and three are sensitivity variants.
All use the same annual citywide totals and differ in their spatial allocation.

## Data and outputs

| Dataset | Estimation design | Role |
|---|---|---|
| [SFCTA expanded](outputs/human_mileage_candidates/sfcta_expanded.csv) | Time-varying observed-network proxy plus estimated mileage on missing roads | Primary A |
| [HPMS 2022 static](outputs/human_mileage_candidates/hpms_2022_static.csv) | 2022 benchmark spatial shares, scaled to each year’s city total | Primary B |
| [SFCTA low](outputs/human_mileage_candidates/sfcta_expanded_low.csv) | Missing-road traffic density set to 25% of the reference density | Sensitivity |
| [SFCTA equal](outputs/human_mileage_candidates/sfcta_expanded_equal.csv) | Missing-road density set equal to the reference density | Sensitivity |
| [HPMS area allocation](outputs/human_mileage_candidates/hpms_2022_static_area.csv) | Same fixed-share design, with area rather than centerline cell allocation | Sensitivity |

Each file contains **325 rows** keyed by `superzone_id, year`. All five estimates can also be compared in [one wide table, in million miles](outputs/human_mileage_candidates/human_mileage_comparison_million_miles.csv), or [one long table with flags](outputs/human_mileage_candidates/human_mileage_all_candidates.csv).

## A. Fill the missing-road contribution

For each zone/year, start with the existing SFCTA partial-network mileage proxy `P`. Let `C` be covered surface-street length and `U` be uncovered surface-street length, measured using the earlier 20 m corridor coverage calculation.

1. Calculate local annual mileage density `P/C` on covered roads.
2. Calculate the pooled density across observed zones, `sum(P)/sum(C)`.
3. Blend the local and pooled densities. Local weight is `C/(C+k)`, where `k = 3,672.70 m`, the median positive covered-road length across zones. This reduces reliance on small amounts of local coverage.
4. Estimate missing-road mileage as `U × blended density × alpha`.
5. Add it to the existing-network proxy. Zone 31, which lacks source observations, uses pooled density over its entire street length.
6. Normalize the 65 raw zone estimates into shares and multiply those shares by the paper’s annual citywide mileage.

The primary assumption is **alpha = 0.5**: unobserved roads have half the reference traffic density. This is an explicit scenario assumption, not a fitted or empirically verified correction. Variants use **0.25** and **1.0**. These are alternatives for testing, not confidence bounds. The method uses local/pool density, not a claim that road classes have been matched individually.

`sfcta_*_diagnostics.csv` records source missingness, covered/uncovered length, blending weights, raw observed and imputed contributions, imputed share, and the citywide calibration factor. The existing-network quantity is itself modeled; the “observed component” label identifies the part supported by source coverage, not direct mileage measurement. Zone 31 is explicitly marked as wholly imputed.

## B. Use the HPMS spatial distribution

Use the **2022 HPMS human-traffic benchmark** in the corrected June 2026 Waymo CSV4 release. This release was selected for its broader available cell coverage; the exposure values remain a 2022 benchmark, not 2026 human mileage.

The existing cell-to-zone pipeline apportions the benchmark using surface-centerline length. All 65 zones have a positive allocation. Normalize these allocations into zone shares, then multiply by each year’s citywide mileage. This assumes a constant spatial distribution of human travel across 2021–2025. The area-allocation variant tests sensitivity to how cell mileage is split across zone boundaries.

Neither version uses Waymo’s own vehicle miles or crash counts to determine human-mileage weights. However, the published benchmark’s spatial availability can reflect the provider’s footprint. These are retrospective exposure candidates; the 2026 release must not be described as data available to a real-time forecast in 2021.

## Common totals and units

All candidates use the original panel’s annual citywide totals, so comparisons isolate differences in spatial allocation:

| Year | Citywide million vehicle-miles |
|---|---:|
| 2021 | 3,158.9 |
| 2022 | 3,487.5 |
| 2023 | 3,425.5 |
| 2024 | 3,307.7 |
| 2025 | 3,465.8 |

The explicit calibration assumption allocates the entire citywide total across the 65 study zones. The excluded islands and differences in surface-street/highway/vehicle-class coverage are not independently measured or removed. Consequently these datasets are coherent **full-zone estimates under stated assumptions**, not certified complete traffic observations.

Use `human_mileage_million_miles` where the model expects the baseline `N_H` unit. `human_mileage_miles` is also supplied. The original panel and its `N_H` column remain unchanged. Joining the candidate on zone/year is straightforward, but fitting must also specify an AV-exposure allocation consistent with the chosen human-exposure interpretation; substituting zone-level human mileage does not automatically supply zone-level AV mileage.

## Model use

Start with primary A and primary B under identical training/validation splits and otherwise fixed modeling choices. Then compare the sensitivity variants. Select using training/validation performance, and preserve the final test split for reporting. No candidate has been chosen based on the paper’s crash outcomes during this preparation.

The two primary spatial allocations have zone-wise Pearson correlations of about **0.82–0.84** across years, so they offer meaningfully different allocations while sharing exactly the same annual total. This is a descriptive comparison, not evidence that either is more accurate.

## Reproduce and verify

```sh
research/.venv/bin/python research/build_human_mileage_candidates.py
research/.venv/bin/python -m pytest research/test_human_mileage_candidates.py -q
```

No new downloads are required. [Validation and input hashes](outputs/human_mileage_candidates/validation.json) identify the exact baseline panel and derived source inputs. Checks cover all 65 zones and five years, unique keys, positive finite values, conservation of annual totals, static HPMS shares, zone 31 imputation, and the sensitivity multiplier calculation.

Source refinement or direct traffic validation can improve these estimates.
Model comparisons should retain the stated spatial and annualization assumptions.
