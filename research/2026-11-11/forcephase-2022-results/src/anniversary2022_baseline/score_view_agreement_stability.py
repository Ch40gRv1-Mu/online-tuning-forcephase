"""Replicate zero-fit cross-view agreement with two new training seeds."""

import argparse
import fcntl
import json
from pathlib import Path
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha, write
from .predict_relative_cost import calibrate, choose, gains, measured_gains, SPLITS
from .score_static_learnability import fit
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def vote(values, mode):
    if mode == "unanimous":
        return int(values[0]) if np.all(values == values[0]) else 0
    count = np.bincount(values, minlength=3)
    return int(count.argmax()) if count.max() >= 2 else 0


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "owner.lock").open("w") as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (args.out / "summary.json").exists():
            raise ValueError("preserve the existing view-agreement replication")
        r16 = DATA / "mechanism_R16_20261111"
        r17 = DATA / "mechanism_R17_20261111"
        old = json.loads((r16 / "summary.json").read_text())
        assert old["status"] == json.loads((r17 / "summary.json").read_text())["status"] == "complete"
        keys, _, costs, _, _, _ = load()
        split, previous = read_csv(SPLITS), read_csv(r17 / "predictions.csv")
        assert [r["instance_key"] for r in split] == [r["instance_key"] for r in previous] == keys
        inner = np.array([r["inner_validation"] == "True" for r in split])
        iso = np.array([r["iso_group"] for r in split])
        fine = np.array([r["fine_group"] for r in split])
        coarse = np.array([r["coarse_group"] for r in split])
        source_features = DATA / "mechanism_R16_features_20261111/features.npz"
        with np.load(source_features) as archive:
            assert archive["keys"].tolist() == keys
            views = {"uniform79": (archive["uniform79"], archive["uniform_fee"]),
                     "paired79": (archive["paired79"], archive["paired_fee"])}
            basic_fee = archive["base_fee"]
        shared = np.zeros(len(keys)); index = {k: i for i, k in enumerate(keys)}
        for row in map(json.loads, (source_features.parent / "feature_receipts.jsonl").read_text().splitlines()):
            shared[index[row["instance_key"]]] = row["read_CPU_s"] + row["parse_CPU_s"]
        acquisition = views["uniform79"][1] + views["paired79"][1] - basic_fee - shared
        output = [{"instance_key": k, "D_PAR2": float(costs[i, 0])} for i, k in enumerate(keys)]
        scores, fits = {}, []
        fold_dir = args.out / "fold_arrays"; fold_dir.mkdir(exist_ok=True)
        for mode, count in (("coarse", 4), ("fine", 5)):
            folds = np.array([int(r[mode + "_fold"]) for r in split])
            groups = coarse if mode == "coarse" else fine
            pair_action = np.zeros((3, len(keys)), dtype=int)
            pair_fee, enabled = np.zeros((3, len(keys))), np.zeros((3, len(keys)), dtype=bool)
            pair_action[0] = [ACTIONS.index(r[mode + "_two_view_agreement_action"]) for r in previous]
            pair_fee[0] = [float(r[mode + "_two_view_agreement_decision_CPU_s"]) for r in previous]
            for fold in range(count):
                ids = np.flatnonzero(folds == fold)
                enabled[0, ids] = all(old["scores"][mode + "_" + v]["cuts"][fold]["margin_PAR2_s"] is not None for v in views)
                train, validation = (folds != fold) & ~inner, (folds != fold) & inner
                assert not (set(iso[ids]) & set(iso[train | validation]))
                assert not (set(fine[train]) & set(fine[validation]))
                for j, seed in enumerate((20261112, 20261113), 1):
                    if time.monotonic() - start > 900:
                        raise TimeoutError("bounded agreement replication exceeded fifteen minutes")
                    child_actions, child_fees, cuts = [], [], []
                    for view, (x, fee) in views.items():
                        tick = time.process_time()
                        model = fit("expressive", x[train], costs[train], seed + fold)
                        vp = gains(model, x[validation], "trees_relative")
                        cut = calibrate(vp, costs[validation], fee[validation])
                        hp, h = measured_gains(model, x[ids], "trees_relative")
                        child_actions.append(choose(hp, cut)); child_fees.append(h); cuts.append(cut)
                        fits.append({"mode": mode, "fold": fold, "seed": seed, "view": view,
                                     "margin_PAR2_s": cut, "CPU_s": time.process_time() - tick})
                        np.savez_compressed(fold_dir / f"{mode}_{fold}_{seed}_{view}.npz",
                                            validation_ids=np.flatnonzero(validation), held_ids=ids,
                                            validation_scores=vp, held_scores=hp, inference_CPU_s=h)
                    enabled[j, ids] = all(cut is not None for cut in cuts)
                    if all(cut is not None for cut in cuts):
                        equal = child_actions[0] == child_actions[1]
                        pair_action[j, ids] = np.where(equal, child_actions[0], 0)
                        pair_fee[j, ids] = acquisition[ids] + child_fees[0] + child_fees[1]
            variants = {"seed0": (pair_action[0], pair_fee[0]), "seed1": (pair_action[1], pair_fee[1]),
                        "seed2": (pair_action[2], pair_fee[2])}
            for aggregation in ("majority", "unanimous"):
                action, fee = np.zeros(len(keys), dtype=int), np.zeros(len(keys))
                for i in range(len(keys)):
                    if enabled[:, i].sum() < (2 if aggregation == "majority" else 3):
                        continue
                    tick = time.process_time()
                    action[i] = vote(pair_action[:, i], aggregation)
                    extra = np.maximum(pair_fee[:, i] - acquisition[i], 0)
                    fee[i] = acquisition[i] + extra[enabled[:, i]].sum() + time.process_time() - tick
                variants[aggregation] = action, fee
            for variant, (action, fee) in variants.items():
                name = mode + "_" + variant
                chosen = timed_cost(costs[np.arange(len(keys)), action], fee, 600)
                result = assess(costs[:, 0], chosen, groups, 600)
                result["actions"] = {a: int((action == i).sum()) for i, a in enumerate(ACTIONS)}
                if mode == "coarse":
                    result["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], chosen, coarse)
                scores[name] = result
                for i, row in enumerate(output):
                    row[name + "_action"] = ACTIONS[action[i]]
                    row[name + "_PAR2"] = float(chosen[i])
                    row[name + "_decision_CPU_s"] = float(fee[i])
                print(f"SCORED {name}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}", flush=True)
            write_csv(args.out / "predictions.csv", output)
            write(args.out / "summary.json", {"status": "running", "scores": scores, "fits": fits})
        # Fixed majority policy, preserving each child's validation margin.
        pairs = []
        for seed in (20261111, 20261112, 20261113):
            children = {}
            for view, (x, fee) in views.items():
                model = fit("expressive", x[~inner], costs[~inner], seed)
                cut = calibrate(gains(model, x[inner], "trees_relative"), costs[inner], fee[inner])
                children[view] = {"model": model, "cut": cut}
            pairs.append(children)
        joblib.dump({"pairs": pairs, "aggregation": "majority_of_cross_view_agreements",
                     "qualification": "variable maximum<=100000, literal count<=100000",
                     "feature_sha256": sha(source_features)}, args.out / "development_view_agreement.joblib")
        write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": scores,
              "fits": fits, "reused_seed0_base_fits": 18, "new_outer_fits": len(fits),
              "full_development_model_fits": 6, "CPU_s": time.process_time() - cpu,
              "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
              "source_sha256": sha(__file__), "source_scores_sha256": sha(r17 / "summary.json"),
              "features_sha256": sha(source_features), "model_sha256": sha(args.out / "development_view_agreement.joblib"),
              "cost_scope": "Shared measured extraction and query cost; larger1876 basic acquisition remains optimistic unknown zero"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
