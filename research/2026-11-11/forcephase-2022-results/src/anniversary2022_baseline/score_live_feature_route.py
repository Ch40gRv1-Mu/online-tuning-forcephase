"""Run the normal CNF router and replay its measured actions and CPU on 2022 timings."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import resource
import sqlite3
import time

import numpy as np

from .common import sha, write
from .route_phase_2022 import WIDTH_BYTES, route_formula
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, load, read_csv, write_csv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--case-panel", type=Path, required=True)
    ap.add_argument("--verifier", type=Path, required=True)
    ap.add_argument("--extractor", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    old_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    keys, _, costs, _, _, _ = load()
    source = {
        "frozen": DATA / "scc_width_fixed_20261110/predictions.csv",
        "groups": DATA / "scc_blocked_replay_20261110/predictions.csv",
        "sizes": BASE,
    }
    fixed = {r["instance_key"]: r for r in read_csv(source["frozen"])}
    groups = {r["instance_key"]: r for r in read_csv(source["groups"])}
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        sizes = {k: int(b) for k, b in db.execute("select hash,bytes from features") if k in fixed}
    if set(keys) != set(fixed) or fixed.keys() != groups.keys() or fixed.keys() != sizes.keys():
        raise ValueError("mismatched full cohort")
    eligible = [k for k in keys if sizes[k] <= WIDTH_BYTES]
    if len(eligible) != 2843:
        raise ValueError("unexpected frozen input scope")
    prior = {r["instance_key"]: args.case_panel / "cnf" / (r["case"] + ".cnf")
             for r in read_csv(args.case_panel / "association_only.csv")}
    verifier, extractor = args.verifier.resolve(), args.extractor.resolve()

    def job(key):
        path = args.cache / f"{key}.cnf.gz"
        if not path.is_file():
            path = prior[key]
        return {"instance_key": key, **route_formula(path, extractor, sizes[key], verifier, key)}

    args.out.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
        records = {}
        for row in pool.map(job, eligible):
            records[row["instance_key"]] = row
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            if len(records) % 400 == 0:
                stream.flush()
                print(f"Measured {len(records)}/{len(eligible)} CNF routes", flush=True)
    actions = np.array([records.get(k, {}).get("action", "D") for k in keys])
    actual_h = np.array([records.get(k, {}).get("feature_CPU_s", 0) for k in keys])
    ids = np.array([ACTIONS.index(a) for a in actions])
    chosen = costs[np.arange(len(keys)), ids]
    score = {}
    shape = np.array([groups[k]["shape_block"] for k in keys])
    broad = np.array([fixed[k]["coarse_cluster_group"] for k in keys])
    for budget in (60, 120, 300, 600):
        baseline = timed_cost(costs[:, 0], 0, budget)
        paid = timed_cost(chosen, actual_h, budget)
        score[str(budget)] = {
            "fine_shape_vs_D": assess(baseline, paid, shape, budget),
            "coarse_cluster_vs_D": assess(baseline, paid, broad, budget),
        }
    flips = [k for k, action in zip(keys, actions) if action != fixed[k]["frozen_action"]]
    write_csv(args.out / "predictions.csv", [
        {"instance_key": k, "action": actions[i], "frozen_action": fixed[k]["frozen_action"],
         "feature_CPU_s": float(actual_h[i]), "PAR2": float(value)}
        for i, (k, value) in enumerate(zip(keys, timed_cost(chosen, actual_h, 600)))
    ])
    final_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    write(args.out / "summary.json", {
        "parents": len(keys), "acquired": len(records),
        "successful": sum(r["status"] == "ok" for r in records.values()),
        "action_mismatches": flips, "feature_CPU_s": float(actual_h.sum()),
        "identity_CPU_s": sum(r["identity_CPU_s"] for r in records.values()),
        "budgets": score, "analysis_and_collection_CPU_s": time.process_time() - cpu,
        "child_CPU_s": final_children.ru_utime + final_children.ru_stime - old_children.ru_utime - old_children.ru_stime,
        "elapsed_wall_s": time.monotonic() - start, "new_solver_calls": 0,
        "extractor_sha256": sha(extractor), "verifier_sha256": sha(verifier),
        "inputs_sha256": {name: sha(path) for name, path in source.items()},
    })
    print("Action mismatches:", len(flips), "actual feature CPU:", float(actual_h.sum()),
          "T600:", score["600"], flush=True)


if __name__ == "__main__":
    main()
