# Audit v2 reproduction chain from a clean clone (executed 2026-10-19)

Clone: `git clone -b research/forcephase-study` at commit `a94a989` into `/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase/repro_check_v2/src`; run inside the gs-srun container
(1 node, 32 CPUs) by:

    FP_DATA=/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase/repro_check_v2/data scripts/repro_small.sh /mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase/repro_check_v2/out_small          # separate data root
    FP_DATA=/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase scripts/audit_v2/run_m3_revision.sh /mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase/repro_check_v2/out_m3

Log: [repro_chain.log](repro_chain.log). Wall 489 s, CPU 2,057 s (both steps).

1. `repro_small.sh`: built all six solver variants (upstream, fpc, fpc2 and the assertion builds) and the tools,
   quick M0 suite **0 failures**, downloaded the 20 smoke instances into the fresh data root, ran D/I−/F−/F+ at 10 s
   with LRAT proofs and verification: **29 solved / 51 timeout** (same as the original smoke run), collected and
   produced the M2-style tables and figures.
2. `run_m3_revision.sh` (revised M3 analysis from the committed run CSVs + raw telemetry, read-only):
   identical to the committed audit-v2 outputs: strict gate summary, revised out-of-fold costs
   (`revised/oof_costs.csv`), round-1/revised comparison, policy consistency report — byte-identical;
   `revised/selectors.csv` and `reproduce_round1/selectors.csv` identical in every column (PAR2, solved, CIs,
   number of switches, chosen models) except the diagnostic `wAUC` (max |Δ| 0.0023), which is computed from
   continuous scores of logistic fits whose last bits depend on the BLAS threading of the machine; the univariate
   signal table identical (header line now set by the script).

This re-analyses existing records; it does not re-run the round-1 solver experiments (M2–M5).
