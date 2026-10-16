"""Test-set metrics (unweighted and weighted by test-zone weights)."""
from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.special import gammaln
from scipy.stats import kendalltau


def deviance_terms(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """Per-zone Poisson deviance contributions (mu floored at 1e-10)."""
    y = np.clip(np.asarray(y, float), 0, None)
    mu = np.clip(np.asarray(mu, float), 1e-10, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(y > 0, y * np.log(y / mu) - (y - mu), -(y - mu))
    return 2.0 * t


def metrics(y: np.ndarray, mu: np.ndarray) -> Dict[str, float]:
    y = np.asarray(y, float)
    mu = np.asarray(mu, float)
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    tau = kendalltau(y, mu, variant="b").correlation
    return {
        "r2": 1.0 - float(np.sum((y - mu) ** 2)) / ss_tot if ss_tot > 0 else 0.0,
        "mae": float(np.mean(np.abs(y - mu))),
        "kendall_tau_b": float(tau) if np.isfinite(tau) else float("nan"),
        "deviance": float(np.sum(deviance_terms(y, mu))),
        "total_true": float(y.sum()),
        "total_pred": float(mu.sum()),
    }


def weighted_kendall_tau_b(y: np.ndarray, mu: np.ndarray, w: np.ndarray) -> float:
    """Kendall tau-b with pair (i, j) weighted by w_i w_j."""
    n = len(y)
    iu = np.triu_indices(n, k=1)
    ww = np.outer(w, w)[iu]
    sy = np.sign((y[:, None] - y[None, :])[iu])
    sm = np.sign((mu[:, None] - mu[None, :])[iu])
    denom = np.sqrt(np.sum(ww * (sy != 0)) * np.sum(ww * (sm != 0)))
    return float(np.sum(ww * sy * sm) / denom) if np.isfinite(denom) and denom > 0 else float("nan")


def weighted_metrics(y: np.ndarray, mu: np.ndarray, w: np.ndarray) -> Dict[str, float]:
    """Weighted R2, MAE, deviance (n * sum w_i d_i) and Kendall tau-b; w sums to 1."""
    y, mu, w = (np.asarray(a, float) for a in (y, mu, w))
    ybar = float(np.sum(w * y))
    ss_res = float(np.sum(w * (y - mu) ** 2))
    ss_tot = float(np.sum(w * (y - ybar) ** 2))
    return {
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0,
        "mae": float(np.sum(w * np.abs(y - mu))),
        "deviance": float(len(y) * np.sum(w * deviance_terms(y, mu))),
        "kendall_tau_b": weighted_kendall_tau_b(y, mu, w),
    }


def poisson_loglik(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    mu = np.clip(np.asarray(mu, float), 1e-10, None)
    y = np.asarray(y, float)
    return y * np.log(mu) - mu - gammaln(y + 1)
