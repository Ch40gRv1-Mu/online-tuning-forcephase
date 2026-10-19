#!/usr/bin/env python3
"""Audit v2, step 0: record the identity of all first-round evidence.

  scripts/audit_v2/evidence_snapshot.py --out results/audit_v2/evidence_snapshot.json

Hashes (SHA-256) every committed first-round artefact that later steps read or
must not change (run CSVs, M3 dataset/folds/selectors, policies, freeze file,
experiment specs, manifests, report tables/numbers), the build identities
(BUILDINFO + binary hash), and counts of the external run records.  Nothing is
modified.
"""

import argparse
import glob
import hashlib
import json
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.environ.get("FP_DATA", "/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase")
PATTERNS = ["results/*/runs.csv", "results/m3/dataset.csv", "results/static_features_*.csv",
            "results/m0/m0_report.json", "reports/m3/*.csv", "reports/*/numbers.json", "reports/*/tables.md",
            "reports/m3/rq3.md", "reports/m3/feature_signal.md", "reports/m2/encoding.md",
            "configs/policies/*", "configs/m5_freeze.json", "configs/experiments/*.json",
            "configs/solver_configs.json", "benchmarks/*.csv", "benchmarks/derived/*.txt",
            "patches/*.patch", "solver/*.hpp", "solver/*.cpp", "scripts/*.py", "scripts/*.sh",
            "reports/*.md"]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    files = {}
    for pat in PATTERNS:
        for p in sorted(glob.glob(os.path.join(ROOT, pat))):
            rel = os.path.relpath(p, ROOT)
            if os.path.isfile(p) and "audit_v2" not in rel:
                files[rel] = {"sha256": sha(p), "bytes": os.path.getsize(p)}
    builds = {}
    for b in sorted(glob.glob(os.path.join(ROOT, "build", "*", "BUILDINFO"))):
        info = dict(l.strip().split("=", 1) for l in open(b) if "=" in l)
        binp = os.path.join(os.path.dirname(b), "cadical")
        builds[os.path.basename(os.path.dirname(b))] = {
            "buildinfo": info, "binary_sha256_actual": sha(binp) if os.path.exists(binp) else None}
    results = glob.glob(os.path.join(DATA, "runs", "results", "*", "*.json"))
    snap = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_head": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "first_round_commit": "c2380c0974dfe8d8a51048b2e8c25a870d5ce6c5",
        "m5_freeze_tag": git("rev-parse", "m5-freeze"),
        "submodules": git("submodule", "status"),
        "fp_data": DATA, "external_result_records": len(results),
        "external_attempt_logs": len(glob.glob(os.path.join(DATA, "runs", "attempts", "*.jsonl"))),
        "files": files, "builds": builds,
        "seen_evaluation_sets": {"test": "seen in round 1 (M5, 2026-10-19)", "t2026": "seen in round 1 (M5)"},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(snap, f, indent=1, sort_keys=True)
    print(f"{len(files)} files, {len(builds)} builds, {len(results)} result records -> {a.out}")


if __name__ == "__main__":
    main()
