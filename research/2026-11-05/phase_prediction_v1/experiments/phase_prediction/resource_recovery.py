"""Explicit nonbinding proof-cap recovery; never rewrites an inherited record."""
import json,shutil,time
from pathlib import Path
import run_pilot as common

def proof_capacity_available(base,workers,cap,active_proofs):
    # Bytes already written by an active job consume its reserved capacity.
    # Count physical allocation before reading free space, conservatively.
    allocated=0
    for path in active_proofs:
        try:allocated+=min(path.stat().st_blocks*512,cap)
        except FileNotFoundError:pass
    return shutil.disk_usage(base).free+allocated>=12*1024**3+workers*cap

def wait_for_capacity(base,workers,cap,active,condition,stop,proof,on_wait=lambda:None,empty_timeout=10):
    """Release the shared lock while existing workers finish and release storage."""
    empty_since=None;last_notice=None
    with condition:
        while not proof_capacity_available(base,workers,cap,active):
            if stop.is_set():return False
            now=time.monotonic()
            if last_notice is None or now-last_notice>=45:on_wait();last_notice=now
            if active:empty_since=None
            elif empty_since is None:empty_since=now
            elif now-empty_since>=empty_timeout:raise RuntimeError('disk reserve unavailable with no active proof')
            condition.wait(.25)
        if stop.is_set():return False
        active.add(proof)
    return True

def prior_recoveries(plan):
    if plan.get('version')==2:
        return [{'stage':plan['additional_source_stage'],'identity':plan['additional_source_identity'],
                 'resources_sha256':plan['additional_resources_sha256'],'log_sha256':plan['additional_log_sha256']}]
    return plan.get('prior_recoveries',[])

def load_plan(root,spec,identity):
    if not spec.get('resource_recovery'):return None
    path=Path(root)/'metadata/recovery_plan.json'
    if common.sha(path)!=spec['recovery_plan_sha256']:raise ValueError('changed recovery plan')
    plan=json.loads(path.read_text())
    if plan['source_stage']!='long600_fit16' or plan['target_stage']!=spec['stage']:
        raise ValueError('wrong recovery scope')
    old=plan['source_identity']
    if old['proof_file_limit_bytes']!=4*1024**3 or identity['proof_file_limit_bytes']!=8*1024**3:
        raise ValueError('unexpected proof cap recovery')
    version=plan.get('version',1)
    if version not in (1,2,3):raise ValueError('unknown resource recovery version')
    def compare(prior):
        differing={k for k in set(prior)|set(identity) if prior.get(k)!=identity.get(k)}
        allowed={'runner_sha256','proof_file_limit_bytes'}
        if version>=2:allowed.add('resource_recovery_sha256')
        if not differing<=allowed or 'runner_sha256' not in differing:
            raise ValueError('changed measurement semantics')
        if prior['proof_file_limit_bytes'] not in (4*1024**3,8*1024**3):
            raise ValueError('unexpected source proof cap')
    compare(old)
    if version>=2:
        expected_sources=['long600_fit16_recovery_v1']
        if version==3:expected_sources.append('long600_fit16_recovery_v2')
        sources=prior_recoveries(plan)
        if plan['target_stage']!=f'long600_fit16_recovery_v{version}' or [x['stage'] for x in sources]!=expected_sources:
            raise ValueError('wrong disk-admission recovery scope')
        if not identity.get('resource_recovery_sha256'):raise ValueError('unbound recovery implementation')
        for source in sources:compare(source['identity'])
    if spec['cutoff_s']!=600 or spec['seeds']!=[0] or spec['workers']!=2:
        raise ValueError('changed recovery budget or seed')
    reused=plan['reused_records'];new=plan['new_keys']
    keys=[(x['hash'],x['seed'],x['action']) for x in reused]
    fresh=[tuple(x) for x in new]
    if (version==1 and (len(reused)!=56 or len(new)!=8)) or not 56<=len(reused)<=63 or \
            len(reused)+len(new)!=64 or len(set(keys+fresh))!=64:
        raise ValueError('recovery matrix changed')
    allowed_sources={plan['source_stage']}
    if version>=2:allowed_sources.update(x['stage'] for x in prior_recoveries(plan))
    if any(x.get('source_stage',plan['source_stage']) not in allowed_sources for x in reused):
        raise ValueError('unfrozen source stage')
    return plan

