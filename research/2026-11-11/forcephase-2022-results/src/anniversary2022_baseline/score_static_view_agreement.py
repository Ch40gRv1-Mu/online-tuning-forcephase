"""Zero-fit agreement policies over the same heldout static feature views."""

import argparse
from pathlib import Path
import json
import time

import numpy as np

from .common import sha, write
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv
from .predict_relative_cost import SPLITS


def combine(actions, rule):
    if rule == "two_view_agreement":
        return int(actions[0]) if actions[0] == actions[1] else 0
    count = np.bincount(actions, minlength=3)
    return int(count.argmax()) if count.max() >= 2 else 0


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    source = DATA / "mechanism_R16_20261111"
    summary = json.loads((source / "summary.json").read_text())
    assert summary["status"] == "complete"
    keys, _, costs, _, _, _ = load()
    split, rows = read_csv(SPLITS), read_csv(source / "predictions.csv")
    assert [r["instance_key"] for r in split] == [r["instance_key"] for r in rows] == keys
    fine = np.array([r["fine_group"] for r in split])
    coarse = np.array([r["coarse_group"] for r in split])
    feature_file = DATA / "mechanism_R16_features_20261111/features.npz"
    with np.load(feature_file) as data:
        assert data["keys"].tolist() == keys
        acquisition = {"base43": data["base_fee"], "uniform79": data["uniform_fee"], "paired79": data["paired_fee"]}
    shared = np.zeros(len(keys))
    index = {key: i for i, key in enumerate(keys)}
    for record in map(json.loads, (feature_file.parent / "feature_receipts.jsonl").read_text().splitlines()):
        shared[index[record["instance_key"]]] = record["read_CPU_s"] + record["parse_CPU_s"]
    result, output = {}, [{"instance_key": key, "D_PAR2": float(costs[i, 0])} for i, key in enumerate(keys)]
    for mode in ("coarse", "fine"):
        folds = np.array([int(r[mode + "_fold"]) for r in split])
        groups = coarse if mode == "coarse" else fine
        for policy, required in (("two_view_agreement", ("uniform79", "paired79")),
                                 ("three_view_majority", ("base43", "uniform79", "paired79"))):
            action, fee = np.zeros(len(keys), dtype=int), np.zeros(len(keys))
            for fold in np.unique(folds):
                ids = np.flatnonzero(folds == fold)
                active = [view for view in required if summary["scores"][mode + "_" + view]["cuts"][fold]["margin_PAR2_s"] is not None]
                constant_D = len(required) - len(active)
                if (policy == "two_view_agreement" and constant_D) or (policy == "three_view_majority" and constant_D >= 2):
                    continue
                # Charge each shared extractor once, all active model queries,
                # and actual combination. No lazy early-exit discount is used.
                common_fee = acquisition["base43"][ids].copy()
                if "uniform79" in active:
                    common_fee += acquisition["uniform79"][ids] - acquisition["base43"][ids]
                if "paired79" in active:
                    common_fee += acquisition["paired79"][ids] - acquisition["base43"][ids]
                if "uniform79" in active and "paired79" in active:
                    common_fee -= shared[ids]
                for view in active:
                    old = np.array([float(rows[i][mode + "_" + view + "_decision_CPU_s"]) for i in ids])
                    common_fee += np.maximum(old - acquisition[view][ids], 0)
                for j, i in enumerate(ids):
                    votes = [ACTIONS.index(rows[i][mode + "_" + view + "_action"]) for view in required]
                    tick = time.process_time()
                    action[i] = combine(votes, policy)
                    fee[i] = common_fee[j] + time.process_time() - tick
            chosen = timed_cost(costs[np.arange(len(keys)), action], fee, 600)
            score = assess(costs[:, 0], chosen, groups, 600)
            score["actions"] = {a: int((action == i).sum()) for i, a in enumerate(ACTIONS)}
            if mode == "coarse":
                score["exact_eight_block_95_pct"] = exact_small_block_interval(costs[:, 0], chosen, coarse)
            name = mode + "_" + policy
            result[name] = score
            for i, row in enumerate(output):
                row[name + "_action"] = ACTIONS[action[i]]
                row[name + "_PAR2"] = float(chosen[i])
                row[name + "_decision_CPU_s"] = float(fee[i])
            print(f"SCORED {name}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
    write_csv(args.out / "predictions.csv", output)
    write(args.out / "summary.json", {"status": "complete", "parents": len(keys), "scores": result,
          "new_classifier_fits": 0, "new_threshold_fits": 0, "CPU_s": time.process_time() - cpu,
          "wall_s": time.monotonic() - start, "new_solver_calls": 0, "short_search_calls": 0,
          "source_sha256": sha(__file__), "base_score_sha256": sha(source / "summary.json"),
          "feature_sha256": sha(feature_file), "cost_boundary": "shared feature/query costs conservatively reused; unknown1876 acquisition remains optimistic zero"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
