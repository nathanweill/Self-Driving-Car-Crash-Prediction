"""Conservative, reproducible SF centerline matching with a manual review queue.

Keeps every CSV2 source row: repeated SGO IDs may represent different vehicles.
Coordinates for 'near', addresses, and blocks are approximations, not observations.
"""
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, MultiPoint

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
WORDS = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "ROAD": "RD", "DRIVE": "DR", "TERRACE": "TER", "PLACE": "PL", "COURT": "CT", "LANE": "LN", "HIGHWAY": "HWY", "CIRCLE": "CIR", "ALLEY": "ALY", "TUNNEL": "TUNL", "SOUTH": "S", "NORTH": "N", "EAST": "E", "WEST": "W"}


def canonical(text):
    text = unicodedata.normalize("NFKD", str(text)).upper().replace("’", "").replace("'", "")
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = " ".join(text.split())
    text = re.sub(r"\bBAYSHORE\b", "BAY SHORE", text)
    text = re.sub(r"^ST GERMAIN\b", "SAINT GERMAIN", text)
    text = re.sub(r"\b0+(\d+(?:ST|ND|RD|TH))\b", r"\1", text)
    words = [WORDS.get(w, w) for w in text.split()]
    # These written number forms occur in the source descriptions.
    ordinals = {"FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH", "SIXTH": "6TH", "SEVENTH": "7TH", "EIGHTH": "8TH", "NINTH": "9TH", "TENTH": "10TH"}
    return " ".join(ordinals.get(w, w) for w in words)


def line_parts(geometry):
    return list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]


class Geocoder:
    def __init__(self, streets):
        self.streets = streets[streets.active.eq(True) & ~streets.layer.str.startswith("PAPER", na=False)].copy()
        self.streets["canonical"] = self.streets.streetname.map(canonical)
        self.groups = {name: g for name, g in self.streets.groupby("canonical")}
        self.aliases = defaultdict(set)
        self.nodes = defaultdict(set)
        self.node_points = defaultdict(list)
        for _, r in self.streets.iterrows():
            name = r.canonical
            self.aliases[canonical(r.street)].add(name)
            parts = line_parts(r.geometry)
            if not parts or any(p.is_empty for p in parts): continue
            for key, xy in [(r.f_node_cnn, parts[0].coords[0]), (r.t_node_cnn, parts[-1].coords[-1])]:
                if pd.notna(key):
                    self.nodes[name].add(str(key))
                    self.node_points[str(key)].append(Point(xy))
        self.aliases["EMBARCADERO"].add("THE EMBARCADERO")

    def resolve(self, name):
        name = canonical(name)
        if name in self.groups: return name
        possibilities = self.aliases.get(name, set())
        return next(iter(possibilities)) if len(possibilities) == 1 else None

    def intersect(self, left, right, near=False):
        a, b = self.resolve(left), self.resolve(right)
        if not a or not b: return None, "unmatched_street", {"street_a": a or canonical(left), "street_b": b or canonical(right)}
        common = self.nodes[a] & self.nodes[b]
        if not common: return None, "no_shared_intersection_node", {"street_a": a, "street_b": b}
        # Stable input order keeps centroid rounding independent of hash seed.
        points = [p for k in sorted(common) for p in self.node_points[k]]
        cloud = MultiPoint(points)
        point = cloud.centroid
        spread = max(p.distance(point) for p in points)
        meta = {"street_a": a, "street_b": b, "matched_nodes": ";".join(sorted(common)), "candidate_radius_m": round(spread, 3)}
        if spread > 60: return None, "multiple_intersections", meta
        meta["uncertainty_radius_m"] = max(spread, 100 if near else 20)
        return point, "intersection_near" if near else "intersection_at", meta

    def address(self, number, street, block=False):
        name = self.resolve(street)
        if not name: return None, "unmatched_address_street", {"street_a": canonical(street)}
        candidates, ids, radii = [], [], []
        for _, r in self.groups[name].iterrows():
            for side in ["lf", "rt"]:
                a = pd.to_numeric(r[f"{side}_fadd"], errors="coerce")
                b = pd.to_numeric(r[f"{side}_toadd"], errors="coerce")
                if pd.isna(a) or pd.isna(b) or a <= 0 or b <= 0: continue
                lo, hi = sorted([a, b])
                if block:
                    if max(lo, number) > min(hi, number + 99): continue
                    val = (max(lo, number) + min(hi, number + 99)) / 2
                else:
                    if not lo <= number <= hi or int(number) % 2 != int(a) % 2: continue
                    val = number
                fraction = (val - a) / (b - a) if b != a else .5
                # Interpolate in the centerline's from-to direction, not at a parcel entrance.
                candidates.append(r.geometry.interpolate(float(fraction), normalized=True))
                ids.append(str(r.cnn))
                radii.append(r.geometry.length / 2 if block else 40)
        meta = {"street_a": name, "centerline_ids": ";".join(sorted(set(ids)))}
        if not candidates: return None, "address_outside_published_ranges", meta
        p = MultiPoint(candidates).centroid
        spread = max(q.distance(p) for q in candidates)
        meta["candidate_radius_m"] = round(spread, 3)
        if spread > (150 if block else 50): return None, "ambiguous_address_range", meta
        meta["uncertainty_radius_m"] = max(spread + max(radii), 60 if block else 40)
        return p, "block_range_approximation" if block else "address_interpolation", meta

    def locate(self, text):
        original = str(text).strip()
        text = re.sub(r"^near\s+", "", original, flags=re.I)
        block = re.fullmatch(r"(\d+)\s+block\s+of\s+(.+)", text, flags=re.I)
        if block: return self.address(int(block[1]), block[2], True)
        pair = re.split(r"\s+(at|near|and)\s+|\s*(&)\s*", text, flags=re.I)
        # Capturing groups from either separator introduce None entries.
        pair = [x for x in pair if x]
        if len(pair) == 3: return self.intersect(pair[0], pair[2], pair[1].casefold() == "near")
        address = re.fullmatch(r"(\d+)\s+(.+)", text)
        if address: return self.address(int(address[1]), address[2])
        return None, "description_needs_review", {}


