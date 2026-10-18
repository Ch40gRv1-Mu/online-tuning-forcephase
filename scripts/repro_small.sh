#!/usr/bin/env bash
# Small end-to-end reproduction from a clean checkout (about 10 minutes on 8 cores):
#   1. build the pinned solver variants and the checkers
#   2. run the quick M0 correctness/semantics suite
#   3. download the 20 smoke instances (if missing) and run the smoke experiment locally
#      (D, I-, F-, F+; 10 s; LRAT proofs; verification)
#   4. collect the records and produce the M2-style tables/figures for the smoke data
#
#   scripts/repro_small.sh [outdir]      (default: $FP_DATA/repro_small)
#
# Needs: g++/gcc, make, python3 (stdlib), xz; for step 4 the analysis venv
# (numpy/pandas/matplotlib, see pyproject.toml) at $FP_PY or 'python3' with those packages.
# Results of step 3 are shared with the main ledger (content-addressed run ids), so
# re-running is cheap and never overwrites existing records.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FP_DATA="${FP_DATA:-/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase}"
OUT="${1:-$FP_DATA/repro_small}"
PY="${FP_PY:-/mnt/data/zhaofeng/venvs/online-tuning-forcephase/bin/python}"
JOBS="${JOBS:-8}"
mkdir -p "$OUT"
cd "$ROOT"
git submodule update --init third_party/cadical third_party/lrat-trim third_party/drat-trim
JOBS=$JOBS scripts/build_solver.sh
scripts/build_tools.sh
g++ -O2 -static -Ibuild/fpc/src/src -o build/api_phase_test tests/api_phase_test.cpp build/fpc/src/build/libcadical.a
FP_TMP="$OUT" python3 tests/m0_suite.py --quick --jobs "$JOBS" --out "$OUT/m0"
# smoke instances
python3 - <<'EOF'
import csv, os, subprocess, sys
root = os.getcwd()
need = [l.strip() for l in open("benchmarks/smoke20.txt") if l.strip() and not l.startswith("#")]
data = os.environ["FP_DATA"]
missing = [h for h in need if not os.path.exists(os.path.join(data, "benchmarks", "cnf", h + ".cnf.xz"))]
if missing:
    print(f"downloading {len(missing)} smoke instances")
    subprocess.run([sys.executable, "scripts/fetch_benchmarks.py", "--splits", "train", "--jobs", "4",
                    "--hash-file", "benchmarks/smoke20.txt"], check=True)
EOF
python3 scripts/fprun.py run --exp configs/experiments/smoke.json --jobs "$JOBS"
python3 scripts/fprun.py status --exp configs/experiments/smoke.json
python3 scripts/collect.py --exp configs/experiments/smoke.json --out "$OUT/smoke_runs.csv"
"$PY" - "$OUT" <<'EOF'
import sys, pandas as pd
out = sys.argv[1]
d = pd.read_csv(f"{out}/smoke_runs.csv")
d["split"] = "train"  # smoke instances are train instances; analysis script reads train+val
d.to_csv(f"{out}/smoke_runs_for_analysis.csv", index=False)
EOF
"$PY" scripts/analyze_m2.py --runs "$OUT/smoke_runs_for_analysis.csv" --out "$OUT/smoke_m2" > "$OUT/smoke_m2.log"
echo "done: $OUT (m0/m0_report.json, smoke_runs.csv, smoke_m2/tables.md, smoke_m2/figures/)"
