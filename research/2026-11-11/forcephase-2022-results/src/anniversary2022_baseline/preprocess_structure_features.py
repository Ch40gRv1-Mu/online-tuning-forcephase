"""R33 actual no-search preprocessing features on count-admitted cached2022 CNFs."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_large_linear42 import atomic, timer_for, wait4
from .route_phase_2022 import load_formula
from .score_static_seed_agreement import load_views
from .structural_clusters import DATA, ROOT, load, read_csv

BINARY=ROOT/'work/preprocess_structure_20261111/preprocess_structure_v4'
REFERENCE=DATA/'mechanism_R21_features_20261111/features.npz'
NAMES=['log_active_variables','log_remaining_clauses','log_literal_occurrences','log_mean_clause_width',
    'binary_fraction','ternary_fraction','long_fraction','horn_fraction','inverse_horn_fraction',
    'pure_positive_fraction','pure_negative_fraction','positive_occurrence_fraction','mean_clause_balance','log_degree_CV2']


def execute(raw):
    wall,cpu=time.monotonic(),time.thread_time()
    process=subprocess.Popen([str(BINARY)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    timer=timer_for(process,8)
    try:
        closed_early=False
        try:process.stdin.write(raw);process.stdin.close()
        except BrokenPipeError:
            # A parser may close after an early result or error. Preserve its
            # output and actual exit instead of killing it and losing evidence.
            closed_early=True
            try:process.stdin.close()
            except BrokenPipeError:pass
        output=process.stdout.read(100001);process.stdout.close()
        if len(output)>100000:os.kill(process.pid,signal.SIGKILL)
        code,child,rss=wait4(process)
    except BaseException:
        try:os.kill(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        try:code,child,rss=wait4(process)
        except ChildProcessError:pass
        raise
    finally:timer.cancel()
    rec={'native_exit':code,'child_CPU_s':child,'maxrss':rss,'wall_s':time.monotonic()-wall,
        'stdin_closed_early':closed_early,
        'wrapper_CPU_s':time.thread_time()-cpu}
    if code==0:
        value=json.loads(output)
        assert value['decisions']==0
        up,post,change=map(np.array,(value['UP'],value['post'],value['change']))
        assert up.shape==post.shape==(14,) and change.shape==(6,)
        assert np.isfinite(np.r_[up,post,change]).all()
        rec.update(status='ok',UP=up.tolist(),post=post.tolist(),change=change.tolist(),decisions=0)
    else:rec.update(status='preprocess_error_paid_D',native_error=output.decode(errors='replace')[:800])
    return rec


def main(args):
    wall,cpu=time.monotonic(),time.process_time()
    usage=resource.getrusage(resource.RUSAGE_CHILDREN);initial_children=usage.ru_utime+usage.ru_stime
    args.out.mkdir(parents=True,exist_ok=False)
    with (args.out/'owner.lock').open('w') as lock,threadpool_limits(limits=1):
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fits=0
        try:
            keys,_,costs,_,_,_=load()
            with np.load(REFERENCE) as z:
                assert z['keys'].tolist()==keys
                admitted=z['eligible'].copy()
            assert len(keys)==4719 and admitted.sum()==2325
            base,valid=load_views(keys)[0]['linear42'];assert valid.all()
            identity_file=DATA/'cnf_graph_cnn_20261110/feature_receipts.jsonl'
            identity={r['instance_key']:r['raw_sha256'] for r in map(json.loads,identity_file.read_text().splitlines())}
            panel=ROOT/'work/astra_structure_panel_20261110'
            fallback={r['instance_key']:panel/'cnf'/(r['case']+'.cnf') for r in read_csv(panel/'association_only.csv')}
            binary_sha=sha(BINARY)
            # Integrated zero-search/propagation acceptance, not a separate run campaign.
            toy=execute(b'p cnf 3 3\n1 0\n-1 2 0\n-2 3 0\n')
            atomic(args.out/'first_semantic_receipt.json',toy)
            assert toy['status']=='ok' and toy['decisions']==0 and toy['UP'][1]==0
            atomic(args.out/'semantics.json',{'unit_chain_exhausted_without_decisions':True,
                'read_dimacs_and_real_simplify_API':True,'toy_physical_receipt':toy,
                'CDCL_solve_calls':0,'known_answers_used_as_features':False})
            ids=np.flatnonzero(admitted);index={k:i for i,k in enumerate(keys)}
            up,post,change=np.zeros((len(keys),14)),np.zeros((len(keys),14)),np.zeros((len(keys),6))
            successful=np.zeros(len(keys),bool);fee=np.zeros(len(keys))
            reused_count=0
            def job(key):
                if args.reuse is not None and (args.reuse/'records'/(key+'.json')).is_file():
                    previous=args.reuse/'records'/(key+'.json')
                    old=json.loads(previous.read_text())
                    assert old['raw_sha256']==identity[key] and old['binary_sha256']==binary_sha
                    rec={**old,'reused_physical_measurement':True,'ancestor_receipt':str(previous),
                        'ancestor_receipt_sha256':sha(previous)}
                    atomic(args.out/'records'/(key+'.json'),rec)
                    return key,rec
                began=time.thread_time()
                path=ROOT/'work/signed_boundary_20261110/cnf_cache'/(key+'.cnf.gz')
                if not path.is_file():path=fallback[key]
                raw=load_formula(path)
                assert hashlib.sha256(raw).hexdigest()==identity[key]
                header=next(line.strip().split() for line in raw.splitlines() if line.strip().startswith(b'p'))
                assert header[:2]==[b'p',b'cnf']
                preparation=time.thread_time()-began
                if int(header[2])>100000:
                    rec={'native_exit':None,'child_CPU_s':0.,'wrapper_CPU_s':0.,
                        'status':'header_resource_paid_D','native_not_launched':True,
                        'reason':'Same100k header cap enforced before library reserve'}
                else:rec=execute(raw)
                rec.update(instance_key=key,raw_sha256=identity[key],binary_sha256=binary_sha,
                    read_identity_CPU_s=preparation)
                rec['feature_CPU_s']=preparation+rec['wrapper_CPU_s']+rec['child_CPU_s']
                atomic(args.out/'records'/(key+'.json'),rec)
                return key,rec
            with ThreadPoolExecutor(max_workers=4) as pool:
                todo=iter(keys[i] for i in ids)
                pending=deque(pool.submit(job,next(todo)) for _ in range(4))
                done=0
                while pending:
                    key,rec=pending.popleft().result();i=index[key]
                    reused_count+=rec.get('reused_physical_measurement',False)
                    fee[i]=rec['feature_CPU_s']
                    if rec['status']=='ok':
                        successful[i]=True;up[i]=rec['UP'];post[i]=rec['post'];change[i]=rec['change']
                    done+=1
                    if done%100==0 or done==32:
                        print(f'PREPROCESSED {done}/2325 actual static inputs',flush=True)
                        atomic(args.out/'progress.json',{'completed':done,'total':2325,'successes':int(successful.sum())})
                    if time.monotonic()-wall>2400:raise TimeoutError('bounded no-search preprocessing exceeded40 minutes')
                    try:pending.append(pool.submit(job,next(todo)))
                    except StopIteration:pass
            # Exact UP/post comparison establishes added information before scoring.
            informative=successful & (np.max(np.abs(up-post),axis=1)>1e-7)
            oracle_sum=float((costs[informative,0]-costs[informative].min(axis=1)).sum())
            oracle_pp=100*oracle_sum/costs[:,0].sum()
            passed=int(informative.sum())>=50 and oracle_pp>=.5
            # A count-stratified cross-parent feature reassociation null; no labels/family.
            extra=np.c_[post,change];null=extra.copy()
            bins=np.floor(base[:,[0,1]]/np.log(4)).astype(int)
            for b in np.unique(bins[successful],axis=0):
                members=np.flatnonzero(successful & (bins==b).all(axis=1))
                order=sorted(members,key=lambda i:hashlib.sha256(('R33_count_null:'+keys[i]).encode()).hexdigest())
                if len(order)>1:null[order]=extra[np.roll(order,1)]
            common=np.c_[base,successful.astype(float),up]
            np.savez_compressed(args.out/'features.npz',keys=np.array(keys),admitted=admitted,valid=successful,
                informative=informative,fee=fee,UP57=common,BVE77=np.c_[common,extra],null77=np.c_[common,null])
            usage=resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(args.out/'summary.json',{'status':'complete','parents':4719,'attempted':int(admitted.sum()),
                'successful':int(successful.sum()),'errors_paid_D':int(np.sum(admitted&~successful)),
                'reused_compatible_physical_measurements':int(reused_count),
                'newly_informative':int(informative.sum()),'informative_oracle_population_pp':oracle_pp,
                'information_screen_passed':bool(passed),'reward':None,'feature_CPU_sum_s':float(fee.sum()),
                'physical_parent_CPU_s':time.process_time()-cpu,'physical_child_CPU_s':usage.ru_utime+usage.ru_stime-initial_children,
                'wall_s':time.monotonic()-wall,'native_binary_sha256':binary_sha,'source_sha256':sha(__file__),
                'input_reference_sha256':sha(REFERENCE),'identity_receipts_sha256':sha(identity_file),
                'feature_names':NAMES,'new_CDCL_solve_calls':0,
                'preprocess_API_calls_successful':2*int(successful.sum())+2,
                'preprocess_API_calls_upper_bound':2*int(admitted.sum())+2,
                'resource':'4workers, per native4CPU/6alarm/8wrapper,1GiB supervised RSS threshold (not a hard DATA limit), header100k before reserve; count-admitted100k maxID/200k occurrences',
                'meaning':'One actual static elimination round after rootUP, deliberately not an exact replay of default D initial/inprocessing state; no search, sweep, probes, walk or lucky phases'})
        except BaseException as exc:
            usage=resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(args.out/'failure.json',{'error':repr(exc),'physical_parent_CPU_s':time.process_time()-cpu,
                'physical_child_CPU_s':usage.ru_utime+usage.ru_stime-initial_children,'wall_s':time.monotonic()-wall,
                'completed_records':len(list((args.out/'records').glob('*.json')))})
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DATA/'mechanism_R33_features_20261111')
    parser.add_argument('--reuse',type=Path)
    main(parser.parse_args())
