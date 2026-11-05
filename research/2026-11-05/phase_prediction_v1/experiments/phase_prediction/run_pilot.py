"""Standalone Linux pilot executor for public SAT CNFs, no family metadata.

This file and an identifier/size-only pilot CSV are sufficient on the server.
The learner and professor attachments remain local. Logs/results are immutable.
"""
import argparse
import csv
import hashlib
import json
import lzma
import os
import platform
import queue
import random
import re
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

FLAGS={'D':['--phase=1','--forcephase=0'],'Fplus':['--phase=1','--forcephase=1'],
       'Fminus':['--phase=0','--forcephase=1']}


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def write(path,value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');tmp.rename(path)


def child(cmd,log,cutoff,cpu,memory=3*1024**3,file_limit_bytes=1024**3):
    # prlimit/taskset exec the solver, so wait4 accounts for this one process.
    actual=['prlimit',f'--as={memory}',f'--fsize={file_limit_bytes}',f'--cpu={cutoff+2}',
            '--','taskset','-c',str(cpu),*map(str,cmd)]
    begin=time.monotonic();killed=False
    with log.open('w') as f:
        process=subprocess.Popen(actual,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        while True:
            pid,status,usage=os.wait4(process.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-begin>cutoff+10 and not killed:
                os.killpg(process.pid,signal.SIGKILL);killed=True
            time.sleep(.01)
    process.returncode=os.waitstatus_to_exitcode(status)
    text=log.read_text(errors='replace')
    result={'command':actual,'exit_code':process.returncode,'cpu_s':usage.ru_utime+usage.ru_stime,
            'wall_s':time.monotonic()-begin,'maxrss_kb':usage.ru_maxrss,'watchdog_killed':killed,
            'affinity_cpu':cpu,'log':str(log)}
    for key in ['conflicts','decisions','propagations','restarts','rephased']:
        match=re.search(r'^c '+key+r':\s+(\d+)',text,re.M)
        if match:result[key]=int(match.group(1))
    return result,text


def clause_stream(path):
    clause=[]
    with path.open() as f:
        for line in f:
            line=line.lstrip()
            if not line or line.startswith(('c','p')):continue
            for tok in line.split():
                v=int(tok)
                if v:clause.append(v)
                else:yield clause;clause=[]
    if clause:raise ValueError('unterminated clause')


def check_model(path,text,nv):
    values=bytearray(nv+1)
    for line in text.splitlines():
        if line.startswith('v '):
            for token in line[2:].split():
                lit=int(token)
                if abs(lit)>nv:return False
                if lit:
                    value=2 if lit>0 else 1
                    if values[abs(lit)] not in (0,value):return False
                    values[abs(lit)]=value
    return all(any(values[abs(l)]==(2 if l>0 else 1) for l in c) for c in clause_stream(path))


def direct_certificate(path):
    units={}
    for index,c in enumerate(clause_stream(path),1):
        if not c:return {'kind':'empty_clause','clauses':[index]}
        if len(c)==1:
            if -c[0] in units:return {'kind':'unit_pair','clauses':[units[-c[0]],index]}
            units[c[0]]=index
    return None


def prepare(root,rows,allowed_roles=frozenset({'development_fit'})):
    data=root/'data';data.mkdir(exist_ok=True)
    output=[]
    for index,row in enumerate(rows,1):
        h=row['hash']
        if not re.fullmatch('[0-9a-f]{32}',h):raise ValueError('invalid benchmark identifier')
        if row['role'] not in allowed_roles:raise ValueError('input role is not authorized for this execution stage')
        path=data/(h+'.cnf');xz=data/(h+'.cnf.xz')
        if not xz.exists():
            tmp=xz.with_suffix('.part')
            subprocess.run(['curl','-fsSL','--connect-timeout','15','--max-time','180',
                            f'https://benchmark-database.de/file/{h}','-o',str(tmp)],check=True)
            tmp.rename(xz)
        if row.get('expected_sha256_xz') and sha(xz)!=row['expected_sha256_xz']:
            raise ValueError('compressed source checksum mismatch')
        if not path.exists():
            tmp=path.with_suffix('.part');total=0
            with lzma.open(xz,'rb') as src,tmp.open('wb') as dst:
                for b in iter(lambda:src.read(1<<20),b''):
                    total+=len(b)
                    if total>100000000:raise ValueError('pilot CNF size cap exceeded')
                    dst.write(b)
            tmp.rename(path)
        if row.get('expected_sha256_cnf') and sha(path)!=row['expected_sha256_cnf']:
            raise ValueError('original source checksum mismatch')
        stat_path=root/'results'/f'{h}.features.json'
        if stat_path.exists():record=json.loads(stat_path.read_text())
        else:
            cost,text=child([root/'bin/cnf_structure',path],root/'logs'/f'{h}.features.log',30,0)
            if cost['exit_code']!=0:raise ValueError('feature extraction failed: '+h)
            features=json.loads(text)
            record={'hash':h,'source_sha256':sha(path),'compressed_sha256':sha(xz),
                    'features':features,'feature_cpu_s':cost['cpu_s'],'feature_wall_s':cost['wall_s'],
                    'metadata_count_mismatch':features['s_header_variables']!=int(row['variables']) or features['s_clauses']!=int(row['clauses']),
                    'extractor_sha256':sha(root/'bin/cnf_structure'),'source_check':'prior_sha256_match' if row.get('expected_sha256_cnf') else 'TLS_public_URI_and_xz_CRC_then_recorded_sha256'}
            write(stat_path,record)
        if record['source_sha256']!=sha(path):raise ValueError('cached input changed')
        if record['extractor_sha256']!=sha(root/'bin/cnf_structure'):raise ValueError('cached extractor identity changed')
        output.append({**row,'path':str(path),'sha256':record['source_sha256'],
                       'header_variables':int(record['features']['s_header_variables']),
                       'features_file':str(stat_path)})
        print(f'prepared {index}/{len(rows)}',flush=True)
    write(root/'results/prepared.json',output)
    return output


def run(root,rows,T,workers,max_cpu_hours):
    binary=root/'bin/cadical';checker=root/'bin/lrat-check'
    if subprocess.check_output([str(binary),'--version'],text=True).strip()!='3.0.1':
        raise ValueError('unexpected solver version')
    identity={'binary_sha256':sha(binary),'checker_sha256':sha(checker),'runner_sha256':sha(Path(__file__)),
              'host':platform.node(),'source_commit':'c60730422e758ef1cebe7aeddf2dda31c996bf04'}
    write(root/'results/run_identity.json',identity)
    records=root/'results/runs';records.mkdir(exist_ok=True)
    jobs=[];aliases=[]
    for row in rows:
        for action in FLAGS:
            key={**identity,'input_sha256':row['sha256'],'action':action,'seed':0,'T':T,'memory_bytes':3*1024**3}
            rid=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()[:32]
            aliases.append({'hash':row['hash'],'action':action,'run_id':rid})
            if not (records/(rid+'.json')).exists():jobs.append((row,action,rid))
    write(root/'results/run_aliases.json',aliases)
    random.Random(20261103).shuffle(jobs)
    cpus=queue.Queue()
    for cpu in sorted(os.sched_getaffinity(0))[:workers]:cpus.put(cpu)
    previous=[json.loads(p.read_text()) for p in records.glob('*.json')]
    used=sum(r.get('cpu_s',0)+r.get('verification_cpu_s',0) for r in previous)
    used+=sum(json.loads(p.read_text()).get('feature_cpu_s',0) for p in (root/'results').glob('*.features.json'))
    lock=threading.Lock();done=0;stop=threading.Event();start=time.monotonic()
    if used/3600>=max_cpu_hours:stop.set()
    def one(job):
        nonlocal used,done
        if stop.is_set():return
        if shutil.disk_usage(root).free<12*1024**3:
            stop.set();raise RuntimeError('disk reserve reached; no new measurements launched')
        row,action,rid=job;cpu=cpus.get()
        try:
            path=Path(row['path']);cmd=[binary,*FLAGS[action],'--stats','--seed=0','-t',str(T),path]
            r,text=child(cmd,root/'logs'/(rid+'.log'),T,cpu)
            r.update({'run_id':rid,'hash':row['hash'],'action':action,'cutoff_s':T,
                      'input_sha256':row['sha256'],'identity':identity,'verification_cpu_s':0.,
                      'status':{10:'SAT',20:'UNSAT',0:'UNKNOWN'}.get(r['exit_code'],'ERROR'),
                      'verify':'NOT_ANSWERED'})
            if r['exit_code']<0 and r['watchdog_killed']:r['status']='TIMEOUT'
            if r['status']=='SAT':
                c0=time.thread_time()
                r['verify']='VERIFIED_MODEL' if check_model(path,text,int(row['header_variables'])) else 'INVALID_MODEL'
                r['verification_cpu_s']+=time.thread_time()-c0
            elif r['status']=='UNSAT':
                c0=time.thread_time()
                direct=direct_certificate(path)
                r['verification_cpu_s']+=time.thread_time()-c0
                if direct:r['verify']='VERIFIED_DIRECT';r['certificate']=direct
                else:
                    proof=root/'logs'/(rid+'.lrat')
                    cert,_=child([binary,*FLAGS[action],'--stats','--seed=0','--lrat','--binary=false',
                                  '-t',str(T),path,proof],root/'logs'/(rid+'.cert.log'),T,cpu)
                    r['certification']=cert;r['verification_cpu_s']+=cert['cpu_s']
                    r['verify']='UNVERIFIED_CERTIFICATION'
                    same=all(k in cert and k in r and cert[k]==r[k] for k in ['conflicts','decisions'])
                    if cert['exit_code']==20 and same:
                        check,output=child([checker,path,proof],root/'logs'/(rid+'.check.log'),60,cpu)
                        r['checker']=check;r['verification_cpu_s']+=check['cpu_s']
                        r['verify']='VERIFIED_LRAT' if check['exit_code']==0 and re.search(r'^[cs] VERIFIED',output,re.M) else 'UNVERIFIED_CHECKER' if check['exit_code']<0 or check['watchdog_killed'] else 'INVALID_PROOF'
                        if r['verify']=='VERIFIED_LRAT':proof.unlink(missing_ok=True)
            r['contended']=r['cpu_s']>1 and r['wall_s']/r['cpu_s']>1.10
            r['resolved']=r['verify'].startswith('VERIFIED_') and r['cpu_s']<=T and not r['contended']
            r['par2']=r['cpu_s'] if r['resolved'] else 2*T
            with lock:
                if (records/(rid+'.json')).exists():raise ValueError('immutable result collision')
                write(records/(rid+'.json'),r)
                used+=r['cpu_s']+r['verification_cpu_s'];done+=1
                if used/3600>=max_cpu_hours or time.monotonic()-start>6*3600:stop.set()
                if r['verify'] in ['INVALID_MODEL','INVALID_PROOF'] or r['status']=='ERROR':stop.set()
                write(root/'results/progress.json',{'completed_this_launch':done,'scheduled_this_launch':len(jobs),
                    'cpu_hours_this_launch':used/3600,'wall_s':time.monotonic()-start,'stopped':stop.is_set()})
                print(f'{done}/{len(jobs)} {action} {r["status"]} {r["verify"]} cpu_h={used/3600:.4f}',flush=True)
        finally:cpus.put(cpu)
    with ThreadPoolExecutor(workers) as ex:
        futures=[ex.submit(one,j) for j in jobs]
        for future in as_completed(futures):future.result()
    complete=[json.loads(p.read_text()) for p in sorted(records.glob('*.json'))]
    (root/'results/runs.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in complete))


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','run','all'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--pilot',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=60);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--max-cpu-hours',type=float,default=8)
    a=p.parse_args();root=a.root.resolve()
    for name in ['data','results','logs']: (root/name).mkdir(exist_ok=True,parents=True)
    with a.pilot.open() as f:rows=list(csv.DictReader(f))
    if a.stage in ['prepare','all']:prepared=prepare(root,rows)
    else:prepared=json.loads((root/'results/prepared.json').read_text())
    if a.stage in ['run','all']:run(root,prepared,a.timeout,a.workers,a.max_cpu_hours)


if __name__=='__main__':main()
