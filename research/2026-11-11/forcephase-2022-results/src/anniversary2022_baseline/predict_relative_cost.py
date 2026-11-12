"""Predict a CNF's phase cost before search, using existing 2022 outcomes."""

import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import time

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .common import sha, write
from .route_phase_2022 import SOLVER_FLAGS, load_formula
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, ROOT, load, read_csv, write_csv
from .structural_views import features


SEED = 20261110
SPLITS = DATA / "cnf_graph_cnn_20261110/splits.csv"
GRAPH_WORK = Path(__file__).resolve().parents[2] / "work/cnf_graph_cnn_20261110/graphs"
KINDS = ("trees_relative", "trees_absolute", "ridge_relative")
QUANTILES = (0, .25, .5, .75, .9, .95, .99)


def fit(kind, x, costs, seed):
    if kind.startswith("trees"):
        model = ExtraTreesRegressor(n_estimators=64, max_depth=6, min_samples_leaf=32,
                                    max_features=.8, n_jobs=4, random_state=seed)
    else:
        model = make_pipeline(StandardScaler(), Ridge(alpha=10))
    target = costs / 1200 if kind.endswith("absolute") else (costs[:, :1] - costs[:, 1:]) / 1200
    model.fit(x, target)
    if kind.startswith("trees"):
        model.n_jobs = 1
    return model


def gains(model, x, kind):
    prediction = model.predict(x)
    if kind.endswith("absolute"):
        return (prediction[:, :1] - prediction[:, 1:]) * 1200
    return prediction * 1200


def choose(predicted_gain, cut):
    if cut is None:
        return np.zeros(len(predicted_gain), dtype=int)
    best = predicted_gain.argmax(axis=1)
    return np.where(predicted_gain[np.arange(len(best)), best] > cut, best + 1, 0)


def calibrate(predicted_gain, costs, fee):
    """Fit one global switching margin using inner validation parents only."""
    maxima = predicted_gain.max(axis=1)
    cuts = np.unique(np.maximum(0, np.r_[0, np.quantile(maxima, QUANTILES)]))
    best_cut, best_cost = None, float(costs[:, 0].sum())
    for cut in cuts:
        actions = choose(predicted_gain, float(cut))
        paid = timed_cost(costs[np.arange(len(costs)), actions], fee + .003, 600)
        total = float(paid.sum())
        if total < best_cost - 1e-8:
            best_cut, best_cost = float(cut), total
    return best_cut


def measured_gains(model, x, kind):
    predicted = np.empty((len(x), 2))
    inference = np.empty(len(x))
    model.predict(x[:1])
    for i in range(len(x)):
        start = time.process_time()
        predicted[i] = gains(model, x[i:i + 1], kind)[0]
        inference[i] = time.process_time() - start
    if not np.isfinite(predicted).all():
        raise ValueError("nonfinite held-out prediction")
    return predicted, inference


def load_views(keys, base, rows, view):
    if view == "rule6":
        def receipts(path):
            return {row["instance_key"]: row for row in map(json.loads, path.read_text().splitlines())
                    if row["status"] == "ok"}
        live = receipts(DATA / "live_feature_route_20261110/feature_receipts.jsonl")
        histogram = receipts(DATA / "static_unit_pressure_20261110/feature_receipts.jsonl")
        assert live.keys() == histogram.keys() and len(live) == 2843
        x = np.zeros((len(keys), 6))
        fee = np.zeros(len(keys))
        eligible = np.array([key in live for key in keys])
        for i in np.flatnonzero(eligible):
            row, raw = live[keys[i]], histogram[keys[i]]
            f = raw["features"]
            score = row["scc_demand_share"]
            assert np.isclose(row["mean_width"], f["raw_mean_width"], rtol=1e-9)
            x[i] = [score or 0, score is not None, row["mean_width"], f["pure_positive_share"],
                    f["pure_negative_share"], f["raw_binary_share"]]
            fee[i] = row["feature_CPU_s"] + raw["feature_cpu_s"] + raw["worker_cpu_s"]
        return {"rule6_costed": (x, eligible, fee)}
    blocks, _ = features(keys, base)
    full = blocks["combined"]
    eligible = np.array([row["eligible"] == "True" for row in rows])
    pooled = np.zeros((len(keys), 22), dtype=np.float64)
    for i in np.flatnonzero(eligible):
        with np.load(GRAPH_WORK / (keys[i] + ".npz")) as archive:
            pooled[i] = archive["pooled"]
    fee = np.array([float(row["feature_CPU_s"]) for row in rows])
    return {
        "gbd_full_free": (full, np.ones(len(keys), dtype=bool), np.zeros(len(keys))),
        "pooled_costed": (pooled, eligible, fee),
    }


