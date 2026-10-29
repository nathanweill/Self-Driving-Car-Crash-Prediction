# Refined Waymo crash locations

Candidate locations for 757 Waymo source rows, combining official street
centerlines, reported descriptions and compatible public coordinates. The
original geocodes, source conflicts and unresolved descriptions are retained.

## Result

| Measure | Before | Refined |
|---|---:|---:|
| Waymo source rows retained | 757 | 757 |
| Unique SGO report IDs | 755 | 755 |
| Candidate point coordinates / unique point zone | 709 | 749 |
| Rows with at least one supported candidate zone | 709 | 750 |
| Stable within the method's assumed default location support | 133 | 146 |

Of the **48** originally unresolved rows: **40** now have candidate points,
**one** retains two possible junctions, **one** is excluded from the SF candidate
set because NHTSA identifies Atlanta, and **six** remain unassigned. No records
are deleted. The counts are source rows, which may be vehicle involvements;
757 rows are not 757 distinct crash events.

The source comparison identified **15 coordinate conflicts**; those retain the
description-based primary and preserve the public coordinates as alternatives.
One public latitude/longitude reversal is corrected and logged. Seventeen
previously assigned point zones change after compatible public-coordinate
refinement. For the eight police-reported injury events selected in the 2026 H1
extension, the point-zone counts are unchanged; fractional allocation changes.
A 65-zone comparison table quantifies that effect.

## How the refinement works

1. Join the public DMV-linked TIMS records to Waymo by SGO report ID; check report
   version and incident month before using coordinates. All 1,406 historical
   Waymo records returned by the query are paginated and checked against the
   service count. Preserve the raw coordinates and source version.
2. Match street spelling/suffix corrections and explicit interpretation rules
   against the pinned official SF centerlines. Every edited query and rationale
   is recorded in `inputs/waymo_geocode_interpretations.json`. No automatic fuzzy
   matching. One interpretation, 24th **Avenue** at Ortega instead of 24th
   **Street**, is explicitly marked as an unconfirmed correction hypothesis,
   supported by the reported ZIP 94122 and the actual intersecting road pair.
3. Where exact node IDs fail, connect the nearest points on the two named roads
   only if the gap is at most 40m for “at” or 150m for “near.” This is an
   approximation; grade separation and actual incident position are not inferred.
   Retain separate distant junctions rather than manufacture a midpoint.
4. Parking/alley descriptions tied to an address use frontage proxies with at
   least a 150m buffer. Block descriptions use a midpoint with radius covering
   the endpoints. Ramp complexes use at least 100m. Ferry Plaza is represented
   by the nearby Embarcadero/Market junction with a 150m buffer.
5. Accept a public point as primary when it agrees with the available description
   candidate within `max(100m, description radius + 50m)` and version/month match.
   When no description point exists, a matched public coordinate is retained as
   a candidate. Public points use a **50m sensitivity radius**, not a measured
   accuracy claim. Coordinates far from a supported description remain alternate
   evidence and do not replace it. Reverse latitude/longitude only when the
   original pair fails and the reversed pair alone fits the SF bounding box.
6. Produce point-zone assignments plus two zone-allocation choices: equal shares
   across intersected candidate zones, or shares proportional to buffered area
   within each zone. Each has default and minimum-100m variants. Normalize over
   retained study zones. These are sensitivity weights, **not probabilities**.
   Boundary instability remains visible; it is not a processing failure.

## What remains unresolved

| Report ID | Source description | Why not assigned |
|---|---|---|
| 30270-13206 | Toland Street near Toland Place | Toland Place is absent from the pinned centerline; no matched public coordinate |
| 30270-11738 | Shoreline Highway at Fulton Street | Highway name does not match the SF road file; selecting a replacement route would be an unconfirmed location hypothesis |
| 30270-10446 | Ellis Street near Farren Street | Farren is absent from the current street file; historical naming/abandonment does not establish a 2025 crash point |
| 30270-10349 | Division Street at Vernon Street | Named centerlines are about 7.2km apart; a typo is possible but its correction is unverified |
| 30270-7795 | Parking lot at City College of San Francisco | Multiple campus lots; the description does not identify which one |
| 30270-5318 | 8077 O'Farrell Street | Number outside published address ranges; no supported replacement number |

Additionally, **30270-11362**, Winston/20th Avenue, has two matching junctions;
its candidate-zone weights are delivered without a single point. **30270-15497**
is retained but excluded from SF allocation because the NHTSA record identifies
Atlanta, Georgia. Its original Waymo County/State fields are preserved.

Exact resolution requires an original collision report, provider correction,
more specific address/lot details, or the original study's verified crosswalk. The 15
source-coordinate conflicts are separate from the six unresolved descriptions;
all have retained description-based candidates. See the conflict CSV for IDs,
distances, raw source coordinates, and retained zones.

## Files and join keys

All below are in `outputs/geocoding_refined/`:

- `waymo_sf_geocoding_refined.csv`: full 757-row crosswalk, original and revised
  fields, interpretation flags, source conflicts, and candidate zones.
- `zone_allocation_sensitivities.csv`: source-row/zone weights for both radius
  scenarios and both weighting methods. Fractional counts require an appropriate
  modeling treatment; do not insert them unchanged into an integer-count model.
- `original_48_resolution_audit.csv`: disposition of every original unresolved row.
- `unresolved_locations.csv` and `public_coordinate_conflicts.csv`: remaining
  source issues, distinguished from normal zone-boundary sensitivity.
- `review_queue.csv`: all remaining review reasons, including boundary sensitivity.
- `waymo_sf_geocoding_refined.geojson`: primary candidate points for mapping.
- `h1_injury_allocation_comparison.csv`: impact on the existing eight-event H1 outcome.
- `validation.json`: counts and input hashes.

Use `source_csv_row` as the row-level join key. SGO report ID is not unique across
Waymo vehicle involvements. Keep `sf_scope_candidate`, `geocode_method`, and
`interpretation_kind` when selecting analytical inputs. Exact reproduction of
the original commercial results still requires the original crosswalk;
these files are alternatives for evaluation.

Builder: `refine_waymo_geocoding.py`; six focused tests in
`test_geocoding_refinement.py`; integrated into `reproduce.py`. Current complete
pipeline verification is recorded in [README.md](README.md) and [validation.json](validation.json).

Sources: [TIMS data provenance](https://tims.berkeley.edu/tools/avsafety.php),
[NHTSA crash reporting](https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting),
[official SF street centerlines](https://data.sf.gov/Geographic-Locations-and-Boundaries/San-Francisco-Basemap-Street-Centerlines/3psu-pn9h),
[SFMTA Oak/Octavia reference](https://www.sfmta.com/reports/octavia-boulevard-oak-street-laguna-street-oakfell-hayes-valley-daylighting),
[Recreation and Parks road plan](https://sfrecpark.org/DocumentCenter/View/11719/M-Special-Area-Plans),
[Ferry Plaza operator location](https://foodwise.org/markets/ferry-plaza-farmers-market/visitor-info/).
Additional interpretation-specific evidence links are in the input JSON. Raw
responses and hashes are preserved in `sources.json`; no online geocoding is
needed to reproduce the outputs. No GitHub push or collaborator message occurred.
