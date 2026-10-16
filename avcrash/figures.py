"""Figures: zone map, east/west split, predicted-mean heatmaps, sparsity panels."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely.geometry import box  # noqa: E402

from . import io  # noqa: E402


def _bounds(zones, pad=0.02):
    minx, miny, maxx, maxy = zones.total_bounds
    px, py = max((maxx - minx) * pad, 100.0), max((maxy - miny) * pad, 100.0)
    return minx - px, miny - py, maxx + px, maxy + py


def _coloring(zones) -> Dict[int, int]:
    """Greedy graph coloring of adjacent zones (for display only)."""
    g = zones[["superzone_id", "geometry"]].copy()
    g["geometry"] = g.geometry.buffer(0)
    j = gpd.sjoin(g.rename(columns={"superzone_id": "a"}), g.rename(columns={"superzone_id": "b"}),
                  predicate="intersects")[["a", "b"]]
    adj = {k: set() for k in g["superzone_id"]}
    for a, b in j[j.a != j.b].itertuples(index=False):
        adj[a].add(b)
        adj[b].add(a)
    color: Dict[int, int] = {}
    for u in sorted(adj, key=lambda k: len(adj[k]), reverse=True):
        used = {color[v] for v in adj[u] if v in color}
        color[u] = next(c for c in range(len(adj) + 1) if c not in used)
    return color


def zone_map(zones, path: Path):
    g = zones[["superzone_id", "geometry"]].copy()
    g["color"] = g["superzone_id"].map(_coloring(zones))
    minx, miny, maxx, maxy = _bounds(g)
    fig, ax = plt.subplots(figsize=(9, 9), facecolor="white")
    gpd.clip(g, box(minx, miny, maxx, maxy)).plot(column="color", categorical=True, cmap="tab20", ax=ax,
                                                   edgecolor="black", linewidth=0.4)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(f"Zones (n={len(g)})", fontsize=14)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def geosplit_map(zones, regions: pd.DataFrame, center, angle_deg: float, path: Path):
    g = zones[["superzone_id", "geometry"]].merge(regions, on="superzone_id")
    minx, miny, maxx, maxy = _bounds(g)
    fig, ax = plt.subplots(figsize=(9, 9), facecolor="white")
    colors = {"east": "#2A9D8F", "west": "#E76F51"}
    for r, sub in g.groupby("region"):
        sub.plot(ax=ax, color=colors[r], alpha=0.75, edgecolor="white", linewidth=0.7)
    phi = np.radians(angle_deg)
    d = np.array([-np.sin(phi), np.cos(phi)]) * 2e4  # direction of the line (normal at angle_deg)
    cx, cy = center
    ax.plot([cx - d[0], cx + d[0]], [cy - d[1], cy + d[1]], color="#1f1f1f", linestyle=(0, (6, 3)), linewidth=2.4)
    ax.legend(handles=[Patch(facecolor=colors["west"], label="west"), Patch(facecolor=colors["east"], label="east"),
                       Line2D([0], [0], color="#1f1f1f", linestyle=(0, (6, 3)), label="boundary")],
              loc="lower right", framealpha=0.95)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def prediction_heatmap(cfg, zones, pred: pd.DataFrame, path: Path, vmax: float = 10.0):
    """Predicted mean AV crashes per test zone with the observed test-year crashes overlaid
    (common color scale from 0 to ``vmax`` for all maps)."""
    year = int(pred["year"].iloc[0])
    g = zones[["superzone_id", "geometry"]].merge(pred[["superzone_id", "mu"]], on="superzone_id", how="left")
    minx, miny, maxx, maxy = _bounds(zones)
    clip = box(minx, miny, maxx, maxy)
    g = gpd.clip(g, clip)
    pts = io.read_av_crashes(cfg, [year])
    pts = gpd.clip(pts, clip)
    pts = gpd.sjoin(pts, g[g.superzone_id.isin(pred.superzone_id)][["superzone_id", "geometry"]],
                    how="inner", predicate="intersects")
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="white")
    g.plot(column="mu", cmap="YlOrRd", vmin=0.0, vmax=vmax, ax=ax, missing_kwds={"color": "lightgrey"},
           edgecolor="0.35", linewidth=0.25)
    sm = plt.cm.ScalarMappable(cmap="YlOrRd", norm=plt.Normalize(0.0, vmax))
    fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04, label="Predicted mean AV crashes")
    if len(pts):
        pts.plot(ax=ax, color="#22d3ee", markersize=60, alpha=0.9, edgecolor="white", linewidth=0.25, zorder=5)
    ax.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor="#22d3ee", markeredgecolor="white",
                              markersize=14, alpha=0.9, linestyle="", label=f"Observed crashes in {year}")],
              loc="lower left", framealpha=0.92)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def sparsity(cfg, zones, panel: pd.DataFrame, out_dir: Path):
    """Per year: histogram of AV crashes per zone and map of the crash locations."""
    minx, miny, maxx, maxy = _bounds(zones)
    clip = box(minx, miny, maxx, maxy)
    pts = io.sjoin_zones(io.read_av_crashes(cfg, sorted(panel.year.unique())), zones)
    cmax = int(panel.n_av.max())
    nz = panel.superzone_id.nunique()
    for y in sorted(panel.year.unique()):
        c = panel[panel.year == y].n_av.astype(int)
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.2), gridspec_kw={"width_ratios": [1, 1.15]}, facecolor="white")
        a1.hist(c, bins=np.arange(-0.5, cmax + 1.5, 1), color="#b91c1c", edgecolor="white")
        a1.set_xlabel("AV crashes in the zone")
        a1.set_ylabel("Number of zones")
        a1.set_ylim(0, 50)
        a1.set_xlim(-0.7, cmax + 0.7)
        a1.set_xticks(range(0, cmax + 1, 2))
        a1.spines[["top", "right"]].set_visible(False)
        a1.set_title(f"{y}: {int(c.sum())} AV crashes, {int((c == 0).sum())} of {nz} zones with none", fontsize=11)
        z = zones[["superzone_id", "geometry"]].copy()
        z["geometry"] = z.geometry.buffer(15).buffer(-15)
        gpd.clip(z, clip).plot(ax=a2, facecolor="#f3f4f6", edgecolor="0.25", linewidth=0.7)
        p = pts[pts.year == y]
        p.plot(ax=a2, color="#dc2626", markersize=22, alpha=0.7, edgecolor="white", linewidth=0.3)
        a2.set_xlim(minx, maxx)
        a2.set_ylim(miny, maxy)
        a2.set_aspect("equal")
        a2.set_axis_off()
        a2.set_title(f"{y}: AV crash locations ({len(p)} points)", fontsize=11)
        fig.tight_layout()
        fig.savefig(Path(out_dir) / f"sparsity_{y}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
