"""Full4719 original OOF replay after the fixed68 CPU-failure retry cohort ends."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .common import sha
from .measure_compact_prefetch import atomic, CONFIG
from .predict_relative_cost import SPLITS
from .recover_compact_cpu import ORIGINAL, OUT
from .score_interpretable_two_percent import evaluate
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def main(args):
    start, cpu = time.monotonic(), time.process_time()
    completion = json.loads((args.root / "completion.json").read_text())
    assert completion["status"] == "complete" and completion["cohort"] == 68
    assert not (args.root / "scores.json").exists()
    cohort = json.loads((args.root / "cohort.json").read_text())
    policy = json.loads((args.root / "policy.json").read_text())
    manifest = read_csv(CONFIG / "manifest.csv")
    first = {r["instance_key"]: json.loads((ORIGINAL / "records" / (r["instance_key"] + ".json")).read_text()) for r in manifest}
    retry = {r["instance_key"]: json.loads((args.root / "records" / (r["instance_key"] + ".json")).read_text()) for r in cohort["cohort"]}
    assert len(first) == 4719 and len(retry) == 68
    for key, row in retry.items():
        assert first[key]["native"]["native_exit"] == -24
        assert row["first_record_sha256"] == sha(ORIGINAL / "records" / (key + ".json"))
        assert row["retry"]["native_binary_sha256"] == policy["retry_binary_sha256"]
        assert row["status"] != "ok" or row["model_input_float32_match"]
    keys, _, costs, _, _, _ = load()
    split = read_csv(SPLITS)
    original = read_csv(DATA / "mechanism_R12_20261111/predictions.csv")
    iso = read_csv(DATA / "mechanism_R11_20261111/predictions.csv")
    previous = read_csv(ORIGINAL / "replay_prefix_4719/predictions.csv")
    summary = json.loads((DATA / "mechanism_R12_20261111/summary.json").read_text())
    assert all([r["instance_key"] for r in rows] == keys for rows in (split, original, iso, previous))
    coarse = np.array([r["coarse_group"] for r in split]); fine = np.array([r["fine_group"] for r in split])
    first_fee = np.array([first[k]["acquisition_CPU_s"] for k in keys])
    second_fee = np.array([retry[k]["retry_acquisition_CPU_s"] if k in retry else 0. for k in keys])
    restored = np.array([k in retry and retry[k]["status"] == "ok" for k in keys])
    failed = np.array([first[k]["status"] != "ok" for k in keys]) & ~restored
    result, rows = {}, [{"instance_key": k, "restored_input": bool(restored[i]),
        "first_acquisition_CPU_s": float(first_fee[i]), "second_acquisition_CPU_s": float(second_fee[i]),
        "still_failed_paidD": bool(failed[i])} for i, k in enumerate(keys)]
    for mode in ("iso_diagnostic", "coarse", "fine"):
        name = mode + "_linear42_min3"
        folds = np.array([int(r["diagnostic_iso_fold"]) for r in iso]) if mode == "iso_diagnostic" else np.array([int(r[mode + "_fold"]) for r in split])
        enabled = np.array([summary["scores"][name]["cuts"][f]["margin_PAR2_s"] is not None for f in folds])
        actions = np.array([ACTIONS.index(r[name + "_action"]) for r in original])
        query = np.array([float(r[name + "_decision_CPU_s"]) for r in original])
        actions[failed & enabled], query[failed & enabled] = 0, 0
        selected = costs[np.arange(len(keys)), actions]
        before_second_fee = timed_cost(selected, query + first_fee * enabled, 600)
        paid = timed_cost(selected, query + (first_fee + second_fee) * enabled, 600)
        old = np.array([float(r[mode + "_PAR2"]) for r in previous])
        groups = fine if mode == "fine" else coarse
        score = evaluate(costs[:, 0], paid, groups, coarse, mode)
        score["over_one_attempt_candidate"] = evaluate(old, paid, groups, coarse, mode)
        score["actions"] = {a: int((actions == j).sum()) for j, a in enumerate(ACTIONS)}
        changes, added_fee = float((before_second_fee - old).sum()), float((paid - before_second_fee).sum())
        assert np.isclose(changes + added_fee, (paid - old).sum(), rtol=0, atol=1e-7)
        cliffs = (before_second_fee < 600) & (paid >= 600)
        score["cost_decomposition"] = {"restored_predictions_including_query_PAR2_delta_s": changes,
            "extra_acquisition_PAR2_delta_s": added_fee,
            "extra_acquisition_cliff_lost_solves": int(cliffs.sum()),
            "rescued_vs_one_attempt": int(((old >= 600) & (paid < 600)).sum()),
            "lost_vs_one_attempt": int(((old < 600) & (paid >= 600)).sum()),
            "unknown_fee_inputs": 0}
        score["mixed_two_percent_screen"] = bool(score["gain_pct"] >= 2 and
            score.get("exact_eight_block_95_pct", score["block_interval_95_pct"])[0] > 0) if mode == "iso_diagnostic" else None
        result[mode] = score
        for i, row in enumerate(rows):
            row[mode + "_action"], row[mode + "_PAR2"] = ACTIONS[actions[i]], float(paid[i])
        print(f"CPU_RETRY {mode}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}", flush=True)
    write_csv(args.root / "predictions.csv", rows)
    atomic(args.root / "scores.json", {"status": "complete", "parents": len(keys), "recovery_cohort": 68,
        "restored_inputs": int(restored.sum()), "still_failed_paidD": int(failed.sum()), "scores": result,
        "fixed_controls_mean_PAR2_s": {a: float(costs[:, i].mean()) for i, a in enumerate(ACTIONS)},
        "first_acquisition_CPU_sum_s": float(first_fee.sum()), "retry_acquisition_CPU_sum_s": float(second_fee.sum()),
        "CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
        "source_sha256": sha(__file__), "cohort_sha256": sha(args.root / "cohort.json"),
        "policy_sha256": sha(args.root / "policy.json"), "new_solver_calls": 0, "new_model_fits": 0,
        "scope": "All4719 repeated2022 development original OOF choices, both attempts charged. Nominal intervals, Mac features plus publisher cluster times, not independent or same-machine solver deployment."})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=OUT)
    main(p.parse_args())
