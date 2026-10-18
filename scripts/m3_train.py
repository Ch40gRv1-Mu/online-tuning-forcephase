#!/usr/bin/env python3
"""M3: one-shot selection (static / time-only / online) with family-grouped CV.

  scripts/m3_train.py --dataset results/m3/dataset.csv --census results/m2_census/runs.csv \
      --static results/static_features_dev.csv --out reports/m3 --policy-dir configs/policies

Decision problems (dev = train ∪ val only):
  static : before search choose D or F- from cheap CNF features (cnffeatures,
           its CPU time is added to the deployed cost);
  oneshot(K, feature set): at the first restart with >= K conflicts of a
           NATIVE prefix, keep NATIVE or switch to NEGATIVE for the rest of
           the run (track C).  Branch costs come from deterministic replays.
Learning is cost-sensitive: label = alternative cheaper, weight = |cost
difference| (PAR2 seconds); both-timeout pairs get weight 0 (censored).
Model families: decision trees (depth <= 3) and L2 logistic regression.
Evaluation: nested family-grouped CV (outer 5 folds, inner 4 folds choose
hyperparameters); out-of-fold decisions give the deployed PAR2 of the
procedure.  Bootstrap CIs resample family groups.
"""

import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.tree import DecisionTreeClassifier  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis"))
import fpstats as fs  # noqa: E402

T = 300.0
FOLD_SEED = 7
STATIC = ["s_log_vars", "s_log_clauses", "s_cv_ratio", "s_mean_len", "s_unit_frac", "s_bin_frac",
          "s_ter_frac", "s_pos_frac", "s_horn_frac", "s_antihorn_frac"]
TIME_ONLY = ["r_time", "r_log_conflicts", "r_stable"]
R_GROUP = ["r_time", "r_log_conflicts", "r_stable", "r_rephase_due", "c_stable_frac", "c_rephases",
           "c_conf_per_sec"]
P_GROUP = ["c_neg_dec_frac", "c_native_pos_frac", "w_neg_dec_frac", "w_native_pos_frac", "x_saved_neg_frac",
           "x_saved_flip_frac", "x_target_set_frac", "x_target_neg_frac", "c_target_src_frac"]
Q_GROUP = ["c_glue_mean", "c_glue_low_frac", "c_size_mean", "c_minsize_mean", "w_glue_mean", "w_glue_low_frac",
           "x_glue_fast", "x_glue_slow", "x_glue_ratio", "c_units_per_kconf", "c_bin_per_kconf"]
T_GROUP = ["c_dec_per_conf", "c_props_per_dec", "c_ticks_per_conf", "c_backjump_mean", "c_chrono_frac",
           "c_restarts_per_kconf", "c_reuse_frac", "x_trail_frac", "x_trail_ratio", "x_jump_avg", "x_level_avg",
           "x_best_frac", "x_target_frac", "x_active_frac", "x_irr_per_var", "x_red_per_irr"]
FEATURE_SETS = {
    "time": TIME_ONLY,
    "C+R": STATIC + R_GROUP,
    "C+R+P": STATIC + R_GROUP + P_GROUP,
    "C+R+Q": STATIC + R_GROUP + Q_GROUP,
    "C+R+T": STATIC + R_GROUP + T_GROUP,
    "all": STATIC + R_GROUP + P_GROUP + Q_GROUP + T_GROUP,
}
GRID = [("tree", {"max_depth": d, "min_samples_leaf": m}) for d in (1, 2, 3) for m in (10, 30)] + \
       [("logit", {"C": c}) for c in (0.1, 1.0)]


def make_model(kind, params):
    if kind == "tree":
        return DecisionTreeClassifier(random_state=0, **params)
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(C=params["C"], max_iter=2000))


def fit_predict(kind, params, X, y, w, Xte):
    """Return P(alternative better) for Xte; constant if training is degenerate."""
    m = w > 0
    if m.sum() < 5 or len(np.unique(y[m])) < 2:
        frac = (w[m] * y[m]).sum() / max(w[m].sum(), 1e-9) if m.any() else 0.0
        return np.full(len(Xte), frac), None
    model = make_model(kind, params)
    if kind == "tree":
        model.fit(X[m], y[m], sample_weight=w[m])
    else:
        model.fit(X[m], y[m], logisticregression__sample_weight=w[m])
    return model.predict_proba(Xte)[:, 1], model


