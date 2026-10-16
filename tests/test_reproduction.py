"""Rebuild the panel and rerun the six setups; compare with the saved results/.

Takes about two minutes. The selection-frequency, residual and Street View
analyses are not rerun here (python -m avcrash all does that).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from avcrash.config import ROOT, load_config
from avcrash.pipeline import build_base, run_setup

RESULTS = ROOT / "results"
CFG = load_config()
NUM = ["observed", "Mean", "STD", "MAD (scaled)", "P2.5", "P5", "P25", "P50", "P75", "P95", "P97.5"]


@pytest.fixture(scope="module")
def base():
    return build_base(CFG)


def test_panel(base):
    _, zones, panel = base
    saved = pd.read_csv(RESULTS / "panel.csv")
    assert len(zones) == 65 and panel.shape == saved.shape
    assert list(panel.columns) == list(saved.columns)
    num = panel.select_dtypes("number").columns
    assert np.allclose(panel[num].to_numpy(float), saved[num].to_numpy(float), rtol=1e-12, atol=1e-12)
    assert (panel["region"] == saved["region"]).all()


@pytest.mark.parametrize("setup", list(CFG.setups))
def test_setup(base, setup):
    _, _, panel = base
    res = run_setup(CFG, CFG.setup(setup), panel)
    d = RESULTS / "runs" / setup
    obs = json.loads((d / "observed_metrics.json").read_text())
    assert res.selected == obs["selected_features"]
    assert np.allclose(res.model.beta, list(obs["beta"].values()), rtol=1e-8, atol=1e-8)
    for kind in ("full", "null"):
        for k, v in obs[kind].items():
            assert abs(res.observed[kind][k] - v) < 1e-8, (kind, k)
        for p in ("p1", "p2", "p4"):
            saved = pd.read_csv(d / f"{kind}_{p}.csv")
            assert np.allclose(res.uq[f"{kind}_{p}"][NUM].to_numpy(float), saved[NUM].to_numpy(float),
                               rtol=1e-6, atol=1e-6), (kind, p)
