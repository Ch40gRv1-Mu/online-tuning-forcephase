"""Merge complete native-cost prefixes with fixed R12 OOF choices; no fitting."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .common import sha
from .measure_large_linear42 import atomic, CONFIG
from .predict_relative_cost import SPLITS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def main(args):
    began,cpu=time.monotonic(),time.process_time()
    prefix=json.loads((args.root/("prefix_"+str(args.through)+".json")).read_text())
    assert prefix["status"]=="complete_prefix" and prefix["through"]==args.through
    manifest=read_csv(CONFIG/"manifest.csv")
    assert len(manifest)==1876
    large={r["instance_key"]:json.loads((args.root/"records"/(r["instance_key"]+".json")).read_text())
           for r in manifest[:args.through]}
    assert len(large)==args.through
    for key,row in large.items():
        assert row["instance_key"]==key and row["identity"]["verified"]
        assert row["status"] in ("ok","native_error_D_fallback")
        assert row["status"]!="ok" or row["model_input_float32_match"]
    small_source=DATA/"native_GBD_route_v3_20261111/feature_receipts.jsonl"
    small={r["instance_key"]:r for r in map(json.loads,small_source.read_text().splitlines()) if r["status"]=="ok"}
    assert len(small)==2843 and not (small.keys()&large.keys())
    keys,_,costs,_,_,_=load()
    split=read_csv(SPLITS)
    old_rows=read_csv(DATA/"mechanism_R12_20261111/predictions.csv")
    iso_rows=read_csv(DATA/"mechanism_R11_20261111/predictions.csv")
    old=json.loads((DATA/"mechanism_R12_20261111/summary.json").read_text())
    assert [r["instance_key"] for r in split]==[r["instance_key"] for r in old_rows]==[r["instance_key"] for r in iso_rows]==keys
    known=np.array([k in small or k in large for k in keys])
    fee=np.array([small[k]["feature_CPU_s"] if k in small else large[k]["acquisition_CPU_s"] if k in large else 0. for k in keys])
    bad=np.array([k in large and large[k]["status"]=="native_error_D_fallback" for k in keys])
    coarse=np.array([r["coarse_group"] for r in split])
    fine=np.array([r["fine_group"] for r in split])
    output=[{"instance_key":k,"feature_fee_measured":bool(known[i]),"native_failure_observed":bool(bad[i]),
             "observed_acquisition_CPU_s":float(fee[i])} for i,k in enumerate(keys)]
    scores={}
    for mode in ("iso_diagnostic","coarse","fine"):
        name=mode+"_linear42_min3"
        folds=np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows]) if mode=="iso_diagnostic" else np.array([int(r[mode+"_fold"]) for r in split])
        enabled=np.array([old["scores"][name]["cuts"][i]["margin_PAR2_s"] is not None for i in folds])
        action=np.array([ACTIONS.index(r[name+"_action"]) for r in old_rows])
        query=np.array([float(r[name+"_decision_CPU_s"]) for r in old_rows])
        original=timed_cost(costs[np.arange(len(keys)),action],query,600)
        assert np.allclose(original,[float(r[name+"_PAR2"]) for r in old_rows],rtol=0,atol=1e-8)
        affected=bad&enabled
        original_failure_switch=int(np.sum(affected&(action!=0)))
        action[affected]=0
        query[affected]=0
        paid=timed_cost(costs[np.arange(len(keys)),action],query+enabled*fee,600)
        groups=fine if mode=="fine" else coarse
        result=assess(costs[:,0],paid,groups,600)
        if mode!="fine": result["exact_eight_block_95_pct"]=exact_small_block_interval(costs[:,0],paid,coarse)
        result.update(measured_acquisition_parents=int((known&enabled).sum()),unknown_acquisition_parents=int((~known&enabled).sum()),
            feature_failures_with_enabled_policy=int(affected.sum()),previous_switches_replaced_by_D=original_failure_switch,
            original_R12_gain_pct=old["scores"][name]["gain_pct"],
            actions={a:int(np.sum(action==i)) for i,a in enumerate(ACTIONS)})
        scores[mode]=result
        for i,row in enumerate(output):
            row[mode+"_action"]=ACTIONS[action[i]];row[mode+"_PAR2"]=float(paid[i])
        print(f"COSTED {mode}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}, unknown_fees={result['unknown_acquisition_parents']}",flush=True)
    out=args.root/("replay_prefix_"+str(args.through))
    out.mkdir(exist_ok=False)
    write_csv(out/"predictions.csv",output)
    atomic(out/"summary.json",{"status":"complete_partial_cost_replay","scores":scores,"all_parents":4719,
        "new_large_measured":args.through,"native_successes":int(sum(r["status"]=="ok" for r in large.values())),
        "measured_feature_failures":int(bad.sum()),"all_measured_fees":int(known.sum()),"remaining_unknown":int((~known).sum()),
        "CPU_s":time.process_time()-cpu,"wall_s":time.monotonic()-began,"source_sha256":sha(__file__),
        "prefix_receipt_sha256":sha(args.root/("prefix_"+str(args.through)+".json")),"small_fee_receipts_sha256":sha(small_source),
        "original_prediction_sha256":sha(DATA/"mechanism_R12_20261111/predictions.csv"),"new_fits":0,"new_solver_calls":0,
        "scope":"Original complete4719 OOF program with observed native fees/failures; remaining fees optimistic unknown0, no in-sample candidate reward or independent test",
        "timing_boundary":"Mac feature acquisition plus cluster solver CPU is exploratory mixed-hardware replay, not actual same-machine deployment"})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through",type=int,required=True)
    parser.add_argument("--root",type=Path,default=DATA/"linear42_large_cost_20261111")
    main(parser.parse_args())