def run(args):
    started, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve an existing run; choose a new identity")
        keys, base, costs, _, _, _ = load()
        rows = read_csv(SPLITS)
        if [row["instance_key"] for row in rows] != keys:
            raise ValueError("full cohort or fixed split mismatch")
        views = load_views(keys, base, rows, args.view)
        inner = np.array([row["inner_validation"] == "True" for row in rows])
        coarse = np.array([row["coarse_group"] for row in rows])
        fine = np.array([row["fine_group"] for row in rows])
        iso = np.array([row["iso_group"] for row in rows])
        outputs = [{"instance_key": key, "D_PAR2": costs[i, 0],
                    "coarse_group": coarse[i], "fine_group": fine[i]} for i, key in enumerate(keys)]
        results = {}
        fits = []
        inputs = {"matrix": DATA / "raw_data_20261110/matrix.csv", "splits": SPLITS,
                  "GBD": BASE, "encoding_receipt": DATA / "cnf_graph_cnn_20261110/preparation.json"}
        if args.view == "rule6":
            inputs.update(live_features=DATA / "live_feature_route_20261110/feature_receipts.jsonl",
                          static_features=DATA / "static_unit_pressure_20261110/feature_receipts.jsonl")
        for mode, fold_count in (("coarse", 4), ("fine", 5)):
            folds = np.array([int(row[mode + "_fold"]) for row in rows])
            blocks = coarse if mode == "coarse" else fine
            for view, (x, eligible, fee) in views.items():
                for kind in KINDS:
                    name = f"{mode}_{view}_{kind}"
                    actions = np.zeros(len(keys), dtype=int)
                    raw_actions = np.zeros(len(keys), dtype=int)
                    overhead = np.zeros(len(keys))
                    raw_overhead = np.zeros(len(keys))
                    predicted = np.zeros((len(keys), 2))
                    choices = []
                    for fold in range(fold_count):
                        if time.monotonic() - started > 900 or time.process_time() - cpu > 3600:
                            raise TimeoutError("frozen analysis budget exhausted")
                        test = folds == fold
                        train = ~test & ~inner & eligible
                        validation = ~test & inner & eligible
                        assert not (set(iso[test]) & set(iso[train | validation]))
                        assert not (set(fine[train]) & set(fine[validation]))
                        begin = time.process_time()
                        model = fit(kind, x[train], costs[train], SEED + fold)
                        validation_gain = gains(model, x[validation], kind)
                        cut = calibrate(validation_gain, costs[validation], fee[validation])
                        ids = np.flatnonzero(test & eligible)
                        held_gain, inference = measured_gains(model, x[ids], kind)
                        raw_actions[ids] = choose(held_gain, 0)
                        raw_overhead[ids] = fee[ids] + inference
                        actions[ids] = choose(held_gain, cut)
                        if cut is not None:
                            overhead[ids] = fee[ids] + inference
                        predicted[ids] = held_gain
                        receipt = {"variant": name, "fold": fold, "train": int(train.sum()),
                                   "validation": int(validation.sum()), "held_out": len(ids),
                                   "switch_margin_PAR2_s": cut, "disabled": cut is None,
                                   "CPU_s": time.process_time() - begin,
                                   "measured_inference_CPU_s": float(inference.sum())}
                        choices.append(receipt)
                        fits.append(receipt)
                    paid = timed_cost(costs[np.arange(len(keys)), actions], overhead, 600)
                    raw_paid = timed_cost(costs[np.arange(len(keys)), raw_actions], raw_overhead, 600)
                    result = assess(costs[:, 0], paid, blocks, 600)
                    result["actions"] = {a: int((actions == i).sum()) for i, a in enumerate(ACTIONS)}
                    result["feature_cost_status"] = {
                        "gbd_full_free": "unmeasured optimistic zero",
                        "pooled_costed": "measured reused encoding CPU",
                        "rule6_costed": "sum of existing measured extraction receipts; combined route not remeasured",
                    }[view]
                    result["raw_zero_margin"] = assess(costs[:, 0], raw_paid, blocks, 600)
                    result["outer_fold_choices"] = choices
                    if mode == "coarse":
                        result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], paid, blocks)
                    results[name] = result
                    for i, row in enumerate(outputs):
                        row[name + "_action"] = ACTIONS[actions[i]]
                        row[name + "_PAR2"] = float(paid[i])
                        row[name + "_gain_Fplus_s"] = float(predicted[i, 0])
                        row[name + "_gain_Fminus_s"] = float(predicted[i, 1])
                        row[name + "_CPU_s"] = float(overhead[i])
                    write_csv(args.out / "predictions.csv", outputs)
                    write(args.out / "summary.json", {"status": "running", "results": results, "fits": fits,
                                                       "new_solver_calls": 0, "new_feature_calls": 0})
                    print(f"SCORED {name}: gain={result['gain_pct']:+.5f}%, solved={result['solved']}, actions={result['actions']}", flush=True)
        # A deployable pooled-input predictor uses a fixed final fit/calibration
        # split. Its configuration is independent of the outer result ranking.
        export_view = "rule6_costed" if args.view == "rule6" else "pooled_costed"
        x, eligible, fee = views[export_view]
        train, validation = eligible & ~inner, eligible & inner
        model = fit("trees_relative", x[train], costs[train], SEED)
        cut = calibrate(gains(model, x[validation], "trees_relative"), costs[validation], fee[validation])
        model_path = args.out / "relative_predictor.joblib"
        joblib.dump({"model": model, "cut": cut, "kind": "trees_relative", "format": "relative_cost_v1",
                     "feature_view": export_view,
                     "feature_source_sha256": sha(Path(__file__).parent / "cnn_phase.py"),
                     "target": "PAR2(D) minus PAR2(Fplus/Fminus) at T600"}, model_path)
        summary = {"status": "complete", "parents": len(keys), "results": results, "fits": fits,
                   "feature_views": {name: {"columns": x.shape[1], "coverage": int(e.sum())}
                                     for name, (x, e, _) in views.items()},
                   "new_solver_calls": 0, "new_feature_calls": 0,
                   "physical_analysis_CPU_s": time.process_time() - cpu,
                   "wall_s": time.monotonic() - started, "sklearn_version": sklearn.__version__,
                   "source_sha256": sha(__file__), "input_sha256": {n: sha(p) for n, p in inputs.items()},
                   "final_pooled_margin_PAR2_s": cut, "final_model_sha256": sha(model_path),
                   "score_scope": "Repeatedly used2022 development; grouped held-out scoring; no independent test"}
        write(args.out / "summary.json", summary)


