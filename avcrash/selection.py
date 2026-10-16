"""Forward selection with the BIC (Step 6 of the preprocessing appendix)."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .model import PoissonModel


def eligible(candidates: Sequence[str], selected: List[str], parents: Dict[str, Sequence[str]]) -> List[str]:
    """Strong heredity: a product term is eligible once both of its factors are selected.
    (Log-transformed products have a different name and are ordinary candidates.)"""
    out = []
    for c in candidates:
        if c in selected:
            continue
        p = parents.get(c)
        if p is not None and not all(x in selected for x in p):
            continue
        out.append(c)
    return out


def forward_bic(df: pd.DataFrame, candidates: Sequence[str], fit_cfg: dict, parents: Dict[str, Sequence[str]],
                tol: float = 1e-9, sample_weight: Optional[np.ndarray] = None):
    """Greedy forward selection minimizing BIC = 2 L(beta) + k log(n) on ``df``.

    At each step every eligible candidate is added in turn (in pool order) and the
    one with the smallest BIC is kept; selection stops when no candidate lowers
    the BIC by more than ``tol``. Returns (selected, trace) where trace lists the
    accepted steps (the first row is the intercept-only model).
    """
    n = len(df)
    selected: List[str] = []
    m = PoissonModel([], fit_cfg).fit(df, sample_weight)
    best = m.bic(n)
    trace = [dict(step=0, added=None, k=1, bic=best, nll=m.info.fun)]
    while True:
        cands = eligible(candidates, selected, parents)
        if not cands:
            break
        scores = []
        for c in cands:
            mc = PoissonModel(selected + [c], fit_cfg).fit(df, sample_weight)
            if np.isfinite(mc.bic(n)):
                scores.append((mc.bic(n), c, mc))
        if not scores:
            break
        b, c, mc = min(scores, key=lambda t: t[0])  # first minimum in pool order
        if not b < best - tol:
            break
        selected.append(c)
        best = b
        trace.append(dict(step=len(selected), added=c, k=len(selected) + 1, bic=b, nll=mc.info.fun))
    return selected, trace
