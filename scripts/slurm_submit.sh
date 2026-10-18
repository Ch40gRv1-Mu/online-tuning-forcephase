#!/usr/bin/env bash
# Submit an experiment as a Slurm array of exclusive CPU nodes; every task
# runs one shard of 'scripts/fprun.py run' inside the gs-srun container.
#
#   scripts/slurm_submit.sh <experiment.json>[,<experiment.json>...] <num_nodes> [jobs_per_node=48] [partition=cpu-low] [time=24:00:00]
#
# Logs: $FP_DATA/logs/slurm/<exp>-<jobid>_<task>.{out,err}.  Resumable:
# resubmitting skips runs with existing results.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXP="$(for e in ${1//,/ }; do realpath "$e"; done | paste -sd,)"; N="$2"; JOBS="${3:-48}"; PART="${4:-cpu-low}"; TIME="${5:-24:00:00}"
FP_DATA="${FP_DATA:-/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase}"
NAME="$(python3 -c "import json,sys; n=[json.load(open(p))['name'] for p in sys.argv[1].split(',')]; print(n[0] if len(n)==1 else n[0]+'-plus'+str(len(n)-1))" "$EXP")"
mkdir -p "$FP_DATA/logs/slurm"
sbatch --parsable --job-name="fp-$NAME" --partition="$PART" --nodes=1 --ntasks=1 --exclusive \
  --mem=0 --time="$TIME" --array="0-$((N-1))" \
  --output="$FP_DATA/logs/slurm/$NAME-%A_%a.out" --error="$FP_DATA/logs/slurm/$NAME-%A_%a.err" \
  --export=ALL,FP_DATA="$FP_DATA",FP_EXP="$EXP",FP_N="$N",FP_JOBS="$JOBS",FP_ROOT="$ROOT" <<'EOS'
#!/usr/bin/env bash
source /mnt/data/shared/config/env.sh
export GENESIS_IMAGE_VER="${GENESIS_IMAGE_VER:-1_26}"
echo "task $SLURM_ARRAY_TASK_ID/$FP_N on $(hostname) at $(date -u)"
gs-srun --ntasks=1 --cpus-per-task="$SLURM_CPUS_ON_NODE" \
  bash -c "cd '$FP_ROOT' && FP_LOCAL=/tmp/fp_local_\$USER python3 scripts/fprun.py run --exp '$FP_EXP' --shard $SLURM_ARRAY_TASK_ID/$FP_N --jobs $FP_JOBS"
echo "finished at $(date -u)"
EOS
