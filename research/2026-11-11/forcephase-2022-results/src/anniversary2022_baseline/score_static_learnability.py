"""Distinguish static representation capacity from structural distribution shift."""

import argparse
import fcntl
import hashlib
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, measured_gains, SPLITS
from .score_static_boosting import views
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def fit(capacity, x, costs, seed):
    if capacity == "compact":
        trees, depth, leaf = 64, 6, 32
    else:
        trees, depth, leaf = 256, 12, 4
    model = ExtraTreesRegressor(n_estimators=trees, max_depth=depth, min_samples_leaf=leaf,
                                max_features=.8, n_jobs=4, random_state=seed)
    model.fit(x, (costs[:, :1] - costs[:, 1:]) / 1200)
    model.n_jobs = 1
    return model


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve the existing learnability experiment")
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [r["instance_key"] for r in split] == keys
        iso = np.array([r["iso_group"] for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        inner = np.array([r["inner_validation"] == "True" for r in split])
        iso_fold = np.array([int(hashlib.sha256(("static_learnability_iso_v1:" + g).encode()).hexdigest(), 16) % 5
                             for g in iso])
        inputs, sources = views(keys)
        output = [{"instance_key": k, "D_PAR2": float(costs[i, 0]), "diagnostic_iso_fold": int(iso_fold[i])}
                  for i, k in enumerate(keys)]
        scores, fits = {}, []
        for regime, count in (("coarse", 4), ("fine", 5), ("iso_diagnostic", 5)):
            folds = iso_fold if regime == "iso_diagnostic" else np.array([int(r[regime + "_fold"]) for r in split])
            groups = fine if regime == "fine" else coarse
            for view, (x, valid, acquisition) in inputs.items():
                for capacity in ("compact", "expressive"):
                    name = f"{regime}_{view}_{capacity}"
                    action = np.zeros(len(keys), dtype=int)
                    raw_action = np.zeros(len(keys), dtype=int)
                    fee, raw_fee = np.zeros(len(keys)), np.zeros(len(keys))
                    free_action, free_fee = np.zeros(len(keys), dtype=int), np.zeros(len(keys))
                    cuts = []
                    for fold in range(count):
                        if time.monotonic() - start > 1200:
                            raise TimeoutError("learnability comparison exceeded twenty minutes")
                        held = folds == fold
                        train, validation = ~held & ~inner & valid, ~held & inner & valid
                        assert not (set(iso[held]) & set(iso[train | validation]))
                        assert not (set(fine[train]) & set(fine[validation]))
                        begin = time.process_time()
                        model = fit(capacity, x[train], costs[train], 20261111 + fold)
                        prediction = gains(model, x[validation], "trees_relative")
                        cut = calibrate(prediction, costs[validation], acquisition[validation])
                        free_cut = calibrate(prediction, costs[validation], np.zeros(validation.sum()))
                        ids = np.flatnonzero(held & valid)
                        prediction, inference = measured_gains(model, x[ids], "trees_relative")
                        action[ids], raw_action[ids] = choose(prediction, cut), choose(prediction, 0)
                        raw_fee[ids] = acquisition[ids] + inference
                        if cut is not None:
                            fee[ids] = acquisition[ids] + inference
                        free_action[ids] = choose(prediction, free_cut)
                        if free_cut is not None:
                            free_fee[ids] = inference
                        cuts.append({"fold": fold, "margin_PAR2_s": cut, "free_margin_PAR2_s": free_cut})
                        fits.append({"name": name, "fold": fold, "train": int(train.sum()),
                                     "validation": int(validation.sum()), "CPU_s": time.process_time() - begin})
                    selected = timed_cost(costs[np.arange(len(keys)), action], fee, 600)
                    raw_selected = timed_cost(costs[np.arange(len(keys)), raw_action], raw_fee, 600)
                    free_selected = timed_cost(costs[np.arange(len(keys)), free_action], free_fee, 600)
                    score = assess(costs[:, 0], selected, groups, 600)
                    score.update(cuts=cuts, actions={a: int((action == i).sum()) for i, a in enumerate(ACTIONS)},
                                 zero_margin=assess(costs[:, 0], raw_selected, groups, 600),
                                 free_features=assess(costs[:, 0], free_selected, groups, 600))
                    if regime != "fine":
                        score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    if regime == "iso_diagnostic":
                        score["within_iso_parent_interval"] = assess(costs[:, 0], selected, iso, 600)
                    scores[name] = score
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[action[i]]
                        row[name + "_PAR2"] = float(selected[i])
                        row[name + "_decision_CPU_s"] = float(fee[i])
                    write_csv(args.out / "predictions.csv", output)
                    write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                    print(f"SCORED {name}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
        # Fixed export of the expressive raw view, independent of outer rank.
        x, valid, acquisition = inputs["raw236_costed"]
        model = fit("expressive", x[valid & ~inner], costs[valid & ~inner], 20261111)
        validation = valid & inner
        cut = calibrate(gains(model, x[validation], "trees_relative"), costs[validation], acquisition[validation])
        joblib.dump({"model": model, "cut": cut, "view": "raw236_costed", "features_sha256": sources},
                    args.out / "development_expressive_predictor.joblib")
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
              "fits": fits, "full_development_model_fits": 1, "final_margin_PAR2_s": cut,
              "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "new_solver_calls": 0, "short_search_calls": 0, "new_CNF_feature_calls": 0,
              "scope": "Repeated2022 development. Iso holdouts diagnose within-regime learning, not independent confirmation or replacement of coarse transfer.",
              "source_sha256": sha(__file__), "input_feature_sha256": sources, "splits_sha256": sha(SPLITS),
              "model_sha256": sha(args.out / "development_expressive_predictor.joblib")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
