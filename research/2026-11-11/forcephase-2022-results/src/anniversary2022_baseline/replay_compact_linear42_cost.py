"""Fixed R12 OOF replay using only actually measured compact-native fees."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from .common import sha
from .measure_compact_linear42 import atomic,CONFIG
from .predict_relative_cost import SPLITS
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess,timed_cost
from .structural_clusters import ACTIONS,DATA,load,read_csv,write_csv


def main(args):
    wall,cpu=time.monotonic(),time.process_time()
    header=json.loads((args.root/("prefix_"+str(args.through)+".json")).read_text())
    assert header["status"]=="complete_prefix" and header["through"]==args.through
    manifest=read_csv(CONFIG/"manifest.csv")
    assert len(manifest)==4719
    measured={r["instance_key"]:json.loads((args.root/"records"/(r["instance_key"]+".json")).read_text()) for r in manifest[:args.through]}
    for k,r in measured.items():
        assert r["instance_key"]==k and r["identity"]["verified"]
        assert r["status"] in ("ok","native_error_D_fallback")
        assert r["status"]!="ok" or r["model_input_float32_match"]
    keys,_,costs,_,_,_=load()
    split=read_csv(SPLITS)
    predictions=read_csv(DATA/"mechanism_R12_20261111/predictions.csv")
    iso_rows=read_csv(DATA/"mechanism_R11_20261111/predictions.csv")
    old=json.loads((DATA/"mechanism_R12_20261111/summary.json").read_text())
    assert [r["instance_key"] for r in split]==[r["instance_key"] for r in predictions]==[r["instance_key"] for r in iso_rows]==keys
    known=np.array([k in measured for k in keys])
    fee=np.array([measured[k]["acquisition_CPU_s"] if k in measured else 0. for k in keys])
    failed=np.array([k in measured and measured[k]["status"]!="ok" for k in keys])
    coarse=np.array([r["coarse_group"] for r in split]);fine=np.array([r["fine_group"] for r in split])
    rows=[{"instance_key":k,"compact_fee_measured":bool(known[i]),"compact_acquisition_CPU_s":float(fee[i]),
        "compact_native_error_observed":bool(failed[i])} for i,k in enumerate(keys)]
    scores={}
    for mode in ("iso_diagnostic","coarse","fine"):
        name=mode+"_linear42_min3"
        folds=np.array([int(r["diagnostic_iso_fold"]) for r in iso_rows]) if mode=="iso_diagnostic" else np.array([int(r[mode+"_fold"]) for r in split])
        enabled=np.array([old["scores"][name]["cuts"][f]["margin_PAR2_s"] is not None for f in folds])
        action=np.array([ACTIONS.index(r[name+"_action"]) for r in predictions])
        query=np.array([float(r[name+"_decision_CPU_s"]) for r in predictions])
        previous=timed_cost(costs[np.arange(len(keys)),action],query,600)
        assert np.allclose(previous,[float(r[name+"_PAR2"]) for r in predictions],rtol=0,atol=1e-8)
        affected=failed&enabled;switches_replaced=int(np.sum(affected&(action!=0)))
        action[affected]=0;query[affected]=0
        selected=timed_cost(costs[np.arange(len(keys)),action],query+fee*enabled,600)
        groups=fine if mode=="fine" else coarse
        score=assess(costs[:,0],selected,groups,600)
        if mode!="fine":score["exact_eight_block_95_pct"]=exact_small_block_interval(costs[:,0],selected,coarse)
        score.update(actions={a:int(np.sum(action==i)) for i,a in enumerate(ACTIONS)},
            measured_fee_parents=int(np.sum(known&enabled)),unknown_fee_parents=int(np.sum(~known&enabled)),
            measured_failure_D_actions=int(affected.sum()),previous_switches_replaced_by_D=switches_replaced)
        scores[mode]=score
        for i,r in enumerate(rows):r[mode+"_action"]=ACTIONS[action[i]];r[mode+"_PAR2"]=float(selected[i])
        print(f"COMPACT_COSTED {mode}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}, unknown_costs={score['unknown_fee_parents']}",flush=True)
    out=args.root/("replay_prefix_"+str(args.through));out.mkdir(exist_ok=False)
    write_csv(out/"predictions.csv",rows)
    atomic(out/"summary.json",{"status":"complete_compact_cost_replay" if known.all() else "complete_partial_compact_cost_replay",
        "all_parents":4719,"actually_measured_compact_inputs":int(known.sum()),"unknown_costs":int((~known).sum()),
        "native_feature_failures":int(failed.sum()),"scores":scores,"CPU_s":time.process_time()-cpu,
        "wall_s":time.monotonic()-wall,"source_sha256":sha(__file__),"prefix_receipt_sha256":sha(args.root/("prefix_"+str(args.through)+".json")),
        "original_R12_predictions_sha256":sha(DATA/"mechanism_R12_20261111/predictions.csv"),"new_model_fits":0,"new_solver_calls":0,
        "cost_identity":"Only actual compact-native measurements, including reused compatible32; no old57-field fees mislabeled as new profile",
        "unknown_policy":"Until measured, original OOF actions retained and acquisition fees not yet added; unknown native failures may also change actions, so this is not a guaranteed performance bound",
        "scope":"Repeated2022 development, nominal intervals; Mac acquisition plus publisher cluster solver timing, not actual same-machine end-to-end deployment or independent confirmation"})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through",type=int,required=True)
    parser.add_argument("--root",type=Path,default=DATA/"linear42_compact_cost_v2_20261111")
    main(parser.parse_args())
