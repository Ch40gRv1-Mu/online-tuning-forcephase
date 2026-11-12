"""Screen archived clause features on the size-excluded D branch."""

import argparse
import json
from pathlib import Path
import sqlite3
import time

import numpy as np

from .common import sha, write
from .phase_rule_2022 import WIDTH_CUT
from .score_scc_complement_stump import metrics, replay
from .score_scc_root_guard import par2
from .structural_clusters import ACTIONS, BASE, DATA, load, read_csv, write_csv


FEATURES = ("mean_clause_width", "binary_share", "pure_positive_share", "pure_negative_share")
SIZE_LIMIT = 3_000_000
STARTUP_S = 0.05


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started, cpu = time.monotonic(), time.process_time()
    keys, x, costs, _, _, _ = load()
    inputs = {
        "features": BASE,
        "fixed_policy": DATA / "scc_width_fixed_20261110/predictions.csv",
        "group_blocks": DATA / "scc_blocked_replay_20261110/predictions.csv",
        "calibration": DATA / "static_unit_pressure_20261110/feature_receipts.jsonl",
    }
    fixed = {r["instance_key"]: r for r in read_csv(inputs["fixed_policy"])}
    grouping = {r["instance_key"]: r for r in read_csv(inputs["group_blocks"])}
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as conn:
        sizes = {k: int(b) for k, b in conn.execute("select hash,bytes from features") if k in fixed}
    if set(keys) != set(fixed) or fixed.keys() != grouping.keys() or fixed.keys() != sizes.keys():
        raise ValueError("archive does not match the 4,719-input cohort")
    base_action = np.array([ACTIONS.index(fixed[k]["frozen_action"]) for k in keys])
    baseline = np.array([float(fixed[k]["frozen_par2"]) for k in keys])
    size = np.array([sizes[k] for k in keys])
    take = (size > SIZE_LIMIT) & (base_action == 0)
    if int(take.sum()) != 1876 or not np.array_equal(costs[take, 0], baseline[take]):
        raise ValueError("unexpected large-formula fallback population")
    with inputs["calibration"].open() as stream:
        rates = [r["raw_bytes"] / r["feature_cpu_s"] for r in map(json.loads, stream)
                 if r["status"] == "ok" and r["raw_bytes"] >= 1_000_000]
    if len(rates) != 604:
        raise ValueError("unexpected calibration scope")
    throughput = float(np.quantile(rates, 0.25))
    assumed_cost = STARTUP_S + size[take] / throughput
    values = np.column_stack((np.expm1(x[take, 2]), x[take, 4], x[take, 7], x[take, 8]))
    if not np.isfinite(values).all():
        raise ValueError("unavailable archived structural feature")
    groups = {
        "shape": np.array([grouping[k]["shape_block"] for k in keys]),
        "coarse_cluster": np.array([fixed[k]["coarse_cluster_group"] for k in keys]),
    }
    _, support = np.unique(groups["shape"][take], return_inverse=True)
    dominant = np.array([grouping[k]["root_unit_block"] in ("units:49", "units:56") for k in keys])
    result = {}
    predictions = [{"instance_key": k, "large_eligible": bool(take[i]), "baseline_PAR2": baseline[i]}
                   for i, k in enumerate(keys)]
    rules = []
    subset_costs = costs[take]
    default = np.zeros(take.sum(), dtype=int)

    def record(name, block, sub_actions, sub_costs):
        chosen = baseline.copy()
        actions = base_action.copy()
        chosen[take] = sub_costs
        actions[take] = sub_actions
        scored = metrics(costs, baseline, chosen, actions, block, dominant)
        scored["against_frozen_two_threshold"] = scored.pop("against_SCC")
        scored["additional_switches"] = int((actions != base_action).sum())
        result[name] = scored
        for i, row in enumerate(predictions):
            row[name + "_action"] = ACTIONS[actions[i]]
            row[name + "_par2"] = float(chosen[i])
        print(name, scored["against_frozen_two_threshold"]["par2_improvement_pct"],
              scored["against_frozen_two_threshold"]["paired_group_bootstrap_95_pct"],
              scored["incremental_D_timeouts_rescued"], scored["incremental_SCC_solves_lost"],
              scored["additional_switches"], flush=True)

    for fee, extra in (("free", np.zeros_like(assumed_cost)), ("assumed", assumed_cost)):
        direct = (values[:, 0] > WIDTH_CUT).astype(int)
        record(f"{fee}_fixed_width_transfer", groups["coarse_cluster"], direct, par2(subset_costs, direct, extra))
        for split, block in groups.items():
            labels, ids = np.unique(block[take], return_inverse=True)
            for guard in (False, True):
                mode = f"{fee}_{split}" + ("_guard" if guard else "")
                actions, h, fitted = replay(values, np.ones(len(default), dtype=bool), subset_costs,
                                            default, np.zeros(len(default)), extra, ids, guard,
                                            support_index=support)
                record(mode, block, actions, par2(subset_costs, actions, h))
                result[mode]["assumed_feature_CPU_s_charged"] = float(h.sum())
                for i, spec in fitted.items():
                    j, cut, left, act = spec if spec else (-1, None, False, 0)
                    rules.append({"variant": mode, "held_group": labels[i], "feature": FEATURES[j] if spec else "",
                                  "cutoff": cut, "side": ("<=" if left else ">") if spec else "",
                                  "action": ACTIONS[act]})
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", predictions)
    write_csv(args.out / "rules.csv", rules)
    write(args.out / "summary.json", {
        "parents": len(keys), "eligible_large": int(take.sum()), "excluded_resource_bytes": int(size[take].sum()),
        "all_censored_large": int((subset_costs.min(axis=1) == 1200).sum()),
        "oracle_headroom_large_s": float((subset_costs[:, 0] - subset_costs.min(axis=1)).sum()),
        "calibration_parents": len(rates), "assumed_throughput_bytes_per_CPU_s": throughput,
        "startup_CPU_s_assumed": STARTUP_S, "full_assumed_CPU_s": float(assumed_cost.sum()),
        "new_solver_calls": 0, "new_feature_calls": 0,
        "analysis_CPU_s": time.process_time() - cpu, "elapsed_wall_s": time.monotonic() - started,
        "input_sha256": {name: sha(path) for name, path in inputs.items()},
        "results": result,
    })


if __name__ == "__main__":
    main()
