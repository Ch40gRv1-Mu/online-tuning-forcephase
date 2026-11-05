"""Strict analysis of a complete three-action development pilot receipt.

Input directory mirrors the server root and contains metadata/pilot_frozen.csv
and results/{prepared.json,run_aliases.json,run_identity.json,runs/*.json}.
Never score an incomplete matrix or silently remove failed/contended runs.
"""
import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path

import policy
import run_pilot as common

ACTIONS=['D','Fplus','Fminus']


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--policies',type=Path)
    a=p.parse_args();root=a.root;out=a.out;out.mkdir(parents=True,exist_ok=True)
    with (root/'metadata/pilot_frozen.csv').open() as f:parents=list(csv.DictReader(f))
    hs={r['hash'] for r in parents}
    if len(hs)!=len(parents) or any(r['role']!='development_fit' for r in parents):
        raise ValueError('pilot must contain unique frozen fit inputs')
    prepared={r['hash']:r for r in json.loads((root/'results/prepared.json').read_text())}
    identity=json.loads((root/'results/run_identity.json').read_text())
    aliases=json.loads((root/'results/run_aliases.json').read_text())
    keys={(r['hash'],r['action']) for r in aliases}
    if len(keys)!=len(aliases) or keys!={(h,c) for h in hs for c in ACTIONS}:
        raise ValueError('planned identity matrix differs from frozen parent list')
    cases={h:{'hash':h,'role':'development_fit','costs':{},'runs':{}} for h in sorted(hs)}
    missing=[];invalid=[]
    for alias in aliases:
        path=root/'results/runs'/(alias['run_id']+'.json')
        if not path.exists():missing.append(alias);continue
        r=json.loads(path.read_text());h=alias['hash'];action=alias['action']
        if (r['hash'],r['action'],r['run_id'])!=(h,action,alias['run_id']):raise ValueError('wrong run alias')
        if r['identity']!=identity or r['input_sha256']!=prepared[h]['sha256']:
            raise ValueError('mixed binary/source/input identities')
        extension=root/'results/certification_extensions'/(r['run_id']+'.json')
        if r['verify']=='UNVERIFIED_CERTIFICATION' and extension.exists():
            extra=json.loads(extension.read_text())
            if extra['original_record_sha256']!=common.sha(path) or extra['input_sha256']!=r['input_sha256']:
                raise ValueError('wrong proof extension input or original record')
            if extra['binary_sha256']!=identity['binary_sha256'] or extra['checker_sha256']!=identity['checker_sha256']:
                raise ValueError('wrong proof extension tool identity')
            counters=('conflicts','decisions','propagations','restarts','rephased')
            if extra['verify']=='VERIFIED_LRAT_EXTENSION' and extra.get('checker_verified') and \
                    extra['original_run_id']==r['run_id'] and extra['measurement_changed'] is False and \
                    extra['checker']['exit_code']==0 and extra['certification']['exit_code']==20 and \
                    all(k in extra['certification'] and k in r and extra['certification'][k]==r[k] for k in counters):
                r={**r,'verify':extra['verify'],'verification_cpu_s':r['verification_cpu_s']+extra['verification_cpu_s'],
                   'verification_extension_file':str(extension),
                   'resolved':r['cpu_s']<=r['cutoff_s'] and not r.get('contended')}
                r['par2']=r['cpu_s'] if r['resolved'] else 2*r['cutoff_s']
        if r.get('contended') or r['status']=='ERROR' or (r['status'] in ['SAT','UNSAT'] and not r['verify'].startswith('VERIFIED_')):
            invalid.append({'hash':h,'action':action,'status':r['status'],'verify':r['verify'],'contended':r.get('contended')})
        cases[h]['runs'][action]=r
        cases[h]['costs'][action]=r['cpu_s'] if r['resolved'] else 2*r['cutoff_s']
    integrity={'planned_parents':len(hs),'planned_runs':len(aliases),'missing':missing,'invalid':invalid,
               'complete_and_valid':not missing and not invalid}
    (out/'integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
    if missing or invalid:raise ValueError('incomplete or invalid pilot; no scores produced; see integrity.json')
    for h,case in cases.items():
        feature=json.loads((root/'results'/(h+'.features.json')).read_text())
        if feature['source_sha256']!=prepared[h]['sha256']:raise ValueError('feature/input mismatch')
        if not set(feature['features'])<=policy.STATIC|{'feature_wall_s'}:
            raise ValueError('unapproved fields in learner feature record')
        case['features']=feature['features'];case['feature_cpu_s']=feature['feature_cpu_s']
        answers={r['status'] for r in case['runs'].values() if r['resolved']}
        if answers=={'SAT','UNSAT'}:raise ValueError('contradictory verified answers')
        case['answer']=next(iter(answers)) if answers else 'UNKNOWN'
        observed=[c for c in ACTIONS if case['runs'][c]['resolved']]
        winner=min(observed,key=lambda c:case['costs'][c]) if observed else None
        case['nominal_winner']=winner;case['clear_winner']=None
        if winner:
            best=case['costs'][winner]
            lower={c:case['costs'][c] if case['runs'][c]['resolved'] else case['runs'][c]['cutoff_s'] for c in ACTIONS}
            if all(lower[c]-best>max(.02,.10*best) for c in ACTIONS if c!=winner):case['clear_winner']=winner
    values=list(cases.values());baselines={c:statistics.mean(r['costs'][c] for r in values) for c in ACTIONS}
    sbs=min(ACTIONS,key=lambda c:baselines[c]);oracle=statistics.mean(min(r['costs'].values()) for r in values)
    summary={'dataset_role':'development_fit_pilot; not held-out validation','parents':len(values),
             'static_mean_par2':baselines,'static_solved':{c:sum(r['runs'][c]['resolved'] for r in values) for c in ACTIONS},
             'pilot_single_best_static_diagnostic':sbs,'oracle_mean_par2_diagnostic':oracle,
             'oracle_improvement_over_D':1-oracle/baselines['D'],
             'oracle_improvement_over_pilot_SBS':1-oracle/baselines[sbs],
             'nominal_winners':dict(Counter(r['nominal_winner'] or 'unresolved' for r in values)),
             'clear_winners':dict(Counter(r['clear_winner'] or 'ambiguous_or_unresolved' for r in values)),
             'feature_mean_cpu_s':statistics.mean(r['feature_cpu_s'] for r in values),
             'feature_median_cpu_s':statistics.median(r['feature_cpu_s'] for r in values),
             'solver_cpu_hours':sum(x['cpu_s'] for r in values for x in r['runs'].values())/3600,
             'verification_cpu_hours':sum(x['verification_cpu_s'] for r in values for x in r['runs'].values())/3600,
             'policies_diagnostic':[]}
    if a.policies:
        for path in sorted(a.policies.glob('*.json')):
            tree=json.loads(path.read_text())
            if 'feature' not in tree and set(tree)!={'action'}:continue
            digest=policy.validate(tree);needs_features='feature' in tree
            cost=statistics.mean(r['costs'][policy.decide(tree,r['features'])]+(r['feature_cpu_s'] if needs_features else 0) for r in values)
            summary['policies_diagnostic'].append({'name':path.stem,'sha256':digest,'mean_par2_with_feature_cpu':cost,
                                                   'improvement_over_D':1-cost/baselines['D'],
                                                   'scope':'same development-fit inputs; not policy validation'})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Keep raw run IDs in a traceable data artifact, not in the learner features.
    (out/'cases.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in values))
    print(json.dumps(summary))


if __name__=='__main__':main()
