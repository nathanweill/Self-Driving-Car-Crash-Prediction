"""Supplementary analyses: selection stability, residual dependence, Street View comparison."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

import numpy as np
import pandas as pd

from .metrics import metrics, poisson_loglik
from .selection import forward_bic


# --------------------------------------------------------------------------- selection frequency
def selection_frequency(cfg, res, n_draws: int, seed: int) -> Dict[str, object]:
    """Repeat the forward selection on the training window with Bayesian-bootstrap zone
    weights (Exp(1) per zone, normalized to mean 1, i.e. K x Dirichlet(1)); no rescaling."""
    parents = cfg.selection["interaction_parents"]
    train, cands = res.train, res.pool.final
    replicated, _ = forward_bic(train, cands, cfg.fit, parents, tol=cfg.selection["tol"])
    _, inverse = np.unique(train["superzone_id"].to_numpy(), return_inverse=True)
    rng = np.random.default_rng(seed)
    freq, sets, sizes = Counter(), Counter(), []
    for _ in range(n_draws):
        g = rng.exponential(size=inverse.max() + 1)
        sel, _ = forward_bic(train, cands, cfg.fit, parents, tol=cfg.selection["tol"],
                             sample_weight=(g / g.mean())[inverse])
        freq.update(sel)
        sets["|".join(sorted(sel))] += 1
        sizes.append(len(sel))
    return {
        "setup": res.setup.name, "B": n_draws, "seed": seed,
        "pipeline_selected": res.selected, "replicated_selected": replicated,
        "freq": {k: v / n_draws for k, v in sorted(freq.items(), key=lambda kv: -kv[1])},
        "size_dist": {int(k): int(v) for k, v in sorted(Counter(sizes).items())},
        "top_sets": sets.most_common(5),
    }


# --------------------------------------------------------------------------- residual dependence
def _lag1_pearson(R: np.ndarray) -> float:
    left, right = R[:, :-1], R[:, 1:]
    m = np.isfinite(left) & np.isfinite(right)
    x, y = left[m], right[m]
    return float(np.corrcoef(x, y)[0, 1]) if x.size > 1 and np.std(x) > 0 and np.std(y) > 0 else np.nan


def _icc(R: np.ndarray) -> float:
    """ICC = (VR - 1) / (T - 1), VR = T Var_u(mean_t R) / Var(R), zones observed in all T years."""
    T = R.shape[1]
    block = R[np.isfinite(R).all(axis=1)]
    vr = T * np.var(block.mean(axis=1)) / np.var(block)
    return float((vr - 1.0) / (T - 1))


def residual_dependence(train: pd.DataFrame, mu: np.ndarray, n_perm: int, seed: int,
                        min_mu: float = 1e-8) -> Dict[str, float]:
    """Pearson residuals (n_A - mu) / sqrt(mu) of the training rows: lag-one correlation across
    consecutive years within a zone, ICC, and one-sided permutation p-values (residuals
    shuffled across zones independently within each year)."""
    keep = mu > min_mu
    f = pd.DataFrame({"superzone_id": train["superzone_id"].to_numpy()[keep], "year": train["year"].to_numpy()[keep],
                      "r": (train["n_av"].to_numpy(float)[keep] - mu[keep]) / np.sqrt(mu[keep])})
    years = sorted(train["year"].unique())
    R = f.pivot(index="superzone_id", columns="year", values="r").reindex(columns=years).sort_index().to_numpy(float)
    obs_lag, obs_icc = _lag1_pearson(R), _icc(R)
    rng = np.random.default_rng(seed)
    idx = [np.flatnonzero(np.isfinite(R[:, t])) for t in range(R.shape[1])]
    null_lag, null_icc = np.empty(n_perm), np.empty(n_perm)
    for i in range(n_perm):
        S = R.copy()
        for t, ix in enumerate(idx):
            if ix.size > 1:
                S[ix, t] = rng.permutation(R[ix, t])
        null_lag[i], null_icc[i] = _lag1_pearson(S), _icc(S)
    p = lambda null, o: float((1 + np.count_nonzero(null[np.isfinite(null)] >= o)) / (np.isfinite(null).sum() + 1))
    return {"lag1_pearson": obs_lag, "lag1_p": p(null_lag, obs_lag), "lag1_null_975": float(np.quantile(null_lag, 0.975)),
            "icc": obs_icc, "icc_p": p(null_icc, obs_icc), "icc_null_975": float(np.quantile(null_icc, 0.975)),
            "n_rows": int(keep.sum()), "n_zones": int(R.shape[0])}


# --------------------------------------------------------------------------- Street View comparison
def evaluation_summary(res) -> Dict[str, object]:
    """Test summary used to compare candidate pools: R2 and tau of the selected and intercept-only
    models, and the mean per-zone Poisson log-likelihood gain over the intercept-only model."""
    y = res.test["n_av"].to_numpy(float)
    full, null = metrics(y, res.mu), metrics(y, res.mu_null)
    gain = poisson_loglik(y, res.mu) - poisson_loglik(y, res.mu_null)
    return {"setup": res.setup.name, "n_features": len(res.selected), "features": "|".join(res.selected),
            "r2_full": full["r2"], "r2_null": null["r2"], "tau_full": full["kendall_tau_b"],
            "tau_null": null["kendall_tau_b"], "ll_gain": float(gain.mean())}
