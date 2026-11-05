"""Evaluate at most two context-proposed, interpretable static policies.

Codex writes a bounded proposal plan using prior development feedback; numeric
thresholds and leaf actions are fitted only on fit data. This is an auditable
policy evaluation loop, not transformer training or an external LLM service.
"""
import argparse
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path

from analyze_matrix import deployed_cost
import policy
import run_pilot as common
from policy_fit_total_budget import train as train_total_budget

ACTIONS=['D','Fplus','Fminus']


def cost(case,action,fee=0.):
    return statistics.mean(deployed_cost(r,fee) for r in case['outcomes'][action])


def train_legacy_bare_solver_loss(rows,features,depth=2,min_leaf=12):
    """Deterministic cost-sensitive greedy tree with a fixed quantile grid."""
    if not set(features)<=policy.STATIC or depth not in (1,2,3) or min_leaf<8:
        raise ValueError('unsupported proposal capacity or feature')
    def leaf(rr):
        action=min(ACTIONS,key=lambda a:(sum(cost(r,a) for r in rr),a))
        return {'action':action}
    def raw_loss(rr,node):
        return sum(cost(r,policy.decide(node,r['features'])) for r in rr)
    def grow(rr,level):
        best=leaf(rr);best_loss=raw_loss(rr,best);initial_loss=best_loss
        if level>=depth or len(rr)<2*min_leaf:return best
        split=None
        for feature in sorted(features):
            values=sorted({r['features'].get(feature) for r in rr if r['features'].get(feature) is not None})
            if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
                raise ValueError('non-numeric training feature')
            if len(values)<2:continue
            thresholds=sorted({values[(len(values)-1)*q//8] for q in range(1,8)})
            for threshold in thresholds:
                for missing in ('left','right'):
                    left=[];right=[]
                    for r in rr:
                        v=r['features'].get(feature)
                        go_left=(missing=='left') if v is None else v<=threshold
                        (left if go_left else right).append(r)
                    if min(len(left),len(right))<min_leaf:continue
                    node={'feature':feature,'threshold':threshold,'missing':missing,
                          'left':leaf(left),'right':leaf(right)}
                    loss=raw_loss(rr,node)
                    # A fixed 1% in-fit improvement is required for a split;
                    # uncertainty is assessed later, not by adding more splits.
                    if loss<best_loss and loss<initial_loss*.99:
                        best_loss=loss;best=node;split=(left,right)
        if split:
            best['left']=grow(split[0],level+1);best['right']=grow(split[1],level+1)
        return best
    tree=grow(rows,0);policy.validate(tree,max_depth=depth)
    # Charge the real full extractor when a proposal uses any static feature.
    measured=sum(cost(r,policy.decide(tree,r['features']),r['feature_cpu_s']) for r in rows)
    simple=leaf(rows)
    return simple if raw_loss(rows,simple)<=measured else tree


train = train_total_budget


def validate_development_panel(cases,plan):
    """A trajectory is not a parent; an incomplete seed panel cannot earn reward."""
    required=plan.get('required_seeds',[0,1])
    if required not in ([0],[0,1]):raise ValueError('unfrozen development seeds')
    ids=[r['hash'] for r in cases]
    if len(set(ids))!=len(ids):raise ValueError('duplicate parent cannot enlarge the panel')
    cutoffs=set()
    for r in cases:
        if r['role'] not in ('development_fit','development_feedback'):
            raise ValueError('protected data cannot enter policy updates')
        if set(r['outcomes'])!={'D','Fplus','Fminus','Iminus'}:
            raise ValueError('strong static control is missing')
        if not set(r['features'])<=policy.STATIC:raise ValueError('forbidden training input')
        fee=r['feature_cpu_s']
        if isinstance(fee,bool) or not isinstance(fee,(int,float)) or not math.isfinite(fee) or fee<0:
            raise ValueError('invalid feature cost')
        for outcomes in r['outcomes'].values():
            if sorted(x['seed'] for x in outcomes)!=required:
                raise ValueError('incomplete or duplicate seeds')
            for x in outcomes:
                if x['status']=='ERROR':raise ValueError('failure cannot become a timeout label')
                if x['status'] in ('SAT','UNSAT') and not x['verify'].startswith('VERIFIED_'):
                    raise ValueError('unverified answer in development')
                cutoffs.add(x['cutoff_s'])
    if len(cutoffs)!=1:raise ValueError('mixed development cutoffs')
    if 'cutoff_s' in plan and cutoffs!={plan['cutoff_s']}:
        raise ValueError('plan and measured cutoff disagree')
    return {'required_seeds':required,'cutoff_s':next(iter(cutoffs)),
            'independent_parents':len(cases)}


def evaluate(rows,tree,baseline):
    policy.validate(tree)
    if isinstance(baseline,dict):policy.validate(baseline)
    elif baseline not in (*ACTIONS,'Iminus'):raise ValueError('unknown reference action')
    needs_features='feature' in tree
    selected=[cost(r,policy.decide(tree,r['features']),r['feature_cpu_s'] if needs_features else 0.) for r in rows]
    base=[cost(r,policy.decide(baseline,r['features']),r['feature_cpu_s'] if 'feature' in baseline else 0.)
          if isinstance(baseline,dict) else cost(r,baseline) for r in rows]
    baseline_mean=statistics.mean(base);chosen_mean=statistics.mean(selected)
    if baseline_mean<=0:raise ValueError('nonpositive baseline cost')
    rng=random.Random(20261104);samples=[]
    for _ in range(2000):
        indices=[rng.randrange(len(rows)) for _ in rows]
        b=statistics.mean(base[i] for i in indices)
        if b>0:samples.append(1-statistics.mean(selected[i] for i in indices)/b)
    samples.sort()
    examples=[]
    def used(node):
        return set() if 'action' in node else {node['feature']}|used(node['left'])|used(node['right'])
    fields=used(tree)|(used(baseline) if isinstance(baseline,dict) else set())
    for i in sorted(range(len(rows)),key=lambda i:selected[i]-base[i],reverse=True)[:3]:
        examples.append({'features':{k:rows[i]['features'].get(k) for k in sorted(fields)},
                         'selected_action':policy.decide(tree,rows[i]['features']),
                         'baseline_par2':base[i],'selected_par2':selected[i]})
    def solved_sum(reference):
        observed=isinstance(reference,dict) and 'feature' in reference
        return sum(statistics.mean(x['resolved'] and x['cpu_s']+(r['feature_cpu_s'] if observed else 0.)<=x['cutoff_s']
            for x in r['outcomes'][policy.decide(reference,r['features']) if isinstance(reference,dict) else reference])
            for r in rows)
    return {'reward':1-chosen_mean/baseline_mean,'baseline_par2':baseline_mean,'policy_par2':chosen_mean,
            'policy_solved_seed_average_count':solved_sum(tree),
            'baseline_solved_seed_average_count':solved_sum(baseline),
            'sum_par2_regret_to_free_three_action_oracle':sum(selected[i]-min(cost(r,a) for a in ACTIONS)
                for i,r in enumerate(rows)),
            'descriptive_95pct_bootstrap':[samples[len(samples)*25//1000],samples[len(samples)*975//1000]],
            'feedback_parents':len(rows),'worst_numeric_examples':examples,
            'interval_scope':'Exploratory repeated development feedback, not confirmation; parent is resampling unit.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--memory',type=Path,required=True);a=p.parse_args()
    integrity=json.loads((a.analysis/'integrity.json').read_text())
    summary=json.loads((a.analysis/'summary.json').read_text())
    if not integrity['complete_and_valid'] or summary['mode']!='static':raise ValueError('not a valid static matrix')
    cases=[json.loads(s) for s in (a.analysis/'cases.jsonl').read_text().splitlines() if s]
    plan=json.loads(a.plan.read_text())
    panel_contract=validate_development_panel(cases,plan)
    if any(r['role'] not in ('development_fit','development_feedback') for r in cases):
        raise ValueError('protected data cannot enter policy updates')
    if any(set(r['outcomes'])!={'D','Fplus','Fminus','Iminus'} for r in cases):
        raise ValueError('strong static control is missing')
    if any(not set(r['features'])<=policy.STATIC for r in cases):raise ValueError('forbidden training input')
    fit=[r for r in cases if r['role']=='development_fit'];feedback=[r for r in cases if r['role']=='development_feedback']
    if len(fit)<24 or len(feedback)<16:raise ValueError('too few independent development parents')
    round_id=plan['round']
    if round_id not in range(2,9) or not 1<=len(plan['proposals'])<=2:raise ValueError('update cap exceeded')
    prior=[json.loads(s) for s in a.memory.read_text().splitlines() if s] if a.memory.exists() else []
    if any(r.get('round')==round_id for r in prior):raise ValueError('round already recorded; immutable feedback')
    baseline=min(['D','Fplus','Fminus','Iminus'],key=lambda c:(statistics.mean(cost(r,c) for r in fit),c))
    a.out.mkdir(parents=True,exist_ok=False);records=[];controls={};round_start=time.process_time()
    common.write(a.out/'proposal_plan.json',plan)
    for index,proposal in enumerate(plan['proposals']):
        started=time.process_time()
        tree=train_total_budget(fit,proposal['features'],proposal['depth'],proposal['min_leaf'])
        feedback_result=evaluate(feedback,tree,baseline)
        key=(proposal['depth'],proposal['min_leaf'])
        if key not in controls:
            control=train_total_budget(fit,sorted(policy.STATIC),*key)
            controls[key]={'policy':control,'policy_sha256':policy.validate(control),
                          'depth':key[0],'min_leaf':key[1],'input_features':sorted(policy.STATIC),
                          'fit_par2':statistics.mean(cost(r,policy.decide(control,r['features']),
                                      r['feature_cpu_s'] if 'feature' in control else 0.) for r in fit),
                          'feedback':evaluate(feedback,control,baseline),
                          'training_scope':'Fit only; predeclared full numeric pool, same tree capacity, grid and total-budget loss.'}
        reference=controls[key]
        episode={'episode_id':f'formal_round{round_id}_{index}','round':round_id,
                 'split_role':'development_feedback','evaluation_kind':'new_server_formal_static_cost_matrix',
                 'policy':tree,'fit_parents':len(fit),'frozen_static_baseline_from_fit':baseline,
                 'proposal_rationale':proposal['rationale'],'proposal_kind':proposal['kind'],
                 'evaluation_cases_sha256':common.sha(a.analysis/'cases.jsonl'),
                 'analysis_identity':summary['identity'],'plan_sha256':common.sha(a.plan),
                 'panel_contract':panel_contract,
                 'matched_simple_control':reference,
                 'policy_vs_matched_simple_control':evaluate(feedback,tree,reference['policy']),
                 'learner_sha256':common.sha(Path(__file__)),
                 'threshold_fitter_sha256':common.sha(Path(__file__).with_name('policy_fit_total_budget.py')),
                 'local_fit_and_evaluation_cpu_s':time.process_time()-started,
                 'protected_test_cases_used':0,'development_gate_cases_used':0,
                 'is_deployment_validation':False,
                 'acceptance':'exploratory_positive_pending_gate_and_deployment' if feedback_result['reward']>0
                              else 'nonpositive_feedback_retained_for_memory_and_counterexamples',
                 **feedback_result}
        common.write(a.out/f'policy_{index}.json',tree);records.append(episode)
    common.write(a.out/'feedback.json',records)
    common.write(a.out/'simple_controls.json',list(controls.values()))
    common.write(a.out/'local_learning_cost.json',{'process_cpu_s':time.process_time()-round_start,
        'scope':'Fit/control/evaluation engineering expense, not deployment feature CPU or server solver expense.'})
    for episode in records:policy.append_episode(a.memory,episode)
    print(json.dumps([{'episode_id':r['episode_id'],'reward':r['reward'],
                       'descriptive_95pct_bootstrap':r['descriptive_95pct_bootstrap']} for r in records]))


if __name__=='__main__':main()
