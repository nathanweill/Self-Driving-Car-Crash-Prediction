"""Spatial units ("zones"): contiguous Ward agglomeration of the SF TAZs.

1. Each TAZ gets static descriptors: residential land-use share, mean
   intersection density (parcel file), share of road segments with a bus lane
   (Street View segment file), and its representative-point coordinates.
2. Starting from one cluster per TAZ, adjacent clusters are merged in order of
   the smallest Ward cost on the standardized descriptors until 70 remain.
3. Zones not connected to the mainland (offshore islands) are dropped,
   which leaves 65 zones.

The bus-lane share comes from Street View labels that cannot be redistributed,
so by default (zones.from_assignment: true) the zones are read from the saved
assignment data/taz_to_zone.csv, which is the output of steps 1-3. Setting
from_assignment: false rebuilds them and needs the segment file.
"""
from __future__ import annotations

import heapq
from collections import defaultdict, deque
from typing import Dict, List, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from . import io


def taz_descriptors(cfg, taz: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach the Ward descriptors to each TAZ (missing values -> mean over TAZs)."""
    lu = io.read_land_use(cfg, taz.crs).drop(columns=["taz_id"])
    j = io.sjoin_zones(lu, taz, key="taz_id")
    agg = j.groupby("taz_id")[["res", "total"]].sum()
    total = (agg["total"] + agg["res"]).replace(0, np.nan)
    feats = pd.DataFrame({
        "res_share": (agg["res"] / total).fillna(0.0),
        "intersection_density_mean": j.groupby("taz_id")["intersection_density"].mean(),
    })
    seg = io.read_segments(cfg, taz.crs)
    seg["bus_lane_share"] = io.bool_indicator(seg["has_bus_lane"])
    sj = io.sjoin_zones(seg, taz, key="taz_id")
    feats = feats.join(sj.groupby("taz_id")["bus_lane_share"].mean(), how="outer")

    out = taz.merge(feats.reset_index(), on="taz_id", how="left")
    assert not out["taz_id"].duplicated().any()
    for c in cfg.zones["ward_features"]:
        out[c] = out[c].fillna(out[c].mean())
    return out


def ward_clusters(cfg, taz: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Contiguity-constrained Ward agglomeration. Returns the TAZs with a superzone_id."""
    zc = cfg.zones
    gdf = taz.sort_values("taz_id").reset_index(drop=True)
    cols = list(zc["ward_features"])
    if zc["include_coordinates"]:
        pts = gdf.geometry.representative_point()
        gdf["centroid_x_m"], gdf["centroid_y_m"] = pts.x.to_numpy(float), pts.y.to_numpy(float)
        cols += ["centroid_x_m", "centroid_y_m"]

    # Adjacency of TAZs whose polygons, buffered by a few meters, intersect.
    base = gdf[["taz_id", "geometry"]].copy()
    base["geometry"] = base.geometry.buffer(float(zc["adjacency_buffer_m"]))
    nb = gpd.sjoin(base.rename(columns={"taz_id": "a"}), base.rename(columns={"taz_id": "b"}),
                   how="inner", predicate="intersects")
    nb = nb[nb["a"] != nb["b"]]
    ids: List = sorted(gdf["taz_id"].unique(), key=lambda x: (str(x), x))
    adjacency: Dict = {t: set() for t in ids}
    for a, b in zip(nb["a"], nb["b"]):
        adjacency[a].add(b)
        adjacency[b].add(a)

    gi = gdf.set_index("taz_id")
    X = np.stack([gi.loc[t, cols].to_numpy(dtype=float) for t in ids])
    Xn = StandardScaler().fit_transform(X)

    # One cluster per TAZ; cluster ids follow the order of `ids`.
    pos = {t: i for i, t in enumerate(ids)}
    active = set(range(1, len(ids) + 1))
    members = {i + 1: [t] for i, t in enumerate(ids)}
    size = {c: 1 for c in active}
    mean = {i + 1: Xn[i].copy() for i in range(len(ids))}
    nbrs = {c: set() for c in active}
    for t in ids:
        for u in adjacency[t]:
            if pos[u] != pos[t]:
                nbrs[pos[t] + 1].add(pos[u] + 1)

    def cost(a: int, b: int) -> float:
        d = mean[a] - mean[b]
        return float(size[a] * size[b] / (size[a] + size[b]) * (d @ d))

    def merge(a: int, b: int) -> int:
        if size[a] < size[b]:
            a, b = b, a
        na, nb_ = size[a], size[b]
        mean[a] = (na * mean[a] + nb_ * mean[b]) / (na + nb_)
        size[a] = na + nb_
        members[a].extend(members[b])
        nbrs[a] = (nbrs[a] | nbrs[b]) - {a, b}
        active.remove(b)
        for x in nbrs[b]:
            if x in active:
                nbrs[x].discard(b)
                nbrs[x].add(a)
        nbrs[b].clear()
        for d in (members, size, mean):
            d.pop(b, None)
        return a

    heap: List[Tuple[float, int, int]] = []

    def push(c: int) -> None:
        for n in nbrs[c]:
            if n in active and n != c:
                a, b = (c, n) if c < n else (n, c)
                heapq.heappush(heap, (cost(a, b), a, b))

    for c in list(active):
        push(c)
    while len(active) > int(zc["n_clusters"]) and heap:
        _, a, b = heapq.heappop(heap)
        if a not in active or b not in active or b not in nbrs[a]:
            continue
        push(merge(a, b))

    label = {cid: k + 1 for k, cid in enumerate(sorted(active))}
    taz_to_zone = {t: label[cid] for cid in active for t in members[cid]}
    gdf["superzone_id"] = gdf["taz_id"].map(taz_to_zone).astype(int)
    return gdf


def drop_islands(cfg, taz_z: gpd.GeoDataFrame, zones: gpd.GeoDataFrame):
    """Keep the zones of the largest connected component (by area); drop offshore islands."""
    zc = cfg.zones
    g = zones[["superzone_id", "geometry"]].copy()
    g["geometry"] = g.geometry.buffer(0)
    left = g.rename(columns={"superzone_id": "l"}).copy()
    left["geometry"] = left.geometry.buffer(float(zc["island_buffer_m"]))
    right = g.rename(columns={"superzone_id": "r"})
    j = gpd.sjoin(left, right, predicate="intersects", how="inner")
    j = j[j["l"] != j["r"]]
    adj: Dict[int, set] = defaultdict(set)
    for a, b in zip(j["l"], j["r"]):
        adj[int(a)].add(int(b))
        adj[int(b)].add(int(a))
    ids = sorted(int(x) for x in g["superzone_id"].unique())
    area = {int(r.superzone_id): float(r.geometry.area) for r in g.itertuples()}
    seen, comps = set(), []
    for s in ids:
        if s in seen:
            continue
        comp, dq = {s}, deque([s])
        seen.add(s)
        while dq:
            u = dq.popleft()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    comp.add(v)
                    dq.append(v)
        comps.append(comp)
    keep = max(comps, key=lambda c: sum(area[i] for i in c))
    return (taz_z[taz_z["superzone_id"].isin(keep)].copy(),
            zones[zones["superzone_id"].isin(keep)].copy())


def zones_from_assignment(cfg):
    """The paper's zones from the saved TAZ -> zone assignment (same output as the Ward build)."""
    taz = io.read_taz(cfg)
    a = pd.read_csv(cfg.files["zone_assignment_csv"])
    taz_z = taz.merge(a, on="taz_id", how="inner")
    assert len(taz_z) == len(a), "every TAZ of the assignment must exist in the TAZ shapefile"
    taz_z = taz_z.sort_values("taz_id").reset_index(drop=True)
    zones = taz_z[["superzone_id", "geometry"]].dissolve(by="superzone_id").reset_index()
    zones = zones.merge(taz_z.groupby("superzone_id").size().rename("n_taz").reset_index(), on="superzone_id")
    zones["area_km2"] = zones.geometry.area / 1e6
    return taz_z, zones.reset_index(drop=True)


def build_zones(cfg):
    """Return (taz_with_zone, zones_gdf). zones_gdf has superzone_id, geometry, n_taz, area_km2."""
    if cfg.zones.get("from_assignment", False):
        return zones_from_assignment(cfg)
    taz = taz_descriptors(cfg, io.read_taz(cfg))
    taz_z = ward_clusters(cfg, taz)
    zones = taz_z[["superzone_id", "geometry"]].dissolve(by="superzone_id").reset_index()
    zones = zones.merge(taz_z.groupby("superzone_id").size().rename("n_taz").reset_index(), on="superzone_id")
    taz_z, zones = drop_islands(cfg, taz_z, zones)
    zones["area_km2"] = zones.geometry.area / 1e6
    return taz_z, zones.reset_index(drop=True)
