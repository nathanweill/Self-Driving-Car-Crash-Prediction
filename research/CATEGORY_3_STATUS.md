# 2026 exposure and outcome coverage

Source coverage checked on 2026-10-29. The matched panel covers Waymo and the
city-street reference series; other-operator evidence is supplied separately.

## Available datasets

1. **Waymo/reference H1 panel:** four alternatives, each covering 65 zones for
   January–June 2026. Two reference mileage methods and two crash-location
   allocations; 19.790413 million Waymo rider-only miles, eight selected
   police-reported injury events, and 1,559 zone-assigned reference injury cases.
   See `EXTENSION_2026_H1_DELIVERY.md` for scope and assumptions.
2. **Other operators' disclosed pilot mileage:** Zoox driverless 302,254.90 miles,
   Zoox drivered 30,498.83; smaller WeRide/Tensor/Nuro totals documented in
   `OTHER_OPERATORS_2026.md`. Monthly/quarterly inputs, source locations, and
   extraction code are preserved.
3. **Zoox SF mileage sensitivity:** five explicitly assumed SF shares (0%, 25%,
   50%, 75%, 100%) of the disclosed driverless pilot total. Usable for exploring
   exposure uncertainty, not as measured SF mileage or total testing bounds.
4. **Zoox crash recovery:** 17 unique SF H1 reports joined by ID and version
   between NHTSA and the DMV-linked TIMS layer; all 17 mapped to study zones.
   Two report minor injury (both point-assigned to zone 36), 13 no injury, and
   two unknown severity. Output includes a 20-metre location sensitivity and
   preserves unknown police/service status. These are diagnostic counts, not
   substitutes for the existing police-reported injury outcome.
5. **Validation:** the extraction scripts and associated tests are integrated in
   `reproduce.py`. Current full-pipeline verification is recorded in [README.md](README.md)
   and [validation.json](validation.json).

## Currently infeasible from the verified public inputs

| Requested quantity | Why it cannot currently be established | What would resolve it |
|---|---|---|
| Verified Zoox SF/zone passenger-pilot miles | CPUC monthly totals are available, but trip geography is redacted | Unredacted geographic aggregates or operator SF/zone mileage; otherwise retain labeled scenarios |
| Total 2026 H1 mileage for all AV operators and modes | Pilot reports omit non-passenger testing; the linked public testing-mileage dashboard ends November 2025 | 2026 testing/deployment mileage by operator/mode, with SF allocation evidence |
| A matched Zoox police-injury rate using pilot mileage | Located crash reports do not establish the same passenger-pilot scope or police-report criterion | Incident-to-service-mode linkage plus police-report status and matching mileage |
| Verified Q2 counts from CPUC's Zoox collision tables | Q2 files label their rows Q1 and redact geography | Corrected source tables; NHTSA/TIMS records already provide an independent diagnostic alternative |
| A complete observed all-operator 65-zone extension | Missing mode-matched exposure and outcomes cannot be supplied by allocating known pilot mileage alone | Above source additions, or a clearly specified broader estimation model with independently justified assumptions |

“Not established” does not mean zero. Missing operators/periods are not coded as
zero, and known pilot totals are not represented as all testing mileage. Estimated
spatial allocations remain usable deliverables; the unresolved issue for the
combined rate panel is which mileage population corresponds to which crashes.

## Model use

Compare the four Waymo/reference candidates under the same model settings.
Keep the recovered Zoox mileage and mapped crash records as a separate extension
package. Test mileage-share scenarios separately; do not add Zoox crash counts to
the Waymo numerator or combine different outcomes as if they were equivalent.
The remaining request is narrowly defined: **Zoox SF mileage and crash linkage
for the same operational mode, plus 2026 mileage for non-passenger testing**.

Source checks: [CPUC quarterly reporting](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting),
[NHTSA SGO](https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting),
[DMV-linked TIMS source definitions](https://tims.berkeley.edu/tools/avsafety.php).
The last source explicitly identifies November 2025 as the end of archived testing
mileage. This is the coverage of verified inputs, not proof no other records exist.
