# Audit v2 compute log (appended as work is done; summarised in reports/audit_v2/COMPUTE_AUDIT_V2.md)

| step | where | CPU (s) | note |
|---|---|---|---|
| evidence snapshot | cpu-207-159 host | ~5 | hashing committed files |
| strict M3 build (3 runs incl. re-runs after appendix A) | host, analysis venv | ~330 | ~110 s CPU each (54 s user + 21 s sys measured for the first) |
| gate regression tests | host | ~5 | |
| integrity audit | gs-srun container, 48 procs | 311 | 36,077 runs + 1,325 CNF hashes |
| v2 builds (fpc2, fpc2-check) + unit/API tests | gs-srun container, 32 CPUs | ~600 | compile time |
| M3 reproduce round 1 (m3_train.py) | host, analysis venv | ~490 | 3m07 user + 5m13 sys (BLAS threads) |
| M3 revised (m3_train_v2.py) | host, analysis venv | ~470 | 2m58 user + 4m55 sys |
| M3 comparison, feature signal, policy consistency | host | ~120 | |
| M1 overhead retest (864 runs) | 1 exclusive node, 16 workers | see ledger | solver CPU summed from result records in reports/audit_v2/COMPUTE_AUDIT_V2.md |
| retest analysis | host | ~30 | |
| v2 controller integration test (first attempt, killed at 1 h Slurm limit, no conflict limit) | container, 20 procs | ~72000 (upper bound, 20 procs x 1 h) | no result; disclosed |
| v2 controller integration test (conflict limit 1e5) | container, 20 procs | 1495 | 20 instances |
| M0 suite on fpc2/fpc2-check | container, 32 procs | ~1500 | 7,838 checks |
| M5 independent recheck | host | ~22 | |
| family effects table | host | ~10 | |
