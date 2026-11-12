"""R39 fixed original-selector veto; original held choices, no new model fitting."""
import json
import os
import time
import numpy as np

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS
from .recover_compact_cpu import OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS,DATA,load,read_csv,write_csv

OUT=DATA/'mechanism_R39_20261111'


def choose_with_guard(base_action,guardian_action,eligible):
    if eligible and base_action!='D' and guardian_action!=base_action:
        return 'D'
    return base_action


def main():
    wall,cpu=time.monotonic(),time.process_time()
    OUT.mkdir(exist_ok=False)
    atomic(OUT/'owner.json',{'pid':os.getpid(),'source_sha256':sha(__file__),
        'no_model_fits':True,'remote_R35_untouched':True})
    try:
        keys,_,costs,_,_,_=load()
        original=read_csv(DATA/'mechanism_R12_20261111/predictions.csv')
        original_summary=json.loads((DATA/'mechanism_R12_20261111/summary.json').read_text())
        recovery=read_csv(RETRY/'predictions.csv')
        recovery_summary=json.loads((RETRY/'scores.json').read_text())
        guard=read_csv(DATA/'mechanism_R38_20261111/predictions.csv')
        gs=json.loads((DATA/'mechanism_R38_20261111/summary.json').read_text())
        assert recovery_summary['status']==gs['status']=='complete'
        split=read_csv(SPLITS)
        assert all([r['instance_key'] for r in table]==keys for table in (original,recovery,guard,split))
        features=DATA/'mechanism_R38_features_20261111'
        with np.load(features/'features.npz') as z:
            assert z['keys'].tolist()==keys
            eligible=z['eligible'].copy()
        assert eligible.sum()==2325
        rec={r['instance_key']:r for r in map(json.loads,(features/'feature_receipts.jsonl').read_text().splitlines())}
        real_fee=np.array([rec[k]['common_CPU_s']+rec[k]['actual_extra_CPU_s'] if e else 0. for k,e in zip(keys,eligible)])
        null_fee=np.array([rec[k]['common_CPU_s']+rec[k]['null_extra_CPU_s'] if e else 0. for k,e in zip(keys,eligible)])
        first=np.array([float(r['first_acquisition_CPU_s']) for r in recovery])
        second=np.array([float(r['second_acquisition_CPU_s']) for r in recovery])
        failed=np.array([r['still_failed_paidD']=='True' for r in recovery]);assert failed.sum()==25
        coarse=np.array([r['coarse_group'] for r in split]);fine=np.array([r['fine_group'] for r in split])
        scores,comparisons,headroom={}, {}, {}
        output=[{'instance_key':k} for k in keys]
        for mode in ('coarse','fine'):
            folds=np.array([int(r[mode+'_fold']) for r in split]);name=mode+'_linear42_min3'
            enabled=np.array([original_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None for f in folds])
            base=np.array([ACTIONS.index(r[name+'_action']) for r in original]);query=np.array([float(r[name+'_decision_CPU_s']) for r in original])
            base[failed&enabled]=0;query[failed&enabled]=0
            assert np.array_equal(base,[ACTIONS.index(r[mode+'_action']) for r in recovery])
            base_h=query+(first+second)*enabled
            base_cost=timed_cost(costs[np.arange(len(keys)),base],base_h,600)
            assert np.allclose(base_cost,[float(r[mode+'_PAR2']) for r in recovery],rtol=0,atol=1e-10)
            groups=fine if mode=='fine' else coarse
            scores[mode+'_original']=evaluate(costs[:,0],base_cost,groups,coarse,mode)
            need=eligible&(base!=0)
            oracle=np.where(need,np.minimum(base_cost,timed_cost(costs[:,0],base_h,600)),base_cost)
            headroom[mode]={'eligible_F_proposals':int(need.sum()),'rejection_oracle_gain_over_D_pct':float(100*(costs[:,0]-oracle).sum()/costs[:,0].sum()),
                'rejection_oracle_increment_over_original_pct':float(100*(base_cost-oracle).sum()/base_cost.sum())}
            selected={};content={}
            for view in ('signed111','rewired111','topology63','constant_veto'):
                decision=np.zeros(len(keys),int) if view=='constant_veto' else np.array([ACTIONS.index(r[mode+'_'+view+'_action']) for r in guard])
                action=np.where(need&(decision!=base),0,base)
                assert all(ACTIONS[action[i]]==choose_with_guard(ACTIONS[base[i]],ACTIONS[decision[i]],bool(eligible[i])) for i in range(len(keys)))
                paid_need=np.zeros(len(keys),bool)
                if view!='constant_veto':
                    variable=np.array([gs['scores'][mode+'_'+view]['cuts'][f]['margin_PAR2_s'] is not None for f in folds])
                    paid_need=need&variable
                extra=(null_fee if view=='rewired111' else real_fee)*paid_need
                paid=timed_cost(costs[np.arange(len(keys)),action],base_h+extra,600)
                no_extra=timed_cost(costs[np.arange(len(keys)),action],base_h,600)
                score=evaluate(costs[:,0],paid,groups,coarse,mode)
                score['over_original']=evaluate(base_cost,paid,groups,coarse,mode)
                score['no_extra_guardian_cost']=evaluate(costs[:,0],no_extra,groups,coarse,mode)
                score.update(guardian_acquisition_calls=int(paid_need.sum()),guardian_logical_CPU_s=float(extra.sum()),
                    constant_guard_shortcuts=int((need&~paid_need).sum()),vetoed_F_proposals=int((need&(action==0)).sum()),
                    guardian_query_unmeasured_optimistic_zero=True,actions={a:int((action==j).sum()) for j,a in enumerate(ACTIONS)})
                scores[mode+'_'+view]=score;selected[view]=paid;content[view]=no_extra
                for i,row in enumerate(output):row[mode+'_'+view+'_action']=ACTIONS[action[i]];row[mode+'_'+view+'_PAR2']=float(paid[i])
                print(f"R39 {mode}_{view}: gain={score['gain_pct']:+.6f}%, solved={score['solved']}",flush=True)
            for control in ('rewired111','constant_veto','topology63'):
                comparisons[mode+'_over_'+control]=evaluate(selected[control],selected['signed111'],groups,coarse,mode)
        passed=True
        for mode in ('coarse','fine'):
            result=scores[mode+'_signed111'];ci=result.get('exact_eight_block_95_pct',result['block_interval_95_pct'])
            passed&=result['gain_pct']>=2 and ci[0]>0
            inc=result['over_original'];passed&=inc['gain_pct']>0 and inc.get('exact_eight_block_95_pct',inc['block_interval_95_pct'])[0]>=0
            for control in ('rewired111','constant_veto','topology63'):
                inc=comparisons[mode+'_over_'+control];passed&=inc['gain_pct']>0 and inc.get('exact_eight_block_95_pct',inc['block_interval_95_pct'])[0]>=0
        write_csv(OUT/'predictions.csv',output)
        atomic(OUT/'policy.json',{'schema':'R39.static_guard_operator.v1','primary_guard':'R38signed111',
            'rule':'eligible and base_action != D and guardian_action != base_action -> D; else base_action',
            'resource_qualification':'CNF nmax<=100000 and literal<=200000','no_instance_identity_input':True,
            'function':'src.anniversary2022_baseline.score_balanced_veto.choose_with_guard',
            'scope':'Executable decision combiner, OOF replay. No standalone full trained guardian or live deployment claim.'})
        atomic(OUT/'summary.json',{'status':'complete','parents':len(keys),'scores':scores,'paired_comparisons':comparisons,
            'headroom':headroom,'primary_screen_passed':bool(passed),'new_model_fits':0,'new_solver_calls':0,
            'new_feature_acquisitions':0,'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall,
            'source_sha256':sha(__file__),'base_paid_receipt_sha256':sha(RETRY/'scores.json'),
            'guardian_summary_sha256':sha(DATA/'mechanism_R38_20261111/summary.json'),
            'scope':'Repeated2022 original OOF replay; measured prior Mac input costs plus publisher solver times. Guardian query optimistic0, no independent/end-to-end deployment.'})
    except BaseException as error:
        atomic(OUT/'failure.json',{'status':'failed','error':repr(error),'reward':None,
            'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall})
        raise


if __name__=='__main__':
    main()
