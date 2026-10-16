"""Candidate pool (Steps 1-5 of the preprocessing appendix).

All steps use only the covariates of the training-region zones in the
selection years; crash counts are never used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .features import CANDIDATES, STREETVIEW

LOG_SUFFIX = "__lg"  # column name of log(1 + x)


@dataclass
class Pool:
    final: List[str]                       # candidates entering forward selection
    screened: List[str]                    # after Steps 1-3
    log1p: List[str]                       # variables replaced by log(1 + x) in Step 4
    corr_dropped: Dict[str, Tuple[str, float]] = field(default_factory=dict)  # Step 5
    screen_years: List[int] = field(default_factory=list)
    screen_rows: int = 0


def screen(rows: pd.DataFrame, cols: List[str], sc: dict) -> List[str]:
    """Step 3: support / variance / binary-dominance screening on zone means."""
    means = rows.groupby("superzone_id")[cols].mean()
    kept = []
    for c in cols:
        x = means[c].fillna(0.0).to_numpy(float)
        nonzero = np.abs(x) > 1e-12
        if nonzero.sum() < sc["min_nonzero_zones"] or nonzero.mean() < sc["min_nonzero_share"]:
            continue
        if np.std(x) < 1e-12:
            continue
        if np.all(np.isclose(x, 0.0, atol=1e-12) | np.isclose(x, 1.0, atol=1e-12)):
            if max((~nonzero).mean(), np.isclose(x, 1.0, atol=1e-12).mean()) > sc["max_binary_dominance"]:
                continue
        kept.append(c)
    return kept


def corr_prune(rows: pd.DataFrame, pool: List[str], threshold: float) -> List[str]:
    """Step 5: repeatedly drop the member of the most correlated pair with the larger
    mean |r| to the remaining pool (ties: alphabetically later name)."""
    C = rows[pool].astype(float).corr().abs().fillna(0.0).to_numpy().copy()
    np.fill_diagonal(C, 0.0)
    keep = list(range(len(pool)))
    while len(keep) > 1:
        sub = C[np.ix_(keep, keep)]
        i, j = np.unravel_index(np.argmax(sub), sub.shape)
        if sub[i, j] <= threshold:
            break
        mi, mj = sub[i].mean(), sub[j].mean()
        drop = keep[i] if (mi > mj or (mi == mj and pool[keep[i]] > pool[keep[j]])) else keep[j]
        keep.remove(drop)
    return [pool[k] for k in keep]


def build_pool(panel: pd.DataFrame, setup, sc: dict, streetview: bool = False) -> Tuple[Pool, pd.DataFrame]:
    """Return the pool and the panel with the log(1 + x) columns added."""
    w = setup.window
    rows = panel[panel["year"].isin(w.selection_years)]
    if setup.train_region is not None:
        rows = rows[rows["region"] == setup.train_region]

    cols = CANDIDATES + (STREETVIEW if streetview else [])
    if sc["drop_uber_total"]:                                   # Step 2
        cols = [c for c in cols if c != "uber_total_mean_per_km2"]
    screened = sorted(screen(rows, cols, sc))                   # Step 3

    panel = panel.copy()                                        # Step 4
    pool, logged = [], []
    for c in screened:
        v = rows[c].astype(float)
        if v.min() >= 0 and v.max() > sc["log1p_if_max_above"] + 1e-9:
            panel[c + LOG_SUFFIX] = np.log1p(panel[c].astype(float))
            pool.append(c + LOG_SUFFIX)
            logged.append(c)
        else:
            pool.append(c)
    rows = panel.loc[rows.index]

    final = corr_prune(rows, pool, sc["corr_threshold"])       # Step 5
    C = rows[pool].astype(float).corr().abs()
    dropped = {d: max(((k, float(C.loc[d, k])) for k in final), key=lambda t: t[1])
               for d in pool if d not in final}
    return Pool(final, screened, logged, dropped, sorted(int(y) for y in rows["year"].unique()), len(rows)), panel
