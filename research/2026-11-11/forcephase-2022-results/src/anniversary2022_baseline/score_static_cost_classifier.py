"""Cost-weighted static classification; all-timeout parents stay in evaluation."""

import argparse
import fcntl
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, SPLITS
from .score_static_seed_agreement import load_views, SEEDS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, load, read_csv, write_csv


def expanded_rewards(costs):
    weights = (costs.max(axis=1, keepdims=True) - costs) / 1200
    parent, action = np.nonzero(weights > 0)
    return parent, action, weights[parent, action]


def fit(x, costs, seed):
    parent, action, weight = expanded_rewards(costs)
    if not len(parent):
        return None
    model = ExtraTreesClassifier(n_estimators=256, max_depth=12, min_samples_leaf=8,
                                max_features=.8, criterion="log_loss", n_jobs=4, random_state=seed)
    model.fit(x[parent], action, sample_weight=weight)
    model.n_jobs = 1
    return model


def scores(model, x):
    if model is None:
        return np.zeros((len(x), 2))
    probability = np.zeros((len(x), 3))
    probability[:, model.classes_] = model.predict_proba(x)
    # Preference scores, not expected PAR2 or calibrated winner probabilities.
    return probability[:, 1:] - probability[:, :1]


def measured_scores(model, x):
    scores(model, x[:1])
    value, fee = np.empty((len(x), 2)), np.empty(len(x))
    for i in range(len(x)):
        tick = time.process_time()
        value[i] = scores(model, x[i:i + 1])[0]
        fee[i] = time.process_time() - tick
    return value, fee


