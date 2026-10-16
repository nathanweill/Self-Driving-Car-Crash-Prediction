"""Joint Poisson model of AV and HV crash counts with the HV rate profiled out.

For zone-year i with HV count nH_i, AV count nA_i, fleet mileages N_H, N_A
and covariates x_i, the profiled negative log-likelihood is

    L(beta) = sum_i w_i [ (nA_i + nH_i) log(N_H + N_A exp(beta'x_i)) - nA_i beta'x_i ]

(up to a constant), with x_i including an intercept. The predicted mean AV
count is  mu_i = nH_i (N_A / N_H) exp(beta'x_i).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def _sigmoid(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


@dataclass
class FitInfo:
    success: bool
    n_iter: int
    fun: float           # minimized profiled NLL (weighted)
    max_abs_grad: float  # gradient at beta on the raw feature scale


class PoissonModel:
    """Profiled joint Poisson model. ``features=[]`` gives the intercept-only model."""

    def __init__(self, features: List[str], fit_cfg: dict):
        self.features = list(features)
        self.fit_cfg = fit_cfg
        self.beta: Optional[np.ndarray] = None
        self.info: Optional[FitInfo] = None

    # design and data -----------------------------------------------------
    def _arrays(self, df: pd.DataFrame):
        X = df[self.features].fillna(0.0).to_numpy(float)
        X = np.hstack([np.ones((len(df), 1)), X])
        return (X, df["n_av"].fillna(0.0).to_numpy(float), df["n_hv"].fillna(0.0).to_numpy(float),
                df["N_A"].to_numpy(float), df["N_H"].to_numpy(float))

    @staticmethod
    def _objective(beta, X, nA, nH, NA, NH, w):
        eta = X @ beta
        rows = (nA + nH) * np.logaddexp(np.log(NH), np.log(NA) + eta) - nA * eta
        d_eta = (nA + nH) * _sigmoid(np.log(NA) - np.log(NH) + eta) - nA
        if w is None:
            return float(np.sum(rows)), X.T @ d_eta
        return float(np.sum(w * rows)), X.T @ (w * d_eta)

    # fit ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame, sample_weight: Optional[np.ndarray] = None) -> "PoissonModel":
        """L-BFGS-B from beta = 0, with the features centered and scaled on the fit rows
        (weighted when ``sample_weight`` is given); beta is returned on the raw scale."""
        X, nA, nH, NA, NH = self._arrays(df)
        w = None
        if sample_weight is not None:
            w = np.asarray(sample_weight, float).reshape(-1)
            if np.all(w == 1.0):
                w = None
        Xs, center, scale = X, None, None
        if X.shape[1] > 1:
            ww = np.ones(len(X)) if w is None else w
            center = ww @ X[:, 1:] / ww.sum()
            scale = np.sqrt(np.maximum(ww @ (X[:, 1:] - center) ** 2 / ww.sum(), 0.0))
            scale = np.where(np.isfinite(scale) & (scale > 0), scale, 1.0)
            Xs = np.hstack([X[:, :1], (X[:, 1:] - center) / scale])
        fc = self.fit_cfg
        res = minimize(
            fun=lambda b: self._objective(b, Xs, nA, nH, NA, NH, w)[0],
            jac=lambda b: self._objective(b, Xs, nA, nH, NA, NH, w)[1],
            x0=np.zeros(X.shape[1]), method="L-BFGS-B", tol=fc["tol"],
            options={"ftol": fc["ftol"], "gtol": fc["gtol"], "maxiter": int(fc["maxiter"])},
        )
        beta = res.x.copy()
        if center is not None:
            slopes = beta[1:] / scale
            beta[0] = beta[0] - float(np.dot(slopes, center))
            beta[1:] = slopes
        self.beta = beta
        grad = self._objective(beta, X, nA, nH, NA, NH, w)[1]
        self.info = FitInfo(bool(res.success), int(res.nit), float(res.fun), float(np.max(np.abs(grad))))
        return self

    # predict ----------------------------------------------------------------
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X, _, nH, NA, NH = self._arrays(df)
        eta = np.clip(X @ self.beta, -self.fit_cfg["eta_clip"], self.fit_cfg["eta_clip"])
        return np.clip(nH * (NA / NH) * np.exp(eta), 0.0, None)

    def bic(self, n: int) -> float:
        return 2.0 * self.info.fun + len(self.beta) * np.log(n)
