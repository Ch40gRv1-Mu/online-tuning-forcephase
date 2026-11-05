"""Frozen timing-implementation qualification, not policy-performance data."""
import argparse,hashlib,json,os,re,resource,signal,subprocess,time
from pathlib import Path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def child(command,log,wall=3):
    start=time.monotonic();killed=False
    with log.open('x') as out:
        p=subprocess.Popen(list(map(str,command)),stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        while True:
            pid,status,usage=os.wait4(p.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-start>wall and not killed:os.killpg(p.pid,signal.SIGKILL);killed=True
            time.sleep(.005)
    p.returncode=os.waitstatus_to_exitcode(status)
    return {'command':list(map(str,command)),'exit_code':p.returncode,'cpu_s':usage.ru_utime+usage.ru_stime,
            'wall_s':time.monotonic()-start,'watchdog_killed':killed,'log_sha256':sha(log)}

def pigeonhole(path,n):
    m=n-1;clauses=[];v=lambda p,h:p*m+h+1
    for p in range(n):clauses.append([v(p,h) for h in range(m)])
    for h in range(m):
        for p in range(n):
            for q in range(p+1,n):clauses.append([-v(p,h),-v(q,h)])
    path.write_text(f'p cnf {n*m} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);a=p.parse_args();b=a.base
    root=b/'results/cpu_budget_v1';binary=b/'bin/cpu-budget-exec-v1'
    if root.exists() or binary.exists():raise ValueError('immutable qualification output exists')
    root.mkdir();start=time.process_time();before=resource.getrusage(resource.RUSAGE_CHILDREN);tests=[]
    result={'status':'FAIL','kind':'IMPLEMENTATION_TIMING_QUALIFICATION_NOT_PERFORMANCE','tests':tests}
    cpu=next((c for c in sorted(os.sched_getaffinity(0)) if c not in (0,1)),min(os.sched_getaffinity(0)))
    def checked(name,command,predicate,wall=3):
        record=child(command,root/(name+'.log'),wall);record['name']=name;record['pass']=bool(predicate(record));tests.append(record)
        if not record['pass']:raise ValueError('qualification failed: '+name)
        return record
    def wrapped(seconds,*cmd):
        return ['prlimit','--as=3221225472','--fsize=16777216','--cpu=3','--','taskset','-c',str(cpu),binary,str(seconds),*cmd]
    try:
        source=b/'src/deploy_budget_v1/cpu_budget_exec.c'
        checked('compile',['cc','-O2','-std=c11',source,'-lm','-o',binary],lambda r:r['exit_code']==0,60)
        native=b/'bin/cadical';checker=b/'bin/lrat-trim'
        if sha(native)!='b57d545231cab5a90357242cc838847356354324d891ef8ddaadcbf224e66bdb':raise ValueError('wrong original solver')
        if sha(checker)!='eb89bf384e1384af0d4e6ba81904c193f57e7848f357f1a6541e7f0bb6286603':raise ValueError('wrong independent checker')
        checked('busy_exec',wrapped(.15,'python3','-c','while True: pass'),
                lambda r:r['exit_code']==-signal.SIGPROF and .12<=r['cpu_s']<=.35 and not r['watchdog_killed'],2)
        checked('blocked_wall',wrapped(.15,'python3','-c','import time; time.sleep(.30)'),
                lambda r:r['exit_code']==0 and r['wall_s']>=.25 and r['cpu_s']<.15,2)
        checked('invalid_nan',wrapped('nan','python3','-c','raise SystemExit(99)'),lambda r:r['exit_code']==64,2)
        checked('argv_exit',wrapped(.5,'python3','-c','import sys; print(sys.argv[1]);sys.exit(7)','literal-argument'),lambda r:r['exit_code']==7,2)
        if 'literal-argument' not in (root/'argv_exit.log').read_text():raise ValueError('exec changed argv')
        expired=False
        for n in (20,30):
            cnf=root/f'php{n}.cnf';proof=root/f'php{n}.lrat';pigeonhole(cnf,n)
            name=f'cadical_php{n}'
            run=child(wrapped(.10,native,'--phase=1','--forcephase=0','--seed=0','--lrat','--binary=true','-t','2',cnf,proof),root/(name+'.log'))
            run.update(name=name,input_sha256=sha(cnf));tests.append(run)
            if run['exit_code']==-signal.SIGPROF and .07<=run['cpu_s']<=.30:
                run['pass']=True;expired=True;proof.unlink(missing_ok=True);break
            if run['exit_code']==20 and run['cpu_s']<.10:
                checked(name+'_proof',[checker,'--no-trim',cnf,proof],
                    lambda r:r['exit_code']==20 and re.search(r'^s VERIFIED',(root/(name+'_proof.log')).read_text(),re.M))
                run['pass']=True;proof.unlink(missing_ok=True)
            else:run['pass']=False;raise ValueError('native solver did not honor CPU timer')
        if not expired:raise ValueError('no native solver budget expiration observed')
        result.update(status='PASS',wrapper_sha256=sha(binary),source_sha256=sha(source),
                      solver_sha256=sha(native),checker_sha256=sha(checker),affinity_cpu=cpu,
                      contract='Native solver wall cap retained; fractional remaining process CPU timer survives exec and terminates native solver.')
    except BaseException as error:
        result['error']=type(error).__name__+': '+str(error)
        raise
    finally:
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        result['physical_cpu_s']=time.process_time()-start+after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
        result['accounting']='Current qualification parent+waited children; outer GNU-time is final complete receipt. Do not add test children again.'
        (root/'qualification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='tests'}),flush=True)

if __name__=='__main__':main()
