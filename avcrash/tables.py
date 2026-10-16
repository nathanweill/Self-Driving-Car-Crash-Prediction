"""LaTeX table bodies and in-text numbers of the paper, generated from results/.

Each table body is written to <out>/<name>.tex. In the paper sources, a block
delimited by  %%BEGIN TAB:<name> ... %%END TAB:<name>  (or a bare marker line
%%TAB:<name>%%) is replaced by the file content with `scripts/fill_tables.py`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from .features import STREETVIEW

SETUPS = ["citywide_2024", "citywide_2025", "geo_w2e_2024", "geo_w2e_2025", "geo_e2w_2024", "geo_e2w_2025"]
LAB = {"citywide_2024": ("Temporal", 2024), "citywide_2025": ("Temporal", 2025),
       "geo_w2e_2024": (r"West$\to$East", 2024), "geo_w2e_2025": (r"West$\to$East", 2025),
       "geo_e2w_2024": (r"East$\to$West", 2024), "geo_e2w_2025": (r"East$\to$West", 2025)}
FNAME = {  # display names of the selected features
    "intercept": "Intercept",
    "uber_dropoffs_mean_per_km2__lg": r"$\log(1+{}$Dropoff density$)$",
    "uber_pickups_mean_per_km2__lg": r"$\log(1+{}$Pickup density$)$",
    "collision_severity_fatal_share": "Fatal-severity share",
    "fatal_crash_share": "Fatal-crash share",
    "avg_killed_per_crash": "Fatalities per crash",
    "med_share": "Medical share",
    "collision_severity_severe_injury_share": "Severe-injury share",
    "total_killed__lg": r"$\log(1+{}$Fatality count$)$",
    "pdr_share": "Industrial share",
    "weather1_raining_share": "Rain share",
    "hv_x_intersection_share__lg": r"$\log(1+{}$HV crashes$\times$intersection share$)$",
    "road_surface_wet_share": "Wet-road share",
    "collision_severity_pain_share": "Complaint-of-pain share",
}
QCOLS = ["P2.5", "P5", "P25", "P50", "P75", "P95", "P97.5"]


def num(x, d=2):
    s = f"{x:.{d}f}"
    return s[1:] if s == "-0." + "0" * d else s


def cell(obs, lo, hi, d=2):
    return f"${num(obs, d)}$ {{\\scriptsize $[{num(lo, d)},\\,{num(hi, d)}]$}}"


def interval(lo, hi, d=1):
    return f"$[{num(lo, d)},\\,{num(hi, d)}]$"


def tt(name):
    return r"\texttt{" + name.replace("_", r"\_") + "}"


class Tables:
    def __init__(self, results: Path):
        self.R = Path(results)
        self.runs = self.R / "runs"
        self.panel = pd.read_csv(self.R / "panel.csv")
        self.NUM: dict = {}

    # readers ------------------------------------------------------------------
    def obs(self, s):
        return json.loads((self.runs / s / "observed_metrics.json").read_text())

    def tot(self, s, kind, p):
        return pd.read_csv(self.runs / s / f"{kind}_p{p}.csv").iloc[0]

    def p4(self, s, kind):
        return pd.read_csv(self.runs / s / f"{kind}_p4.csv").set_index("metric")

    def selfreq(self, s):
        f = self.R / "selection_frequency" / f"{s}.json"
        return json.loads(f.read_text()) if f.exists() else None

    # main-text tables -----------------------------------------------------------
    def prev_metrics(self, s):
        """Previous-year baseline: predict each test zone's count by its count in the previous year."""
        pr = pd.read_csv(self.runs / s / "test_predictions.csv")
        ty = int(pr["year"].iloc[0])
        prev = self.panel[self.panel.year == ty - 1].set_index("superzone_id")["n_av"]
        y, p = pr["n_av"].to_numpy(float), prev.reindex(pr["superzone_id"]).to_numpy(float)
        r2 = 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        return dict(r2=r2, mae=np.abs(y - p).mean(), tau=kendalltau(p, y).statistic, total=p.sum())

    def model_row(self, s, kind, label):
        o, t = self.obs(s), self.p4(s, kind)
        k = len(o["selected_features"]) if kind == "full" else 0
        c = [cell(o[kind][m], t.loc[m, "P2.5"], t.loc[m, "P97.5"]) for m in ("r2", "mae", "kendall_tau_b")]
        p2 = self.tot(s, kind, 2)
        return (f"{label} & ${k}$ & " + " & ".join(c) + f' & ${o[kind]["total_pred"]:.1f}$ & '
                + interval(p2["P2.5"], p2["P97.5"], 0) + r" \\")

    def temporal_table(self, year):
        s = f"citywide_{year}"
        pm = self.prev_metrics(s)
        self.NUM[f"prev_{year}"] = pm
        return "\n".join([self.model_row(s, "full", "Joint Poisson"),
                          self.model_row(s, "null", "Joint Poisson (intercept-only)"),
                          f'Previous-year baseline & N/A & ${num(pm["r2"])}$ & ${num(pm["mae"])}$ & '
                          f'${num(pm["tau"])}$ & ${pm["total"]:.0f}$ & N/A \\\\'])

    def geo_table(self, year):
        out = []
        for d, lab in (("w2e", r"West$\to$East"), ("e2w", r"East$\to$West")):
            s = f"geo_{d}_{year}"
            n = int(self.obs(s)["full"]["total_true"])
            out.append(r"\multicolumn{7}{l}{\textit{" + lab + f", observed test-region total ${n}$" + r"}}\\")
            out.append(self.model_row(s, "full", "Joint Poisson"))
            out.append(self.model_row(s, "null", "Joint Poisson (intercept-only)"))
            if d == "w2e":
                out.append(r"\hline")
        return "\n".join(out)

    def p1_table(self):
        rows = []
        for s in SETUPS:
            sec, yr = LAB[s]
            r = [f"{sec} & {yr}"]
            for kind in ("full", "null"):
                p1 = self.tot(s, kind, 1)
                r.append(f'${p1["observed"]:.1f}$ & ${p1["P50"]:.1f}$ & ' + interval(p1["P2.5"], p1["P97.5"], 1))
            rows.append(" & ".join(r) + r" \\")
        return "\n".join(rows)

    # supplementary tables -------------------------------------------------------
    def quant_table(self, get, d):
        rows = []
        for s in SETUPS:
            sec, yr = LAB[s]
            for kind, kl in (("full", "Full"), ("null", "Null")):
                r = get(s, kind)
                cells = [f"{sec} {yr}" if kind == "full" else "", kl, f'${num(r["observed"], d)}$']
                cells += [f"${num(r[q], d)}$" for q in QCOLS] + [f'${num(r["MAD (scaled)"], d)}$']
                rows.append(" & ".join(cells) + r" \\")
            if s != SETUPS[-1]:
                rows.append(r"\hline")
        return "\n".join(rows)

    def supp_coef(self):
        rows = []
        for s in SETUPS:
            sec, yr = LAB[s]
            o = self.obs(s)
            dr = pd.read_csv(self.runs / s / "coefficient_draws.csv")
            dr = dr[np.isfinite(dr.coef)]
            sf = self.selfreq(s)
            for j, (nm, point) in enumerate(o["beta"].items()):
                v = dr.loc[dr.feature == nm, "coef"].to_numpy()
                med = np.median(v)
                mad = 1.4826 * np.median(np.abs(v - med))
                lo, hi = np.quantile(v, [0.025, 0.975])
                freq = "--" if nm == "intercept" else (f'${sf["freq"].get(nm, 0.0):.2f}$' if sf else "TBD")
                d = 3 if max(abs(lo), abs(hi)) < 10 else 1
                rows.append(" & ".join([f"{sec} {yr}" if j == 0 else "", FNAME[nm], f"${num(point, d)}$",
                                        f"${num(med, d)}$", f"${num(mad, d)}$", interval(lo, hi, d), freq]) + r" \\")
                self.NUM.setdefault("coef", {}).setdefault(s, {})[nm] = dict(point=point, med=med, lo=lo, hi=hi, n=len(v))
            if s != SETUPS[-1]:
                rows.append(r"\hline")
        return "\n".join(rows)

    def supp_null_coef(self):
        rows = []
        for s in SETUPS:
            sec, yr = LAB[s]
            o = self.obs(s)
            b0 = o["null_beta"]
            dr = pd.read_csv(self.runs / s / "null_coefficient_draws.csv")
            v = dr.coef.to_numpy()
            med = np.median(v)
            mad = 1.4826 * np.median(np.abs(v - med))
            lo, hi = np.quantile(v, [0.025, 0.975])
            rows.append(" & ".join([f"{sec} {yr}", f"${num(b0, 3)}$", f"${num(med, 3)}$", f"${num(mad, 3)}$",
                                    interval(lo, hi, 3), f"${np.exp(b0):.1f}$",
                                    interval(np.exp(lo), np.exp(hi), 1)]) + r" \\")
            self.NUM.setdefault("null_coef", {})[s] = dict(point=b0, med=med, lo=lo, hi=hi, rr=np.exp(b0),
                                                           rr_lo=np.exp(lo), rr_hi=np.exp(hi),
                                                           nonconv=int((~dr.converged).sum()), min=float(v.min()))
        return "\n".join(rows)

    def sparsity(self):
        p = self.panel
        rows = []
        for y in sorted(p.year.unique()):
            q = p[p.year == y]
            e, w = q[q.region == "east"], q[q.region == "west"]
            rr = (q.n_av.sum() / q.N_A.iloc[0]) / (q.n_hv.sum() / q.N_H.iloc[0])
            self.NUM.setdefault("rr", {})[int(y)] = rr
            rows.append(" & ".join([str(y), f"${int(q.n_av.sum())}$", f"${int((q.n_av == 0).sum())}$",
                                    f"${int((q.n_av >= 1).sum())}$", f"${int(q.n_av.max())}$",
                                    f"${int(e.n_av.sum())}$", f"${int(w.n_av.sum())}$",
                                    f"${int(q.n_hv.sum())}$", f"${q.N_A.iloc[0]:.2f}$", f"${q.N_H.iloc[0]:.1f}$",
                                    f"${rr:.1f}$"]) + r" \\")
        self.NUM["n_zones"] = int(p.superzone_id.nunique())
        self.NUM["n_east"] = int(p[p.region == "east"].superzone_id.nunique())
        self.NUM["n_west"] = int(p[p.region == "west"].superzone_id.nunique())
        self.NUM["zero_share_all"] = float((p.n_av == 0).mean())
        for ty, tr in ((2024, [2021, 2022, 2023]), (2025, [2021, 2022, 2023, 2024])):
            a = p[p.year.isin(tr)].groupby("year").agg(nA=("n_av", "sum"), nH=("n_hv", "sum"),
                                                       NA=("N_A", "first"), NH=("N_H", "first"))
            rr_tr = (a.nA.sum() / a.NA.sum()) / (a.nH.sum() / a.NH.sum())
            self.NUM.setdefault("rr_pooled", {})[ty] = dict(train=rr_tr, test=self.NUM["rr"][ty],
                                                            ratio=self.NUM["rr"][ty] / rr_tr)
        return "\n".join(rows)

    def streetview(self):
        e = pd.read_csv(self.R / "streetview_comparison.csv")
        keys = [("citywide_2023", "Temporal", 2023), ("geo_w2e_2023", r"West$\to$East", 2023),
                ("geo_e2w_2023", r"East$\to$West", 2023)] + [(s, *LAB[s]) for s in
                                                            ["citywide_2024", "geo_w2e_2024", "geo_e2w_2024",
                                                             "citywide_2025", "geo_w2e_2025", "geo_e2w_2025"]]
        rows, diffs = [], []
        for k, sec, yr in keys:
            a = e[(e.setup == k) & (e.pool == "main")].iloc[0]
            b = e[(e.setup == k) & (e.pool == "streetview")].iloc[0]
            assert abs(a.r2_null - b.r2_null) < 1e-12, k  # same intercept-only model
            vsel = [tt(f) for f in str(b.features).split("|") if f in STREETVIEW]
            fa, fb = f"{a.ll_gain:+.3f}", f"{b.ll_gain:+.3f}"
            diffs.append(float(fb) - float(fa))
            rows.append(" & ".join([sec, str(yr), f"${a.n_features}$", f"${b.n_features}$",
                                    ", ".join(vsel).replace(r"}, \texttt{", ", ") if vsel else "--",
                                    f"${a.r2_null:.2f}$", f"${a.r2_full:.2f}$", f"${b.r2_full:.2f}$",
                                    f"${fa}$", f"${fb}$"]) + r" \\")
            if (yr != 2025 and k.startswith("geo_e2w")):
                rows.append(r"\hline")
        self.NUM["vlm"] = dict(diffs=diffs, better=int(sum(x > 0 for x in diffs)), worse=int(sum(x < 0 for x in diffs)),
                               same=int(sum(x == 0 for x in diffs)), mean=float(np.mean(diffs)))
        return "\n".join(rows)

    def preprocessing(self):
        rows = []
        for s in SETUPS:
            sec, yr = LAB[s]
            c = json.loads((self.runs / s / "candidate_pool.json").read_text())
            dropped = ", ".join(tt(d.replace("__lg", "")) + (r"$^{\ell}$" if d.endswith("__lg") else "")
                                + f" (${v[1]:.3f}$)" for d, v in sorted(c["corr_dropped"].items()))
            rows.append(" & ".join([f"{sec} {yr}", ", ".join(map(str, c["screen_years"])), f'${c["screen_rows"]}$',
                                    f'${len(c["screened"])}$', f'${len(c["final"])}$', dropped]) + r" \\")
            self.NUM.setdefault("pool", {})[s] = dict(screened=len(c["screened"]), final=len(c["final"]), log1p=c["log1p"])
        return "\n".join(rows)

    def bic_trace(self):
        rows = []
        for s in SETUPS:
            sec, yr = LAB[s]
            tr = pd.read_csv(self.runs / s / "selection_trace.csv")
            n = self.obs(s)["n_train_rows"]
            for i, t in tr.iterrows():
                nm = "Null (intercept only)" if pd.isna(t["added"]) else "+ " + FNAME[t["added"]]
                dB = "" if i == 0 else f'${t["bic"] - tr.loc[i - 1, "bic"]:.2f}$'
                rows.append(" & ".join([f"{sec} {yr}" if i == 0 else "", f"${n}$" if i == 0 else "", nm,
                                        f'${int(t["k"])}$', dB]) + r" \\")
            if s != SETUPS[-1]:
                rows.append(r"\hline")
        return "\n".join(rows)

    # driver ---------------------------------------------------------------------
    def write(self, out: Path):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        p4row = lambda m: (lambda s, k: self.p4(s, k).loc[m])
        totrow = lambda i: (lambda s, k: self.tot(s, k, i))
        frags = {
            "tab_rolling_2024": self.temporal_table(2024),
            "tab_rolling_2025": self.temporal_table(2025),
            "tab_geo_2024": self.geo_table(2024),
            "tab_geo_2025": self.geo_table(2025),
            "tab_p1": self.p1_table(),
            "tab_supp_q_r2": self.quant_table(p4row("r2"), 2),
            "tab_supp_q_tau": self.quant_table(p4row("kendall_tau_b"), 2),
            "tab_supp_q_mae": self.quant_table(p4row("mae"), 2),
            "tab_supp_q_dev": self.quant_table(p4row("deviance"), 1),
            "tab_supp_q_p1": self.quant_table(totrow(1), 1),
            "tab_supp_q_p2": self.quant_table(totrow(2), 1),
            "tab_supp_coef": self.supp_coef(),
            "tab_supp_null_coef": self.supp_null_coef(),
            "tab_sparsity": self.sparsity(),
            "tab_preproc": self.preprocessing(),
            "tab_bic_trace": self.bic_trace(),
        }
        if (self.R / "streetview_comparison.csv").exists():
            frags["tab_vlm"] = self.streetview()
        for k, v in frags.items():
            (out / f"{k}.tex").write_text(v + "\n")
        for s in SETUPS:
            self.NUM.setdefault("obs", {})[s] = self.obs(s)
            self.NUM.setdefault("p1", {})[s] = {k: self.tot(s, k, 1)[["observed", "P50", "P2.5", "P97.5"]].to_dict()
                                                for k in ("full", "null")}
            self.NUM.setdefault("p2", {})[s] = {k: self.tot(s, k, 2)[["observed", "P50", "P2.5", "P97.5", "within_95"]].to_dict()
                                                for k in ("full", "null")}
            self.NUM.setdefault("p4", {})[s] = {k: self.p4(s, k)[["observed", "P50", "P2.5", "P97.5"]].to_dict(orient="index")
                                                for k in ("full", "null")}
            sf = self.selfreq(s)
            if sf:
                self.NUM.setdefault("selfreq", {})[s] = dict(
                    freq={k: sf["freq"].get(k) for k in self.obs(s)["selected_features"]}, size=sf["size_dist"],
                    top=sf["top_sets"][:1], replicated=sf["replicated_selected"] == sf["pipeline_selected"])
        rd = self.R / "residual_dependence.json"
        if rd.exists():
            self.NUM["residual_dependence"] = json.loads(rd.read_text())
        (out / "numbers.json").write_text(json.dumps(self.NUM, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
        return list(frags)


def fill(paper_dir: Path, tables_dir: Path) -> list:
    """Insert the table bodies into the LaTeX sources at their markers (idempotent)."""
    changed = []
    for tex in Path(paper_dir).glob("*.tex"):
        s = orig = tex.read_text()
        body = lambda n: (Path(tables_dir) / f"{n}.tex").read_text().rstrip("\n")
        s = re.sub(r"%%BEGIN TAB:(\w+)[^\n]*\n.*?%%END TAB:\1", lambda m: f"%%TAB:{m.group(1)}%%", s, flags=re.S)
        s = re.sub(r"%%TAB:(\w+)%%", lambda m: f"%%BEGIN TAB:{m.group(1)} (generated by make_tables.py; do not edit by hand)"
                   f"\n{body(m.group(1))}\n%%END TAB:{m.group(1)}", s)
        if s != orig:
            tex.write_text(s)
            changed.append(tex.name)
    return changed
