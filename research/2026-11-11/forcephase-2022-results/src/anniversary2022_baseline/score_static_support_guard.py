"""A bounded static novelty guard using saved cost-classifier fold scores."""

import argparse
import fcntl
import json
from pathlib import Path
import time

import joblib
import numpy as np
from scipy.spatial import cKDTree
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import choose, SPLITS
from .score_static_seed_agreement import load_views
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


QUANTILES = (.05, .1, .25, .5, .75, .9, 1.)
CALIBRATION_CLASSIFIER_CPU_S = .020


def support_fit(x, equivalence):
    # Grouping only deduplicates training references; it is not a predictor.
    _, first = np.unique(equivalence, return_index=True)
    reference = x[first].astype(np.float32).astype(float)
    center = np.median(reference, axis=0)
    lower, upper = np.quantile(reference, [.25, .75], axis=0)
    scale = upper - lower
    span = np.ptp(reference, axis=0)
    scale = np.where(scale > 0, scale, np.where(span > 0, span, 1.))
    reference = np.clip((reference - center) / scale, -100, 100)
    tree = cKDTree(reference)
    nearest = tree.query(reference, k=2, workers=4)[0][:, 1]
    positive = nearest[nearest > 0]
    radius = float(np.median(positive)) if len(positive) else 1.
    return {"tree": tree, "center": center, "scale": scale, "radius": radius,
            "reference_parents": len(first)}


def measured_distance(model, x):
    distance, fee = np.empty(len(x)), np.empty(len(x))
    for i, row in enumerate(x):
        tick = time.process_time()
        encoded = row.astype(np.float32).astype(float)
        encoded = np.clip((encoded - model["center"]) / model["scale"], -100, 100)
        distance[i] = model["tree"].query(encoded, k=1, workers=1)[0] / model["radius"]
        fee[i] = time.process_time() - tick
    return distance, fee


def mask(distance, cutoff):
    if cutoff is None:
        return np.zeros(len(distance), dtype=bool)
    if cutoff == "all":
        return np.ones(len(distance), dtype=bool)
    return distance <= cutoff


def query_fee(fee, cutoff):
    return fee if cutoff not in (None, "all") else np.zeros(len(fee))


def fit_guard(distance, distance_fee, base_action, costs):
    best, best_cost = None, float(costs[:, 0].sum())
    candidates = [*np.unique(np.quantile(distance, QUANTILES)).tolist(), "all"]
    for cutoff in candidates:
        supported = mask(distance, cutoff)
        if supported.sum() < 32:
            continue
        action = np.where(supported, base_action, 0)
        fee = query_fee(distance_fee, cutoff) + supported * CALIBRATION_CLASSIFIER_CPU_S
        total = timed_cost(costs[np.arange(len(costs)), action], fee, 600).sum()
        if total < best_cost - 1e-8:
            best, best_cost = cutoff, float(total)
    return best