def group_folds(groups, k, seed):
    uniq = sorted(set(groups))
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    sizes = pd.Series(groups).value_counts()
    uniq.sort(key=lambda g: -sizes[g])  # big first, shuffled ties
    load = [0] * k
    fold_of = {}
    for g in uniq:
        f = int(np.argmin(load))
        fold_of[g] = f
        load[f] += sizes[g]
    return np.array([fold_of[g] for g in groups])


def deployed_cost(choose_alt, cost_base, cost_alt):
    return np.where(choose_alt, cost_alt, cost_base)


def nested_cv(X, y, w, cb, ca, groups, outer, seed=0, shuffle_labels=False):
    """Out-of-fold P(alt) with inner-CV hyperparameter choice per outer fold."""
    n = len(y)
    proba = np.full(n, np.nan)
    chosen = []
    rng = np.random.default_rng(seed)
    for f in sorted(set(outer)):
        tr, te = outer != f, outer == f
        ytr = y[tr].copy()
        if shuffle_labels:  # control: permute (label, weight) pairs within the training folds
            perm = rng.permutation(tr.sum())
            ytr = ytr[perm]
            wtr = w[tr][perm]
        else:
            wtr = w[tr]
        inner = group_folds(groups[tr], 4, seed + 100 + f)
        best, best_cost = None, np.inf
        for kind, params in GRID:
            p_in = np.full(tr.sum(), np.nan)
            for g in range(4):
                itr, ite = inner != g, inner == g
                p_in[ite], _ = fit_predict(kind, params, X[tr][itr], ytr[itr], wtr[itr], X[tr][ite])
            cost = deployed_cost(p_in > 0.5, cb[tr], ca[tr]).mean()
            if cost < best_cost - 1e-9:
                best, best_cost = (kind, params), cost
        proba[te], _ = fit_predict(best[0], best[1], X[tr], ytr, wtr, X[te])
        chosen.append({"fold": int(f), "kind": best[0], "params": best[1], "inner_cost": best_cost})
    return proba, chosen


def select_full(X, y, w, cb, ca, groups, seed=0):
    folds = group_folds(groups, 5, seed + 999)
    best, best_cost = None, np.inf
    for kind, params in GRID:
        p = np.full(len(y), np.nan)
        for g in range(5):
            tr, te = folds != g, folds == g
            p[te], _ = fit_predict(kind, params, X[tr], y[tr], w[tr], X[te])
        cost = deployed_cost(p > 0.5, cb, ca).mean()
        if cost < best_cost - 1e-9:
            best, best_cost = (kind, params), cost
    _, model = fit_predict(best[0], best[1], X, y, w, X)
    return best, best_cost, model


def export_tree(model, features, path, K, comment):
    t = model.tree_
    lines = []

    def rec(i):
        if t.children_left[i] == -1:
            v = t.value[i][0]
            return f"{v[1] / v.sum():.6g}"
        f = features[t.feature[i]]
        miss = "L" if getattr(t, "missing_go_to_left", np.ones(t.node_count))[i] else "R"
        return f"( {f} {t.threshold[i]:.9g} {miss} {rec(t.children_left[i])} {rec(t.children_right[i])} )"
    body = rec(0)
    lines += [f"# {comment}", "fpc-policy 1", "type oneshot", f"prefix {K}", "threshold 0.5", f"model tree {body}"]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return body


def export_logit(model, features, path, K, comment):
    imp, sc, lr = model.named_steps["simpleimputer"], model.named_steps["standardscaler"], \
        model.named_steps["logisticregression"]
    terms = []
    for j, name in enumerate(features):
        scale = sc.scale_[j] if sc.scale_[j] > 0 else 1.0
        terms.append(f"{name} {sc.mean_[j]:.9g} {scale:.9g} {imp.statistics_[j]:.9g} {lr.coef_[0][j]:.9g}")
    lines = [f"# {comment}", "fpc-policy 1", "type oneshot", f"prefix {K}", "threshold 0.5",
             f"model linear {lr.intercept_[0]:.9g} {len(features)} " + " ".join(terms)]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def export_json(model, kind, features, path, meta):
    """Frozen model as JSON (tree nodes or standardized logistic terms)."""
    obj = dict(meta, kind=kind, features=features)
    if kind == "tree":
        t = model.tree_
        miss = getattr(t, "missing_go_to_left", np.ones(t.node_count))
        nodes = []
        for i in range(t.node_count):
            v = t.value[i][0]
            nodes.append({"feature": features[t.feature[i]] if t.children_left[i] != -1 else None,
                          "threshold": float(t.threshold[i]), "missing_left": bool(miss[i]),
                          "left": int(t.children_left[i]), "right": int(t.children_right[i]),
                          "value": float(v[1] / v.sum())})
        obj["nodes"] = nodes
    else:
        imp, sc, lr = (model.named_steps["simpleimputer"], model.named_steps["standardscaler"],
                       model.named_steps["logisticregression"])
        obj["bias"] = float(lr.intercept_[0])
        obj["terms"] = [{"feature": f, "mean": float(sc.mean_[j]), "scale": float(sc.scale_[j] or 1.0),
                         "impute": float(imp.statistics_[j]), "weight": float(lr.coef_[0][j])}
                        for j, f in enumerate(features)]
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


