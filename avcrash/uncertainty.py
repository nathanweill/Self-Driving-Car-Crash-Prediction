"""Uncertainty quantification.

P1 (TrainZone-Mean): refit the selected model (and the intercept-only model) on
   training data reweighted by zone, W_u ~ Gamma(4) normalized to mean 1 and
   shared by all years of a zone (scaled Dirichlet(4) random weighting). Each
   draw is rescaled around the unweighted fit, beta* = beta0 + 2 (beta_w - beta0)
   and mu* = mu0 (mu_w / mu0)^2, so that the draws have the variance of the
   classical bootstrap. Reported: the predicted test total sum(mu*), and the
   coefficient draws beta*.
P2 (Poisson-Pred): Poisson counts simulated from the fitted test means; reported: the total.
P3 (TestZone-Metric): test metrics recomputed with Dirichlet(4) weights over
   test zones at fixed predictions, rescaled as m* = m0 + 2 (m_w - m0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from .metrics import metrics, weighted_metrics
from .model import PoissonModel

QUANTILES = (0.025, 0.05, 0.25, 0.5, 0.75, 0.95, 0.975)
QCOLS = ("P2.5", "P5", "P25", "P50", "P75", "P95", "P97.5")
P3_METRICS = ("r2", "mae", "kendall_tau_b", "deviance")


def summarize(values: np.ndarray, observed: float, *, metric: str, pipeline: str) -> Dict[str, object]:
    """Mean, SD, scaled MAD (1.4826 x median absolute deviation) and percentiles of the draws."""
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    q = np.quantile(v, QUANTILES)
    med = float(np.median(v))
    row = {"pipeline": pipeline, "metric": metric, "observed": float(observed),
           "Mean": float(np.mean(v)), "STD": float(np.std(v, ddof=1)),
           "MAD (scaled)": 1.4826 * float(np.median(np.abs(v - med))),
           "within_95": bool(q[0] <= observed <= q[-1])}
    row.update({c: float(x) for c, x in zip(QCOLS, q)})
    return row


@dataclass
class ZoneDraws:
    beta: np.ndarray       # (B, p) rescaled coefficient draws
    mu: np.ndarray         # (n_test, B) rescaled test means
    converged: np.ndarray  # (B,)


def zone_weights(zone_ids: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Gamma(4) weight per zone, normalized to mean 1, repeated over the zone's rows."""
    _, inverse = np.unique(zone_ids, return_inverse=True)
    g = rng.gamma(shape=4.0, scale=1.0, size=inverse.max() + 1)
    return (g / g.mean())[inverse]


def zone_random_weighting(train: pd.DataFrame, test: pd.DataFrame, features: List[str], fit_cfg: dict,
                          n_draws: int, seed: int) -> ZoneDraws:
    rng = np.random.default_rng(seed)
    base = PoissonModel(features, fit_cfg).fit(train)
    beta0, mu0 = base.beta, base.predict(test)
    zones = train["superzone_id"].to_numpy()
    beta = np.full((n_draws, len(beta0)), np.nan)
    mu = np.full((len(test), n_draws), np.nan)
    ok = np.zeros(n_draws, bool)
    for b in range(n_draws):
        w = zone_weights(zones, rng)
        m = PoissonModel(features, fit_cfg).fit(train, sample_weight=w)
        mu_b = m.predict(test)
        beta[b] = beta0 + 2.0 * (m.beta - beta0)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(mu0 > 0, mu_b / mu0, 0.0)
        mu[:, b] = np.where(mu0 > 0, mu0 * ratio ** 2, 0.0)
        # A Poisson draw is taken (and discarded) to keep the random stream of the
        # original implementation, which also simulated test counts here.
        rng.poisson(lam=np.clip(mu[:, b], 0.0, 1e12))
        ok[b] = m.info.success
    return ZoneDraws(beta, mu, ok)


def poisson_total(mu: np.ndarray, y_obs: np.ndarray, n_draws: int, seed: int, pipeline: str) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    mu = np.clip(np.asarray(mu, float), 0.0, None)
    totals = np.array([float(rng.poisson(lam=mu).sum()) for _ in range(n_draws)])
    return summarize(totals, float(np.sum(y_obs)), metric="total_count", pipeline=pipeline)


def test_zone_metrics(y: np.ndarray, mu: np.ndarray, n_draws: int, seed: int, pipeline: str) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(y)
    center = weighted_metrics(y, mu, np.full(n, 1.0 / n))
    draws = []
    for _ in range(n_draws):
        mw = weighted_metrics(y, mu, rng.dirichlet(np.full(n, 4.0)))
        draws.append({k: center[k] + 2.0 * (mw[k] - center[k]) for k in mw})
    draws = pd.DataFrame(draws)
    obs = metrics(y, mu)
    return pd.DataFrame([summarize(draws[m].to_numpy(), obs[m], metric=m, pipeline=pipeline) for m in P3_METRICS])
