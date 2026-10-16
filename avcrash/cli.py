"""Command-line entry point:  python -m avcrash <command> [options]

  panel                 build the zones and the 2021-2025 zone-year panel
  run                   fit, evaluate and quantify uncertainty for the six setups
  selection-frequency   repeat the forward selection on reweighted training data
  residuals             cross-year dependence of the training residuals (temporal setups)
  streetview            rerun the nine evaluations with the Street View covariates added
  figures               maps, heatmaps and sparsity figures
  tables                LaTeX table bodies and in-text numbers (optionally fill a paper)
  all                   everything above, in order
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import time
import warnings
from pathlib import Path

import pandas as pd

from .config import ROOT, load_config

log = logging.getLogger("avcrash")
EVALS_2023 = ["citywide_2023", "geo_w2e_2023", "geo_e2w_2023"]


def _base(cfg, results: Path, streetview: bool = False):
    from .pipeline import build_base
    cache = results / ".cache" / f"base{'_streetview' if streetview else ''}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    t = time.time()
    base = build_base(cfg, streetview=streetview)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(base))
    log.info("built zones and panel%s in %.0fs", " (with Street View)" if streetview else "", time.time() - t)
    return base


def cmd_panel(cfg, a):
    taz_z, zones, panel = _base(cfg, a.results)
    panel.to_csv(a.results / "panel.csv", index=False)
    zones.to_crs("EPSG:4326").to_file(a.results / "zones.geojson", driver="GeoJSON")
    taz_z[["taz_id", "superzone_id"]].sort_values("taz_id").to_csv(a.results / "taz_to_zone.csv", index=False)
    log.info("panel: %d zones x %d years, %d columns", panel.superzone_id.nunique(), panel.year.nunique(), panel.shape[1])


def cmd_run(cfg, a):
    from .pipeline import run_setup, save_setup
    _, _, panel = _base(cfg, a.results)
    for s in a.setups or list(cfg.setups):
        t = time.time()
        res = run_setup(cfg, cfg.setup(s), panel)
        save_setup(res, a.results / "runs" / s)
        o = res.observed
        log.info("%-14s %s | R2 %.3f (null %.3f) | %.0fs", s, res.selected, o["full"]["r2"], o["null"]["r2"], time.time() - t)


def cmd_selection_frequency(cfg, a):
    from .diagnostics import selection_frequency
    from .pipeline import run_setup
    _, _, panel = _base(cfg, a.results)
    sf = cfg.uncertainty["selection_frequency"]
    out = a.results / "selection_frequency"
    out.mkdir(parents=True, exist_ok=True)
    for s in a.setups or list(cfg.setups):
        t = time.time()
        res = run_setup(cfg, cfg.setup(s), panel, with_uq=False)
        d = selection_frequency(cfg, res, int(sf["n_draws"]), int(sf["seed"]))
        (out / f"{s}.json").write_text(json.dumps(d, indent=1))
        log.info("%-14s selection frequency done in %.0fs", s, time.time() - t)


def cmd_residuals(cfg, a):
    from .diagnostics import residual_dependence
    from .pipeline import run_setup
    _, _, panel = _base(cfg, a.results)
    rp = cfg.uncertainty["residual_permutations"]
    out = {}
    for s in ("citywide_2024", "citywide_2025"):
        res = run_setup(cfg, cfg.setup(s), panel, with_uq=False)
        for kind, m in (("full", res.model), ("null", res.null_model)):
            out[f"{s}_{kind}"] = residual_dependence(res.train, m.predict(res.train), int(rp["n_perm"]), int(rp["seed"]))
    (a.results / "residual_dependence.json").write_text(json.dumps(out, indent=1))
    log.info("residual dependence written")


def cmd_streetview(cfg, a):
    from .diagnostics import evaluation_summary
    from .pipeline import run_setup
    _, _, panel = _base(cfg, a.results)
    _, _, panel_sv = _base(cfg, a.results, streetview=True)
    rows = []
    for s in EVALS_2023 + list(cfg.setups):
        for pool, p, sv in (("main", panel, False), ("streetview", panel_sv, True)):
            res = run_setup(cfg, cfg.setup(s), p, streetview=sv, with_uq=False)
            rows.append({"pool": pool, **evaluation_summary(res)})
            log.info("%-14s %-10s %s", s, pool, res.selected)
    pd.DataFrame(rows).to_csv(a.results / "streetview_comparison.csv", index=False)


def cmd_figures(cfg, a):
    from . import figures
    from .geosplit import split_regions
    _, zones, panel = _base(cfg, a.results)
    out = a.results / "figures"
    out.mkdir(parents=True, exist_ok=True)
    figures.zone_map(zones, out / "superzone_map.png")
    gs = cfg.geosplit
    figures.geosplit_map(zones, split_regions(zones, gs["center"], gs["angle_deg"]), gs["center"], gs["angle_deg"],
                         out / "geosplit.png")
    names = {"citywide_2024": "heatmap24", "citywide_2025": "heatmap25",
             "geo_w2e_2024": "geoheatmap24", "geo_w2e_2025": "geoheatmap25"}
    for s, fn in names.items():
        pred = pd.read_csv(a.results / "runs" / s / "test_predictions.csv")
        figures.prediction_heatmap(cfg, zones, pred, out / f"{fn}.png", vmax=float(cfg.raw["figures"]["heatmap_vmax"]))
    (out / "sparsity").mkdir(exist_ok=True)
    figures.sparsity(cfg, zones, panel, out / "sparsity")
    log.info("figures written to %s", out)


def cmd_tables(cfg, a):
    from .tables import Tables, fill
    out = a.results / "tables"
    names = Tables(a.results).write(out)
    log.info("wrote %d table bodies to %s", len(names), out)
    if a.paper:
        log.info("filled: %s", fill(a.paper, out))


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m avcrash", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["panel", "run", "selection-frequency", "residuals", "streetview",
                                       "figures", "tables", "all"])
    p.add_argument("--config", type=Path, default=None, help="YAML config (default: config/paper.yaml)")
    p.add_argument("--results", type=Path, default=ROOT / "results", help="output directory")
    p.add_argument("--setups", nargs="+", default=None, help="subset of setups (default: all six)")
    p.add_argument("--paper", type=Path, default=None, help="LaTeX directory to fill with the tables")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    a.results.mkdir(parents=True, exist_ok=True)
    cfg = load_config(a.config)
    steps = {"panel": cmd_panel, "run": cmd_run, "selection-frequency": cmd_selection_frequency,
             "residuals": cmd_residuals, "streetview": cmd_streetview, "figures": cmd_figures, "tables": cmd_tables}
    for name in (list(steps) if a.command == "all" else [a.command]):
        steps[name](cfg, a)


if __name__ == "__main__":
    main()
