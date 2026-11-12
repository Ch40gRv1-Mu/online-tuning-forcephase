"""Replay directional tests of four signed-structure hypotheses."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .positive_binary_replay import write_json
from .score_signed_topology import metrics
from .structural_clusters import ACTIONS, load, write_csv


def candidate_rules(f):
    reach = f["signed_reach"]
    depth = f["signed_dag_depth"]
    collision = f["signed_collision_rate"]
    fanout = f["gate_fanout_balance"]
    gate_sign = f["gate_sign_balance"]
    pos_inside, neg_inside = f["positive_inside_exclusion"], f["negative_inside_exclusion"]
    pos_external, neg_external = f["log_positive_external_max"], f["log_negative_external_max"]
    pos_choice = (pos_inside >= 0.95) & (neg_inside < 0.95) & (pos_external > 0)
    neg_choice = (neg_inside >= 0.95) & (pos_inside < 0.95) & (neg_external > 0)
    return {
        "H01_reach_collision": (reach, reach * collision <= 0),
        "H06_depth_collision": (depth, depth * collision <= 0),
        "H09_gate_degree_proxy": (fanout, fanout * gate_sign > 0),
        "H14_choice_bottleneck_proxy": (
            f["choice_density"] * np.where(neg_choice, 1 / (1 + neg_external),
                                           np.where(pos_choice, -1 / (1 + pos_external), 0)),
            pos_choice | neg_choice,
        ),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topology-results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    started, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, groups, folds = load()
    with (args.topology_results / "feature_receipts.jsonl").open() as stream:
        records = [json.loads(line) for line in stream]
    by_key = {r["instance_key"]: r for r in records if r["status"] == "ok"}
    assert len(by_key) == sum(r["status"] == "ok" for r in records)
    valid = np.array([key in by_key for key in keys])
    feature_names = next(iter(by_key.values()))["features"]
    X = {name: np.array([by_key[key]["features"][name] if key in by_key else 0 for key in keys])
         for name in feature_names}
    h = np.array([by_key[key]["feature_cpu_s"] if key in by_key else 0 for key in keys])
    adjusted = np.where((costs < 1200) & (costs + h[:, None] <= 600), costs + h[:, None], 1200)
    result = []
    predictions = {}
    for name, (signal, guard) in candidate_rules(X).items():
        use = valid & guard & (signal != 0)
        direction = np.where(signal > 0, 1, 2)
        magnitude = np.abs(signal)
        fixed = np.where(use, direction, 0)
        chosen = np.zeros(len(keys), dtype=int)
        probed = np.zeros(len(keys), dtype=bool)
        selected = []
        for fold in range(5):
            test = folds == fold
            train = ~test
            support = magnitude[train & use]
            train_probed = train & valid
            if len(support) >= 30:
                cuts = np.unique(np.r_[0, np.quantile(support, [.25, .5, .75, .9])])
            else:
                cuts = []
            best_gain, threshold = 0, None
            for cut in cuts:
                switched = use & (magnitude >= cut)
                if (train & switched).sum() < 30:
                    continue
                train_actions = np.where(switched, direction, 0)[train_probed]
                gain = (costs[train_probed, 0] - adjusted[train_probed, train_actions]).sum()
                if gain > best_gain:
                    best_gain, threshold = float(gain), float(cut)
            if threshold is not None:
                switched = test & use & (magnitude >= threshold)
                chosen[switched] = direction[switched]
                probed[test & valid] = True
            selected.append({"fold": fold, "strength_threshold": threshold, "train_net_gain_s": best_gain})
        predictions[name + "_fixed"] = fixed
        predictions[name + "_fitted"] = chosen
        result.append({"hypothesis": name, "nonzero_directional_signals": int(use.sum()),
                       "fixed_direction": metrics(costs, adjusted, fixed, valid, groups),
                       "fit_strength_or_D": metrics(costs, adjusted, chosen, probed, groups),
                       "thresholds": selected})
        print(name, f"fixed {result[-1]['fixed_direction']['with_extractor_cpu']['par2_improvement_pct']:+.4f}%",
              f"fitted {result[-1]['fit_strength_or_D']['with_extractor_cpu']['par2_improvement_pct']:+.4f}%", flush=True)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", [
        {"instance_key": key, "fold": int(folds[i]),
         **{name: ACTIONS[value[i]] for name, value in predictions.items()}}
        for i, key in enumerate(keys)
    ])
    write_json(args.out / "summary.json", {
        "parents": len(keys), "feature_covered": int(valid.sum()), "results": result,
        "analysis_cpu_s": time.process_time() - cpu, "elapsed_wall_s": time.monotonic() - started,
        "new_solver_calls": 0, "new_extraction_calls": 0,
    })


if __name__ == "__main__":
    main()
