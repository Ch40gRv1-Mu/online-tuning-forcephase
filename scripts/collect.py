#!/usr/bin/env python3
"""Collect run records of experiments into a flat CSV (stdlib only).

  scripts/collect.py --exp configs/experiments/X.json [--exp ...] --out results/X/runs.csv

One row per planned run (missing runs are listed with status 'missing', so
nothing silently disappears).  PAR2 per run = CPU seconds if status is
'solved', otherwise 2T.  The CSV is small and committed; raw logs stay in
$FP_DATA/runs/raw/<id[:2]>/<id>/.
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fprun  # noqa: E402

FIELDS = ["run_id", "exp", "config", "instance", "family", "family_group", "split", "temporal_tag",
          "gbd_result", "variant", "seed", "repeat", "timeout", "status", "result", "cpu", "wall", "par2",
          "exit_code", "terminated_by", "conflicts", "decisions", "propagations", "restarts", "rephased",
          "maxrss_kb", "verify_method", "verify_ok", "verify_cpu", "proof_bytes", "host", "core",
          "slurm_job", "switches", "applied_at", "occ_conflicts_a0", "occ_conflicts_a1", "occ_time_a0",
          "occ_time_a1", "hook_time", "dec_free", "dec_neg", "decision_slot", "decision_score",
          "checkpoints_crossed", "start_utc"]


def row_of(run, rec, man):
    key = run["key"]
    m = man.get(key["instance"], {})
    r = {"run_id": run["run_id"], "exp": run["exp"], "config": run["config"], "instance": key["instance"],
         "family": m.get("family"), "family_group": m.get("family_group"), "split": m.get("split"),
         "temporal_tag": m.get("temporal_tag"), "gbd_result": m.get("result"), "variant": key["variant"],
         "seed": key["seed"], "repeat": key.get("repeat", 0), "timeout": key["timeout"]}
    if rec is None:
        r["status"] = "missing"
        return r
    T = key["timeout"]
    st = rec["stats"]
    tel = rec.get("telemetry") or {}
    fin = tel.get("final") or {}
    dec = tel.get("decision") or {}
    r.update({
        "status": rec["status"], "result": rec["result"], "cpu": round(rec["cpu"], 4), "wall": round(rec["wall"], 4),
        "par2": round(rec["cpu"], 4) if rec["status"] == "solved" else 2 * T,
        "exit_code": rec["exit_code"], "terminated_by": rec["terminated_by"],
        "conflicts": st.get("conflicts"), "decisions": st.get("decisions"), "propagations": st.get("propagations"),
        "restarts": st.get("restarts"), "rephased": st.get("rephased"), "maxrss_kb": rec["maxrss_kb"],
        "verify_method": rec["verification"].get("method"), "verify_ok": rec["verification"].get("ok"),
        "verify_cpu": round(rec["verification"].get("cpu", 0), 4),
        "proof_bytes": (rec.get("proof") or {}).get("bytes"), "host": rec["host"], "core": rec["core"],
        "slurm_job": rec.get("slurm_job"), "switches": fin.get("switches"), "applied_at": fin.get("applied_at"),
        "occ_conflicts_a0": (fin.get("occ_conflicts") or [None, None])[0],
        "occ_conflicts_a1": (fin.get("occ_conflicts") or [None, None])[1],
        "occ_time_a0": (fin.get("occ_time") or [None, None])[0],
        "occ_time_a1": (fin.get("occ_time") or [None, None])[1],
        "hook_time": fin.get("hook_time"), "dec_free": fin.get("dec_free"), "dec_neg": fin.get("dec_neg"),
        "decision_slot": dec.get("slot"), "decision_score": dec.get("score"),
        "checkpoints_crossed": max([c["crossed"][1] for c in tel.get("checkpoints") or []], default=0),
        "start_utc": rec["start_utc"],
    })
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", action="append", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    man = fprun.manifest()
    rows = []
    seen = set()
    for e in a.exp:
        exp = fprun.load_experiment(e)
        for run in fprun.plan(exp, man):
            if run["run_id"] in seen:
                continue
            seen.add(run["run_id"])
            p = fprun.result_path(run["run_id"])
            rec = fprun.load_json(p) if os.path.exists(p) else None
            rows.append(row_of(run, rec, man))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{len(rows)} rows -> {a.out} {counts}")


if __name__ == "__main__":
    main()
