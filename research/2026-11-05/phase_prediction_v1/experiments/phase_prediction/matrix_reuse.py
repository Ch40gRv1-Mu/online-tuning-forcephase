"""SHA-bound reuse of validated T600 measurements in a frozen broader panel."""
import csv,json,shutil
from pathlib import Path
import run_pilot as common

def load_plan(root,spec,identity):
    digest=spec.get('validated_reuse_plan_sha256')
    if not digest:return None
    if spec.get('resource_recovery'):raise ValueError('two reuse contracts cannot be mixed')
    path=Path(root)/'metadata/validated_reuse_plan.json'
    if common.sha(path)!=digest:raise ValueError('changed validated reuse plan')
    p=json.loads(path.read_text())
    if p['version']!=1 or p['target_stage']!=spec['stage'] or p['source_stage']!='long600_fit16_recovery_v3':
        raise ValueError('wrong broader-panel reuse scope')
    with (Path(root)/'metadata/cohort.csv').open() as f:parents=list(csv.DictReader(f))
    if len(parents)!=40 or spec['seeds']!=[0,1] or spec['cutoff_s']!=600:
        raise ValueError('broader-panel plan changed')
    if any(r['role'] not in ('development_fit','development_feedback') for r in parents):
        raise ValueError('protected input cannot enter development')
    if sum(r['role']=='development_fit' for r in parents)!=24:raise ValueError('development split changed')
    expected={(r['hash'],s,a) for r in parents for s in spec['seeds'] for a in spec['actions']}
    reused=[(r['hash'],r['seed'],r['action']) for r in p['reused_records']]
    fresh=[tuple(x) for x in p['new_keys']]
    if len(reused)!=64 or len(fresh)!=256 or len(set(reused+fresh))!=320 or set(reused+fresh)!=expected:
        raise ValueError('incomplete frozen reuse/new matrix')
    allowed={'runner_sha256','resource_recovery_sha256','matrix_reuse_sha256','proof_file_limit_bytes'}
    if not identity.get('matrix_reuse_sha256') or identity['proof_file_limit_bytes']!=8*1024**3:
        raise ValueError('unbound or wrong reuse implementation')
    for old in p['allowed_source_identities']:
        if {k for k in set(old)|set(identity) if old.get(k)!=identity.get(k)}-allowed:
            raise ValueError('different solver/input-observer/proof semantics')
        if old['proof_file_limit_bytes'] not in (4*1024**3,8*1024**3):raise ValueError('unexpected old proof cap')
    return p

def validate_record(record,path,plan):
    matches=[x for x in plan['reused_records'] if x['run_id']==record['run_id']]
    if len(matches)!=1:raise ValueError('unbound reused run')
    bound=matches[0]
    if common.sha(path)!=bound['sha256']:raise ValueError('changed reused bytes')
    if any(record[k]!=bound[k] for k in ('hash','action','seed','role','input_sha256')):
        raise ValueError('wrong reused parent, role, action or input')
    if record['identity'] not in plan['allowed_source_identities'] or record['cutoff_s']!=600:
        raise ValueError('different physical identity')
    if record['status']=='ERROR' or record.get('contended'):raise ValueError('failed/contended result is not reusable')
    if record['status'] in ('SAT','UNSAT') and not record['verify'].startswith('VERIFIED_'):
        raise ValueError('unverified source answer')
    if record['proof_bytes']>=record['identity']['proof_file_limit_bytes']:
        raise ValueError('source proof cap may have bound')
    return bound

def inherit(base,root,spec,identity):
    plan=load_plan(root,spec,identity)
    if plan is None:return {},[]
    source=Path(base)/'phases'/plan['source_stage']
    complete=source/'results/completion.json';aliases=source/'results/aliases.json'
    if common.sha(complete)!=plan['source_completion_sha256'] or common.sha(aliases)!=plan['source_aliases_sha256']:
        raise ValueError('changed completed source stage')
    if json.loads(complete.read_text())['status']!='COMPLETE':raise ValueError('source not complete')
    with (Path(root)/'metadata/cohort.csv').open() as f:parents={r['hash']:r for r in csv.DictReader(f)}
    bykey={};ids=[]
    for item in plan['reused_records']:
        path=source/'results/runs'/(item['run_id']+'.json');r=json.loads(path.read_text())
        validate_record(r,path,plan)
        row=parents[r['hash']]
        if r['role']!=row['role'] or r['input_sha256']!=row['expected_sha256_cnf']:
            raise ValueError('current cohort differs from measured source')
        target=Path(root)/'results/runs'/path.name;target.parent.mkdir(exist_ok=True)
        if target.exists():raise ValueError('immutable broader-panel output exists')
        shutil.copyfile(path,target);bykey[(r['hash'],r['seed'],r['action'])]=r['run_id'];ids.append(r['run_id'])
    common.write(Path(root)/'results/validated_reuse_source.json',{
        'source_stage':plan['source_stage'],'source_completion_sha256':common.sha(complete),
        'source_archive_sha256':plan['source_archive_sha256'],'reused_runs':len(ids),
        'accounting':'Logical rows reference earlier physical work; no second physical charge.'})
    return bykey,ids
