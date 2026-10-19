#!/usr/bin/env python3
"""Audit v2 P2: execute the low-noise overhead retest (docs/CORRECTION_PROTOCOL.md §6).

  scripts/audit_v2/overhead_retest.py [--workers 16] [--dry-run]

Runs configs/experiments/audit_v2_m1.json with a fixed schedule instead of
fprun's random sharding:
  * 16 worker processes, each pinned to one physical core of a distinct CCD
    (cores 0, 6, ..., 90 on the 2x48-core EPYC 9454 nodes);
  * every instance is assigned to one worker (LPT on the expected load
    18 x round-1 upstream median CPU) and its 18 runs execute sequentially on
    that core;
  * order within an instance: 6 blocks, each a random permutation of
    (Dupstream, Doff, D) drawn with numpy default_rng(20261019 + instance index).
Resumable (existing results are skipped).  The schedule is written to
results/audit_v2/m1/schedule.csv before execution.
"""

import argparse
import multiprocessing as mp
import os
import random
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import fprun  # noqa: E402

CONFIGS = ["Dupstream", "Doff", "D"]


def order_for(index, seed=20261019):
    import numpy as np
    rng = np.random.default_rng(seed + index)
    out = []
    for block in range(6):
        perm = rng.permutation(3)
        out += [(CONFIGS[p], block) for p in perm]
    return out


def worker(args):
    wid, core, items, log = args
    done = {}
    for run in items:
        try:
            st = fprun.execute(run, core, log)
        except Exception as e:  # keep going; the run stays missing and is reported
            st = f"runner-error:{e!r}"
        done[st] = done.get(st, 0) + 1
    return wid, done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    exp = fprun.load_experiment(os.path.join(fprun.ROOT, "configs", "experiments", "audit_v2_m1.json"))
    runs = fprun.plan(exp)
    by = {(r["config"], r["key"]["instance"], r["key"].get("repeat", 0)): r for r in runs}
    lst = [l.split() for l in open(os.path.join(fprun.ROOT, "benchmarks", "derived", "audit_v2", "m1_retest48.txt"))
           if l.strip() and not l.startswith("#")]
    insts = [(i, h, float(c)) for i, (h, _s, c) in enumerate(lst)]
    cores = [6 * k for k in range(a.workers)]
    allowed = os.sched_getaffinity(0)
    if not set(cores) <= allowed:
        raise SystemExit(f"cores {cores} not all allowed ({sorted(allowed)[:8]}...): need an exclusive node")
    loads = [0.0] * a.workers
    assign = {}
    for i, h, c in sorted(insts, key=lambda x: -x[2]):
        w = min(range(a.workers), key=lambda k: loads[k])
        assign[h] = w
        loads[w] += 18 * c
    items = [[] for _ in range(a.workers)]
    rows = []
    for i, h, c in insts:
        rep = {cfg: 0 for cfg in CONFIGS}
        for pos, (cfg, block) in enumerate(order_for(i)):
            run = by[(cfg, h, rep[cfg])]
            rows.append((assign[h], cores[assign[h]], i, h, pos, cfg, rep[cfg], run["run_id"]))
            rep[cfg] += 1
            items[assign[h]].append(run)
    # instances of one worker run one after another (each instance's 18 runs contiguous)
    os.makedirs(os.path.join(fprun.ROOT, "results", "audit_v2", "m1"), exist_ok=True)
    with open(os.path.join(fprun.ROOT, "results", "audit_v2", "m1", "schedule.csv"), "w") as f:
        f.write("worker,core,instance_index,instance,position,config,repeat,run_id\n")
        for r in sorted(rows, key=lambda r: (r[0], r[2], r[4])):
            f.write(",".join(map(str, r)) + "\n")
    print(f"[retest] {len(runs)} runs, {len(insts)} instances, expected max worker load "
          f"{max(loads) / 3600:.2f} h, total {sum(loads) / 3600:.1f} CPU h; cores {cores}", flush=True)
    if a.dry_run:
        return
    for k in range(a.workers):
        items[k].sort(key=lambda r: [x[2] * 100 + x[4] for x in rows if x[7] == r["run_id"]][0])
    os.makedirs(os.path.join(fprun.DATA, "runs", "attempts"), exist_ok=True)
    log = os.path.join(fprun.DATA, "runs", "attempts", f"audit_v2_m1-{socket.gethostname()}-{os.getpid()}.jsonl")
    with mp.Pool(a.workers) as pool:
        for wid, done in pool.imap_unordered(worker, [(k, cores[k], items[k], log) for k in range(a.workers)]):
            print(f"[retest] worker {wid} done {done}", flush=True)


if __name__ == "__main__":
    main()
