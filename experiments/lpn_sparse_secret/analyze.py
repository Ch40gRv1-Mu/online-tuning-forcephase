"""Evaluate the pre-registered predictions Q1-Q5 of the LPN sparse-secret
experiment (see README.md, section "Predictions").

Per instance: r_X = log2((c_X + 0.1) / (c_D + 0.1)); c = CPU seconds if the
run answered within T and passed verification (SAT model on the CNF, LPN
semantics check; UNSAT LRAT proof), else 2T. Both unsolved gives r = 0.
Effects are medians over instances with 95% bootstrap CIs (10,000
resamples over instances). Verdict: "supported" = predicted sign and CI
excludes 0; "contradicted" = opposite sign and CI excludes 0; otherwise
"not supported (CI includes 0)". Only instances with every configuration
recorded are used; missing runs are counted.

Usage: python3 analyze.py --exp lpn_sparse_main --manifest benchmarks/lpn_sparse_main.csv
Writes results/<exp>/predictions.{md,json} and results/<exp>/effects.png.
"""

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fplib  # noqa: E402

LBL = fplib.CONFIG_LABELS
ENCS = ("implicit", "explicit", "implicitflip")
VERIFIED = {"VERIFIED_MODEL", "VERIFIED_LRAT"}
OFFSET, BOOT_N, BOOT_SEED = 0.1, 10000, 20261021
# Chart tokens (light mode); colour follows the configuration.
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
COLOR = {"D": "#2a78d6", "Im": "#eb6834", "Fm": "#1baf7a", "Fp": "#eda100",
         "D_noR": "#e87ba4", "Im_noR": "#008300", "S": "#6250d6"}


def load(exp):
    d = fplib.RESULTS / exp
    latest, n_attempts = {}, Counter()
    for l in open(d / "runs.jsonl"):
        r = json.loads(l)
        r.setdefault("attempt", 1)
        latest[r["run_id"]] = r  # append-only ledger: last attempt wins
        n_attempts[r["run_id"]] += 1
    runs = list(latest.values())
    for r in runs:
        r["vkey"] = f"{r['run_id']}#a{r['attempt']}"
        r["n_attempts"] = n_attempts[r["run_id"]]
        if "contended" not in r:
            r["contended"] = r["cpu_s"] > 1 and r["wall_s"] / r["cpu_s"] > 1.10
    ver = {}
    if (d / "verify.jsonl").exists():
        for l in open(d / "verify.jsonl"):
            v = json.loads(l)
            ver[v.get("vkey", v["run_id"] + "#a1")] = v
    return runs, ver


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def boot_median(xs, n=BOOT_N, seed=BOOT_SEED):
    rng = random.Random(seed)
    meds = sorted(statistics.median(rng.choices(xs, k=len(xs))) for _ in range(n))
    return [meds[int(0.025 * n)], meds[int(0.975 * n) - 1]]


def boot_diff(xs, ys, n=BOOT_N, seed=BOOT_SEED):
    """CI of median(xs) - median(ys) for independent samples."""
    rng = random.Random(seed)
    d = sorted(statistics.median(rng.choices(xs, k=len(xs))) - statistics.median(rng.choices(ys, k=len(ys)))
               for _ in range(n))
    return [d[int(0.025 * n)], d[int(0.975 * n) - 1]]


def verdict(ci, predicted_negative):
    lo, hi = ci
    if hi < 0:
        return "supported" if predicted_negative else "contradicted"
    if lo > 0:
        return "contradicted" if predicted_negative else "supported"
    return "not supported (CI includes 0)"


def fmt(x, ci):
    return f"{x:+.2f} [{ci[0]:+.2f}, {ci[1]:+.2f}] (×{2 ** x:.2f})"


LBL = fplib.CONFIG_LABELS
ENCS = ("implicit", "explicit", "implicitflip")


