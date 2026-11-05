"""Extract existing-CNF structure only; never calls a SAT solver."""
import argparse,csv,hashlib,json,lzma,os,queue,resource,shutil,subprocess,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import run_pilot as common

COHORT_SHA='f259dc2a26cca843360015833ae78291898bf7b1e7450389bd07bf7ea611ecf4'

def cpu():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time()+r.ru_utime+r.ru_stime

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--cohort',type=Path,required=True)
    a=p.parse_args();base=a.base;root=base/'phases/depth192_v1';root.mkdir(parents=True,exist_ok=True)
    for d in ('results','logs','metadata'):(root/d).mkdir(exist_ok=True)
    if common.sha(a.cohort)!=COHORT_SHA:raise ValueError('changed fixed cohort')
    with a.cohort.open() as f:rows=list(csv.DictReader(f))
    if len(rows)!=192 or len({r['hash'] for r in rows})!=192 or any(r['role'] not in ('development_fit','development_feedback') for r in rows):
        raise ValueError('invalid development-only extraction cohort')
    (root/'metadata/cohort.csv').write_bytes(a.cohort.read_bytes())
    started=cpu();binary=base/'bin/cnf_depth_v1';source=Path(__file__).with_name('cnf_depth.cpp')
    if binary.exists():raise ValueError('refuse rebuilding a deployed extractor')
    subprocess.run(['g++','-O3','-std=c++17',str(source),'-o',str(binary)],check=True)
    identity={'binary_sha256':common.sha(binary),'source_sha256':common.sha(source),
              'base_structure_source_sha256':common.sha(source.with_name('cnf_structure.cpp')),
              'runner_sha256':common.sha(Path(__file__)),'cohort_sha256':COHORT_SHA}
    common.write(root/'results/identity.json',identity)
    # These exercise the definitions while producing the real extractor version.
    examples=[('gatechain','p cnf 5 6\n-1 -2 3 0\n1 -3 0\n2 -3 0\n-3 -4 5 0\n3 -5 0\n4 -5 0\n',2),
              ('gatecycle','p cnf 4 6\n-2 -3 1 0\n2 -1 0\n3 -1 0\n-1 -4 2 0\n1 -2 0\n4 -2 0\n',1)]
    for name,text,depth in examples:
        path=root/'metadata'/(name+'.cnf');path.write_text(text)
        result=json.loads(subprocess.check_output([str(binary),str(path)],text=True))
        if result['d_gate_condensation_depth']!=depth:raise ValueError('gate-depth definition error')
        if name=='gatecycle' and result['d_gate_cyclic_variable_fraction']<=0:raise ValueError('cycle not preserved')
    known={}
    for path in [base/'results/prepared.json',*base.glob('phases/*/results/prepared.json')]:
        if path.exists():
            for r in json.loads(path.read_text()):
                if r['hash'] in known and known[r['hash']]!=r['sha256']:raise ValueError('changed input identity')
                known[r['hash']]=r['sha256']
    if sum(int(r['bytes']) for r in rows)>shutil.disk_usage(base).free-12*1024**3:
        raise RuntimeError('insufficient bounded public-input storage')
    lock=threading.Lock();done=0;records={};start_wall=time.monotonic();cpus=queue.Queue()
    for core in sorted(os.sched_getaffinity(0))[:8]:cpus.put(core)
    def one(row,memory,slot,retry=False):
        nonlocal done
        slot=cpus.get()
        h=row['hash'];path=base/'data'/(h+'.cnf');xz=base/'data'/(h+'.cnf.xz')
        attempt={'memory_bytes':memory,'retry':retry};item={'hash':h,'role':row['role'],'identity':identity,'attempts':[]}
        if retry:item=json.loads((root/'results'/(h+'.json')).read_text())
        try:
            if cpu()-started>6*3600:raise RuntimeError('feature-stage CPU envelope reached')
            if not xz.exists():
                part=xz.with_suffix('.depth_download')
                subprocess.run(['curl','-fsSL','--connect-timeout','15','--max-time','180','--max-filesize','100000000',
                                'https://benchmark-database.de/file/'+h,'-o',str(part)],check=True,capture_output=True)
                part.rename(xz)
            if not path.exists():
                part=path.with_suffix('.depth_plain');total=0
                with lzma.open(xz,'rb') as src,part.open('wb') as dst:
                    while True:
                        data=src.read(1<<20)
                        if not data:break
                        total+=len(data)
                        if total>100000000:raise ValueError('plain CNF cap')
                        dst.write(data)
                part.rename(path)
            if path.stat().st_size>100000000:raise ValueError('plain CNF cap')
            observed=common.sha(path)
            if h in known and observed!=known[h]:raise ValueError('cached public CNF identity changed')
            item['input_sha256']=observed;item['compressed_sha256']=common.sha(xz)
            suffix='retry' if retry else 'initial';log=root/'logs'/(h+'.'+suffix+'.log')
            measured,text=common.child([binary,path],log,30,slot,memory=memory)
            attempt.update(measured)
            if measured['exit_code']!=0:raise RuntimeError('feature extraction returned '+str(measured['exit_code']))
            features=json.loads(text)
            if any(v is not None and (isinstance(v,bool) or not isinstance(v,(int,float))) for v in features.values()):
                raise ValueError('non-numeric extractor output')
            item.update(status='VALID',features=features,feature_cpu_s=measured['cpu_s'],maxrss_kb=measured['maxrss_kb'])
        except Exception as e:
            item.update(status='FEATURE_ERROR',error=type(e).__name__+': '+str(e))
            if isinstance(e,subprocess.CalledProcessError):attempt['preparation_stderr']=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr
        item['attempts'].append(attempt)
        with lock:
            common.write(root/'results'/(h+'.json'),item);records[h]=item
            if not retry:done+=1
            progress={'completed':done,'scheduled':192,'valid':sum(x['status']=='VALID' for x in records.values()),
                      'actual_process_and_waited_children_cpu_s':cpu()-started,'wall_s':time.monotonic()-start_wall}
            common.write(root/'results/progress.json',progress)
            print(json.dumps(progress),flush=True)
        cpus.put(slot)
        return item
    # Only resource scheduling changes order: cached public inputs first.
    rows.sort(key=lambda r:not (base/'data'/(r['hash']+'.cnf')).exists())
    with ThreadPoolExecutor(8) as executor:
        futures=[executor.submit(one,r,1536*1024**2,i%8) for i,r in enumerate(rows)]
        for f in as_completed(futures):f.result()
    failed=[r for r in rows if records[r['hash']]['status']!='VALID']
    with ThreadPoolExecutor(4) as executor:
        futures=[executor.submit(one,r,3*1024**3,i%4,True) for i,r in enumerate(failed)]
        for f in as_completed(futures):f.result()
    summary={'status':'COMPLETE_WITH_COVERAGE','parents':192,'valid':sum(x['status']=='VALID' for x in records.values()),
             'failed':[h for h,r in records.items() if r['status']!='VALID'],'identity':identity,
             'actual_process_and_waited_children_cpu_s':cpu()-started,'wall_s':time.monotonic()-start_wall,
             'new_solver_runs':0,'note':'Feature failures retained; only parent GNU-time is complete physical billing.'}
    common.write(root/'results/completion.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