def validate_reused(record,path,plan):
    key=(record['hash'],record['seed'],record['action'])
    bound={ (x['hash'],x['seed'],x['action']):x for x in plan['reused_records']}.get(key)
    if bound is None or common.sha(path)!=bound['sha256'] or record['run_id']!=bound['run_id']:
        raise ValueError('unbound reused result')
    source=bound.get('source_stage',plan['source_stage'])
    expected_identity=plan['source_identity']
    if source!=plan['source_stage']:
        allowed={x['stage']:x['identity'] for x in prior_recoveries(plan)}
        if source not in allowed:raise ValueError('wrong record source')
        expected_identity=allowed[source]
    if record['identity']!=expected_identity or record['status']=='ERROR' or record.get('contended'):
        raise ValueError('invalid reused physical measurement')
    if record['status'] in ('SAT','UNSAT') and not record['verify'].startswith('VERIFIED_'):
        raise ValueError('unverified reused answer')
    if record['cutoff_s']!=600 or record['proof_bytes']>=expected_identity['proof_file_limit_bytes']:
        raise ValueError('old proof cap may have bound')
    return bound

def inherit(base,root,spec,identity):
    plan=load_plan(root,spec,identity)
    if plan is None:return {},[]
    source=Path(base)/'phases'/plan['source_stage']
    if (source/'results/completion.json').exists():raise ValueError('unexpected completed source')
    progress=json.loads((source/'results/progress.json').read_text())
    if not progress['stopped']:raise ValueError('source is not stopped')
    failed=source/'results/runs'/(plan['failed_record']['run_id']+'.json')
    if common.sha(failed)!=plan['failed_record']['sha256']:raise ValueError('changed failure evidence')
    failure=json.loads(failed.read_text())
    if failure['exit_code']!=-25 or failure['proof_bytes']!=4*1024**3:
        raise ValueError('not the frozen proof-cap failure')
    evidence=Path(root)/'results/recovery_failures';evidence.mkdir(exist_ok=True)
    shutil.copyfile(failed,evidence/failed.name)
    resources=Path(base)/'logs/long600_fit16.resources.txt'
    common.write(Path(root)/'results/recovery_source.json',{
        'source_progress':progress,'physical_parent_resources':resources.read_text(),
        'source_failure_sha256':common.sha(failed),
        'note':'Source failure and physical expense retained; never a timeout training row.'})
    for prior in prior_recoveries(plan):
        stage=prior['stage'];additional=Path(base)/'phases'/stage
        if (additional/'results/completion.json').exists():raise ValueError('additional source already complete')
        ap=json.loads((additional/'results/progress.json').read_text())
        if not ap['stopped']:raise ValueError('additional source is not stopped')
        ar=Path(base)/'logs'/(stage+'.resources.txt')
        if common.sha(ar)!=prior['resources_sha256']:raise ValueError('changed stopped-source resources')
        al=Path(base)/'logs'/(stage+'.log')
        if common.sha(al)!=prior['log_sha256'] or 'RuntimeError: disk reserve reached' not in al.read_text():
            raise ValueError('additional source did not stop for disk admission')
        common.write(Path(root)/'results'/(stage+'_source.json'),{
            'source_progress':ap,'physical_parent_resources':ar.read_text(),'source_log':al.read_text(),
            'reason':'Recorded disk-admission stop; completed valid rows retained, no solver result discarded.'})
        for receipt in prior.get('failure_receipts',[]):
            path=additional/'results'/receipt['filename']
            if path.name!=receipt['filename'] or common.sha(path)!=receipt['sha256']:
                raise ValueError('changed scheduling failure evidence')
            dest=evidence/stage;dest.mkdir(exist_ok=True);shutil.copyfile(path,dest/path.name)
    bykey={};ids=[]
    for item in plan['reused_records']:
        origin=Path(base)/'phases'/item.get('source_stage',plan['source_stage'])
        path=origin/'results/runs'/(item['run_id']+'.json');r=json.loads(path.read_text())
        validate_reused(r,path,plan)
        target=Path(root)/'results/runs'/path.name;target.parent.mkdir(exist_ok=True)
        if target.exists():raise ValueError('recovery output already exists')
        shutil.copyfile(path,target)
        bykey[(r['hash'],r['seed'],r['action'])]=r['run_id'];ids.append(r['run_id'])
    return bykey,ids