def predict(args):
    start = time.process_time()
    payload = joblib.load(args.model)
    if payload["format"] not in ("pooled_relative_cost_v1", "relative_cost_v1"):
        raise ValueError("unsupported predictor format")
    action, predicted, native_cpu = "D", None, 0.0
    if payload["cut"] is not None:
        raw = load_formula(args.cnf)
        if len(raw) <= 3_000_000:
            if payload.get("feature_view", "pooled_costed") == "rule6_costed":
                scope = "scc" if len(raw) <= 1_500_000 else "width"
                output = subprocess.check_output(
                    [str(ROOT / "work/live_feature_route_20261110/extract"), "--selector", scope],
                    input=raw, timeout=5)
                selector_cpu, score, width = map(float, output.split())
                output = subprocess.check_output(
                    [str(ROOT / "work/positive_binary_replay_20261110/count"), "--pressure"],
                    input=raw, timeout=5).split()
                native_cpu = selector_cpu + float(output[4])
                positive, negative, binary, _ = map(float, output[-4:])
                x = np.array([[max(score, 0), score >= 0, width, positive, negative, binary]])
            else:
                from .cnn_phase import encode_formula
                x = encode_formula(raw)["pooled"][None, :]
            predicted = gains(payload["model"], x, payload["kind"])
            action = ACTIONS[int(choose(predicted, payload["cut"])[0])]
    print(json.dumps({"action": action, "solver_flags": SOLVER_FLAGS[action],
                      "predicted_PAR2_saving_s": None if predicted is None else
                      dict(zip(ACTIONS[1:], map(float, predicted[0]))),
                      "switch_margin_PAR2_s": payload["cut"],
                      "CPU_s_after_import": time.process_time() - start + native_cpu}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("run")
    sub.add_argument("--out", type=Path, required=True)
    sub.add_argument("--view", choices=("base", "rule6"), default="base")
    sub = commands.add_parser("predict")
    sub.add_argument("cnf", type=Path)
    sub.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    {"run": run, "predict": predict}[args.command](args)


if __name__ == "__main__":
    main()
