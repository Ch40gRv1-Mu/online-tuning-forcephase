# Audit v2 compute log (appended as work is done; summarised in reports/audit_v2/COMPUTE_AUDIT_V2.md)

| step | where | CPU (s) | note |
|---|---|---|---|
| evidence snapshot | cpu-207-159 host | ~5 | hashing committed files |
| strict M3 build (3 runs incl. re-runs after appendix A) | host, analysis venv | ~330 | ~110 s CPU each (54 s user + 21 s sys measured for the first) |
| gate regression tests | host | ~5 | |
| integrity audit | gs-srun container, 48 procs | 311 | 36,077 runs + 1,325 CNF hashes |
