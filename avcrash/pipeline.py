"""End-to-end run of one evaluation configuration ("setup")."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import features, uncertainty as uq, zones as zmod
from .geosplit import split_regions
from .metrics import metrics
from .model import PoissonModel
from .pool import Pool, build_pool
from .selection import forward_bic

ALL_YEARS = [2021, 2022, 2023, 2024, 2025]


def build_base(cfg, streetview: bool = False):
    """Zones and the zone-year panel for 2021-2025, with the east/west region of each zone."""
    taz_z, zones = zmod.build_zones(cfg)
    panel = features.build_panel(cfg, taz_z, zones, ALL_YEARS, streetview=streetview)
    regions = split_regions(zones, cfg.geosplit["center"], cfg.geosplit["angle_deg"])
    panel = panel.merge(regions, on="superzone_id", how="left")
    return taz_z, zones, panel


@dataclass
class SetupResult:
    setup: object
    pool: Pool
    selected: List[str]
    trace: List[dict]
    model: PoissonModel
    null_model: PoissonModel
    train: pd.DataFrame
    test: pd.DataFrame
    mu: np.ndarray
    mu_null: np.ndarray
    observed: Dict[str, Dict[str, float]]
    uq: Dict[str, object] = field(default_factory=dict)


def split_rows(panel: pd.DataFrame, setup):
    w = setup.window
    train = panel[panel["year"].isin(w.train_years)]
    test = panel[panel["year"] == w.test_year]
    if setup.train_region is not None:
        train = train[train["region"] == setup.train_region]
        test = test[test["region"] != setup.train_region]
    return train.copy(), test.copy()


def run_setup(cfg, setup, panel: pd.DataFrame, *, streetview: bool = False, with_uq: bool = True) -> SetupResult:
    panel = panel[panel["year"].isin(setup.window.years)]
    pool, panel = build_pool(panel, setup, cfg.screening, streetview=streetview)
    train, test = split_rows(panel, setup)
    selected, trace = forward_bic(train, pool.final, cfg.fit, cfg.selection["interaction_parents"],
                                  tol=cfg.selection["tol"])
    model = PoissonModel(selected, cfg.fit).fit(train)
    null = PoissonModel([], cfg.fit).fit(train)
    mu, mu0 = model.predict(test), null.predict(test)
    y = test["n_av"].to_numpy(float)
    res = SetupResult(setup, pool, selected, trace, model, null, train, test, mu, mu0,
                      {"full": metrics(y, mu), "null": metrics(y, mu0)})
    if with_uq:
        run_uncertainty(cfg, res)
    return res


def run_uncertainty(cfg, res: SetupResult) -> None:
    u = cfg.uncertainty
    B, s = int(u["n_draws"]), u["seeds"]
    y = res.test["n_av"].to_numpy(float)
    for kind, feats, mu in (("full", res.selected, res.mu), ("null", [], res.mu_null)):
        d = uq.zone_random_weighting(res.train, res.test, feats, cfg.fit, B, s["p1"])
        keep = np.isfinite(d.beta).all(axis=1)
        res.uq[f"{kind}_draws"] = d
        res.uq[f"{kind}_p1"] = pd.DataFrame([uq.summarize(d.mu[:, keep].sum(axis=0), float(mu.sum()),
                                                          metric="predicted_total", pipeline="P1")])
        res.uq[f"{kind}_p2"] = pd.DataFrame([uq.poisson_total(mu, y, B, s[f"p2_{kind}"], "P2")])
        res.uq[f"{kind}_p3"] = uq.test_zone_metrics(y, mu, B, s[f"p3_{kind}"], "P3")


def save_setup(res: SetupResult, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    s = res.setup
    obs = {
        "setup": s.name, "test_year": s.window.test_year, "train_years": s.window.train_years,
        "train_region": s.train_region, "n_train_rows": len(res.train),
        "selected_features": res.selected,
        "beta": dict(zip(["intercept"] + res.selected, map(float, res.model.beta))),
        "null_beta": float(res.null_model.beta[0]),
        "full": res.observed["full"], "null": res.observed["null"],
        "max_abs_grad": res.model.info.max_abs_grad, "null_max_abs_grad": res.null_model.info.max_abs_grad,
    }
    if res.uq:
        for kind in ("full", "null"):
            d = res.uq[f"{kind}_draws"]
            obs[f"{kind}_p1_nonconverged_refits"] = int((~d.converged).sum())
    (out / "observed_metrics.json").write_text(json.dumps(obs, indent=2) + "\n")
    pool = {"screen_years": res.pool.screen_years, "screen_rows": res.pool.screen_rows,
            "screened": res.pool.screened, "log1p": res.pool.log1p,
            "corr_dropped": {k: list(v) for k, v in res.pool.corr_dropped.items()}, "final": res.pool.final}
    (out / "candidate_pool.json").write_text(json.dumps(pool, indent=2) + "\n")
    pd.DataFrame(res.trace).to_csv(out / "selection_trace.csv", index=False)
    pred = res.test[["superzone_id", "year", "region", "n_av", "n_hv"]].copy()
    pred["mu"], pred["mu_null"] = res.mu, res.mu_null
    pred.to_csv(out / "test_predictions.csv", index=False)
    if not res.uq:
        return
    for kind in ("full", "null"):
        for p in ("p1", "p2", "p3"):
            res.uq[f"{kind}_{p}"].to_csv(out / f"{kind}_{p}.csv", index=False)
        d = res.uq[f"{kind}_draws"]
        names = ["intercept"] + (res.selected if kind == "full" else [])
        rows = [{"draw": b, "feature": nm, "coef": float(d.beta[b, j]), "converged": bool(d.converged[b])}
                for b in range(d.beta.shape[0]) for j, nm in enumerate(names)]
        fname = "coefficient_draws.csv" if kind == "full" else "null_coefficient_draws.csv"
        pd.DataFrame(rows).to_csv(out / fname, index=False)
