"""Proof-timed, immutable development matrices, separate from the P1 pilot.

The JSON specification and cohort CSV are frozen before launch. All successful
UNSAT runs must pass LRAT checking; errors stop new work. Never invokes a second
solver to certify a measured run. No family metadata or known answers are read.
"""
import argparse
import csv
import hashlib
import json
import os
import queue
import random
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import online_gate
import run_pilot as common
import resource_recovery
import matrix_reuse

STATIC = {**common.FLAGS, 'Iminus': ['--phase=0','--forcephase=0']}
ASCII_VERIFY='timed_LRAT_independent_check'
BINARY_VERIFY='timed_binary_LRAT_lrat_trim'


def hydrate_cached(cache_file,destination,identity,row,seed,action,T):
    """Reuse only an identical physical run, never merely a matching name."""
    item=json.loads(cache_file.read_text());source=Path(item['record_path'])
    if common.sha(source)!=item['record_sha256']:raise ValueError('cached measurement changed')
    r=json.loads(source.read_text())
    if r['run_id']!=destination.stem or r['identity']!=identity or r['input_sha256']!=row['sha256'] or \
            (r['hash'],r['seed'],r['action'],r['cutoff_s'])!=(row['hash'],seed,action,T):
        raise ValueError('cached measurement has different physical semantics')
    if r.get('contended') or r['status']=='ERROR' or \
            (r['status'] in ('SAT','UNSAT') and not r['verify'].startswith('VERIFIED_')):
        raise ValueError('failed measurement cannot be reused as a valid result')
    if identity['mode']!='static':raise ValueError('online reuse requires separate telemetry handling')
    if destination.exists():raise ValueError('immutable destination exists')
    shutil.copyfile(source,destination)
    # Preserve evidence when a compatible failed attempt's valid runs are
    # reused in a new stage. Keep the original JSON and command paths intact.
    source_logs=source.parent.parent.parent/'logs'
    target_logs=destination.parent.parent.parent/'logs'
    target_logs.mkdir(exist_ok=True)
    for original in source_logs.glob(r['run_id']+'*.log'):
        target=target_logs/original.name
        if target.exists() and common.sha(target)!=common.sha(original):
            raise ValueError('changed cached log evidence')
        if not target.exists():shutil.copyfile(original,target)
    return r['run_id']