def semantic_check():
    cost = np.array([[1., 4., 6.], [10., 2., 5.], [6., 8., 1.], [1200., 1200., 1200.]])
    parent, action, weight = expanded_rewards(cost)
    assert 3 not in parent
    reward = np.bincount(action, weights=weight, minlength=3)
    assert np.allclose(reward * 1200, cost.max(axis=1).sum() - cost.sum(axis=0))
    assert reward.argmax() == cost.sum(axis=0).argmin()
    return {"unnormalized_expected_reward_ranking": True, "tied_rows_have_zero_weight": True}


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve cost-classifier results")
        check = semantic_check()
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [r["instance_key"] for r in split] == keys
        inner = np.array([r["inner_validation"] == "True" for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        iso = np.array([r["iso_group"] for r in split])
        diagnostic = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
        assert [r["instance_key"] for r in diagnostic] == keys
        iso_fold = np.array([int(r["diagnostic_iso_fold"]) for r in diagnostic])
        inputs, _ = load_views(keys)
        inputs = {name: inputs[name] for name in args.views}
        output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
        results, fits = {}, []
        variants = ("seed0", "seed1", "seed2", "mean3", "min3")
        fold_dir = args.out / "fold_arrays"
        fold_dir.mkdir(exist_ok=True)
        for mode, count in (("coarse", 4), ("fine", 5), ("iso_diagnostic", 5)):
            folds = iso_fold if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
            groups = fine if mode == "fine" else coarse
            for view, (x, valid) in inputs.items():
                action = {v: np.zeros(len(keys), dtype=int) for v in variants}
                fee = {v: np.zeros(len(keys)) for v in variants}
                cuts = {v: [] for v in variants}
                for fold in range(count):
                    if time.monotonic() - start > 1800:
                        raise TimeoutError("cost-classifier comparison exceeded thirty minutes")
                    held = folds == fold
                    train, validation = ~held & ~inner & valid, ~held & inner & valid
                    assert not (set(iso[held]) & set(iso[train | validation]))
                    assert not (set(fine[train]) & set(fine[validation]))
                    ids = np.flatnonzero(held & valid)
                    vp, hp, hf = [], [], []
                    for j, seed in enumerate(SEEDS):
                        tick = time.process_time()
                        model = fit(x[train], costs[train], seed + fold)
                        vp.append(scores(model, x[validation]))
                        p, h = measured_scores(model, x[ids])
                        hp.append(p)
                        hf.append(h)
                        fits.append({"mode": mode, "view": view, "fold": fold, "seed": seed,
                                     "CPU_s": time.process_time() - tick,
                                     "training_parents": int(train.sum()),
                                     "positive_reward_training_parents": int((np.ptp(costs[train], axis=1) > 0).sum())})
                    vp, hp, hf = map(np.asarray, (vp, hp, hf))
                    np.savez_compressed(fold_dir / f"{mode}_{view}_{fold}.npz", validation_ids=np.flatnonzero(validation),
                                        held_ids=ids, validation_scores=vp, held_scores=hp, inference_CPU_s=hf)
                    aggregation = np.zeros(len(ids))
                    for i in range(len(ids)):
                        tick = time.process_time()
                        hp[:, i].mean(axis=0), hp[:, i].min(axis=0)
                        aggregation[i] = time.process_time() - tick
                    for variant in variants:
                        if variant.startswith("seed"):
                            j = int(variant[-1]); validation_score, held_score, paid = vp[j], hp[j], hf[j]
                        elif variant == "mean3":
                            validation_score, held_score, paid = vp.mean(axis=0), hp.mean(axis=0), hf.sum(axis=0) + aggregation
                        else:
                            validation_score, held_score, paid = vp.min(axis=0), hp.min(axis=0), hf.sum(axis=0) + aggregation
                        cut = calibrate(validation_score, costs[validation], np.zeros(validation.sum()))
                        action[variant][ids] = choose(held_score, cut)
                        if cut is not None:
                            fee[variant][ids] = paid
                        cuts[variant].append({"fold": fold, "preference_score_margin": cut})
                for variant in variants:
                    name = f"{mode}_{view}_{variant}"
                    selected = timed_cost(costs[np.arange(len(keys)), action[variant]], fee[variant], 600)
                    result = assess(costs[:, 0], selected, groups, 600)
                    result.update(cuts=cuts[variant], actions={a: int((action[variant] == i).sum()) for i, a in enumerate(ACTIONS)})
                    if mode != "fine":
                        result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    if mode == "iso_diagnostic":
                        result["within_iso_parent_interval"] = assess(costs[:, 0], selected, iso, 600)
                    results[name] = result
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[action[variant][i]]
                        row[name + "_PAR2"] = float(selected[i])
                        row[name + "_decision_CPU_s"] = float(fee[variant][i])
                    print(f"SCORED {name}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": results, "fits": fits})
        primary_view = args.views[0]
        x, valid = inputs[primary_view]
        models = [fit(x[valid & ~inner], costs[valid & ~inner], seed) for seed in SEEDS]
        validation = valid & inner
        cut = calibrate(np.min([scores(m, x[validation]) for m in models], axis=0), costs[validation], np.zeros(validation.sum()))
        joblib.dump({"models": models, "aggregation": "min_preference_score", "cut": cut,
                     "view": primary_view, "target": "unnormalized max_cost_minus_action_cost classification"},
                    args.out / "development_cost_classifier.joblib")
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": results,
              "fits": fits, "full_development_model_fits": 3, "final_score_margin": cut,
              "views": args.views, "primary_view": primary_view,
              "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start, "semantic_checks": check,
              "cost_boundary": "GBD acquisition unmeasured optimistic zero; measured model/aggregation CPU paid",
              "new_solver_calls": 0, "short_search_calls": 0, "new_CNF_feature_calls": 0,
              "source_sha256": sha(__file__), "GBD_sha256": sha(BASE), "splits_sha256": sha(SPLITS),
              "model_sha256": sha(args.out / "development_cost_classifier.joblib")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--views", nargs="+", choices=("legacy52", "linear42", "all57"),
                        default=["legacy52", "all57"])
    main(parser.parse_args())
