import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from avcrash.config import load_config
from avcrash.model import PoissonModel

FIT = load_config().fit


def _toy(n=300, seed=0):
    rng = np.random.default_rng(seed)
    x1, x2 = rng.normal(size=n), rng.uniform(0, 50, size=n)
    nh = rng.poisson(20, size=n).astype(float)
    NA, NH = 5.0, 3000.0
    mu = nh * NA / NH * np.exp(2.5 + 0.4 * x1 + 0.01 * x2)
    return pd.DataFrame({"n_av": rng.poisson(mu).astype(float), "n_hv": nh, "N_A": NA, "N_H": NH, "x1": x1, "x2": x2})


def test_gradient_matches_finite_differences():
    df = _toy()
    m = PoissonModel(["x1", "x2"], FIT)
    X, nA, nH, NA, NH = m._arrays(df)
    w = np.random.default_rng(1).gamma(4.0, size=len(df))
    b = np.array([2.0, 0.3, 0.02])
    f, g = m._objective(b, X, nA, nH, NA, NH, w)
    eps = 1e-6
    num = [(m._objective(b + eps * e, X, nA, nH, NA, NH, w)[0] - m._objective(b - eps * e, X, nA, nH, NA, NH, w)[0])
           / (2 * eps) for e in np.eye(3)]
    assert np.allclose(g, num, rtol=1e-5, atol=1e-4)


def test_fit_recovers_coefficients_and_converges():
    m = PoissonModel(["x1", "x2"], FIT).fit(_toy(n=3000))
    assert m.info.success and m.info.max_abs_grad < 1e-3
    assert np.allclose(m.beta, [2.5, 0.4, 0.01], atol=0.1)


def test_intercept_only_matches_one_dimensional_mle():
    df = _toy()
    m = PoissonModel([], FIT).fit(df)
    nA, nH = df.n_av.to_numpy(), df.n_hv.to_numpy()
    f = lambda b: np.sum((nA + nH) * np.logaddexp(np.log(3000.0), np.log(5.0) + b) - nA * b)
    b0 = minimize_scalar(f, bounds=(-10, 10), method="bounded", options={"xatol": 1e-12}).x
    assert abs(m.beta[0] - b0) < 1e-6


def test_unit_weights_equal_unweighted_fit():
    df = _toy()
    a = PoissonModel(["x1"], FIT).fit(df)
    b = PoissonModel(["x1"], FIT).fit(df, sample_weight=np.ones(len(df)))
    assert np.array_equal(a.beta, b.beta)
