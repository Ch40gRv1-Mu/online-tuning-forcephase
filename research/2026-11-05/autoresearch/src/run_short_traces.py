"""Formal, fractional CPU-bounded original-CNF probes; no parent reruns."""
from pathlib import Path
import concurrent.futures as futures
import gzip,hashlib,json,math,multiprocessing,os,resource,signal,subprocess,sys,time

ROOT=Path('/root/forcephase_subinstances_paired_v1_20261028')
CAMPAIGN=ROOT/'autoresearch/H04_short_original_D_trace'
CONFIGS={'D':['--phase=1','--forcephase=0']}
BUDGETS=(.1,.3)
BINARY=ROOT/'data/bin/cadical';CHECKER=ROOT/'data/bin/lrat-check'
sys.path.insert(0,str(ROOT/'experiments/lpn_sparse_secret'))
sys.path.insert(0,str(ROOT/'experiments/variable_subsample'))
import fplib
import run as original_driver

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def initialize(q):os.sched_setaffinity(0,{q.get()})

def limits(cpu):
    resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024**3,1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(cpu+1),math.ceil(cpu+1)))

def live_cpu(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return (int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
    except FileNotFoundError:return None

def bounded(cmd,log,budget,wall_cap):
    started=time.monotonic();term=False;killed=False;trigger=None
    with Path(log).open('x') as output:
        p=subprocess.Popen([str(x) for x in cmd],stdout=output,stderr=subprocess.STDOUT,preexec_fn=lambda:limits(budget))
        while True:
            pid,status,ru=os.wait4(p.pid,os.WNOHANG)
            if pid:break
            cpu=live_cpu(p.pid)
            wall=time.monotonic()-started
            if ((cpu is not None and cpu>=budget+.05) or wall>=wall_cap) and not killed:
                try:p.kill();killed=True
                except ProcessLookupError:pass
            elif cpu is not None and cpu>=budget and not term:
                try:p.terminate();term=True;trigger=cpu
                except ProcessLookupError:pass
            time.sleep(.002)
    p.returncode=os.waitstatus_to_exitcode(status)
    text=Path(log).read_text(errors='replace')
    r=dict(cmd=[str(x) for x in cmd],exit_code=p.returncode,cpu_s=ru.ru_utime+ru.ru_stime,wall_s=time.monotonic()-started,term_sent=term,hard_killed=killed,term_trigger_cpu_s=trigger,max_rss_bytes=ru.ru_maxrss*1024)
    r.update(fplib.parse_stats(text))
    r['status']='SAT' if p.returncode==10 else 'UNSAT' if p.returncode==20 else 'INTERRUPTED' if term and p.returncode in (-signal.SIGTERM,0) else 'OTHER'
    return r,text

def verify(p,config,probe,stdout,stem):
    if probe['status']=='SAT':
        check,txt=bounded([sys.executable,Path(__file__),'check-model',p['path'],str(stem)+'.log'],str(stem)+'.model.log',60,70)
        good=check['exit_code']==0 and check['cpu_s']<=60 and 'MODEL_VALID' in txt
        return dict(verify='VERIFIED_MODEL' if good else 'UNVERIFIED_MODEL',verified=good,model_check=check)
    if probe['status']=='UNSAT':
        direct=original_driver.direct_unsat_certificate(p['path'])
        if direct:return dict(**direct,verified=True)
        proof=Path(str(stem)+'.lrat')
        cert,_=bounded([BINARY,*CONFIGS[config],'--stats','--seed=0','--lrat','--binary=false',p['path'],proof],str(stem)+'.cert.log',1,3)
        same=all(k in probe and k in cert and probe[k]==cert[k] for k in ('conflicts','decisions'))
        good=False;check=None
        if cert['status']=='UNSAT' and same and cert['cpu_s']<=1:
            check,txt=bounded([CHECKER,p['path'],proof],str(stem)+'.check.log',60,70)
            good=check['exit_code']==0 and check['cpu_s']<=60 and ('c VERIFIED' in txt or 's VERIFIED' in txt)
        result=dict(verify='VERIFIED_LRAT' if good else 'UNVERIFIED_CERTIFICATION',verified=good,certification=cert,same_search=same,proof_check=check)
        if proof.exists():
            result['proof_bytes']=proof.stat().st_size;result['proof_sha256']=sha(proof)
            target=Path(str(proof)+'.gz')
            with proof.open('rb') as source,gzip.open(target,'xb',compresslevel=1) as dest:
                for b in iter(lambda:source.read(1024*1024),b''):dest.write(b)
            # Retain the short-probe raw proof as well; no cleanup is needed in this bounded campaign.
            result['proof_gzip']=str(target)
        return result
    return dict(verify='NOT_ANSWERED',verified=False)

def work(job):
    p,config,budget=job
    iid=f"{p['id']}.{config}.b{int(budget*1000)}"
    out=CAMPAIGN/'records'/(iid+'.json')
    if out.exists():
        r=json.loads(out.read_text());assert r['input_sha256']==p['sha256'];return r
    stat=os.statvfs(CAMPAIGN)
    if stat.f_bavail*stat.f_frsize<16*1024**3:raise RuntimeError('Disk reserve reached')
    begin=time.monotonic();cpu0=time.process_time();children0=resource.getrusage(resource.RUSAGE_CHILDREN)
    assert sha(p['path'])==p['sha256']
    stem=CAMPAIGN/'logs'/iid
    probe,stdout=bounded([BINARY,*CONFIGS[config],'--stats','--seed=0',p['path']],str(stem)+'.log',budget,3)
    verified=verify(p,config,probe,stdout,stem)
    parsed=all(k in probe for k in ('conflicts','decisions','propagations'))
    acceptable=(probe['status'] in ('SAT','UNSAT') and verified['verified']) or probe['status']=='INTERRUPTED'
    available=bool(parsed and acceptable and not probe['hard_killed'] and probe['cpu_s']<=budget+.05)
    if probe['status']=='SAT' and verified['verify']=='UNVERIFIED_MODEL':
        raise RuntimeError('SAT model could not be validated: '+iid)
    children1=resource.getrusage(resource.RUSAGE_CHILDREN)
    total_cpu=time.process_time()-cpu0+children1.ru_utime+children1.ru_stime-children0.ru_utime-children0.ru_stime
    r=dict(id=p['id'],family=p['family'],config=config,budget=budget,input_sha256=p['sha256'],available=available,probe=probe,verification=verified,feature_cpu_s=total_cpu,feature_wall_s=time.monotonic()-begin,affinity=sorted(os.sched_getaffinity(0)))
    if available:
        r['features']=dict(conflicts_per_cpu_s=probe['conflicts']/max(probe['cpu_s'],1e-9),decisions_per_cpu_s=probe['decisions']/max(probe['cpu_s'],1e-9),propagations_per_cpu_s=probe['propagations']/max(probe['cpu_s'],1e-9),conflicts_per_decision=probe['conflicts']/max(probe['decisions'],1),verified_solved=int(verified['verified']))
    tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(r)+'\n');tmp.rename(out)
    return r

def main():
    CAMPAIGN.mkdir(parents=True,exist_ok=True)
    for name in ('records','logs'):(CAMPAIGN/name).mkdir(exist_ok=True)
    assert sha(BINARY)=='025f51c05ddfd257e9d29a96e33ff62cb429150307b14282bcdabc12de8eb5cb'
    assert sha(CHECKER)=='44de8e0f3e46fff595e1a0810f34ef696a65da912c4c0987c431170f2d28eb07'
    ps=[]
    for name in ('reused_parent_instances.jsonl','instances.jsonl'):
        ps += [json.loads(s) for s in (ROOT/'results/parent_expansion/v1'/name).read_text().splitlines() if s]
    assert len(ps)==300 and len({p['id'] for p in ps})==300
    jobs=[(p,c,b) for p in ps for c in CONFIGS for b in BUDGETS]
    jobs.sort(key=lambda j:hashlib.sha256(f"H04-v1:{j[0]['id']}:{j[1]}:{j[2]}".encode()).hexdigest())
    with (CAMPAIGN/'RUN_STARTED.json').open('x') as f:
        json.dump(dict(pid=os.getpid(),created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),jobs=len(jobs),configs=CONFIGS,budgets=BUDGETS,workers=8,source_sha256=sha(__file__),fplib_sha256=sha(fplib.__file__),driver_sha256=sha(original_driver.__file__),binary_sha256=sha(BINARY)),f,indent=2)
    q=multiprocessing.Queue()
    for cpu in range(8):q.put(cpu)
    rows=[];begin=time.monotonic()
    with futures.ProcessPoolExecutor(max_workers=8,initializer=initialize,initargs=(q,)) as ex:
        for future in futures.as_completed([ex.submit(work,job) for job in jobs]):
            rows.append(future.result())
            if len(rows)%40==0:
                status=dict(completed=len(rows),total=len(jobs),available=sum(r['available'] for r in rows),wall_s=time.monotonic()-begin)
                (CAMPAIGN/'progress.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
    rows.sort(key=lambda r:(r['id'],r['config'],r['budget']))
    with (CAMPAIGN/'features.jsonl').open('x') as f:
        for r in rows:f.write(json.dumps(r)+'\n')
    summary=dict(status='EXTRACTION_COMPLETE',jobs=len(rows),available=sum(r['available'] for r in rows),all_feature_cpu_s=sum(r['feature_cpu_s'] for r in rows),solver_probe_cpu_s=sum(r['probe']['cpu_s'] for r in rows),verified_solved=sum(r['verification']['verified'] for r in rows),wall_s=time.monotonic()-begin)
    (CAMPAIGN/'completion.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='check-model':
        valid=fplib.check_model(sys.argv[2],fplib.parse_witness(Path(sys.argv[3]).read_text(errors='replace')))
        print('MODEL_VALID' if valid else 'MODEL_INVALID');sys.exit(0 if valid else 1)
    main()
