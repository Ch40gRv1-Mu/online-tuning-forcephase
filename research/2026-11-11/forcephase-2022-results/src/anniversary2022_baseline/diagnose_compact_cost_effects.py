"""Decompose a completed compact-cost replay; never fit or change a policy."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv


def main(args):
    wall, cpu = time.monotonic(), time.process_time()
    prefix_path = args.root / f"prefix_{args.through}.json"
    prefix = json.loads(prefix_path.read_text())
    assert prefix["status"] == "complete_prefix" and prefix["through"] == args.through
    replay_root = args.root / f"replay_prefix_{args.through}"
    replay = json.loads((replay_root / "summary.json").read_text())
    replay_rows = read_csv(replay_root / "predictions.csv")
    manifest = read_csv(DATA.parent.parent / "configs/anniversary2022_baseline/linear42_compact_cost_20261111/manifest.csv")
    records = {r["instance_key"]: json.loads((args.root / "records" / (r["instance_key"] + ".json")).read_text())
               for r in manifest[:args.through]}
    keys, _, costs, _, _, _ = load()
    rows = read_csv(DATA / "mechanism_R12_20261111/predictions.csv")
    iso_rows, split = read_csv(DATA / "mechanism_R11_20261111/predictions.csv"), read_csv(SPLITS)
    old = json.loads((DATA / "mechanism_R12_20261111/summary.json").read_text())
    assert keys == [r["instance_key"] for r in rows] == [r["instance_key"] for r in iso_rows]
    assert keys == [r["instance_key"] for r in split] == [r["instance_key"] for r in replay_rows]
    assert len(records) == args.through == replay["actually_measured_compact_inputs"]
    known = np.array([k in records for k in keys])
    failed = np.array([k in records and records[k]["status"] != "ok" for k in keys])
    fee = np.array([records[k]["acquisition_CPU_s"] if k in records else 0. for k in keys])
    base_total = float(costs[:, 0].sum())
    results = {}
    for mode in ("iso_diagnostic", "coarse", "fine"):
        name = mode + "_linear42_min3"
        folds = np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows]) if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
        enabled = np.array([old["scores"][name]["cuts"][f]["margin_PAR2_s"] is not None for f in folds])
        actions = np.array([ACTIONS.index(r[name + "_action"]) for r in rows])
        query = np.array([float(r[name + "_decision_CPU_s"]) for r in rows])
        free = costs[np.arange(len(keys)), actions]
        before = timed_cost(free, query, 600)
        assert np.allclose(before, [float(r[name + "_PAR2"]) for r in rows], rtol=0, atol=1e-8)
        affected = failed & enabled
        changed = affected & (actions != 0)
        actions[affected], query[affected] = 0, 0
        selected = costs[np.arange(len(keys)), actions]
        after_fallback = timed_cost(selected, query, 600)
        after_fee = timed_cost(selected, query + fee * enabled, 600)
        assert np.allclose(after_fee, [float(r[mode + "_PAR2"]) for r in replay_rows], rtol=0, atol=1e-8)
        components = {"original_query": float((before - free).sum()),
                      "native_failure_D_fallback": float((after_fallback - before).sum()),
                      "measured_acquisition": float((after_fee - after_fallback).sum())}
        assert np.isclose(sum(components.values()), (after_fee - free).sum(), rtol=0, atol=1e-7)
        cliffs = (after_fallback < 600) & (after_fee >= 600)
        ordinary = (after_fee < 600) & enabled
        ordinary_effect = float(fee[ordinary].sum())
        cliff_effect = float((after_fee - after_fallback)[cliffs].sum())
        assert np.isclose(ordinary_effect + cliff_effect, components["measured_acquisition"], rtol=0, atol=1e-7)
        results[mode] = {
            "free_original_gain_pct": float(100 * (base_total - free.sum()) / base_total),
            "with_original_query_gain_pct": float(100 * (base_total - before.sum()) / base_total),
            "after_native_failures_before_new_fees_gain_pct": float(100 * (base_total - after_fallback.sum()) / base_total),
            "after_measured_fees_gain_pct": float(100 * (base_total - after_fee.sum()) / base_total),
            "incremental_cost_PAR2_seconds": components,
            "incremental_cost_percentage_points_of_D": {k: 100 * v / base_total for k, v in components.items()},
            "fallback_changed_nonD_choices": int(changed.sum()),
            "fallback_rescued_vs_original_choices": int(((before >= 600) & (after_fallback < 600)).sum()),
            "fallback_lost_solves_vs_original_choices": int(((before < 600) & (after_fallback >= 600)).sum()),
            "new_acquisition_cliff_lost_solves": int(cliffs.sum()),
            "ordinary_solved_acquisition_cost_PAR2_s": ordinary_effect,
            "cliff_acquisition_cost_PAR2_s": cliff_effect,
            "new_acquisition_cliff_association_keys": [keys[i] for i in np.flatnonzero(cliffs)],
            "unknown_fee_parents_in_enabled_models": int((~known & enabled).sum()),
            "scope": "Exact arithmetic on the same original OOF choices; unknown fees omitted only in this explicitly incomplete replay. No refitting or threshold changes."
        }
    out = args.root / f"cost_effects_prefix_{args.through}.json"
    assert not out.exists()
    atomic(out, {"status": "complete_cost_effect_diagnosis", "through": args.through,
                 "full_population": len(keys), "remaining_unmeasured": int((~known).sum()),
                 "native_failure_exit_counts": dict(Counter(str(r["native"]["native_exit"]) for r in records.values() if r["status"] != "ok")),
                 "results": results, "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - wall,
                 "source_sha256": sha(__file__), "prefix_sha256": sha(prefix_path),
                 "replay_summary_sha256": sha(replay_root / "summary.json"),
                 "new_model_fits": 0, "new_solver_calls": 0,
                 "claim_scope": "Repeated2022 development replay. Mac feature fees plus publisher cluster solving, not same-machine end-to-end deployment or independent confirmation."})
    print(json.dumps({"output": str(out), "results": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", type=int, required=True)
    parser.add_argument("--root", type=Path, default=DATA / "linear42_compact_cost_v3_20261111")
    main(parser.parse_args())
