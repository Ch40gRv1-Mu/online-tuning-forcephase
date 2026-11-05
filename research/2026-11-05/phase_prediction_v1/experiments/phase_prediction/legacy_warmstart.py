"""One transparent in-context feedback round from historical CaDiCaL costs.

This is an offline warm start, not a new server run or deployment validation.
Professor MiniSAT outcomes and all protected/gate cases are excluded. Only
numeric static features are joined; family and file-name fields are unused.
"""
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import policy

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'results/phase_prediction_v1'
ACTIONS=['D','Fplus','Fminus']


def read(path):
    with path.open() as f:return list(csv.DictReader(f))


def features(r):
    def number(k):
        v=float(r[k])
        if not math.isfinite(v):raise ValueError('nonfinite source feature')
        return v
    result={'s_header_variables':number('header_vars'),'s_variables':number('vars'),
            's_clauses':number('clauses'),'s_log_variables':math.log1p(number('vars')),
            's_log_clauses':math.log1p(number('clauses')),
            's_cv_ratio':number('clauses')/max(1,number('vars')),
            's_mean_length':number('s_mean_len')}
    for old,new in [('s_unit_frac','s_unit_fraction'),('s_bin_frac','s_binary_fraction'),
                    ('s_ter_frac','s_ternary_fraction'),('s_pos_frac','s_positive_fraction'),
                    ('s_horn_frac','s_horn_fraction'),('s_antihorn_frac','s_antihorn_fraction')]:
        result[new]=number(old)
    assert set(result)<=policy.STATIC
    return result


def mean_cost(rows,action):return statistics.mean(r['costs'][action] for r in rows)


def train_stump(rows,feature):
    values=sorted({r['features'][feature] for r in rows})
    thresholds=sorted({values[(len(values)-1)*q//8] for q in range(1,8)})
    candidates=[]
    for threshold in thresholds:
        left=[r for r in rows if r['features'][feature]<=threshold]
        right=[r for r in rows if r['features'][feature]>threshold]
        if min(len(left),len(right))<8:continue
        la=min(ACTIONS,key=lambda a:(mean_cost(left,a),a))
        ra=min(ACTIONS,key=lambda a:(mean_cost(right,a),a))
        p={'feature':feature,'threshold':threshold,'missing':'left','left':{'action':la},'right':{'action':ra}}
        loss=statistics.mean(r['costs'][policy.decide(p,r['features'])]+r['feature_cpu_s'] for r in rows)
        candidates.append((loss,threshold,p))
    if not candidates:
        action=min(ACTIONS,key=lambda a:(mean_cost(rows,a),a))
        return {'action':action}
    return min(candidates,key=lambda c:(c[0],c[1]))[2]


def main():
    cohort=read(OUT/'development_frozen.csv')
    roles={r['hash']:r['role'] for r in cohort if r['role'] in {'development_fit','development_feedback'}}
    protected={r['hash'] for r in read(OUT/'test_candidates.csv')}
    assert not set(roles)&protected
    fs={r['instance']:r for name in ['static_features_dev.csv','static_features_heldout.csv']
        for r in read(ROOT/'results'/name) if r['instance'] in roles}
    costs=defaultdict(dict);bad=Counter()
    for name in ['m2_census','m5_heldout']:
        for r in read(ROOT/'results'/name/'runs.csv'):
            if r['instance'] not in roles or r['config'] not in ACTIONS or r['seed']!='0' or r['variant']!='orig':continue
            if r['status'] not in {'solved','timeout'}:
                bad['legacy_status_invalid']+=1;continue
            if r['status']=='solved' and r['verify_ok'].lower() not in {'true','1'}:
                bad['legacy_answer_unverified']+=1;continue
            if r['config'] in costs[r['instance']]:raise ValueError('duplicate historical cost')
            T=float(r['timeout'])
            cost=float(r['cpu']) if r['status']=='solved' else 2*T
            costs[r['instance']][r['config']]=cost
    cases=[]
    for h,role in sorted(roles.items()):
        if set(costs[h])!=set(ACTIONS) or h not in fs:
            bad['incomplete_historical_triplet_or_features']+=1;continue
        try:
            f=features(fs[h]);overhead=float(fs[h]['cpu_time'])
            if not math.isfinite(overhead) or overhead<0:raise ValueError('bad extraction CPU')
        except (ValueError,KeyError,ZeroDivisionError):
            bad['invalid_historical_features']+=1;continue
        cases.append({'hash':h,'role':role,'features':f,'feature_cpu_s':overhead,'costs':costs[h]})
    fit=[r for r in cases if r['role']=='development_fit']
    feedback=[r for r in cases if r['role']=='development_feedback']
    if len(fit)<16 or len(feedback)<8:raise ValueError('insufficient complete legacy development cases')
    baseline=min(ACTIONS,key=lambda a:(mean_cost(fit,a),a))
    baseline_feedback=mean_cost(feedback,baseline)
    hypotheses=[('length_stump','s_mean_length'),('binary_stump','s_binary_fraction')]
    output=OUT/'legacy_warmstart';output.mkdir(exist_ok=True)
    history=OUT/'context/episodes.jsonl'
    if history.exists():
        prior=[json.loads(s) for s in history.read_text().splitlines() if s]
        if any(r.get('episode_id','').startswith('legacy_round1_') for r in prior):
            raise ValueError('warm-start feedback already recorded; do not duplicate episodes')
    summaries=[]
    for label,feature in hypotheses:
        p=train_stump(fit,feature)
        policy_hash=policy.validate(p)
        (output/(label+'.json')).write_text(json.dumps(p,indent=2)+'\n')
        selected=[r['costs'][policy.decide(p,r['features'])]+r['feature_cpu_s'] for r in feedback]
        loss=statistics.mean(selected);reward=1-loss/baseline_feedback
        episode={'episode_id':'legacy_round1_'+label,'split_role':'development_feedback',
                 'evaluation_kind':'offline_static_cost_matrix_legacy_cadical_3.0.1_seed0',
                 'is_new_server_measurement':False,'is_deployment_validation':False,
                 'policy':p,'reward':reward,'fit_cases':len(fit),'feedback_cases':len(feedback),
                 'frozen_static_baseline':baseline,'baseline_feedback_par2':baseline_feedback,
                 'policy_feedback_par2_including_legacy_feature_cpu':loss,
                 'overhead_basis':'recorded legacy cheap-static extraction CPU; new graph extractor cost not measured',
                 'proposal_rationale':'Predeclared simple clause-length or binary-fraction hypothesis; thresholds and leaves fit on fit only',
                 'acceptance':'warmstart_hypothesis_only_pending_new_server_reproduction',
                 'protected_test_cases_used':0,'development_gate_cases_used':0}
        policy.append_episode(history,episode);summaries.append({**episode,'policy_sha256':policy_hash})
    receipt={'source':'legacy audited static costs; not professor MiniSAT CSV',
             'fit':len(fit),'feedback':len(feedback),'excluded':dict(bad),'baseline':baseline,
             'policies':summaries,'source_files_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in [ROOT/'results/m2_census/runs.csv',ROOT/'results/m5_heldout/runs.csv',
                           ROOT/'results/static_features_dev.csv',ROOT/'results/static_features_heldout.csv',
                           OUT/'development_frozen.csv',Path(__file__)]}}
    (output/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (output/'cases.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in cases))
    print(json.dumps({'fit':len(fit),'feedback':len(feedback),'baseline':baseline,
                      'rewards':{r['episode_id']:r['reward'] for r in summaries},'new_server_validation':False}))


if __name__=='__main__':main()