def tau_of(row):
    return f"1/{round(int(row['m']) / int(row['t']))}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()
    runs, ver = load(a.exp)
    sem = {}
    sp = fplib.RESULTS / a.exp / "lpn_semantic.jsonl"
    for l in open(sp):
        s = json.loads(l)
        sem[s["vkey"]] = s["semantic"]
    man = {r["hash"]: r for r in csv.DictReader(open(a.manifest))}
    T = runs[0]["timeout_s"]
    configs = [c for c in fplib.CONFIGS if any(r["config"] == c for r in runs)]
    cost, unverified = {}, []
    for r in runs:
        v = ver.get(r["vkey"], {}).get("verify")
        ok = r["solved_within_T"] and v in VERIFIED and (r["status"] != "SAT" or sem.get(r["vkey"]) == "LPN_OK")
        if r["status"] in ("SAT", "UNSAT") and r["solved_within_T"] and not ok:
            unverified.append(r["run_id"])
        cost[(r["hash"], r["config"])] = r["cpu_s"] if ok else 2 * T
    complete = sorted(h for h in man if all((h, c) in cost for c in configs))
    missing = sum(1 for h in man for c in configs if (h, c) not in cost)

    def r(h, c, base="D"):
        return math.log2((cost[(h, c)] + OFFSET) / (cost[(h, base)] + OFFSET))

    def sel(enc, kind, tau=None, n=None):
        return [h for h in complete if man[h]["enc"] == enc and man[h]["kind"] == kind
                and (tau is None or tau_of(man[h]) == tau) and (n is None or int(man[h]["n"]) == n)]

    def eff(hs, c, base="D"):
        xs = [r(h, c, base) for h in hs]
        if not xs:
            return None
        return {"n": len(xs), "median_log2_ratio": statistics.median(xs), "ci": boot_median(xs),
                "wins": sum(x < -math.log2(1.05) for x in xs), "losses": sum(x > math.log2(1.05) for x in xs)}

    out = {"exp": a.exp, "T": T, "offset_s": OFFSET, "n_instances_manifest": len(man),
           "n_instances_complete": len(complete), "missing_runs": missing,
           "unverified_answers": unverified, "cells": {}, "by_tau": {}, "by_n": {}, "predictions": {}}
    for enc in ENCS:
        for kind in ("planted", "random"):
            hs = sel(enc, kind)
            if not hs:
                continue
            c = {"n_instances": len(hs)}
            for cfg in configs:
                c[cfg] = {"solved": sum(cost[(h, cfg)] < 2 * T for h in hs),
                          "par2": sum(cost[(h, cfg)] for h in hs) / len(hs)}
                if cfg != "D":
                    c[cfg].update(eff(hs, cfg))
            out["cells"][f"{enc}/{kind}"] = c
            for tau in sorted({tau_of(man[h]) for h in hs}):
                ht = sel(enc, kind, tau)
                out["by_tau"][f"{enc}/{kind}/tau={tau}"] = {
                    "n": len(ht), **{cfg: {"solved": sum(cost[(h, cfg)] < 2 * T for h in ht),
                                           "median_r": statistics.median([r(h, cfg) for h in ht]) if cfg != "D" else None}
                                     for cfg in configs}}
            for n in sorted({int(man[h]["n"]) for h in hs}):
                hn = sel(enc, kind, n=n)
                out["by_n"][f"{enc}/{kind}/n={n}"] = {
                    "n": len(hn), **{cfg: {"solved": sum(cost[(h, cfg)] < 2 * T for h in hn)} for cfg in configs}}

    P = out["predictions"]
    C = out["cells"]
    q1 = C["implicit/planted"]["Fm"]
    P["Q1"] = {"claim": "implicit+planted: F- faster than D", "median": q1["median_log2_ratio"], "ci": q1["ci"],
               "verdict": verdict(q1["ci"], True),
               "by_tau": {tau: eff(sel("implicit", "planted", tau), "Fm")
                          for tau in sorted({tau_of(man[h]) for h in sel("implicit", "planted")})}}
    ds = []
    for h in sel("implicit", "planted"):
        twin = h.replace("lpn-implicit-", "lpn-explicit-")
        if twin in complete:
            ds.append(r(twin, "Fm") - r(h, "Fm"))
    dci = boot_median(ds)
    P["Q2"] = {"claim": "F- advantage over D smaller in explicit than implicit (paired d > 0)",
               "n_pairs": len(ds), "median_d": statistics.median(ds), "ci": dci,
               "verdict": verdict(dci, False),
               "explicit_Fm_vs_D": C["explicit/planted"]["Fm"]["median_log2_ratio"],
               "explicit_Fm_vs_D_ci": C["explicit/planted"]["Fm"]["ci"]}
    fp, fm = C["implicitflip/planted"]["Fp"], C["implicitflip/planted"]["Fm"]
    vp, vm = verdict(fp["ci"], True), verdict(fm["ci"], False)
    P["Q3"] = {"claim": "implicitflip+planted: F+ faster than D and F- slower than D",
               "Fp": {"median": fp["median_log2_ratio"], "ci": fp["ci"], "verdict": vp},
               "Fm": {"median": fm["median_log2_ratio"], "ci": fm["ci"], "verdict": vm},
               "solved": {cfg: C["implicitflip/planted"][cfg]["solved"] for cfg in configs},
               "verdict": "supported" if vp == vm == "supported" else
               ("contradicted" if "contradicted" in (vp, vm) else "not supported")}
    q4 = {}
    for enc in ENCS:
        pl, rd = C[f"{enc}/planted"]["Fm"], C[f"{enc}/random"]["Fm"]
        vacuous = all(C[f"{enc}/random"][cfg]["solved"] == 0 for cfg in configs)
        smaller = abs(rd["median_log2_ratio"]) < abs(pl["median_log2_ratio"])
        no_adv = rd["ci"][1] >= 0
        q4[enc] = {"planted_median": pl["median_log2_ratio"], "random_median": rd["median_log2_ratio"],
                   "random_ci": rd["ci"], "random_solved": {cfg: C[f"{enc}/random"][cfg]["solved"] for cfg in configs},
                   "verdict": ("vacuous (nothing solved on random)" if vacuous else
                               "supported" if smaller and no_adv else "not supported")}
    P["Q4"] = {"claim": "random: F- effect smaller than planted, no consistent F- advantage", **q4}
    q5 = {}
    for key in C:
        enc, kind = key.split("/")
        hs = sel(enc, kind)
        q5[key] = {"Fm_vs_Im": eff(hs, "Fm", "Im"), "Fm_vs_Im_noR": eff(hs, "Fm", "Im_noR")}
    P["Q5"] = {"claim": "exploratory: F- vs I- (initial sign) and F- vs I-/no-R (forcing vs rephase off)", **q5}

    res = fplib.RESULTS / a.exp
    (res / "predictions.json").write_text(json.dumps(out, indent=1))
    write_md(out, configs, res / "predictions.md")
    figure(out, configs, a.exp)
    print((res / "predictions.md").read_text())


