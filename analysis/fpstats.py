"""Shared analysis helpers for online-tuning-forcephase (numpy/pandas).

All statistics are computed from the run CSVs written by scripts/collect.py.
Conventions:
  * cost of a run = CPU seconds if status == 'solved' (verified), else 2T;
  * per-instance cost of a configuration = mean over seeds/repeats;
  * instances are clustered by 'family_group' for bootstrap intervals.
"""

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Categorical slots from the dataviz reference palette (light mode), fixed
# per entity so a configuration keeps its colour in every figure.
COLORS = {
    "D": "#2a78d6", "Fminus": "#eb6834", "Iminus": "#1baf7a", "Fplus": "#eda100",
    "D_noR": "#e87ba4", "Iminus_noR": "#008300", "S_saved": "#6250d6", "P_neg": "#e34948",
}
LABELS = {"D": "D (stock)", "Fminus": "F− (forced neg.)", "Iminus": "I− (init neg.)",
          "Fplus": "F+ (forced pos.)", "D_noR": "D/no-R", "Iminus_noR": "I−/no-R",
          "S_saved": "S (pure saved)", "P_neg": "P− (decision-only neg.)"}
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"


def load_runs(path):
    df = pd.read_csv(path, dtype={"instance": str})
    return df


def wide_cost(df, configs=None, value="par2"):
    """Instance x config table of mean cost (over seeds and repeats)."""
    d = df if configs is None else df[df.config.isin(configs)]
    return d.pivot_table(index="instance", columns="config", values=value, aggfunc="mean")


def wide_solved(df, configs=None):
    d = df if configs is None else df[df.config.isin(configs)]
    s = d.assign(solved=(d.status == "solved").astype(float))
    return s.pivot_table(index="instance", columns="config", values="solved", aggfunc="mean")


def instance_meta(df):
    cols = ["instance", "family", "family_group", "split", "gbd_result", "temporal_tag"]
    return df[cols].drop_duplicates("instance").set_index("instance")


def observed_answer(df):
    """SAT/UNSAT per instance from verified runs; flags conflicting answers."""
    s = df[df.status == "solved"].groupby("instance").result.agg(lambda x: set(x))
    conflicts = [i for i, v in s.items() if len(v) > 1]
    ans = s.map(lambda v: next(iter(v)) if len(v) == 1 else "CONFLICT")
    return ans, conflicts


def summary_table(df, configs, T):
    rows = []
    meta = instance_meta(df)
    ans, _ = observed_answer(df)
    for c in configs:
        d = df[df.config == c]
        per = d.groupby("instance").agg(par2=("par2", "mean"),
                                        solved=("status", lambda x: (x == "solved").mean()))
        st = d.status.value_counts()
        res = d[d.status == "solved"].result.value_counts()
        rows.append({
            "config": c, "instances": per.shape[0], "runs": len(d),
            "solved": round(per.solved.sum(), 2),
            "solved_SAT": int(res.get("SAT", 0)), "solved_UNSAT": int(res.get("UNSAT", 0)),
            "PAR2": per.par2.mean(),
            "timeout": int(st.get("timeout", 0)), "memout": int(st.get("memout", 0)),
            "crash/error": int(st.get("crash", 0) + st.get("error", 0)),
            "wrong": int(st.get("wrong", 0)), "unverified": int(st.get("unverified", 0)),
            "missing": int(st.get("missing", 0)),
        })
    return pd.DataFrame(rows)


def cluster_bootstrap(values, groups, stat=np.mean, B=10000, seed=12345):
    """Percentile CI of stat(values) resampling whole groups (clusters)."""
    values = np.asarray(values, float)
    groups = np.asarray(groups)
    uniq, inv = np.unique(groups, return_inverse=True)
    idx_by_g = [np.flatnonzero(inv == k) for k in range(len(uniq))]
    rng = np.random.default_rng(seed)
    G = len(uniq)
    out = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, G, G)
        idx = np.concatenate([idx_by_g[k] for k in pick])
        out[b] = stat(values[idx])
    return stat(values), np.percentile(out, 2.5), np.percentile(out, 97.5)


def instance_bootstrap(values, stat=np.mean, B=10000, seed=12345):
    values = np.asarray(values, float)
    rng = np.random.default_rng(seed)
    n = len(values)
    out = np.array([stat(values[rng.integers(0, n, n)]) for _ in range(B)])
    return stat(values), np.percentile(out, 2.5), np.percentile(out, 97.5)


def paired_relative_ci(cost_a, cost_b, groups, B=10000, seed=12345):
    """Relative PAR2 reduction of b vs a, 1 - mean(b)/mean(a), with cluster CI."""
    a = np.asarray(cost_a, float)
    b = np.asarray(cost_b, float)
    groups = np.asarray(groups)
    uniq, inv = np.unique(groups, return_inverse=True)
    idx_by_g = [np.flatnonzero(inv == k) for k in range(len(uniq))]
    rng = np.random.default_rng(seed)
    G = len(uniq)
    out = np.empty(B)
    for k in range(B):
        pick = rng.integers(0, G, G)
        idx = np.concatenate([idx_by_g[g] for g in pick])
        out[k] = 1 - b[idx].mean() / a[idx].mean()
    point = 1 - b.mean() / a.mean()
    return point, np.percentile(out, 2.5), np.percentile(out, 97.5)


def win_loss(cost_a, cost_b, T, factor=1.0):
    """Counts of b better/worse than a; both-timeout instances are censored ties."""
    a = np.asarray(cost_a, float)
    b = np.asarray(cost_b, float)
    both_to = (a >= 2 * T) & (b >= 2 * T)
    better = (~both_to) & (b * factor < a)
    worse = (~both_to) & (a * factor < b)
    return {"b_better": int(better.sum()), "b_worse": int(worse.sum()),
            "tie_or_within_factor": int((~both_to).sum() - better.sum() - worse.sum()),
            "both_timeout": int(both_to.sum())}


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.title.set_color(INK)


def md_table(df, floatfmt="{:.1f}"):
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                cells.append(floatfmt.format(v) if np.isfinite(v) else "–")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
