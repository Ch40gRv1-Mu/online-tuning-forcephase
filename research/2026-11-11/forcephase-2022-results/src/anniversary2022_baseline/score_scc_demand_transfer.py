"""Evaluate the fixed SCC demand guard on newly covered development formulas."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .collect_signed_topology import eligible
from .positive_binary_replay import write_json
from .score_signed_topology import metrics
from .structural_clusters import ACTIONS, load, write_csv


THRESHOLD = 0.10


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection", required=True, type=Path)
    ap.add_argument("--earlier-features", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    original = eligible()
    expanded = eligible("boundary-transfer")
    with args.earlier_features.open() as stream:
        old = {r["instance_key"]: r for r in map(json.loads, stream)}
    new = {key: json.loads((args.collection / "records" / (key + ".json")).read_text()) for key in expanded}
    assert set(original) == set(old) and len(new) == 855 and len(old) == 1988
    records = old | new
    assert all(r["instance_key"] == key for key, r in records.items())
    keys, _, costs, _, groups, _ = load()
    probes = np.array([records.get(key, {}).get("status") == "ok" for key in keys])
    h = np.array([records[key]["feature_cpu_s"] if valid else 0 for key, valid in zip(keys, probes)])
    values = np.array([records[key]["features"]["scc_demand_share"] if valid else 0 for key, valid in zip(keys, probes)])
    actions = np.where(values > THRESHOLD, 2, 0)
    adjusted = np.where((costs < 1200) & (costs + h[:, None] <= 600), costs + h[:, None], 1200)
    selections = {
        "original": np.array([key in old for key in keys]),
        "newly_covered": np.array([key in new for key in keys]),
        "all_parents": np.ones(len(keys), dtype=bool),
    }
    scores = {name: metrics(costs[use], adjusted[use], actions[use], probes[use], np.array(groups)[use])
              for name, use in selections.items()}
    collection = json.loads((args.collection / "collection.json").read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / "predictions.csv", [
        {"instance_key": key, "newly_covered": key in new, "extracted": bool(probes[i]),
         "scc_demand_share": float(values[i]) if probes[i] else "",
         "feature_cpu_s": h[i], "action": ACTIONS[actions[i]], "D_par2": costs[i, 0],
         "selected_par2": adjusted[i, actions[i]]}
        for i, key in enumerate(keys)
    ])
    with (args.out / "new_feature_receipts.jsonl").open("w") as stream:
        for key in sorted(new):
            stream.write(json.dumps(new[key], separators=(",", ":")) + "\n")
    result = {"threshold": THRESHOLD, "action_above": "Fminus", "parents": len(keys),
              "scores": scores, "collection": collection, "new_solver_calls": 0,
              "analysis_cpu_s": time.process_time() - cpu, "analysis_wall_s": time.monotonic() - start}
    write_json(args.out / "summary.json", result)
    print(json.dumps({name: row["with_extractor_cpu"] for name, row in scores.items()}, indent=2))


if __name__ == "__main__":
    main()