def write_md(o, configs, path):
    P = o["predictions"]
    L_ = [f"# {o['exp']}: pre-registered predictions Q1–Q5 (T={o['T']} s)", "",
          f"Instances complete: {o['n_instances_complete']} / {o['n_instances_manifest']}; missing runs: {o['missing_runs']}; "
          f"answered-but-unverified: {len(o['unverified_answers'])}.", "",
          "Effect = median over instances of log2((c_X+0.1)/(c_D+0.1)) with 95% bootstrap CI; ×ratio in parentheses.", "",
          "| prediction | effect [95% CI] | verdict |", "|---|---|---|",
          f"| Q1 implicit+planted: F− vs D | {fmt(P['Q1']['median'], P['Q1']['ci'])} | {P['Q1']['verdict']} |"]
    for tau, e in P["Q1"]["by_tau"].items():
        if e:
            L_.append(f"| Q1 (τ_e = {tau}) | {fmt(e['median_log2_ratio'], e['ci'])} | |")
    L_ += [f"| Q2 paired d = r(explicit) − r(implicit), n={P['Q2']['n_pairs']} | {fmt(P['Q2']['median_d'], P['Q2']['ci'])} | {P['Q2']['verdict']} |",
           f"| Q2 explicit+planted: F− vs D | {fmt(P['Q2']['explicit_Fm_vs_D'], P['Q2']['explicit_Fm_vs_D_ci'])} | |",
           f"| Q3 implicitflip+planted: F+ vs D | {fmt(P['Q3']['Fp']['median'], P['Q3']['Fp']['ci'])} | {P['Q3']['Fp']['verdict']} |",
           f"| Q3 implicitflip+planted: F− vs D (predicted slower) | {fmt(P['Q3']['Fm']['median'], P['Q3']['Fm']['ci'])} | {P['Q3']['Fm']['verdict']} |"]
    for enc in ENCS:
        q = P["Q4"][enc]
        L_.append(f"| Q4 {enc} random: F− vs D (planted {q['planted_median']:+.2f}) | {fmt(q['random_median'], q['random_ci'])} | {q['verdict']} |")
    L_ += ["", f"Q3 solved counts (implicitflip, planted): `{json.dumps(P['Q3']['solved'])}`", "",
           "## Q5 (exploratory)", "", "| cell | F− vs I− | F− vs I−/no-R |", "|---|---|---|"]
    for k, v in P["Q5"].items():
        if k == "claim":
            continue
        L_.append(f"| {k} | {fmt(v['Fm_vs_Im']['median_log2_ratio'], v['Fm_vs_Im']['ci'])} | "
                  f"{fmt(v['Fm_vs_Im_noR']['median_log2_ratio'], v['Fm_vs_Im_noR']['ci'])} |")
    L_ += ["", "## Solved / PAR2 (s) per cell, and median log2 ratio vs D", "",
           "| cell | n | " + " | ".join(LBL[c] for c in configs) + " |", "|---|---:|" + "---|" * len(configs)]
    for k, c in o["cells"].items():
        cells = []
        for cfg in configs:
            x = c[cfg]
            extra = "" if cfg == "D" else f" · {x['median_log2_ratio']:+.2f}"
            cells.append(f"{x['solved']} / {x['par2']:.1f}{extra}")
        L_.append(f"| {k} | {c['n_instances']} | " + " | ".join(cells) + " |")
    L_ += ["", "## Solved by size", "", "| cell | n inst | " + " | ".join(LBL[c] for c in configs) + " |",
           "|---|---:|" + "---:|" * len(configs)]
    for k, c in o["by_n"].items():
        L_.append(f"| {k} | {c['n']} | " + " | ".join(str(c[cfg]["solved"]) for cfg in configs) + " |")
    L_ += ["", "## By noise rate", "", "| cell | n inst | " + " | ".join(f"{LBL[c]} solved" for c in configs) + " |",
           "|---|---:|" + "---:|" * len(configs)]
    for k, c in o["by_tau"].items():
        L_.append(f"| {k} | {c['n']} | " + " | ".join(str(c[cfg]["solved"]) for cfg in configs) + " |")
    path.write_text("\n".join(L_) + "\n")


