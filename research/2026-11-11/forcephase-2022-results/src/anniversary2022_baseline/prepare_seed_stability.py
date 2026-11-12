"""Freeze R35's outcome-independent32-CNF panel before any new solver run."""

import hashlib
import json
from pathlib import Path
import time
import numpy as np

from .common import sha
from .measure_compact_prefetch import atomic, CONFIG
from .recover_compact_cpu import ORIGINAL
from .structural_clusters import DATA, load, read_csv, write_csv


SEED = "forcephase-solver-seed-stability-R35-20261111:"


def main():
    start, cpu = time.monotonic(), time.process_time()
    out = DATA / "solver_seed_stability_R35_20261111"
    out.mkdir(exist_ok=False)
    manifest = read_csv(CONFIG/"manifest.csv")
    assert len(manifest) == 4719
    chosen = sorted(manifest, key=lambda r: hashlib.sha256((SEED+r["instance_key"]).encode()).hexdigest())[:32]
    rows=[]
    for j, r in enumerate(chosen, 1):
        path = ORIGINAL/"records"/(r["instance_key"]+".json")
        old = json.loads(path.read_text())
        assert old["identity"]["verified"]
        rows.append({"ordinal":j,"instance_key":r["instance_key"],"url":r["url"],
            "raw_sha256":old["identity"]["raw_sha256"],"raw_bytes":old["identity"]["raw_bytes"]})
    # This file is frozen before the old-label information check below.
    write_csv(out/"manifest.csv",rows)
    atomic(out/"cohort.json",{"status":"frozen_before_new_runs","sampling_seed":SEED,
        "sampling":"First32 SHA256 ranks from all4719; no phase/status/family/size selection",
        "parents":32,"actions":["D","Fplus","Fminus"],"solver_seeds":[0,1],"runs":192,
        "manifest_sha256":sha(out/"manifest.csv"),"new_solver_calls":0})
    keys,_,costs,_,_,_=load();index={k:i for i,k in enumerate(keys)}
    panel=costs[[index[r["instance_key"]] for r in rows]]
    ordered=np.sort(panel,axis=1)
    clear=(ordered[:,0]<600)&(np.minimum(ordered[:,1],600)-ordered[:,0]>np.maximum(.02,.1*ordered[:,0]))
    oracle=float(100*(panel[:,0]-panel.min(axis=1)).sum()/panel[:,0].sum())
    atomic(out/"information_gate.json",{"source":"Existing permitted publisher seed0 labels; not new-host outcomes",
        "parents":32,"cost_valid":32,"clear":int(clear.sum()),"all_censored":int(np.all(panel>=600,axis=1).sum()),
        "free_oracle_gain_pct":oracle,"gate_passed":bool(clear.sum()>=8 and oracle>=.5),
        "raw_bytes_max":max(r["raw_bytes"] for r in rows),
        "old_host_solver_CPU_projection_for_two_seeds_h":float(np.minimum(panel,600).sum()*2/3600),
        "projection_is_not_new_host_ETA":True,"CPU_s":time.process_time()-cpu,"wall_s":time.monotonic()-start,
        "source_sha256":sha(__file__),"new_solver_calls":0,"no_panel_replacement_if_gate_fails":True})
    print((out/"information_gate.json").read_text())


if __name__ == "__main__":
    main()
