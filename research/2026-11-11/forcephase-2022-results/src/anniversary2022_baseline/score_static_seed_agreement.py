"""Frozen seed agreement and computable-statistics ablations on 2022 labels."""

import argparse
import fcntl
from pathlib import Path
import sqlite3
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, measured_gains, SPLITS
from .score_static_learnability import fit
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, ROOT, load, read_csv, write_csv


SEEDS = (20261111, 20261112, 20261113)


def load_views(keys):
    stat = ("mean", "variance", "min", "max", "entropy")
    prefixes = ("balancecls", "balancevars", "vcg_vdegree", "hornvars", "invhornvars",
                "vcg_cdegree", "vg_degree", "cg_degree")
    fields = ["variables", "clauses", *[f"cls{i}" for i in range(1, 10)], "cls10p",
              "positive", "negative", "horn", "invhorn"]
    fields.extend(p + "_" + s for p in prefixes for s in stat)
    with sqlite3.connect("file:" + str(BASE) + "?mode=ro", uri=True) as db:
        rows = {key: values for key, *values in db.execute("select hash," + ",".join(fields) + " from features")}
    raw = np.array([rows[key] for key in keys], dtype=float)
    valid = np.isfinite(raw).all(axis=1) & (raw >= 0).all(axis=1)
    safe = np.where(np.isfinite(raw), np.maximum(raw, 0), 0)
    n, m = safe[:, 0], safe[:, 1]
    widths = safe[:, 2:12] / np.maximum(m[:, None], 1)
    empty = np.maximum(0, 1 - widths.sum(axis=1))[:, None]
    basic = np.c_[np.log1p(n), np.log1p(m), empty, widths,
                  safe[:, 12:16] / np.maximum(m[:, None], 1), safe[:, 16:26]]
    assert basic.shape[1] == 27

    def degree_summary(prefix):
        k = 16 + 5 * prefixes.index(prefix)
        mean, variance, minimum, maximum, entropy = safe[:, k:k + 5].T
        return np.c_[np.log1p(mean), np.log1p(variance / np.maximum(mean ** 2, 1e-12)),
                     minimum / np.maximum(mean, 1e-12), np.log1p(maximum / np.maximum(mean, 1e-12)), entropy]

    linear42 = np.c_[basic, *[degree_summary(p) for p in ("vcg_vdegree", "hornvars", "invhornvars")]]
    all57 = np.c_[linear42, *[degree_summary(p) for p in ("vcg_cdegree", "vg_degree", "cg_degree")]]
    with np.load(DATA / "mechanism_R06_features_20261111/features.npz") as archive:
        assert archive["keys"].tolist() == keys
        legacy, legacy_valid = archive["base_plus_tail52"], archive["valid"]
    return {"legacy52": (legacy, legacy_valid), "linear42": (linear42, valid), "all57": (all57, valid)}, fields


