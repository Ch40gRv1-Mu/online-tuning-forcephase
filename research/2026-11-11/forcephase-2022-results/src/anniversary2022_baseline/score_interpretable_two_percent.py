"""Original4719 folds for two Astra-proposed small human-readable cost rules."""

import argparse
import fcntl
import json
from pathlib import Path
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .interpretable_cost_tree import fit,predict_indices,rules
from .measure_large_linear42 import atomic
from .predict_relative_cost import SPLITS,calibrate,choose
from .score_static_seed_agreement import load_views
from .score_two_threshold_transfer import exact_small_block_interval
from .score_width_budget_recovery import assess
from .structural_clusters import ACTIONS,DATA,load,read_csv,write_csv


ALGORITHMS=("direct_cost","gain_regression")


def predicted_gains(model,x):
    x=np.asarray(x,dtype=np.float32)
    cost=np.empty((len(x),3))
    def visit(node,ids):
        if 'feature_index' not in node:
            cost[ids]=node['training_mean_costs'];return
        left=x[ids,node['feature_index']].astype(np.float64)<=node['threshold']
        visit(node['left'],ids[left]);visit(node['right'],ids[~left])
    visit(model['tree'],np.arange(len(x)))
    return cost[:,:1]-cost[:,1:]


def evaluate(ref,selected,groups,coarse,mode):
    score=assess(ref,selected,groups,600)
    if mode!='fine':score['exact_eight_block_95_pct']=exact_small_block_interval(ref,selected,coarse)
    return score


def main(args):
    start,cpu=time.monotonic(),time.process_time()
    args.out.mkdir(parents=True,exist_ok=False)
    fits,scores=[],{}
    with (args.out/'owner.lock').open('w') as lock,threadpool_limits(limits=1):
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            keys,_,costs,_,_,_=load()
            split=read_csv(SPLITS)
            iso_rows=read_csv(DATA/'mechanism_R11_20261111/predictions.csv')
            base=read_csv(DATA/'mechanism_R27_20261111/predictions.csv')
            assert [r['instance_key'] for r in split]==[r['instance_key'] for r in iso_rows]==[r['instance_key'] for r in base]==keys
            assert len(keys)==4719
            x,valid=load_views(keys)[0]['linear42'];assert valid.all()
            x=x.astype(np.float32)
            inner=np.array([r['inner_validation']=='True' for r in split])
            iso,coarse,fine=[np.array([r[k+'_group'] for r in split]) for k in ('iso','coarse','fine')]
            output=[{'instance_key':k,'D_PAR2':float(costs[i,0])} for i,k in enumerate(keys)]
            for mode,count in (('iso_diagnostic',5),('coarse',4),('fine',5)):
                folds=np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]) if mode=='iso_diagnostic' else np.array([int(r[mode+'_fold']) for r in split])
                groups=fine if mode=='fine' else coarse
                forest=np.array([float(r[mode+'_relative_control_PAR2']) for r in base])
                for algorithm in ALGORITHMS:
                    actions=np.zeros(len(keys),int);calibrated=np.zeros(len(keys),int);cuts=[];foldrules=[]
                    for fold in range(count):
                        if time.monotonic()-start>600:raise TimeoutError('bounded human-rule comparison exceeded ten minutes')
                        held=folds==fold;train=~held&~inner;val=~held&inner
                        assert not (set(iso[held])&set(iso[train|val]))
                        assert not (set(fine[train])&set(fine[val]))
                        tick=time.process_time();model=fit(x[train],costs[train],algorithm=algorithm)
                        a=predict_indices(model,x[held]);g=predicted_gains(model,x[held])
                        assert np.array_equal(a,choose(g,0))
                        cut=calibrate(predicted_gains(model,x[val]),costs[val],np.zeros(val.sum()))
                        actions[held]=a;calibrated[held]=choose(g,cut)
                        leafrules=rules(model)
                        assert len(leafrules)<=16 and max(len(r['conditions']) for r in leafrules)<=4
                        assert all(c['feature_index'] not in (21,26) for r in leafrules for c in r['conditions'])
                        path=args.out/'fold_policies'/f'{mode}_{algorithm}_{fold}.json'
                        atomic(path,model)
                        record={'mode':mode,'algorithm':algorithm,'fold':fold,'CPU_s':time.process_time()-tick,
                            'train_parents':int(train.sum()),'validation_parents':int(val.sum()),'held_parents':int(held.sum()),
                            'leaves':len(leafrules),'F_leaves':sum(r['action']!='D' for r in leafrules),'margin_PAR2_s':cut}
                        fits.append(record);cuts.append({'fold':fold,'margin_PAR2_s':cut});foldrules.append({'fold':fold,'rules':leafrules})
                    for variant,action in (('raw',actions),('inner_margin',calibrated)):
                        selected=costs[np.arange(len(keys)),action]
                        result=evaluate(costs[:,0],selected,groups,coarse,mode)
                        result.update(actions={a:int(np.sum(action==i)) for i,a in enumerate(ACTIONS)},
                            margins=cuts if variant=='inner_margin' else None,
                            against_original_forest=evaluate(forest,selected,groups,coarse,mode))
                        if mode=='iso_diagnostic':result['within_iso_parent_interval']=assess(costs[:,0],selected,iso,600)
                        name=f'{mode}_{algorithm}_{variant}';scores[name]=result
                        for i,row in enumerate(output):row[name+'_action']=ACTIONS[action[i]];row[name+'_PAR2']=float(selected[i])
                        print(f'READABLE {name}: gain={result["gain_pct"]:+.6f}%, solved={result["solved"]}',flush=True)
                    atomic(args.out/'rules'/f'{mode}_{algorithm}.json',foldrules)
                    write_csv(args.out/'predictions.csv',output)
                    atomic(args.out/'summary.json',{'status':'running','fits':fits,'scores':scores})
            reached={name:bool(score['gain_pct']>=2 and score['exact_eight_block_95_pct'][0]>0)
                for name,score in scores.items() if name.startswith('iso_diagnostic_')}
            atomic(args.out/'summary.json',{'status':'complete','parents':4719,'scores':scores,'fits':fits,
                'completed_policy_fits':len(fits),'new_forest_fits':0,'model_used_at_prediction':'one <=16-leaf explicit JSON tree',
                'user_target_mixed_two_pct':reached,'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-start,
                'source_sha256':sha(__file__),'algorithm_source_sha256':sha(Path(__file__).with_name('interpretable_cost_tree.py')),
                'splits_sha256':sha(SPLITS),'new_solver_calls':0,'new_feature_extractions':0,
                'cost_scope':'Free feature/query prediction screen, same original4719 costs; not complete native-cost replay',
                'scope':'User-directed human-readable ~2% mixed-fold reproduction. Coarse/fine reported separately; repeated development nominal intervals, no independent test',
                'teacher_distillation':False,'interpretation':'Astra uses actual forest/old failures to propose readable learners; numeric thresholds refit within each training fold, never carry full-development example thresholds into held predictions'})
        except BaseException as exc:
            atomic(args.out/'failure.json',{'status':'failed','error':repr(exc),'completed_fits':len(fits),
                'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-start});raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DATA/'interpretable_two_percent_20261111')
    main(parser.parse_args())
