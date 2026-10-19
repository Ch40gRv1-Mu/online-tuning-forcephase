# Data location

Large runtime data is kept outside git under

    FP_DATA=/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase

(override with the `FP_DATA` environment variable; scripts default to this path).

| Path under `$FP_DATA` | Content | Produced by |
|---|---|---|
| `benchmarks/gbd/{meta,base}.db` | GBD metadata snapshots (SHA-256 in `benchmarks/SOURCES.md`) | manual download |
| `benchmarks/cnf/<hash>.cnf.xz` | instances (≈ 1325 files) | `scripts/fetch_benchmarks.py` |
| `runs/results/<id[:2]>/<id>.json` | one immutable record per run (status, CPU, verification, stats, telemetry summary) | `scripts/fprun.py` |
| `runs/raw/<id[:2]>/<id>/` | gzip'ed solver stdout/stderr, telemetry JSONL, checker output | `scripts/fprun.py` |
| `runs/attempts/*.jsonl` | every attempt (start/done/runner-error) for the compute ledger | `scripts/fprun.py` |
| `logs/slurm/` | Slurm job stdout/stderr | `scripts/slurm_submit.sh` |
| `logs/` | other job logs (downloads) | scripts |
| `repro_check/` | clean-clone reproduction test (clone, its own `FP_DATA`, outputs, log) | `scripts/repro_small.sh` |

Node-local scratch (not persistent): `FP_LOCAL=/tmp/fp_local_$USER` inside the gs-srun container (tmpfs) holds
decompressed/scrambled CNFs and LRAT proofs; proofs are deleted after checking (size recorded).

Python analysis environment: `/mnt/data/zhaofeng/venvs/online-tuning-forcephase` (created inside the
container with `UV_PROJECT_ENVIRONMENT=... uv sync` from `pyproject.toml`/`uv.lock`; uv cache
`/mnt/data/zhaofeng/uv_cache`).

Small, committed summaries live in the repository: `results/<experiment>/runs.csv` (one row per planned run,
with run id pointing to the raw record), `results/static_features_*.csv`, `results/m0/`, and `reports/`.
No data was migrated; nothing in the repository is a symlink into `$FP_DATA`.
