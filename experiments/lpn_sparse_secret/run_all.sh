#!/usr/bin/env bash
# End-to-end LPN sparse-secret experiment: build -> reduction test ->
# generate instances (checked against pre-registered SHA-256) -> planted
# pass -> random pass -> LPN semantics check -> model/proof verification ->
# Q1-Q5 analysis. Resumable: re-running skips finished runs.
#
#   experiments/lpn_sparse_secret/run_all.sh                    # formal grid
#   GRID=smoke T=10 experiments/lpn_sparse_secret/run_all.sh    # ~5 min check
#
# Environment (defaults in brackets):
#   GRID [sparse_main]   grid name in lpn_gen.py
#   EXP [lpn_$GRID]      experiment id (results/<EXP>/, $LPN_WORK/runs/<EXP>/)
#   T [120]              per-run CPU cutoff in seconds
#   WORKERS [ncpu-2]     concurrent solver processes (one core each)
#   QUIET_LOAD [WORKERS+8]  wait before each launch while 1-min load >= this
#   MAX_WALL_HOURS [5]   wall-clock cap per pass (planted, random)
#   CONFIGS [D,Im,Fm,Fp,Im_noR]
#   VERIFY_WORKERS [4]   parallel proof checks (each LRAT proof can be GBs)
#   LPN_WORK, LPN_CADICAL, LPN_LRAT_CHECK   see fplib.py / build.sh
#   SKIP_BUILD=1, SKIP_TEST=1
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
PY="${PYTHON:-python3}"
GRID="${GRID:-sparse_main}"
EXP="${EXP:-lpn_$GRID}"
T="${T:-120}"
NCPU="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 8)"
WORKERS="${WORKERS:-$(( NCPU > 3 ? NCPU - 2 : 1 ))}"
QUIET_LOAD="${QUIET_LOAD:-$(( WORKERS + 8 ))}"
MAX_WALL_HOURS="${MAX_WALL_HOURS:-5}"
CONFIGS="${CONFIGS:-D,Im,Fm,Fp,Im_noR}"
keep_awake() { if command -v caffeinate >/dev/null; then caffeinate -i "$@"; else "$@"; fi; }

echo "== $EXP: grid=$GRID T=${T}s workers=$WORKERS quiet_load=$QUIET_LOAD cap=${MAX_WALL_HOURS}h/pass"
[ "${SKIP_BUILD:-0}" = 1 ] || ./build.sh
[ "${SKIP_TEST:-0}" = 1 ] || "$PY" test_reduction.py

M="benchmarks/lpn_$GRID.csv"
"$PY" lpn_gen.py --grid "$GRID" --manifest "$M"
"$PY" - "$GRID" <<'EOF'
import csv, json, sys
from pathlib import Path
grid = sys.argv[1]
base = Path("benchmarks")
fetch = {json.loads(l)["hash"]: json.loads(l)["sha256_cnf"] for l in open(base / f"lpn_{grid}_fetch.jsonl")}
exp = base / "expected" / f"lpn_{grid}.sha256.jsonl"
if exp.exists():  # determinism: generated CNFs must match the pre-registered ones
    want = {json.loads(l)["hash"]: json.loads(l)["sha256_cnf"] for l in open(exp)}
    bad = [h for h in want if fetch.get(h) != want[h]]
    if bad or set(fetch) != set(want):
        sys.exit(f"generated instances differ from {exp}: {len(bad)} mismatches, e.g. {bad[:3]}")
    print(f"{len(want)} generated CNFs match the pre-registered SHA-256")
rows = list(csv.DictReader(open(base / f"lpn_{grid}.csv")))
for kind in ("planted", "random"):
    sub = [r for r in rows if r["kind"] == kind]
    with open(base / f"lpn_{grid}_{kind}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sub)
    with open(base / f"lpn_{grid}_{kind}_fetch.jsonl", "w") as f:
        for r in sub:
            f.write(json.dumps({"hash": r["hash"], "sha256_cnf": fetch[r["hash"]]}) + "\n")
EOF

# planted first (Q1-Q3), then random (Q4); the second invocation of each
# pass re-runs contended runs and finishes anything a wall cap cut short
for kind in planted random; do
  for cap in "$MAX_WALL_HOURS" 1; do
    keep_awake "$PY" run_matrix.py --exp "$EXP" --manifest "benchmarks/lpn_${GRID}_${kind}.csv" \
      --configs "$CONFIGS" --seeds 0 --timeout "$T" --workers "$WORKERS" \
      --quiet-load "$QUIET_LOAD" --max-wall-hours "$cap"
  done
done

"$PY" lpn_check.py --exp "$EXP"          # must precede verify_runs.py (it strips witnesses)
"$PY" verify_runs.py --exp "$EXP" --workers "${VERIFY_WORKERS:-4}"
"$PY" analyze.py --exp "$EXP" --manifest "$M"
echo "== done: results/$EXP/predictions.md"