def fit_stump(distance, distance_fee, costs):
    best, best_cost = (None, 0), float(costs[:, 0].sum())
    for cutoff in [*np.unique(np.quantile(distance, QUANTILES)).tolist(), "all"]:
        supported = mask(distance, cutoff)
        if supported.sum() < 32:
            continue
        for leaf in (1, 2):
            action = np.where(supported, leaf, 0)
            total = timed_cost(costs[np.arange(len(costs)), action], query_fee(distance_fee, cutoff), 600).sum()
            if total < best_cost - 1e-8:
                best, best_cost = (cutoff, leaf), float(total)
    return best


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve the existing support-guard evidence")
        base_dir = DATA / "mechanism_R13b_20261111"
        base = json.loads((base_dir / "summary.json").read_text())
        assert base["status"] == "complete"
        keys, _, costs, _, _, _ = load()
        split = read_csv(SPLITS)
        assert [r["instance_key"] for r in split] == keys
        inner = np.array([r["inner_validation"] == "True" for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        iso = np.array([r["iso_group"] for r in split])
        iso_rows = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
        iso_fold = np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows])
        base_rows = read_csv(base_dir / "predictions.csv")
        assert [r["instance_key"] for r in iso_rows] == [r["instance_key"] for r in base_rows] == keys
        inputs, _ = load_views(keys)
        output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
        results, fits = {}, []
        variants = ("guard_min3", "guard_mean3", "distance_stump")
        for mode, count in (("coarse", 4), ("fine", 5), ("iso_diagnostic", 5)):
            folds = iso_fold if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
            blocks = fine if mode == "fine" else coarse
            for view in ("linear42", "legacy52"):
                x, valid = inputs[view]
                actions = {v: np.zeros(len(keys), dtype=int) for v in variants}
                fees = {v: np.zeros(len(keys)) for v in variants}
                rules = {v: [] for v in variants}
                for fold in range(count):
                    if time.monotonic() - start > 600:
                        raise TimeoutError("bounded support comparison exceeded ten minutes")
                    held = folds == fold
                    train, validation = ~held & ~inner & valid, ~held & inner & valid
                    assert not (set(iso[held]) & set(iso[train | validation]))
                    assert not (set(fine[train]) & set(fine[validation]))
                    with np.load(base_dir / "fold_arrays" / f"{mode}_{view}_{fold}.npz") as data:
                        ids, vid = data["held_ids"], data["validation_ids"]
                        vp, hp = data["validation_scores"], data["held_scores"]
                    assert np.array_equal(ids, np.flatnonzero(held & valid))
                    assert np.array_equal(vid, np.flatnonzero(validation))
                    tick = time.process_time()
                    geometry = support_fit(x[train], iso[train])
                    vd, vf = measured_distance(geometry, x[vid])
                    hd, hf = measured_distance(geometry, x[ids])
                    fits.append({"mode": mode, "view": view, "fold": fold,
                                 "reference_parents": geometry["reference_parents"],
                                 "CPU_s": time.process_time() - tick, "query_CPU_s": float(vf.sum() + hf.sum())})
                    for variant in variants:
                        if variant == "distance_stump":
                            cutoff, leaf = fit_stump(vd, vf, costs[vid])
                            actions[variant][ids] = np.where(mask(hd, cutoff), leaf, 0)
                            fees[variant][ids] = query_fee(hf, cutoff)
                            rule = {"fold": fold, "distance_cutoff": cutoff, "leaf": ACTIONS[leaf]}
                        else:
                            aggregation = variant.removeprefix("guard_")
                            source_name = mode + "_" + view + "_" + aggregation
                            original_cut = base["scores"][source_name]["cuts"][fold]["preference_score_margin"]
                            validation_score = vp.min(axis=0) if aggregation == "min3" else vp.mean(axis=0)
                            held_score = hp.min(axis=0) if aggregation == "min3" else hp.mean(axis=0)
                            cutoff = fit_guard(vd, vf, choose(validation_score, original_cut), costs[vid])
                            supported = mask(hd, cutoff)
                            actions[variant][ids] = np.where(supported, choose(held_score, original_cut), 0)
                            base_fee = np.array([float(base_rows[i][source_name + "_decision_CPU_s"]) for i in ids])
                            fees[variant][ids] = query_fee(hf, cutoff) + supported * base_fee
                            rule = {"fold": fold, "distance_cutoff": cutoff, "original_score_margin": original_cut}
                        rules[variant].append(rule)
                for variant in variants:
                    name = mode + "_" + view + "_" + variant
                    action = actions[variant]
                    selected = timed_cost(costs[np.arange(len(keys)), action], fees[variant], 600)
                    result = assess(costs[:, 0], selected, blocks, 600)
                    result.update(rules=rules[variant], actions={a: int((action == i).sum()) for i, a in enumerate(ACTIONS)})
                    if mode != "fine":
                        result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], selected, coarse)
                    if mode == "iso_diagnostic":
                        result["within_iso_parent_interval"] = assess(costs[:, 0], selected, iso, 600)
                    results[name] = result
                    for i, row in enumerate(output):
                        row[name + "_action"] = ACTIONS[action[i]]
                        row[name + "_PAR2"] = float(selected[i])
                        row[name + "_decision_CPU_s"] = float(fees[variant][i])
                    print(f"SCORED {name}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
                write_csv(args.out / "predictions.csv", output)
                write(args.out / "summary.json", {"status": "running", "scores": results, "support_fits": fits})
        # Fixed export of the new primary guard. Source classifier fit stays
        # untouched; the geometry contains only numeric structural references.
        x, valid = inputs["linear42"]
        payload = joblib.load(base_dir / "development_cost_classifier.joblib")
        from .score_static_cost_classifier import scores as class_scores
        geometry = support_fit(x[valid & ~inner], iso[valid & ~inner])
        validation = valid & inner
        vd, vf = measured_distance(geometry, x[validation])
        preference = np.min([class_scores(m, x[validation]) for m in payload["models"]], axis=0)
        cutoff = fit_guard(vd, vf, choose(preference, payload["cut"]), costs[validation])
        joblib.dump({"classifier": payload, "geometry": geometry, "distance_cutoff": cutoff,
                     "dtype": "float32", "feature_view": "linear42"}, args.out / "development_support_guard.joblib")
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": results,
              "support_fits": fits, "new_classifier_fits": 0, "final_distance_cutoff": cutoff,
              "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
              "source_sha256": sha(__file__), "base_receipt_sha256": sha(base_dir / "summary.json"),
              "splits_sha256": sha(SPLITS), "model_sha256": sha(args.out / "development_support_guard.joblib"),
              "cost_boundary": "GBD acquisition unmeasured free; measured support query plus reused exact classifier-query fees",
              "new_solver_calls": 0, "short_search_calls": 0, "new_CNF_feature_calls": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
