#!/usr/bin/env bash
# Audit v2: one command that reproduces the revised M3 analysis from the committed
# run CSVs and the raw telemetry under $FP_DATA (read-only):
#   strict gate -> reproduce round 1 -> revised M3 (no x_saved_flip_frac) -> comparison
#   -> univariate signal without the flip feature -> Python/C++ policy consistency
#
#   scripts/audit_v2/run_m3_revision.sh [outdir]      (default: reports/audit_v2/m3_rerun)
#
# Needs: analysis venv ($FP_PY), build/fpc2 (scripts/build_solver.sh fpc2) for the C++ check.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT="${1:-reports/audit_v2/m3_rerun}"
PY="${FP_PY:-/mnt/data/zhaofeng/venvs/online-tuning-forcephase/bin/python}"
mkdir -p "$OUT"/reproduce_round1 "$OUT"/revised "$OUT"/policies "$OUT"/policies_round1_copy
"$PY" scripts/audit_v2/m3_build_strict.py --runs results/m2_census/runs.csv --runs results/m3_replay/runs.csv \
  --static results/static_features_dev.csv --out "$OUT/dataset_strict.csv" --report "$OUT/gate_summary.md" > /dev/null
"$PY" scripts/m3_train.py --dataset results/m3/dataset.csv --census results/m2_census/runs.csv \
  --static results/static_features_dev.csv --out "$OUT/reproduce_round1" --policy-dir "$OUT/policies_round1_copy" > /dev/null
"$PY" scripts/audit_v2/m3_train_v2.py --dataset "$OUT/dataset_strict.csv" --census results/m2_census/runs.csv \
  --static results/static_features_dev.csv --folds reports/m3/folds.csv --out "$OUT/revised" \
  --policy-dir "$OUT/policies" > /dev/null
"$PY" scripts/audit_v2/m3_compare.py --round1 reports/m3/selectors.csv \
  --reproduced "$OUT/reproduce_round1/selectors.csv" --revised "$OUT/revised/selectors.csv" \
  --costs-revised "$OUT/revised/oof_costs.csv" --out "$OUT/comparison.md" > /dev/null
"$PY" - "$OUT" <<'EOF'
import sys, pandas as pd
out = sys.argv[1]
pd.read_csv(f"{out}/dataset_strict.csv", dtype={"instance": str}).drop(columns=["f_x_saved_flip_frac"]) \
  .to_csv(f"{out}/dataset_noflip.csv", index=False)
EOF
"$PY" scripts/m3_feature_signal.py --dataset "$OUT/dataset_noflip.csv" --out "$OUT/feature_signal.md" > /dev/null
if [ ! -x build/controller_unit ]; then
  g++ -O2 -static -Ibuild/fpc2/src/src -o build/controller_unit tests/audit_v2/controller_unit.cpp build/fpc2/src/build/libcadical.a
fi
"$PY" scripts/audit_v2/policy_consistency.py --dataset "$OUT/dataset_strict.csv" --census results/m2_census/runs.csv \
  --unit build/controller_unit --out "$OUT/policy_consistency.md" > /dev/null
rm -f "$OUT/dataset_noflip.csv"
echo "done: $OUT (gate_summary.md, comparison.md, revised/selectors.csv, feature_signal.md, policy_consistency.md)"