def main():
    OUT.mkdir(exist_ok=True)
    streets = gpd.read_file(ROOT / "raw/sf/streets.geojson").to_crs(26910)
    coder = Geocoder(streets)
    zones = gpd.read_file(ROOT.parent / "results/zones.geojson").to_crs(26910)
    data = pd.read_csv(ROOT / "raw/waymo/202606_csv2.csv", dtype=str)
    data["source_csv_row"] = data.index + 2
    data = data[data.County.eq("San Francisco") & data.State.eq("California")].copy()
    data["repeated_sgo_id"] = data["SGO Report ID"].duplicated(keep=False)
    rows, points = [], []
    for _, r in data.iterrows():
        p, method, meta = coder.locate(r["Location Address / Description"])
        row = r.to_dict() | meta | {"geocode_method": method}
        row["point_zone_id"] = None
        row["zone_candidates"] = ""
        row["zone_assignment_stable_within_assumed_radius"] = False
        if p is not None:
            point_hits = zones[zones.geometry.covers(p)]
            candidates = zones[zones.intersects(p.buffer(meta["uncertainty_radius_m"]))]
            row["zone_candidates"] = ";".join(map(str, sorted(candidates.superzone_id)))
            if len(point_hits) == 1: row["point_zone_id"] = int(point_hits.iloc[0].superzone_id)
            row["zone_assignment_stable_within_assumed_radius"] = len(candidates) == 1 and len(point_hits) == 1 and bool(candidates.iloc[0].geometry.covers(p.buffer(meta["uncertainty_radius_m"])))
        rows.append(row); points.append(p)
    result = gpd.GeoDataFrame(rows, geometry=points, crs=26910).to_crs(4326)
    result["longitude"] = result.geometry.x
    result["latitude"] = result.geometry.y
    result.drop(columns="geometry").to_csv(OUT / "waymo_sf_geocoding.csv", index=False)
    result[result.geometry.notna()].to_file(OUT / "waymo_sf_geocoding.geojson", driver="GeoJSON")
    review = result[result.geometry.isna() | ~result.zone_assignment_stable_within_assumed_radius | result.repeated_sgo_id]
    review.drop(columns="geometry").to_csv(OUT / "waymo_geocoding_review.csv", index=False)
    summary = {"source_rows": len(result), "unique_sgo_report_ids": result["SGO Report ID"].nunique(),
               "rows_with_coordinates": int(result.geometry.notna().sum()),
               "rows_with_point_inside_one_zone": int(result.point_zone_id.notna().sum()),
               "rows_stable_within_assumed_radius": int(result.zone_assignment_stable_within_assumed_radius.sum()),
               "method_counts": result.geocode_method.value_counts().to_dict(),
               "review_rows": len(review),
               "note": "Automated matches require review. Near locations and range interpolations are approximate. Assumed 20/100/40m radii are sensitivity assumptions, not calibrated uncertainty. Source rows are vehicle involvements, not necessarily unique collision events."}
    (OUT / "geocoding_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
