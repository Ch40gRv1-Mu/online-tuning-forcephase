"""R40: terminal work ONLY as training supervision; inference remains linear42."""
from concurrent.futures import ProcessPoolExecutor
import json
import os
import resource
import signal
import time

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS,calibrate,choose
from .recover_compact_cpu import OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_static_seed_agreement import load_views
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS,DATA,load,read_csv,write_csv

OUT=DATA/'mechanism_R40_v2_20261111'


def training_targets(x,costs,observed_log_work_ratio,fold):
    # This function receives training rows only, including the label-only strata.
    work=np.asarray(observed_log_work_ratio,float)
    mean=np.nanmean(work,axis=0)
    std=np.maximum(np.nanstd(work,axis=0),1e-9)
    z=np.where(np.isfinite(work),(work-mean)/std,0.)*.05
    pattern=((costs<1200)*(2**np.arange(3))).sum(axis=1)
    bins=np.c_[np.floor(x[:,:2]/(2*np.log(2))).astype(int),pattern]
    _,groups=np.unique(bins,axis=0,return_inverse=True)
    rng=np.random.default_rng(20261140+fold)
    null=z.copy();permutable=0
    for g in np.unique(groups):
        ids=np.flatnonzero(groups==g)
        if len(ids)>1:
            permutable+=len(ids)
            null[ids]=z[rng.permutation(ids)]
    gain=(costs[:,[0]]-costs[:,1:])/1200
    actual,control=np.c_[gain,z],np.c_[gain,null]
    assert np.array_equal(actual[:,:2],control[:,:2]) and np.isfinite(actual).all() and np.isfinite(control).all()
    metadata={'auxiliary_mean_train_only':mean.tolist(),'auxiliary_std_train_only':std.tolist(),
        'missing_training_auxiliary':(~np.isfinite(work)).sum(axis=0).tolist(),
        'permutable_training_parents':permutable,'changed_auxiliary_training_parents':int(np.any(z!=null,axis=1).sum()),
        'target_shape':list(actual.shape),'inference_feature_count':x.shape[1],
        'null_preserves_train_size_and_completion_pattern':True,'auxiliary_scale':.05}
    return actual,control,metadata