def validate_spec(spec, rows):
    if spec['mode'] not in ('static','online'):raise ValueError('unknown matrix mode')
    roles={'development_fit','development_feedback'} if spec['mode']=='static' else {'development_fit'}
    if any(r['role'] not in roles for r in rows):raise ValueError('protected input role')
    if len({r['hash'] for r in rows})!=len(rows):raise ValueError('duplicate parent')
    if not rows or len(rows)>144:raise ValueError('invalid parent count')
    if spec['mode']=='online' and len(rows)>16:raise ValueError('online parent cap')
    if spec['actions']!=(list(STATIC) if spec['mode']=='static' else list(common.FLAGS)):
        raise ValueError('unfrozen action space')
    if spec['seeds'] not in ([0],[0,1]):raise ValueError('unfrozen seeds')
    fast=spec.get('fast_development') is True
    if fast:
        if spec['mode']!='static' or spec['cutoff_s']!=60 or spec['seeds']!=[0,1] or \
                len(rows)!=40 or sum(r['role']=='development_fit' for r in rows)!=24 or \
                sum(r['role']=='development_feedback' for r in rows)!=16 or \
                spec.get('memory_bytes')!=1536*1024**2 or spec.get('proof_file_limit_bytes')!=1024**3 or \
                spec['verification']!=BINARY_VERIFY or not spec.get('protocol_sha256'):
            raise ValueError('changed user-directed fast development contract')
        if spec.get('resource_recovery') or spec.get('validated_reuse_plan_sha256'):
            raise ValueError('fast recovery needs its own frozen identity plan')
    elif spec['cutoff_s'] not in (120,600):raise ValueError('unexpected formal cutoff')
    if spec['verification'] not in (ASCII_VERIFY,BINARY_VERIFY):raise ValueError('unverified mode')
    if spec['mode']=='online' and spec['verification']==BINARY_VERIFY:
        raise ValueError('binary online telemetry needs its own prefix/no-op gate')
    if spec['cutoff_s']==600 and spec['verification']!=BINARY_VERIFY:
        raise ValueError('long cutoff requires checked binary proof mode')
    if spec['workers'] not in ((4,8) if fast else (1,2,3,4)):raise ValueError('invalid worker limit')
    allowed_caps=(1024**3,2*1024**3,4*1024**3)
    if spec.get('resource_recovery') or spec.get('validated_reuse_plan_sha256'):allowed_caps=(*allowed_caps,8*1024**3)
    if spec.get('proof_file_limit_bytes',1024**3) not in allowed_caps:
        raise ValueError('unfrozen proof file cap')
    upper=len(rows)*len(spec['actions'])*len(spec['seeds'])*spec['cutoff_s']/3600
    if upper>spec['solver_upper_cpu_hours']+1e-9:raise ValueError('nominal solver budget infeasible')
    if spec['max_total_cpu_hours']<upper:raise ValueError('no room for nominal full matrix')
    return upper


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True)
    p.add_argument('--stage',required=True);p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--cohort',type=Path,required=True);a=p.parse_args()
    if not re.fullmatch('[a-z0-9_]+',a.stage):raise ValueError('invalid stage directory')
    base=a.base.resolve();root=base/'phases'/a.stage;root.mkdir(parents=True,exist_ok=True)
    spec=json.loads(a.spec.read_text())
    if common.sha(a.cohort)!=spec['cohort_sha256']:raise ValueError('cohort changed after freeze')
    with a.cohort.open() as f:rows=list(csv.DictReader(f))
    nominal=validate_spec(spec,rows)
    for d in ('results','logs','metadata'):(root/d).mkdir(exist_ok=True)
    for d in ('bin','data'):
        link=root/d
        if not link.exists():link.symlink_to(base/d,target_is_directory=True)
        if link.resolve()!=(base/d).resolve():raise ValueError('wrong shared input/tool directory')
    frozen=root/'metadata/spec.json'
    if frozen.exists() and json.loads(frozen.read_text())!=spec:raise ValueError('stage spec is immutable')
    common.write(frozen,spec)
    (root/'metadata/cohort.csv').write_bytes(a.cohort.read_bytes())
    binary=base/'bin'/('cadical-fpc2' if spec['mode']=='online' else 'cadical')
    binary_proof=spec['verification']==BINARY_VERIFY
    checker=base/'bin'/('lrat-trim' if binary_proof else 'lrat-check')
    if binary_proof:
        gate=json.loads((base/'results/binary_gate.json').read_text())
        if gate['status']!='PASS' or gate['checker_sha256']!=common.sha(checker):
            raise ValueError('binary proof verifier has not passed its current gate')
        if gate['solver_sha256']!=common.sha(binary):
            raise ValueError('binary proof solver differs from the validated one')
    if spec['mode']=='online':
        gate=json.loads((base/'results/online_gate.json').read_text())
        if gate['status']!='PASS' or gate['binary_sha256']!=common.sha(binary):
            raise ValueError('online binary has not passed the current no-op gate')
    identity={'solver_sha256':common.sha(binary),'checker_sha256':common.sha(checker),
              'extractor_sha256':common.sha(base/'bin/cnf_structure'),
              'runner_sha256':common.sha(Path(__file__)),'common_sha256':common.sha(Path(common.__file__)),
              'telemetry_contract_sha256':common.sha(Path(online_gate.__file__)),
              'mode':spec['mode'],'verification':spec['verification'],
              'proof_file_limit_bytes':spec.get('proof_file_limit_bytes',1024**3),
              'memory_bytes':spec.get('memory_bytes',3*1024**3),
              'checker_options':['--no-trim'] if binary_proof else [],
              'source_commit':'c60730422e758ef1cebe7aeddf2dda31c996bf04'}
    if spec.get('fast_development'):
        identity['extractor_memory_bytes']=3*1024**3
    if spec.get('resource_recovery_version') in (2,3) or spec.get('validated_reuse_plan_sha256'):
        identity['resource_recovery_sha256']=common.sha(Path(resource_recovery.__file__))
    if spec.get('validated_reuse_plan_sha256'):
        identity['matrix_reuse_sha256']=common.sha(Path(matrix_reuse.__file__))
    prior_identity=root/'results/identity.json'
    if prior_identity.exists() and json.loads(prior_identity.read_text())!=identity:
        raise ValueError('cannot resume with changed executable or observer code')
    common.write(prior_identity,identity)
    reuse_by_key,inherited_ids=resource_recovery.inherit(base,root,spec,identity)
    if spec.get('validated_reuse_plan_sha256'):
        reuse_by_key,inherited_ids=matrix_reuse.inherit(base,root,spec,identity)
    # Sampling, roles and aggregate budgets are frozen plan metadata. They do
    # not alter a deterministic single run and must not force duplicate runs.
    common.write(root/'results/plan_identity.json',{'spec_sha256':common.sha(a.spec),
        'cohort_sha256':common.sha(a.cohort),'measurement_identity':identity})
    # This extraction includes real graph features; terminal telemetry is never
    # mixed into these records. The role allowlist is explicit at the boundary.
    proof_cap=spec.get('proof_file_limit_bytes',1024**3)
    if shutil.disk_usage(base).free<12*1024**3+spec['workers']*proof_cap:
        raise RuntimeError('not enough disk for the reserve plus full concurrent proof caps')
    prepared=common.prepare(root,rows,allowed_roles={'development_fit','development_feedback'})
    records=root/'results/runs';records.mkdir(exist_ok=True);aliases=[];jobs=[];reused=list(inherited_ids)
    cache=base/'measurement_cache';cache.mkdir(exist_ok=True)
    for row in prepared:
        for seed in spec['seeds']:
            for action in spec['actions']:
                key={**identity,'input_sha256':row['sha256'],'action':action,'seed':seed,'T':spec['cutoff_s']}
                rid=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()[:32]
                rid=reuse_by_key.get((row['hash'],seed,action),rid)
                aliases.append({'hash':row['hash'],'action':action,'seed':seed,'run_id':rid})
                if not (records/(rid+'.json')).exists() and (cache/(rid+'.json')).exists() and spec['mode']=='static':
                    reused.append(hydrate_cached(cache/(rid+'.json'),records/(rid+'.json'),identity,row,seed,action,spec['cutoff_s']))
                if not (records/(rid+'.json')).exists():jobs.append((row,seed,action,rid))
    common.write(root/'results/aliases.json',aliases)
    common.write(root/'results/reused_measurements.json',reused)
    previous=[json.loads(p.read_text()) for p in records.glob('*.json')]
    used=sum(r['cpu_s']+r['verification_cpu_s'] for r in previous)
    used+=sum(json.loads(p.read_text())['feature_cpu_s'] for p in (root/'results').glob('*.features.json'))
    lock=threading.Lock();stop=threading.Event();done=0;start=time.monotonic();T=spec['cutoff_s']
    active_proofs=set()
    admission=threading.Condition(lock)
    cpuq=queue.Queue()
    for c in sorted(os.sched_getaffinity(0))[:spec['workers']]:cpuq.put(c)
    random.Random(20261104).shuffle(jobs)
    if used>=spec['max_total_cpu_hours']*3600:raise ValueError('stage CPU budget already exhausted')
    def one(job):
        nonlocal used,done
        if stop.is_set():return
        row,seed,action,rid=job;cpu=cpuq.get();path=Path(row['path'])
        proof=root/'logs'/(rid+'.lrat')
        try:
            def note_wait():
                active=[]
                for item in active_proofs:
                    try:
                        st=item.stat();active.append({'proof':item.name,'bytes':st.st_size,'allocated_bytes':st.st_blocks*512})
                    except FileNotFoundError:active.append({'proof':item.name,'absent':True})
                with (root/'results/admission_events.jsonl').open('a') as f:
                    f.write(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                        'free_bytes':shutil.disk_usage(base).free,'active':active,'waiting_run_id':rid})+'\n')
            if not resource_recovery.wait_for_capacity(base,spec['workers'],proof_cap,
                    active_proofs,admission,stop,proof,note_wait):return
            tel=root/'logs'/(rid+'.jsonl')
            flags=STATIC[action] if spec['mode']=='static' else online_gate.online_flags(action)
            cmd=[binary,*flags,f'--seed={seed}','--stats','--lrat',
                 '--binary=true' if binary_proof else '--binary=false','-t',str(T),path,proof]
            if spec['mode']=='online':cmd=['env',f'FPC_LOG={tel}',*cmd]
            r,text=common.child(cmd,root/'logs'/(rid+'.log'),T,cpu,
                                memory=identity['memory_bytes'],file_limit_bytes=proof_cap)
            r.update({'hash':row['hash'],'role':row['role'],'seed':seed,'action':action,'run_id':rid,
                'identity':identity,'input_sha256':row['sha256'],'cutoff_s':T,
                'status':{0:'UNKNOWN',10:'SAT',20:'UNSAT'}.get(r['exit_code'],'ERROR'),
                'verify':'NOT_ANSWERED','verification_cpu_s':0.,'launch_spec_sha256':common.sha(a.spec),
                'proof_bytes':proof.stat().st_size if proof.exists() else 0})
            if r['watchdog_killed']:r['status']='TIMEOUT'
            if r['status']=='SAT':
                begin=time.thread_time();ok=common.check_model(path,text,row['header_variables'])
                r['verification_cpu_s']+=time.thread_time()-begin
                r['verify']='VERIFIED_MODEL' if ok else 'INVALID_MODEL'
            elif r['status']=='UNSAT':
                checker_args=[checker,*identity['checker_options'],path,proof]
                ck,ct=common.child(checker_args,root/'logs'/(rid+'.check.log'),120,cpu,
                                   memory=identity['memory_bytes'])
                r['checker']=ck;r['verification_cpu_s']+=ck['cpu_s']
                expected_exit=20 if binary_proof else 0
                r['verify']='VERIFIED_LRAT' if ck['exit_code']==expected_exit and re.search(r'^[cs] VERIFIED',ct,re.M) else 'UNVERIFIED_CHECKER'
            # Keep failed proofs; delete verified or unfinished output only.
            if r['verify'].startswith('VERIFIED_') or r['status'] in ('UNKNOWN','TIMEOUT'):
                proof.unlink(missing_ok=True)
            r['contended']=r['cpu_s']>1 and r['wall_s']/r['cpu_s']>1.10
            r['resolved']=r['verify'].startswith('VERIFIED_') and r['cpu_s']<=T and not r['contended']
            r['par2']=r['cpu_s'] if r['resolved'] else 2*T
            if spec['mode']=='online':
                stream=online_gate.telemetry(tel)
                cp=online_gate.first_checkpoint(stream)
                r['prefix_reached']=cp is not None;r['telemetry_sha256']=common.sha(tel)
            with lock:
                if (records/(rid+'.json')).exists():raise ValueError('immutable record collision')
                common.write(records/(rid+'.json'),r);used+=r['cpu_s']+r['verification_cpu_s'];done+=1
                if spec['mode']=='static' and not r['contended'] and r['status']!='ERROR' and (
                        r['status'] not in ('SAT','UNSAT') or r['verify'].startswith('VERIFIED_')):
                    cp=cache/(rid+'.json')
                    item={'record_path':str(records/(rid+'.json')),'record_sha256':common.sha(records/(rid+'.json'))}
                    if cp.exists() and json.loads(cp.read_text())!=item:raise ValueError('immutable cache collision')
                    if not cp.exists():common.write(cp,item)
                if used/3600>=spec['max_total_cpu_hours'] or r['status']=='ERROR' or (
                        spec.get('fast_development') and r['contended']) or (
                        r['status'] in ('SAT','UNSAT') and not r['verify'].startswith('VERIFIED_')):
                    stop.set()
                common.write(root/'results/progress.json',{'completed_this_launch':done,'scheduled_this_launch':len(jobs),
                    'total_accounted_cpu_hours':used/3600,'wall_s':time.monotonic()-start,'stopped':stop.is_set()})
                print(f'{done}/{len(jobs)} {action} seed={seed} {r["status"]} {r["verify"]} cpu_h={used/3600:.4f}',flush=True)
        except BaseException as error:
            stop.set()
            # Failed measurements retain their resource receipt too. They are
            # never reclassified as ordinary timeouts or used as labels.
            failure={'hash':row['hash'],'seed':seed,'action':action,'run_id':rid,
                     'error':type(error).__name__+': '+str(error),'identity':identity}
            if 'r' in locals():failure['measured_run']=r
            common.write(root/'results'/(rid+'.failure.json'),failure)
            raise
        finally:
            with admission:
                active_proofs.discard(proof);admission.notify_all()
            cpuq.put(cpu)
    with ThreadPoolExecutor(spec['workers']) as ex:
        futures=[ex.submit(one,j) for j in jobs]
        for future in as_completed(futures):future.result()
    complete=[json.loads(p.read_text()) for p in sorted(records.glob('*.json'))]
    if len(complete)!=len(aliases):raise RuntimeError('stage stopped before the full frozen matrix completed')
    if spec['mode']=='online':
        checks=[]
        for row in prepared:
            for seed in spec['seeds']:
                streams={x['action']:online_gate.telemetry(root/'logs'/(x['run_id']+'.jsonl'))
                         for x in aliases if x['hash']==row['hash'] and x['seed']==seed}
                checks.append({'hash':row['hash'],'seed':seed,**online_gate.check_prefix(streams)})
        common.write(root/'results/prefix_checks.json',checks)
    common.write(root/'results/completion.json',{'status':'COMPLETE','runs':len(complete),'parents':len(rows),
        'accounted_cpu_hours':used/3600,'reused_runs':len(reused),
        'accounting_scope':'logical matrix CPU including reused measurements; parent time file records physical execution',
        'nominal_solver_upper_cpu_hours':nominal,'identity':identity})
    (root/'results/runs.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in complete))


if __name__=='__main__':main()
