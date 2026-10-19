#!/usr/bin/env bash
# Submit the audit v2 overhead retest: one exclusive cpu-low node, gs-srun container,
# scripts/audit_v2/overhead_retest.py (16 workers, one per CCD).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FP_DATA="${FP_DATA:-/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase}"
PY="${FP_PY:-/mnt/data/zhaofeng/venvs/online-tuning-forcephase/bin/python}"
mkdir -p "$FP_DATA/logs/slurm"
sbatch --parsable --job-name=fp-audit-m1 --partition=cpu-low --nodes=1 --ntasks=1 --exclusive --mem=0 \
  --time=12:00:00 --output="$FP_DATA/logs/slurm/audit_v2_m1-%j.out" --error="$FP_DATA/logs/slurm/audit_v2_m1-%j.err" \
  --export=ALL,FP_DATA="$FP_DATA",FP_ROOT="$ROOT",FP_PY="$PY" <<'EOS'
#!/usr/bin/env bash
source /mnt/data/shared/config/env.sh
export GENESIS_IMAGE_VER="${GENESIS_IMAGE_VER:-1_26}"
echo "retest on $(hostname) at $(date -u)"
gs-srun --ntasks=1 --cpus-per-task="$SLURM_CPUS_ON_NODE" \
  bash -c "cd '$FP_ROOT' && FP_LOCAL=/tmp/fp_local_\$USER '$FP_PY' scripts/audit_v2/overhead_retest.py --workers 16"
echo "finished at $(date -u)"
EOS
