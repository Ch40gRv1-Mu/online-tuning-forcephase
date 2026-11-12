"""R34: full original folds, two coordinate sets, unchanged small cost-tree capacity."""

from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import resource
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .linear42_only_vector import linear42_vector
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS
from .recover_compact_cpu import ORIGINAL, OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_static_seed_agreement import load_views
from .score_width_budget_recovery import timed_cost
from .semantic_cost_tree import fit, predict, rules
from .semantic_readable_features import transform, feature_names
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


OUT = DATA / "mechanism_R34_20261111"


def fit_fold(job):
    mode, view, fold, x, c, train, held = job
    cpu = time.process_time()
    with threadpool_limits(limits=1):
        model = fit(x[train], c[train], feature_names(view))
        actions = predict(model, x[held])
        leaf_rules = rules(model)
    return {"mode": mode, "view": view, "fold": fold, "model": model,
        "held_ids": np.flatnonzero(held), "actions": actions, "rules": leaf_rules,
        "CPU_s": time.process_time()-cpu, "train_parents": int(train.sum())}


def main():
    wall, cpu = time.monotonic(), time.process_time()
    usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    completed, status = [], "running"
    try:
        keys, _, costs, _, _, _ = load()
        x, valid = load_views(keys)[0]["linear42"]
        assert valid.all() and x.dtype == np.float64
        split = read_csv(SPLITS); old_iso = read_csv(DATA/"mechanism_R11_20261111/predictions.csv")
        old_small = read_csv(DATA/"interpretable_two_percent_20261111/predictions.csv")
        assert all([r["instance_key"] for r in table] == keys for table in (split, old_iso, old_small))
        first = {k: json.loads((ORIGINAL/"records"/(k+".json")).read_text()) for k in keys}
        retry = {f.stem: json.loads(f.read_text()) for f in (RETRY/"records").glob("*.json")}
        assert json.loads((RETRY/"completion.json").read_text())["status"] == "complete"
        available = np.array([first[k]["status"] == "ok" or (k in retry and retry[k]["status"] == "ok") for k in keys])
        fees = np.array([first[k]["acquisition_CPU_s"] + (retry[k]["retry_acquisition_CPU_s"] if k in retry else 0.) for k in keys])
        assert available.sum() == 4694
        views = {name: transform(x, name) for name in ("raw40", "semantic52")}
        semantic_unique = len(np.unique(views["semantic52"][available, 40:], axis=0))
        oracle = float(100 * (costs[:, 0]-costs.min(axis=1))[available].sum()/costs[:, 0].sum())
        index = {k:i for i,k in enumerate(keys)}
        checked, mismatch = 0, []
        for path in sorted((ORIGINAL/"stages").glob("*.native.json")):
            row = json.loads(path.read_text())
            if row["native_exit"] != 0:
                continue
            actual = transform(linear42_vector(row["features"]), "semantic52")
            expected = views["semantic52"][index[row["instance_key"]]]
            checked += 1
            if not np.array_equal(actual, expected):
                mismatch.append({"association_key": row["instance_key"], "native_receipt": str(path),
                    "different_indices": np.flatnonzero(actual != expected).tolist(),
                    "actual": actual.tolist(), "expected": expected.tolist()})
        qualification = {"parents":len(keys), "available":int(available.sum()), "distinct_semantic_bundles":semantic_unique,
            "available_oracle_population_pp":oracle, "archived_native_payloads_checked":checked,
            "mismatches":mismatch, "new_native_calls":0, "new_solver_calls":0}
        atomic(OUT/"input_qualification.json", qualification)
        if mismatch:
            raise ValueError("New semantic features do not match archived native inputs; no model scoring")
        if semantic_unique < 50 or oracle < .5:
            atomic(OUT/"summary.json", {"status":"low_information_no_fits", "reward":None, **qualification})
            status = "complete_low_information";return
        inner = np.array([r["inner_validation"] == "True" for r in split])
        iso, coarse, fine = [np.array([r[k+"_group"] for r in split]) for k in ("iso", "coarse", "fine")]
        folds = {"iso_diagnostic":np.array([int(r["diagnostic_iso_fold"]) for r in old_iso]),
            **{m:np.array([int(r[m+"_fold"]) for r in split]) for m in ("coarse", "fine")}}
        jobs=[]
        for mode in folds:
            for view in views:
                for fold in np.unique(folds[mode]):
                    held = folds[mode] == fold;train = ~held & ~inner
                    assert not (set(iso[held]) & set(iso[train | (~held & inner)]))
                    assert not (set(fine[train]) & set(fine[~held & inner]))
                    jobs.append((mode,view,int(fold),views[view],costs,train,held))
        with ProcessPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(fit_fold,j) for j in jobs]
            for future in futures:
                result = future.result(timeout=max(1,900-(time.monotonic()-wall)))
                completed.append(result)
                atomic(OUT/"fold_policies"/f"{result['mode']}_{result['view']}_{result['fold']}.json", result["model"])
                atomic(OUT/"rules"/f"{result['mode']}_{result['view']}_{result['fold']}.json", result["rules"])
        output=[{"instance_key":k} for k in keys];scores={};selected={}
        with threadpool_limits(limits=1):
            for mode in folds:
                for view in views:
                    action=np.zeros(len(keys),int);query=np.zeros(len(keys));active=np.zeros(len(keys),bool)
                    for result in completed:
                        if result["mode"]!=mode or result["view"]!=view:continue
                        ids=result["held_ids"];action[ids]=result["actions"]
                        model=result["model"]
                        constantD="feature_index" not in model["tree"] and model["tree"]["action_index"]==0
                        if constantD:continue
                        active[ids]=True
                        for i in ids[available[ids]]:
                            t=time.thread_time();vector=transform(x[i],view);a=predict(model,vector)
                            query[i]=time.thread_time()-t
                            assert a==action[i] and np.array_equal(vector,views[view][i])
                    if view=="raw40":
                        assert np.array_equal(action,[ACTIONS.index(r[mode+"_direct_cost_raw_action"]) for r in old_small]), "Raw control changed; do not attribute to coordinates"
                    free=costs[np.arange(len(keys)),action]
                    action[active & ~available]=0
                    paid=timed_cost(costs[np.arange(len(keys)),action],fees*active+query,600)
                    group=fine if mode=="fine" else coarse
                    result=evaluate(costs[:,0],paid,group,coarse,mode)
                    result["free_unmasked_original_control"]=evaluate(costs[:,0],free,group,coarse,mode)
                    result["actions"]={a:int((action==j).sum()) for j,a in enumerate(ACTIONS)}
                    result["measured_transform_query_CPU_sum_s"]=float(query.sum())
                    result["constantD_skips_native_parents"]=int((~active).sum())
                    scores[mode+"_"+view]=result;selected[mode+"_"+view]=paid
                    for i,row in enumerate(output):row[mode+"_"+view+"_action"]=ACTIONS[action[i]];row[mode+"_"+view+"_PAR2"]=float(paid[i])
                    print(f"SEMANTIC {mode}_{view}: gain={result['gain_pct']:+.6f}%, solved={result['solved']}",flush=True)
            increments={m:evaluate(selected[m+"_raw40"],selected[m+"_semantic52"],fine if m=="fine" else coarse,coarse,m) for m in folds}
        write_csv(OUT/"predictions.csv",output)
        primary=scores["iso_diagnostic_semantic52"]
        reached=bool(primary["gain_pct"]>=2 and primary["exact_eight_block_95_pct"][0]>0 and increments["iso_diagnostic"]["gain_pct"]>0)
        status="complete"
        atomic(OUT/"summary.json", {"status":status,"parents":len(keys),"scores":scores,"paired_increments_over_raw40":increments,
            "primary_two_percent_screen":reached,"completed_fits":len(completed),
            "fit_records":[{k:v for k,v in r.items() if k not in ("model","held_ids","actions","rules")} for r in completed],
            "raw_control_matches_all_original_R31_OOF_actions":True,"qualification":qualification,
            "new_solver_calls":0,"new_native_calls":0,"teacher_fits":0,"source_sha256":sha(__file__),
            "feature_source_sha256":sha(Path(__file__).with_name("semantic_readable_features.py")),
            "learner_source_sha256":sha(Path(__file__).with_name("semantic_cost_tree.py")),
            "scope":"All4719 repeated2022, original folds, identical leaf capacity. Compatible measured Mac native fees plus actual transform/query, cluster solver times; no independent or same-machine solver confirmation."})
    except BaseException as exc:
        atomic(OUT/"failure.json", {"status":"failed","error":repr(exc),"completed_fits":len(completed),"reward":None})
        raise
    finally:
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(OUT/"resources.json", {"status":status,"physical_parent_CPU_s":time.process_time()-cpu,
            "physical_child_CPU_s":usage.ru_utime+usage.ru_stime-usage0.ru_utime-usage0.ru_stime,
            "wall_s":time.monotonic()-wall,"new_solver_calls":0,"source_sha256":sha(__file__)})


if __name__ == "__main__":
    main()
