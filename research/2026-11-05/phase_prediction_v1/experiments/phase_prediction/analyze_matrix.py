"""Strict complete-matrix import for formal development results.

Only development roles are accepted. Independent seeds are averaged within a
parent before any parent-level comparison. Failed or contended runs block the
entire analysis; they cannot disappear from its denominator.
"""
import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import policy
import online_gate
import run_matrix
import run_pilot as common
import resource_recovery
import matrix_reuse

ONLINE_FEATURES = {
    'c_glue_mean','c_glue_low_frac','c_minsize_mean','c_backjump_mean',
    'c_props_per_dec','c_dec_per_conf','x_glue_ratio','x_level_avg',
    'x_jump_avg','x_saved_neg_frac','c_native_pos_frac','r_stable',
}


def deployed_cost(outcome,overhead=0.):
    if not math.isfinite(overhead) or overhead<0:raise ValueError('invalid deployment cost')
    if outcome['resolved'] and outcome['cpu_s']+overhead<=outcome['cutoff_s']:
        return outcome['cpu_s']+overhead
    return 2*outcome['cutoff_s']


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();root=a.root;out=a.out
    out.mkdir(parents=True,exist_ok=True)
    spec=json.loads((root/'metadata/spec.json').read_text())
    with (root/'metadata/cohort.csv').open() as f:parents=list(csv.DictReader(f))
    run_matrix.validate_spec(spec,parents)
    if common.sha(root/'metadata/cohort.csv')!=spec['cohort_sha256']:raise ValueError('cohort changed')
    identity=json.loads((root/'results/identity.json').read_text())
    recovery_plan=resource_recovery.load_plan(root,spec,identity)
    reuse_plan=matrix_reuse.load_plan(root,spec,identity)
    completion=json.loads((root/'results/completion.json').read_text())
    if completion['status']!='COMPLETE' or completion['identity']!=identity:raise ValueError('incomplete stage')
    aliases=json.loads((root/'results/aliases.json').read_text())
    expected={(r['hash'],s,c) for r in parents for s in spec['seeds'] for c in spec['actions']}
    keys={(r['hash'],r['seed'],r['action']) for r in aliases}
    if keys!=expected or len(aliases)!=len(expected):raise ValueError('incomplete planned matrix')
    prepared={r['hash']:r for r in json.loads((root/'results/prepared.json').read_text())}
    cases={r['hash']:{'hash':r['hash'],'role':r['role'],'outcomes':{c:[] for c in spec['actions']}} for r in parents}
    missing=[];invalid=[];cpu=0.;verify_cpu=0.;streams={}
    for alias in aliases:
        path=root/'results/runs'/(alias['run_id']+'.json')
        if not path.exists():missing.append(alias);continue
        r=json.loads(path.read_text());h=alias['hash'];c=alias['action']
        if any(r[k]!=alias[k] for k in ('hash','seed','action','run_id')):raise ValueError('wrong result alias')
        if r['identity']!=identity:
            if recovery_plan is not None:resource_recovery.validate_reused(r,path,recovery_plan)
            elif reuse_plan is not None:matrix_reuse.validate_record(r,path,reuse_plan)
            else:raise ValueError('mixed identities')
        if r['input_sha256']!=prepared[h]['sha256']:raise ValueError('mixed input identities')
        if r['cutoff_s']!=spec['cutoff_s']:raise ValueError('mixed deadlines')
        if r['status']=='ERROR' or r.get('contended') or (
                r['status'] in ('SAT','UNSAT') and not r['verify'].startswith('VERIFIED_')):
            invalid.append({'hash':h,'seed':r['seed'],'action':c,'status':r['status'],'verify':r['verify'],
                            'contended':r.get('contended')})
        cpu+=r['cpu_s'];verify_cpu+=r['verification_cpu_s']
        if spec['mode']=='online':
            tel=root/'logs'/(r['run_id']+'.jsonl')
            if common.sha(tel)!=r['telemetry_sha256']:raise ValueError('changed telemetry evidence')
            streams.setdefault(h,{})[c]=online_gate.telemetry(tel)
        cases[h]['outcomes'][c].append({k:r[k] for k in
            ('seed','cpu_s','cutoff_s','resolved','status','verify','run_id')})
    integrity={'complete_and_valid':not missing and not invalid,'missing':missing,'invalid':invalid,
               'parents':len(parents),'runs':len(aliases)}
    common.write(out/'integrity.json',integrity)
    if missing or invalid:raise ValueError('formal matrix contains missing/invalid/contended runs')
    prefixes={}
    if spec['mode']=='online':
        prefixes={r['hash']:r for r in json.loads((root/'results/prefix_checks.json').read_text())}
        if set(prefixes)!=set(cases) or spec['seeds']!=[0]:raise ValueError('unexpected online prefix matrix')
        for h,records in streams.items():
            checked=online_gate.check_prefix(records)
            if checked['reached']!=prefixes[h]['reached']:raise ValueError('inconsistent prefix receipt')
            if checked['reached'] and any(checked[k]!=prefixes[h][k] for k in ('digest','conflicts','features')):
                raise ValueError('inconsistent prefix observations')
    for h,case in cases.items():
        feature=json.loads((root/'results'/(h+'.features.json')).read_text())
        if feature['source_sha256']!=prepared[h]['sha256']:raise ValueError('wrong feature input')
        if feature['extractor_sha256']!=identity['extractor_sha256']:raise ValueError('mixed feature observers')
        if not math.isfinite(feature['feature_cpu_s']) or feature['feature_cpu_s']<0:
            raise ValueError('invalid feature cost')
        if not set(feature['features'])<=policy.STATIC|{'feature_wall_s'}:raise ValueError('forbidden input feature')
        case['features']={k:v for k,v in feature['features'].items() if k in policy.STATIC}
        case['feature_cpu_s']=feature['feature_cpu_s']
        case['costs']={c:statistics.mean(deployed_cost(r) for r in rows) for c,rows in case['outcomes'].items()}
        case['solved_fraction']={c:statistics.mean(r['resolved'] for r in rows) for c,rows in case['outcomes'].items()}
        answers={r['status'] for rows in case['outcomes'].values() for r in rows if r['resolved']}
        if answers=={'SAT','UNSAT'}:raise ValueError('contradictory verified answers')
        if prefixes:
            case['prefix_reached']=prefixes[h]['reached']
            case['online_features']={k:v for k,v in prefixes[h].get('features',{}).items() if k in ONLINE_FEATURES}
            # Static graph extraction was not required by these fixed online
            # continuations, so its fee is not charged to their recorded costs.
    values=list(cases.values());summaries={}
    for role in sorted({r['role'] for r in values}):
        rr=[r for r in values if r['role']==role]
        means={c:statistics.mean(r['costs'][c] for r in rr) for c in spec['actions']}
        learned_actions=[c for c in spec['actions'] if c!='Iminus']
        oracle=statistics.mean(min(r['costs'][c] for c in learned_actions) for r in rr)
        best=min(means,key=means.get)
        summaries[role]={'parents':len(rr),'mean_par2':means,
            'solved_seed_average_count':{c:sum(r['solved_fraction'][c] for r in rr) for c in spec['actions']},
            'best_static_diagnostic':best,'three_action_oracle_mean_par2':oracle,
            'oracle_improvement_over_D':1-oracle/means['D'],
            'oracle_improvement_over_best_static_control':1-oracle/means[best]}
        summaries[role]['all_actions_censored_parents']=sum(
            all(not x['resolved'] for rows in r['outcomes'].values() for x in rows) for r in rr)
        if spec['mode']=='online':
            summaries[role]['action_semantics']='All configurations share D prefix; names denote fixed continuations after the K=1000 natural restart, not static from-start configurations.'
        else:summaries[role]['action_semantics']='Static option pair from initialization.'
        if spec.get('diagnostic_subcutoffs_s'):
            sub={}
            for cutoff in spec['diagnostic_subcutoffs_s']:
                if cutoff<=0 or cutoff>=spec['cutoff_s']:raise ValueError('invalid diagnostic subcutoff')
                costs={c:[statistics.mean(deployed_cost({**x,'cutoff_s':cutoff}) for x in r['outcomes'][c])
                          for r in rr] for c in spec['actions']}
                averages={c:statistics.mean(v) for c,v in costs.items()}
                minimum=min(averages,key=averages.get)
                opt=statistics.mean(min(costs[c][i] for c in learned_actions) for i in range(len(rr)))
                sub[str(cutoff)]={'mean_par2':averages,'best_static_diagnostic':minimum,
                    'three_action_oracle_mean_par2':opt,
                    'oracle_improvement_over_best_static_control':1-opt/averages[minimum],
                    'scope':'Within longer proof-timed runs; diagnostic censoring only, not a separate shorter-cutoff rerun.'}
            summaries[role]['subcutoff_diagnostics']=sub
    summary={'mode':spec['mode'],'identity':identity,'roles':summaries,
             'resource_recovery':spec.get('resource_recovery',False),
             'timing_contract':{'native_solver_wall_limit_s':spec['cutoff_s'],
                'process_cpu_fallback_s':spec['cutoff_s']+2,'external_wall_watchdog_s':spec['cutoff_s']+10,
                'score':'Observed CPU, success only when verified and CPU<=T; selector adds actual h.',
                'censoring_scope':'Native -t is a wall limit. UNKNOWN does not assert that T CPU seconds were consumed.'},
             'solver_cpu_hours':cpu/3600,'checker_and_model_cpu_hours':verify_cpu/3600,
             'feature_cpu_hours':sum(r['feature_cpu_s'] for r in values)/3600,
             'online_prefix_reached':sum(r.get('prefix_reached',False) for r in values),
             'interpretation':'Development diagnostic; no held-out confirmation or deployed policy claim.'}
    common.write(out/'summary.json',summary)
    (out/'cases.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in values))
    print(json.dumps(summary))


if __name__=='__main__':main()