def run(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve frozen seed-agreement results")
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [row["instance_key"] for row in split] == keys
        inner = np.array([r["inner_validation"] == "True" for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        iso = np.array([r["iso_group"] for r in split])
        # Reuse the already frozen R11 diagnostic assignment exactly.
        iso_rows = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
        assert [r["instance_key"] for r in iso_rows] == keys
        iso_fold = np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows])
        views, fields = load_views(keys)
        output = [{"instance_key": key, "D_PAR2": float(costs[i, 0])} for i, key in enumerate(keys)]
        scores, fits = {}, []
        variants = ("seed0", "seed1", "seed2", "mean3", "min3")
        for mode, count in (("coarse", 4), ("fine", 5), ("iso_diagnostic", 5)):
            folds = iso_fold if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
            groups = fine if mode == "fine" else coarse
            for view, (x, valid) in views.items():
                actions = {v: np.zeros(len(keys), dtype=int) for v in variants}
                fees = {v: np.zeros(len(keys)) for v in variants}
                cuts = {v: [] for v in variants}
                for fold in range(count):
                    if time.monotonic() - start > 1800:
                        raise TimeoutError("seed agreement exceeded thirty minutes")
                    held = folds == fold
                    train, val = ~held & ~inner & valid, ~held & inner & valid
                    assert not (set(iso[held]) & set(iso[train | val]))
                    assert not (set(fine[train]) & set(fine[val]))
                    ids = np.flatnonzero(held & valid)
                    validation, prediction, inference = [], [], []
                    for j, seed in enumerate(SEEDS):
                        began = time.process_time()
                        model = fit("expressive", x[train], costs[train], seed + fold)
                        validation.append(gains(model, x[val], "trees_relative"))
                        p, h = measured_gains(model, x[ids], "trees_relative")
                        prediction.append(p)
                        inference.append(h)
                        fits.append({"mode": mode, "view": view, "fold": fold, "seed": seed,
                                     "CPU_s": time.process_time() - began})
                    validation, prediction, inference = map(np.asarray, (validation, prediction, inference))
                    mean_prediction, min_prediction = prediction.mean(axis=0), prediction.min(axis=0)
                    joint_inference = inference.sum(axis=0)
                    # Charge both aggregation operations to either ensemble,
                    # a conservative measured supplement to all three queries.
                    aggregation = np.zeros(len(ids))
                    for i in range(len(ids)):
                        tick = time.process_time()
                        prediction[:, i].mean(axis=0), prediction[:, i].min(axis=0)
                        aggregation[i] = time.process_time() - tick
                    for variant in variants:
                        if variant.startswith("seed"):
                            j = int(variant[-1])
                            vp, hp, fee = validation[j], prediction[j], inference[j]
                        elif variant == "mean3":
                            vp, hp, fee = validation.mean(axis=0), mean_prediction, joint_inference + aggregation
                        else:
                            vp, hp, fee = validation.min(axis=0), min_prediction, joint_inference + aggregation
                        cut = calibrate(vp, costs[val], np.zeros(val.sum()))
                        actions[variant][ids] = choose(hp, cut)
                        if cut is not None:
                            fees[variant][ids] = fee
                        cuts[variant].append({"fold": fold, "margin_PAR2_s": cut})
                for variant in variants:
                    name = f"{mode}_{view}_{variant}"
                    action = actions[variant]
                    selected = timed_cost(costs[np.arange(len(keys)), action], fees[variant], 600)
                    score = assess(costs[:, 0], selected, groups, 600)
                    score.update(cuts=cuts[variant], actions={a: int((action == i).sum()) for i, a in enumerate(ACTIONS)})
                    if mode != "fine":
                        score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    if mode == "iso_diagnostic":
                        score["within_iso_parent_interval"] = assess(costs[:, 0], selected, iso, 600)
                    scores[name] = score
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[action[i]]
                        row[name + "_PAR2"] = float(selected[i])
                        row[name + "_decision_CPU_s"] = float(fees[variant][i])
                    print(f"SCORED {name}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
        # Prespecified primary agreement policy; native sklearn estimators
        # avoid requiring a custom __main__ class when the file is loaded.
        x, valid = views["legacy52"]
        models = [fit("expressive", x[valid & ~inner], costs[valid & ~inner], seed) for seed in SEEDS]
        validation = valid & inner
        prediction = np.min([gains(m, x[validation], "trees_relative") for m in models], axis=0)
        cut = calibrate(prediction, costs[validation], np.zeros(validation.sum()))
        joblib.dump({"models": models, "aggregation": "min", "cut": cut, "view": "legacy52",
                     "seeds": SEEDS, "feature_cost": "unmeasured acquisition; optimistic only"},
                    args.out / "development_seed_agreement.joblib")
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
              "fits": fits, "full_development_model_fits": 3, "final_margin_PAR2_s": cut,
              "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "view_coverage": {n: int(v.sum()) for n, (_, v) in views.items()}, "GBD_fields": fields,
              "cost_boundary": "All GBD acquisition unmeasured optimistic zero; actual per-query model and aggregation CPU paid",
              "new_solver_calls": 0, "short_search_calls": 0, "new_CNF_feature_calls": 0,
              "source_sha256": sha(__file__), "GBD_sha256": sha(BASE), "splits_sha256": sha(SPLITS),
              "GBD_source_sha256": sha(ROOT / "work/default_D_source_20261111/GBD_CNFBaseFeatures.cc"),
              "model_sha256": sha(args.out / "development_seed_agreement.joblib")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args())
