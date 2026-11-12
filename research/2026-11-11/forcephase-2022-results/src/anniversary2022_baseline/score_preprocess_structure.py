"""R33 actual no-search elimination, UP-only and count-reassociated controls."""

import argparse
import fcntl
from pathlib import Path
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_large_linear42 import atomic
from .predict_relative_cost import SPLITS,choose,calibrate,gains
from .score_horn_renaming import calibrate_free
from .score_interpretable_two_percent import evaluate
from .score_static_learnability import fit
from .score_static_seed_agreement import SEEDS
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS,DATA,load,read_csv,write_csv


def main(args):
    wall,cpu=time.monotonic(),time.process_time();fits=[];scores={};comparisons={}
    args.out.mkdir(parents=True,exist_ok=False)
    with (args.out/'owner.lock').open('w') as lock,threadpool_limits(limits=4):
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            keys,_,costs,_,_,_=load();split=read_csv(SPLITS)
            assert [r['instance_key'] for r in split]==keys
            with np.load(args.features) as z:
                assert z['keys'].tolist()==keys
                views={k:z[k].copy() for k in ('UP57','BVE77','null77')}
                valid,informative,fee=z['valid'].copy(),z['informative'].copy(),z['fee'].copy()
            oracle=100*(costs[:,0]-costs.min(axis=1))[informative].sum()/costs[:,0].sum()
            ordered_costs=np.sort(costs,axis=1)
            clear=(ordered_costs[:,0]<600)&(np.minimum(ordered_costs[:,1],600)-ordered_costs[:,0]>
                np.maximum(.02,.1*ordered_costs[:,0]))
            diagnosis={'parents':4719,'cost_valid':4719,'all_censored':int(np.all(costs>=600,axis=1).sum()),
                'clear_parent_labels':int(clear.sum()),'unverified_in_published_matrix':0,
                'publisher_proofs_reverified_locally':False,'eligible_success':int(valid.sum()),
                'informative_parents':int(informative.sum()),'informative_oracle_population_pp':float(oracle),
                'D_mean_PAR2_s':float(costs[:,0].mean()),'D_solved':3385}
            if informative.sum()<50 or oracle<.5:
                atomic(args.out/'summary.json',{'status':'complete_low_information_no_fits','diagnosis':diagnosis,
                    'reward':None,'fits':[],'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall});return
            iso_rows=read_csv(DATA/'mechanism_R11_20261111/predictions.csv');assert [r['instance_key'] for r in iso_rows]==keys
            inner=np.array([r['inner_validation']=='True' for r in split])
            iso,coarse,fine=[np.array([r[k+'_group'] for r in split]) for k in ('iso','coarse','fine')]
            output=[{'instance_key':k,'D_PAR2':float(costs[i,0])} for i,k in enumerate(keys)]
            for mode,count in (('iso_diagnostic',5),('coarse',4),('fine',5)):
                folds=np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]) if mode=='iso_diagnostic' else np.array([int(r[mode+'_fold']) for r in split])
                groups=fine if mode=='fine' else coarse;selected_views={}
                for name,x in views.items():
                    actions=np.zeros(len(keys),int);cuts=[]
                    for fold in range(count):
                        if time.monotonic()-wall>900:raise TimeoutError('R33 formal score exceeded15min')
                        held=folds==fold;train=~held&~inner&valid;val=~held&inner&valid;test=held&valid
                        assert not(set(iso[held])&set(iso[train|val]))
                        assert not(set(fine[train])&set(fine[val]))
                        vp=[];hp=[]
                        for seed in SEEDS:
                            tick=time.process_time();model=fit('expressive',x[train],costs[train],seed+fold)
                            vp.append(gains(model,x[val],'trees_relative'));hp.append(gains(model,x[test],'trees_relative'))
                            fits.append({'mode':mode,'view':name,'fold':fold,'seed':seed+fold,'CPU_s':time.process_time()-tick})
                        v,h=np.min(vp,axis=0),np.min(hp,axis=0)
                        cut=calibrate(v,costs[val],np.zeros(val.sum()))
                        actions[test]=choose(h,cut);cuts.append({'fold':fold,'margin_PAR2_s':cut})
                        path=args.out/'fold_arrays'/f'{mode}_{name}_{fold}.npz';path.parent.mkdir(exist_ok=True)
                        np.savez_compressed(path,train_ids=np.flatnonzero(train),validation_ids=np.flatnonzero(val),
                            held_ids=np.flatnonzero(test),validation_scores=v,held_scores=h)
                    selected=costs[np.arange(len(keys)),actions];selected_views[name]=selected
                    result=evaluate(costs[:,0],selected,groups,coarse,mode)
                    result.update(actions={a:int((actions==j).sum()) for j,a in enumerate(ACTIONS)},cuts=cuts,
                        charged_preprocess_diagnostic=evaluate(costs[:,0],timed_cost(selected,fee,600),groups,coarse,mode))
                    scores[mode+'_'+name]=result
                    for i,row in enumerate(output):row[mode+'_'+name+'_action']=ACTIONS[actions[i]];row[mode+'_'+name+'_PAR2']=float(selected[i])
                    print(f'R33 {mode}_{name}: gain={result["gain_pct"]:+.6f}%, solved={result["solved"]}',flush=True)
                    write_csv(args.out/'predictions.csv',output)
                    atomic(args.out/'summary.json',{'status':'running','scores':scores,'fits':fits,'diagnosis':diagnosis})
                for control in ('UP57','null77'):
                    comparisons[mode+'_over_'+control]=evaluate(selected_views[control],selected_views['BVE77'],groups,coarse,mode)
            target={}
            for mode in ('iso_diagnostic','coarse','fine'):
                s=scores[mode+'_BVE77'];ci=s.get('exact_eight_block_95_pct',s['block_interval_95_pct'])
                target[mode]=bool(s['gain_pct']>=2 and ci[0]>0 and all(comparisons[mode+'_over_'+control]['gain_pct']>0 for control in ('UP57','null77')))
            atomic(args.out/'summary.json',{'status':'complete','scores':scores,'paired_increment_comparisons':comparisons,
                'fits':fits,'completed_fits':len(fits),'diagnosis':diagnosis,'two_percent_screen':target,
                'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall,'source_sha256':sha(__file__),
                'features_sha256':sha(args.features),'split_sha256':sha(SPLITS),'new_CDCL_solve_calls':0,
                'cost_scope':'Primary free-feature/query predictive screen; measured preprocessing fee diagnostic excludes still unknown count-qualification and original42 acquisition/query costs; not deployment',
                'claim_scope':'Retained4719 repeated2022 development, nominal intervals; no independent confirmation; default D is unmodified'})
        except BaseException as exc:
            atomic(args.out/'failure.json',{'error':repr(exc),'completed_fits':len(fits),'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall});raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features',type=Path,default=DATA/'mechanism_R33_features_20261111/features.npz')
    parser.add_argument('--out',type=Path,default=DATA/'mechanism_R33_20261111')
    main(parser.parse_args())