def eval_json(obj, X):
    """Score rows of X (dict-like per feature) with an exported model; mirrors fpcontrol.cpp."""
    out = []
    for row in X:
        if obj["kind"] == "tree":
            i = 0
            nodes = obj["nodes"]
            while nodes[i]["left"] != -1:
                x = row[obj["features"].index(nodes[i]["feature"])]
                go_left = nodes[i]["missing_left"] if np.isnan(x) else x <= nodes[i]["threshold"]
                i = nodes[i]["left"] if go_left else nodes[i]["right"]
            out.append(nodes[i]["value"])
        else:
            z = obj["bias"]
            for j, t in enumerate(obj["terms"]):
                x = row[j]
                x = t["impute"] if np.isnan(x) else x
                z += t["weight"] * (x - t["mean"]) / t["scale"]
            out.append(1 / (1 + np.exp(-z)))
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--census", required=True)
    ap.add_argument("--static", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--policy-dir", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "figures"), exist_ok=True)
    os.makedirs(a.policy_dir, exist_ok=True)
    ds = pd.read_csv(a.dataset, dtype={"instance": str})
    census = fs.load_runs(a.census)
    census = census[census.split.isin(["train", "val"])]
    static = pd.read_csv(a.static, dtype={"instance": str}).set_index("instance")
    wide = fs.wide_cost(census, ["D", "Iminus", "Fminus", "Fplus"])
    meta = fs.instance_meta(census)
    insts = wide.index.values
    groups = meta.loc[insts, "family_group"].values
    outer = group_folds(groups, 5, FOLD_SEED)
    pd.DataFrame({"instance": insts, "family_group": groups, "fold": outer}).to_csv(
        os.path.join(a.out, "folds.csv"), index=False)
    fold_of = dict(zip(insts, outer))
    cD = wide.loc[insts, "D"].values
    cF = wide.loc[insts, "Fminus"].values
    results = []   # one row per evaluated selector
    decisions = {}  # name -> per-instance deployed cost
    out = ["# M3 tables (generated by scripts/m3_train.py)\n",
           f"Dev instances: {len(insts)}, family groups: {len(set(groups))}, outer folds: 5 (group-balanced, seed {FOLD_SEED}).\n"]

    cI = wide.loc[insts, "Iminus"].values

    def record(name, cost, extra=None):
        decisions[name] = cost
        p, lo, hi = fs.paired_relative_ci(cD, cost, groups)
        q, qlo, qhi = fs.paired_relative_ci(cI, cost, groups)
        r = {"selector": name, "PAR2": cost.mean(), "solved": int((cost < 2 * T).sum()),
             "red_vs_D_%": 100 * p, "CI_lo_%": 100 * lo, "CI_hi_%": 100 * hi,
             "red_vs_I-_%": 100 * q, "I-CI_lo_%": 100 * qlo, "I-CI_hi_%": 100 * qhi}
        if extra:
            r.update(extra)
        results.append(r)

    record("D (always native)", cD)
    record("I- (validation-SBS)", cI)
    record("F- (always negative)", cF)
    record("VBS-static D/F- (oracle)", np.minimum(cD, cF))
    record("VBS-static I-/F- (oracle)", np.minimum(cI, cF))

    # ---------- static selector (D vs F- before search), cost includes feature time
    X = static.loc[insts, STATIC].values.astype(float)
    feat_cpu = static.loc[insts, "cpu_time"].values.astype(float)

    def with_feat(c):
        tot = c + feat_cpu
        return np.where((c < 2 * T) & (tot <= T), tot, 2 * T)
    cbS, caS = with_feat(cD), with_feat(cF)
    y = (cF < cD).astype(int)
    w = np.abs(cF - cD)
    proba, chosen = nested_cv(X, y, w, cbS, caS, groups, outer)
    cost = deployed_cost(proba > 0.5, cbS, caS)
    auc = roc_auc_score(y[w > 0], proba[w > 0], sample_weight=w[w > 0]) if len(set(y[w > 0])) > 1 else np.nan
    record("static selector D/F- (cnffeatures)", cost, {"chose_alt": int((proba > 0.5).sum()), "wAUC": auc})
    proba_s, _ = nested_cv(X, y, w, cbS, caS, groups, outer, shuffle_labels=True)
    record("static selector, shuffled labels", deployed_cost(proba_s > 0.5, cbS, caS),
           {"chose_alt": int((proba_s > 0.5).sum())})
    cbI = with_feat(cI)
    yI, wI = (cF < cI).astype(int), np.abs(cF - cI)
    probaI, _ = nested_cv(X, yI, wI, cbI, caS, groups, outer)
    record("static selector I-/F- (cnffeatures)", deployed_cost(probaI > 0.5, cbI, caS),
           {"chose_alt": int((probaI > 0.5).sum())})
    static_best, static_cv, static_model = select_full(X, y, w, cbS, caS, groups)
    for tag, (yy, ww, cb_, ca_, base) in {"DF": (y, w, cbS, caS, "D"), "IF": (yI, wI, cbI, caS, "Iminus")}.items():
        best_s, cv_s, model_s = select_full(X, yy, ww, cb_, ca_, groups)
        if model_s is not None:
            path = os.path.join(a.policy_dir, f"static_selector_{tag}.json")
            export_json(model_s, best_s[0], STATIC, path,
                        {"name": f"static selector {base}/Fminus", "a": base, "b": "Fminus",
                         "rule": "choose b iff score > 0.5", "params": best_s[1], "grouped_cv_PAR2": cv_s,
                         "generated_by": "scripts/m3_train.py (refit on all dev)"})
            chk = eval_json(json.load(open(path)), X)
            assert np.array_equal(chk > 0.5, model_s.predict_proba(X)[:, 1] > 0.5), "static export mismatch"
    if static_model is not None and static_best[0] == "tree":
        from sklearn.tree import export_text
        static_rule = export_text(static_model, feature_names=STATIC)
    else:
        static_rule = str(static_best)

    # ---------- one-shot online selection at K
    oneshot_summary = []
    final_candidates = []
    combos = sorted({(r.direction, r.K) for r in ds.itertuples() if r.direction in ("nat2neg", "in2neg")
                     and r.track == "C"})
    for direction, K in combos:
        pre = "" if direction == "nat2neg" else "I- prefix "
        d = ds[(ds.K == K) & (ds.track == "C") & (ds.direction == direction)].set_index("instance")
        d = d.reindex(insts)
        has = (d.has_decision == 1) & (d.alt_run == 1)
        cb = d.cost_base.values.astype(float)
        ca = np.where(has, d.cost_alt.values.astype(float), cb)
        bad_digest = int(((d.digest_ok == 0) & has).sum())
        missing = int(((d.status_alt == "missing") & (d.has_decision == 1)).sum())
        record(f"{pre}oracle one-shot @K={K}", np.minimum(cb, ca), {"decision_points": int(has.sum())})
        record(f"{pre}always switch to F- @K={K}", ca, {"decision_points": int(has.sum())})
        yK = (ca < cb).astype(int)
        wK = np.where(has, np.abs(ca - cb), 0.0)
        oneshot_summary.append({"prefix": direction, "K": K, "decision_points": int(has.sum()), "digest_mismatch": bad_digest,
                                "missing_alt": missing,
                                "alt_better": int(((ca < cb) & has).sum()), "base_better": int(((cb < ca) & has).sum()),
                                "both_timeout": int(((ca >= 2 * T) & (cb >= 2 * T) & has).sum()),
                                "PAR2_base": cb.mean(), "PAR2_always_alt": ca.mean(),
                                "PAR2_oracle": np.minimum(cb, ca).mean()})
        for fname, cols in FEATURE_SETS.items():
            Xk = d[["f_" + c for c in cols]].values.astype(float)
            proba, chosen = nested_cv(Xk, yK, wK, cb, ca, groups, outer)
            proba = np.where(has, proba, 0.0)
            cost = deployed_cost(proba > 0.5, cb, ca)
            m = wK > 0
            auc = roc_auc_score(yK[m], proba[m], sample_weight=wK[m]) if len(set(yK[m])) > 1 else np.nan
            regret = (cost - np.minimum(cb, ca)).mean()
            name = f"{pre}one-shot @K={K} [{fname}]"
            record(name, cost, {"chose_alt": int((proba > 0.5).sum()), "decision_points": int(has.sum()),
                                "wAUC": auc, "regret": regret,
                                "models": ";".join(f"{c['kind']}{c['params']}" for c in chosen)})
            final_candidates.append((name, K, fname, cols, Xk, yK, wK, cb, ca, cost.mean(), direction))
            if fname in ("all", "time"):
                ps, _ = nested_cv(Xk, yK, wK, cb, ca, groups, outer, shuffle_labels=True)
                ps = np.where(has, ps, 0.0)
                record(f"{name} shuffled labels", deployed_cost(ps > 0.5, cb, ca),
                       {"chose_alt": int((ps > 0.5).sum())})

    res = pd.DataFrame(results)
    out.append("\n## Deployed PAR2 of selectors (out-of-fold, dev)\n")
    out.append(fs.md_table(res, "{:.2f}"))
    out.append("\n\nred_vs_D_% > 0: lower PAR2 than always-D. CI: 95% family-group cluster bootstrap over the OOF "
               "per-instance costs (does not include model-refit variability). wAUC: cost-weighted AUC of the "
               "out-of-fold scores on decision points with non-zero weight.\n")
    out.append("\n## One-shot decision points per K (track C, NATIVE prefix → NEGATIVE)\n")
    out.append(fs.md_table(pd.DataFrame(oneshot_summary), "{:.2f}"))
    out.append(f"\n\n## Static selector refit on all dev\n\nchosen: {static_best}, CV PAR2 {static_cv:.2f}\n\n```\n{static_rule}\n```\n")

    # ---------- freeze candidates: best online and best time-only per CV, exported as policy files
    exports = []
    to_export = []
    for direction in ("nat2neg", "in2neg"):
        cands = [c for c in final_candidates if c[-1] == direction]
        if not cands:
            continue
        best = min(cands, key=lambda c: c[-2])
        to_export += [best] + [c for c in cands if c[2] == "time" and c[1] == best[1] and c is not best]
    for cand in to_export:
        name, K, fname, cols, Xk, yK, wK, cb, ca, cvcost, direction = cand
        (kind, params), cv2, model = select_full(Xk, yK, wK, cb, ca, groups)
        tag = f"m3_oneshot_{'D' if direction == 'nat2neg' else 'Iminus'}_K{K}_{fname.replace('+', '')}"
        path = os.path.join(a.policy_dir, tag + ".txt")
        deploy = "--fpc=4" if direction == "nat2neg" else "--fpc=4 --fpca0=2"
        comment = (f"{name}; refit on all dev ({kind} {params}); grouped-CV PAR2 {cv2:.2f}; "
                   f"deploy with: {deploy} (FPC_POLICY=<this file>); generated by scripts/m3_train.py")
        if model is None:
            with open(path, "w") as f:
                f.write(f"# {comment}\nfpc-policy 1\ntype oneshot\nprefix {K}\nthreshold 0.5\nmodel tree 0\n")
            body = "0 (degenerate)"
        elif kind == "tree":
            body = export_tree(model, cols, path, K, comment)
        else:
            export_logit(model, cols, path, K, comment)
            body = "linear"
        exports.append({"name": name, "prefix": direction, "policy_file": os.path.relpath(path), "model": f"{kind} {params}",
                        "cv_PAR2": cv2, "outer_cv_PAR2": cvcost, "tree": body})
    out.append("\n## Exported candidate policies (refit on all dev; not yet evaluated on test)\n")
    out.append(fs.md_table(pd.DataFrame(exports), "{:.2f}"))

    # ---------- figure: PAR2 of selectors
    plot = res[~res.selector.str.contains("shuffled")].copy()
    fig, ax = plt.subplots(figsize=(7.0, 0.26 * len(plot) + 1.0), dpi=150)
    yy = np.arange(len(plot))[::-1]
    colors = [fs.COLORS["Fminus"] if "oracle" in s else fs.COLORS["D"] for s in plot.selector]
    ax.barh(yy, plot.PAR2, color=colors, height=0.6)
    ax.set_yticks(yy)
    ax.set_yticklabels(plot.selector, fontsize=7)
    ax.axvline(res.loc[0, "PAR2"], color=fs.INK2, linewidth=0.8, linestyle="--")
    ax.set_xlabel("mean PAR2 over dev instances (s), out-of-fold; orange = oracle (not deployable)")
    fs.style_axes(ax)
    ax.set_xlim(min(plot.PAR2) * 0.9, max(plot.PAR2) * 1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "figures", "selectors_par2.png"))
    plt.close(fig)

    res.to_csv(os.path.join(a.out, "selectors.csv"), index=False)
    pd.DataFrame(decisions, index=insts).to_csv(os.path.join(a.out, "oof_costs.csv"))
    with open(os.path.join(a.out, "tables.md"), "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