def figure(o, configs, tag):
    try:
        import matplotlib
    except ImportError:
        print("matplotlib not installed: skipping figure")
        return
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": ["Helvetica", "Arial", "DejaVu Sans"], "text.color": INK})
    keys = list(o["cells"])
    others = [c for c in configs if c != "D"]
    fig, ax = plt.subplots(figsize=(8.6, 0.62 * len(keys) * len(others) / 2 + 1.6), facecolor=SURFACE)
    style(ax)
    y, ticks, labels = 0, [], []
    for k in reversed(keys):
        c = o["cells"][k]
        for j, cfg in enumerate(reversed(others)):
            x = c[cfg]
            yy = y + j * 0.18
            ax.plot(x["ci"], [yy, yy], color=COLOR[cfg], linewidth=2, solid_capstyle="round")
            ax.scatter([x["median_log2_ratio"]], [yy], s=40, color=COLOR[cfg], edgecolors=SURFACE, linewidths=2,
                       zorder=3, label=LBL[cfg] if k == keys[-1] else None)
        ticks.append(y + 0.18 * (len(others) - 1) / 2)
        labels.append(k)
        y += 1
    ax.axvline(0, color=AXIS, linewidth=1)
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, fontsize=9)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("median log2(cost / cost of D) with 95% CI;  left = faster than D")
    h, l = ax.get_legend_handles_labels()
    ax.legend(h[::-1], l[::-1], frameon=False, fontsize=8.5, loc="upper right", ncol=len(others))
    ax.set_title("LPN: each configuration relative to native D", fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    (fplib.RESULTS / tag).mkdir(parents=True, exist_ok=True)
    fig.savefig(fplib.RESULTS / tag / "effects.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