def fit_job(job):
    mode,kind,fold,xtrain,y,xval,xheld,validation_costs,held_ids,meta=job
    cpu,wall=time.process_time(),time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('R40 fold600wall')))
    signal.alarm(600)
    try:
        with threadpool_limits(limits=1):
            model=ExtraTreesRegressor(n_estimators=256,max_depth=12,min_samples_leaf=4,
                max_features=.8,n_jobs=1,random_state=20261111+fold)
            model.fit(xtrain,y)
            assert model.n_features_in_==42 and model.n_outputs_==4
            # No actual work observation is consulted for validation or held inference.
            vp=model.predict(xval)[:,:2]*1200
            hp=model.predict(xheld)[:,:2]*1200
            cut=calibrate(vp,validation_costs,np.zeros(len(validation_costs)))
            action=choose(hp,cut)
        return {'mode':mode,'kind':kind,'fold':fold,'held_ids':held_ids,'actions':action,
            'validation_scores':vp,'held_scores':hp,'margin_PAR2_s':cut,
            'nodes':sum(t.tree_.node_count for t in model.estimators_),
            'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall,'target_metadata':meta}
    finally:
        signal.alarm(0)


def main():
    wall,cpu=time.monotonic(),time.process_time()
    initial=resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    atomic(OUT/'owner.json',{'pid':os.getpid(),'source_sha256':sha(__file__),
        'started_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'expected_fits':28,
        'remote_R35_untouched':True,'inference_inputs_static42_only':True})
    completed,status=[],'running'
    try:
        keys,_,costs,_,_,_=load()
        x,valid=load_views(keys)[0]['linear42'];assert valid.all() and x.shape==(4719,42)
        matrix_path=DATA/'raw_data_20261110/matrix.csv';matrix_rows=read_csv(matrix_path)
        by_key={r['instance_key']:r for r in matrix_rows}
        assert len(by_key)==len(matrix_rows)==len(keys) and set(by_key)==set(keys)
        raw=[by_key[k] for k in keys]
        raw_costs=np.array([[float(row[a+'_par2']) for a in ACTIONS] for row in raw])
        assert np.allclose(raw_costs,costs,rtol=0,atol=1e-9), 'Work and cost labels must bind to the same physical parent rows'
        counters=np.full((len(keys),3),np.nan)
        for i,row in enumerate(raw):
            for j,a in enumerate(ACTIONS):
                try:v=float(row[a+'_conflicts'])
                except (ValueError,TypeError):continue
                if np.isfinite(v) and v>=0:counters[i,j]=v
        work=np.log1p(counters[:,1:])-np.log1p(counters[:,[0]])
        coverage=np.isfinite(work).sum(axis=0)
        split=read_csv(SPLITS);iso_rows=read_csv(DATA/'mechanism_R11_20261111/predictions.csv')
        original=read_csv(DATA/'mechanism_R12_20261111/predictions.csv')
        old_summary=json.loads((DATA/'mechanism_R12_20261111/summary.json').read_text())
        recovery=read_csv(RETRY/'predictions.csv')
        assert all([r['instance_key'] for r in table]==keys for table in (split,iso_rows,original,recovery))
        inner=np.array([r['inner_validation']=='True' for r in split])
        iso,coarse,fine=[np.array([r[k+'_group'] for r in split]) for k in ('iso','coarse','fine')]
        folds={'iso_diagnostic':np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]),
               **{m:np.array([int(r[m+'_fold']) for r in split]) for m in ('coarse','fine')}}
        jobs=[];target_gates=[]
        for mode,assignment in folds.items():
            for fold in np.unique(assignment):
                held=assignment==fold;train=~held&~inner;val=~held&inner
                assert not(set(iso[held])&set(iso[train|val]))
                assert not(set(fine[train])&set(fine[val]))
                actual,null,metadata=training_targets(x[train],costs[train],work[train],int(fold))
                target_gates.append({'mode':mode,'fold':int(fold),**metadata})
                for kind,y in [('actual_work',actual),('null_work',null)]:
                    jobs.append((mode,kind,int(fold),x[train],y,x[val],x[held],costs[val],np.flatnonzero(held),metadata))
        gate=bool((coverage>=.9*len(keys)).all() and all(m['permutable_training_parents']>=50 for m in target_gates))
        atomic(OUT/'information_gate.json',{'coverage':coverage.tolist(),'parents':len(keys),
            'passed':gate,'fold_targets':target_gates,'terminal_counts_are_train_only_labels':True})
        if not gate:
            status='complete_low_information_no_fits'
            atomic(OUT/'summary.json',{'status':status,'completed_fits':0,'reward':None})
            return
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(fit_job,j) for j in jobs]
            for future in futures:
                result=future.result(timeout=max(1,1200-(time.monotonic()-wall)))
                completed.append(result)
                name=f"{result['mode']}_{result['kind']}_{result['fold']}"
                np.savez_compressed(OUT/(name+'.npz'),held_ids=result['held_ids'],
                    validation_scores=result['validation_scores'],held_scores=result['held_scores'])
                atomic(OUT/'progress.json',{'completed_fits':len(completed),'expected_fits':28,
                    'wall_s':time.monotonic()-wall})
        fees=np.array([float(r['first_acquisition_CPU_s'])+float(r['second_acquisition_CPU_s']) for r in recovery])
        failed=np.array([r['still_failed_paidD']=='True' for r in recovery]);assert failed.sum()==25
        output=[{'instance_key':k} for k in keys];scores={};paid_by_mode={};paired={}
        for mode,assignment in folds.items():
            group=fine if mode=='fine' else coarse;paid_by_mode[mode]={}
            for kind in ('actual_work','null_work','cached_seed0','cached_min3'):
                if kind.startswith('cached_'):
                    variant='seed0' if kind=='cached_seed0' else 'min3'
                    name=mode+'_linear42_'+variant
                    actions=np.array([ACTIONS.index(r[name+'_action']) for r in original])
                    enabled=np.array([old_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None for f in assignment])
                else:
                    actions=np.zeros(len(keys),int);enabled=np.zeros(len(keys),bool)
                    for result in completed:
                        if result['mode']!=mode or result['kind']!=kind:continue
                        ids=result['held_ids'];actions[ids]=result['actions']
                        enabled[ids]=result['margin_PAR2_s'] is not None
                raw_cost=costs[np.arange(len(keys)),actions]
                action=actions.copy();action[failed&enabled]=0
                paid=timed_cost(costs[np.arange(len(keys)),action],fees*enabled,600)
                score=evaluate(costs[:,0],paid,group,coarse,mode)
                score['free_unmasked']=evaluate(costs[:,0],raw_cost,group,coarse,mode)
                score['actions']={a:int((action==j).sum()) for j,a in enumerate(ACTIONS)}
                score['query_unmeasured_optimistic_zero']=True
                scores[mode+'_'+kind]=score;paid_by_mode[mode][kind]=paid
                for i,row in enumerate(output):row[mode+'_'+kind+'_action']=ACTIONS[action[i]];row[mode+'_'+kind+'_PAR2']=float(paid[i])
                print(f"R40 {mode}_{kind}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}",flush=True)
            for control in ('null_work','cached_seed0','cached_min3'):
                paired[mode+'_over_'+control]=evaluate(paid_by_mode[mode][control],paid_by_mode[mode]['actual_work'],group,coarse,mode)
        passed=True
        for mode in ('coarse','fine'):
            s=scores[mode+'_actual_work'];ci=s.get('exact_eight_block_95_pct',s['block_interval_95_pct'])
            passed&=s['gain_pct']>=2 and ci[0]>0
            for control in ('null_work','cached_seed0','cached_min3'):
                s=paired[mode+'_over_'+control];ci=s.get('exact_eight_block_95_pct',s['block_interval_95_pct'])
                passed&=s['gain_pct']>0 and ci[0]>=0
        write_csv(OUT/'predictions.csv',output)
        status='complete'
        atomic(OUT/'summary.json',{'status':status,'scores':scores,'paired_comparisons':paired,
            'primary_screen_passed':bool(passed),'completed_fits':len(completed),'parents':len(keys),
            'fit_records':[{k:v for k,v in r.items() if k not in ('held_ids','actions','validation_scores','held_scores')} for r in completed],
            'inference_inputs':42,'auxiliary_targets_training_only':2,'new_solver_calls':0,'new_feature_acquisitions':0,
            'source_sha256':sha(__file__),'matrix_sha256':sha(matrix_path),'splits_sha256':sha(SPLITS),
            'scope':'Repeated retained2022 full population, original folds. Observed termination work labels are not prefixes/total solve work; query0 optimistic, no independent/deployment claim.'})
    except BaseException as error:
        status='failed';atomic(OUT/'failure.json',{'status':status,'error':repr(error),
            'completed_fits':len(completed),'reward':None})
        raise
    finally:
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(OUT/'resources.json',{'status':status,'physical_parent_CPU_s':time.process_time()-cpu,
            'physical_child_CPU_s':usage.ru_utime+usage.ru_stime-initial.ru_utime-initial.ru_stime,
            'wall_s':time.monotonic()-wall,'completed_fits':len(completed),'new_solver_calls':0})


if __name__=='__main__':
    main()
