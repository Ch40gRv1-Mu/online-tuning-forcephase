"""Matched shallow boosting/bagging on full-cache and joined static views."""

import argparse
import fcntl
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, measured_gains, SPLITS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


class TwoRelativeRegressors:
    def __init__(self, models):
        self.models = models

    def predict(self, x):
        return np.column_stack([model.predict(x) for model in self.models])


def fit(kind, x, costs, seed):
    target = (costs[:, :1] - costs[:, 1:]) / 1200
    models = []
    for action in range(2):
        if kind == "boosting":
            model = HistGradientBoostingRegressor(
                loss="squared_error", max_iter=100, learning_rate=.05, max_depth=3,
                max_leaf_nodes=8, min_samples_leaf=32, l2_regularization=10,
                max_bins=63, categorical_features=None, early_stopping=False,
                random_state=seed + action)
        else:
            model = ExtraTreesRegressor(n_estimators=100, max_depth=3, min_samples_leaf=32,
                                        max_features=1., n_jobs=4, random_state=seed + action)
        model.fit(x, target[:, action])
        if kind == "bagging":
            model.n_jobs = 1
        models.append(model)
    return TwoRelativeRegressors(models)


def views(keys):
    arrays, sources = {}, {}
    for rid in ("R02", "R03", "R04", "R06", "R07", "R08", "R09"):
        path = DATA / f"mechanism_{rid}_features_20261111/features.npz"
        with np.load(path) as archive:
            assert archive["keys"].tolist() == keys
            arrays[rid] = {name: archive[name] for name in archive.files}
        sources[rid] = sha(path)
    base_fee, valid = arrays["R02"]["fee"], arrays["R02"]["valid"]
    fee = base_fee.copy()
    pieces = [arrays["R02"]["ordered90"]]
    for rid, name in (("R03", "quotient56"), ("R04", "community46"), ("R07", "watch_order38"),
                      ("R08", "parity_interface38"), ("R09", "signed_overlap38")):
        assert np.array_equal(arrays[rid]["valid"], valid)
        increment = arrays[rid]["fee"] - base_fee
        assert increment.min() >= -1e-10
        fee += np.maximum(increment, 0)
        pieces.append(arrays[rid][name][:, 14:])
    joined = np.column_stack(pieces)
    assert joined.shape == (len(keys), 236) and np.isfinite(joined).all()
    return {"GBD52_free": (arrays["R06"]["base_plus_tail52"], arrays["R06"]["valid"], np.zeros(len(keys))),
            "raw236_costed": (joined, valid, fee)}, sources


def run(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve existing shallow-ensemble scores")
        keys, _, costs, _, _, _ = load()
        rows = read_csv(SPLITS)
        assert [row["instance_key"] for row in rows] == keys
        inner = np.array([row["inner_validation"] == "True" for row in rows])
        fine = np.array([row["fine_group"] for row in rows])
        coarse = np.array([row["coarse_group"] for row in rows])
        iso = np.array([row["iso_group"] for row in rows])
        inputs, source_sha = views(keys)
        output = [{"instance_key": key, "D_PAR2": float(costs[i, 0])} for i, key in enumerate(keys)]
        scores, fits = {}, []
        for mode, count in (("coarse", 4), ("fine", 5)):
            fold_ids = np.array([int(row[mode + "_fold"]) for row in rows])
            groups = coarse if mode == "coarse" else fine
            for view, (x, valid, acquisition) in inputs.items():
                for kind in ("boosting", "bagging"):
                    name = f"{mode}_{view}_{kind}"
                    action = np.zeros(len(keys), dtype=int)
                    fee = np.zeros(len(keys))
                    free_action = np.zeros(len(keys), dtype=int)
                    free_fee = np.zeros(len(keys))
                    cuts = []
                    for fold in range(count):
                        if time.monotonic() - start > 1200:
                            raise TimeoutError("bounded shallow-ensemble comparison exceeded twenty minutes")
                        held = fold_ids == fold
                        train, validation = ~held & ~inner & valid, ~held & inner & valid
                        assert not (set(iso[held]) & set(iso[train | validation]))
                        assert not (set(fine[train]) & set(fine[validation]))
                        begin = time.process_time()
                        model = fit(kind, x[train], costs[train], 20261111 + fold)
                        prediction = gains(model, x[validation], "trees_relative")
                        cut = calibrate(prediction, costs[validation], acquisition[validation])
                        free_cut = calibrate(prediction, costs[validation], np.zeros(validation.sum()))
                        ids = np.flatnonzero(held & valid)
                        prediction, inference = measured_gains(model, x[ids], "trees_relative")
                        action[ids] = choose(prediction, cut)
                        free_action[ids] = choose(prediction, free_cut)
                        if cut is not None:
                            fee[ids] = acquisition[ids] + inference
                        if free_cut is not None:
                            free_fee[ids] = inference
                        cuts.append({"fold": fold, "margin_PAR2_s": cut, "free_margin_PAR2_s": free_cut})
                        fits.append({"variant": name, "fold": fold, "train": int(train.sum()),
                                     "validation": int(validation.sum()), "CPU_s": time.process_time() - begin})
                    chosen = timed_cost(costs[np.arange(len(keys)), action], fee, 600)
                    free_chosen = timed_cost(costs[np.arange(len(keys)), free_action], free_fee, 600)
                    result = assess(costs[:, 0], chosen, groups, 600)
                    result.update(actions={a: int((action == i).sum()) for i, a in enumerate(ACTIONS)}, cuts=cuts,
                                  free_features=assess(costs[:, 0], free_chosen, groups, 600))
                    if mode == "coarse":
                        result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], chosen, groups)
                    scores[name] = result
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[action[i]]
                        row[name + "_PAR2"] = float(chosen[i])
                        row[name + "_decision_CPU_s"] = float(fee[i])
                    write_csv(args.out / "predictions.csv", output)
                    write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
                    print(f"SCORED {name}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
        # One prespecified full-development export; its outer score does not
        # determine the feature view, hyperparameters, or inner margin.
        x, valid, acquisition = inputs["raw236_costed"]
        model = fit("boosting", x[valid & ~inner], costs[valid & ~inner], 20261111)
        validation = valid & inner
        cut = calibrate(gains(model, x[validation], "trees_relative"), costs[validation], acquisition[validation])
        joblib.dump({"model": model, "cut": cut, "feature_view": "raw236_costed",
                     "feature_sha256": source_sha, "relative_target": "T600 PAR2(D) minus PAR2(Fplus/Fminus)"},
                    args.out / "development_boosted_predictor.joblib")
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
              "fits": fits, "full_development_model_fits": 1, "final_margin_PAR2_s": cut,
              "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "view_coverage": {n: int(v.sum()) for n, (_, v, _) in inputs.items()},
              "new_solver_calls": 0, "short_search_calls": 0, "new_CNF_feature_calls": 0,
              "source_sha256": sha(__file__), "input_feature_sha256": source_sha, "splits_sha256": sha(SPLITS),
              "cost_boundary": {"GBD52_free": "unmeasured acquisition; optimistic predictive evidence",
                                "raw236_costed": "deduplicated sum of measured component routes; unified end-to-end not remeasured"},
              "model_sha256": sha(args.out / "development_boosted_predictor.joblib")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args())
