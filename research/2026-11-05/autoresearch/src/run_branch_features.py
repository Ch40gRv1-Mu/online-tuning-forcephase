"""Formal H06: whole extraction + root propagation + six branches within .3 CPU seconds."""
from pathlib import Path
import concurrent.futures as futures
import hashlib,json,multiprocessing,os,resource,subprocess,time

ROOT=Path('/root/forcephase_subinstances_paired_v1_20261028')
CAMPAIGN=ROOT/'autoresearch/H06_conditioned_propagation'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def initialize(q):os.sched_setaffinity(0,{q.get()})

def work(p):
    out=CAMPAIGN/'records'/(p['id']+'.json')
    if out.exists():
        r=json.loads(out.read_text());assert r['input_sha256']==p['sha256'];return r
    begin=time.monotonic();cpu0=time.process_time();child0=resource.getrusage(resource.RUSAGE_CHILDREN)
    stat0=time.process_time();size=Path(p['path']).stat().st_size;stat_cpu=time.process_time()-stat0
    assert size==p['input_bytes'] and sha(p['path'])==p['sha256']
    seed=int(hashlib.sha256(('forcephase-autoresearch-h06-v1:'+p['id']).encode()).hexdigest()[:16],16)
    r=dict(id=p['id'],family=p['family'],input_sha256=p['sha256'],seed=seed,file_bytes=size,stat_cpu_s=stat_cpu,charged_gate_cpu_s=max(.001,stat_cpu),affinity=sorted(os.sched_getaffinity(0)))
    remaining=.3-(time.process_time()-cpu0);payload=None
    if remaining>0 and time.monotonic()-begin<3:
        try:
            proc=subprocess.run([str(CAMPAIGN/'branch_features'),p['path'],str(remaining),str(seed)],capture_output=True,text=True,timeout=max(.001,3-(time.monotonic()-begin)))
            r.update(returncode=proc.returncode,stderr=proc.stderr[-1000:])
            if proc.returncode==0:payload=json.loads(proc.stdout)
        except subprocess.TimeoutExpired:r['error']='WALL_TIMEOUT'
    child1=resource.getrusage(resource.RUSAGE_CHILDREN)
    r['cpu_s']=time.process_time()-cpu0+child1.ru_utime+child1.ru_stime-child0.ru_utime-child0.ru_stime;r['wall_s']=time.monotonic()-begin
    r['extraction_complete']=payload is not None
    r['available']=bool(payload is not None and payload['usable_branch'] and r['cpu_s']<=.3 and r['wall_s']<=3)
    if payload is not None:r.update(payload)
    r['status']='COMPLETE' if r['available'] else 'FEATURE_UNAVAILABLE'
    tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(r)+'\n');tmp.rename(out)
    return r

def main():
    (CAMPAIGN/'records').mkdir(parents=True,exist_ok=True);ps=[]
    for name in ('reused_parent_instances.jsonl','instances.jsonl'):
        ps += [json.loads(s) for s in (ROOT/'results/parent_expansion/v1'/name).read_text().splitlines() if s]
    assert len(ps)==300 and len({p['id'] for p in ps})==300
    with (CAMPAIGN/'RUN_STARTED.json').open('x') as f:
        json.dump(dict(pid=os.getpid(),created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),parents=300,workers=8,budget_cpu_s=.3,source_sha256=sha(__file__),binary_sha256=sha(CAMPAIGN/'branch_features')),f,indent=2)
    q=multiprocessing.Queue()
    for cpu in range(8):q.put(cpu)
    begin=time.monotonic();rows=[]
    with futures.ProcessPoolExecutor(max_workers=8,initializer=initialize,initargs=(q,)) as ex:
        for future in futures.as_completed([ex.submit(work,p) for p in ps]):
            rows.append(future.result())
            if len(rows)%40==0:print(json.dumps(dict(completed=len(rows),available=sum(r['available'] for r in rows),wall_s=time.monotonic()-begin)),flush=True)
    rows.sort(key=lambda r:r['id'])
    with (CAMPAIGN/'features.jsonl').open('x') as f:
        for r in rows:f.write(json.dumps(r)+'\n')
    summary=dict(status='EXTRACTION_COMPLETE',parents=300,extraction_complete=sum(r['extraction_complete'] for r in rows),available=sum(r['available'] for r in rows),cpu_s=sum(r['cpu_s'] for r in rows),wall_s=time.monotonic()-begin)
    (CAMPAIGN/'completion.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
