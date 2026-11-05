# TA dynamic prefix implementation v1

Frozen before any build or probe execution. Central experiment owner is root; this implementation does not create a second experiment owner. Public fit/feedback manifests only; all node shares together remain within 1 CPU hour for this dynamic stage and the project ledger.

## Observer and source identity

- Qualified base `fpcontrol.cpp`: `d6194cc12ff5a6c570a767053f1bc8460440e3f27bd25576b0164987470bc770`.
- Existing remote FPC2 binary: `b619194fdfd455e8d64f52d8234e0cb0652035acf2214853e1d0ebca6b4e52fd`.
- Existing Linux CPU helper: `7b0e95364847b13f54268cd2b2f5e383839169ca0a613460b05e202c11d8d3e2`.
- The deterministic `dynamic_probe.py patch-observer` transformation adds only `observer="ta-probe-v1"` to the header and checkpoint `learned=now.learned` plus `process_cpu_s=absolute_process_time()`. Expected transformed source SHA: `d92d0ef0638397fb6eddaad64a5b2d8619e8cf5d805d9f56dd469005bef16015`.
- This preserves all existing search code, feature formulas, controller parameters and observation/action order. Existing FPC2 records lack the checkpoint event count and absolute CPU field; they are not silently treated as compatible observations. Terminal learned counts cannot establish event counts at the earlier checkpoint.
- Build a separate copy of `build/fpc2-source`, replace only its `src/fpcontrol.cpp` with the transformed source, then GNU make `cadical` with one compiler slot. Do not replace `bin/cadical-fpc2`, old sources, or receipts. Record build CPU/wall, compiler, transformed source and new binary SHA before task-manifest creation.

## Exact invocation

The internal child sets 1.5GiB address space, a 1GiB output-file cap, a 3CPU hard fallback and `FPC_LOG` to its exclusive trace. It execs:

```text
cpu-budget-exec-v1 2 cadical-ta-probe-v1
  --phase=1 --forcephase=0 --fpc=3 --fpctrack=0
  --fpca0=0 --fpca1=0 --fpcinit=0 --fpcat=1000
  --fpcperiod=0 --fpcmaxsw=1 --fpcrlim=0 --fpcwin=2000000000
  --seed=0 --stats INPUT.cnf
```

The no-op schedule uses NATIVE for both slots. The checkpoint precedes its first schedule event. The helper subtracts already consumed process CPU using `CLOCK_PROCESS_CPUTIME_ID` and sets `ITIMER_PROF` across exec, including parsing. An external 10-second watchdog kills the process group. The parent polls the flushed trace and terminates after the first checkpoint; it does not run a terminal phase-comparison matrix.

The owner launches `dynamic_probe.py run --manifest MANIFEST --solver BINARY --cpu-helper HELPER --observer-source TRANSFORMED_SOURCE --output-dir EXCLUSIVE_OUTPUT --node-id NODE --cpu-set ALLOCATED_FREE_CPUS --max-workers N [--input-cache CACHE]`.

## Manifest, eligibility and receipts

- Manifest binds experiment/shard/node, exact profile, solver/helper/source SHA and the owner's `allocated_cpu_s` share (positive and at most 3600). Task identity hashes input SHA, instance id, full profile and all three method SHA values. The central owner assigns disjoint tasks; nodes never steal or auto-claim another shard.
- Each task contains only public URL, input SHA, role and public metadata. Identity is established by mandatory raw SHA; actual decompressed size remains capped at 100000000 bytes. The task's byte count must use the frozen public checksum list's exact `bytes_cnf` value, rather than the different GBD catalogue `bytes` field; the input loader retains its strict size consistency check. Only fit/feedback are accepted, never gate/test or TA times/winners.
- A complete vector requires the first natural restart record crossing 1000 conflicts, NATIVE action before any switch, absolute process CPU at most 2, at least 20 learned clauses, and all six finite values. Missing denominators and insufficient events retain missing status and fall back to static prediction.
- The six fields are `d_glue_mean ← c_glue_mean`, `d_raw_glue_low_fraction ← c_glue_low_frac`, `d_glue_fast_slow_ratio ← x_glue_ratio`, `d_minimized_learned_length ← c_minsize_mean`, `d_backtrack_target_level ← x_level_avg`, and `d_backjump_span ← c_backjump_mean`. Definitions remain those of the qualified FPC2 source; raw CaDiCaL glue is not relabelled as classic LBD.
- Early terminal results preceding the checkpoint are `EARLY_SOLVED_UNVERIFIED`, no dynamic vector, `answer_adopted=false`; no newly produced SAT/UNSAT answer becomes a label or claim of verified solution. Existing TA labels alone drive scoring. If another branch later adopts early answers it must add and charge model/proof verification under a separately frozen contract.
- Receipt contains `id/instance_id`, role/input SHA, node/platform, all method SHA, full profile, status/reason, six features or missing, raw checkpoint, child CPU/wall, preparation CPU/wall, controller CPU, total accounted CPU, exit/termination and telemetry SHA. Its own canonical content SHA binds the immutable result. Raw trace is retained separately. FAILED, MISSING and resource failures remain charged.
- Output uses a whole-owner flock and immutable manifest binding, per-task inflight markers, atomic receipt/progress checkpoints, strict SHA reuse including failed attempts, and no automatic requeue of unresolved work after SSH loss.

## Scheduling and budget

At most eight workers, each confined to central-owner allocated free CPUs. Limit further by actual spare RAM after 2GiB reserve and 1.5GiB per probe, and by free disk after 12GiB floor plus 1GiB output/256MiB preparation per task. Static extraction and probes share the same node allocation; three static workers do not permit eight additional probes. Parent owner additionally reserves across processes/nodes.

Before admitting each task the node reserves 60CPU seconds from its allocated share, releases unused reservation after its charged receipt, and stops admission if the remaining allocation cannot cover a reservation. Root merges node/build costs into the shared ledger. This conservative admission amount does not extend the solver's 2CPU limit. First 40 fixed tasks form a coverage barrier; only the owner may release the remaining 152 after at least 20 usable vectors and no unresolved failures. No partial feedback scoring.

Implementation checks use only synthetic log fixtures, source transformation identity, receipts and resource arithmetic. Ten dynamic and ten static properties pass; no benchmark download, SAT run, independent audit or dry run is part of these tests.
