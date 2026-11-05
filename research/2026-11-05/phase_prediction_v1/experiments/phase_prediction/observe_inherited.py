"""Read-only observer for a handed-over process. No launch, restart or signal operation."""
import argparse,json,subprocess,sys
from pathlib import Path

REMOTE_CODE=r'''
from pathlib import Path
import json,os,time
base=Path('/home/vipuser/forcephase_phase_prediction_20261104')
phase=base/'phases/long600_fit16'
result={'observed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'stage':'long600_fit16','inherited_pid':6096}
process=Path('/proc/6096')
try:
 result['pid_cmdline']=process.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0')
 result['pid_stat']=process.joinpath('stat').read_text()
 result['pid_present']=True
except FileNotFoundError:result['pid_present']=False
for name in ('progress','completion'):
 p=phase/'results'/(name+'.json')
 result[name]=json.loads(p.read_text()) if p.exists() else None
log=base/'logs/long-screen-transition.log'
result['log_tail']=log.read_text(errors='replace').splitlines()[-8:] if log.exists() else None
resources=base/'logs/long600_fit16.resources.txt'
result['parent_resources']=resources.read_text() if resources.exists() else None
result['run_records']=len(list((phase/'results/runs').glob('*.json')))
result['disk_free_bytes']=os.statvfs(base).f_bavail*os.statvfs(base).f_frsize
result['inference']='Observation only. Missing PID or progress alone never authorizes resubmission.'
print(json.dumps(result,indent=2))
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='223.109.239.36')
    p.add_argument('--socket');p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();project=Path(__file__).resolve().parents[2]
    cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile='+str(project/'data/phase_prediction_v1/known_hosts'),'-p','13752']
    if a.socket:cmd+=['-S',a.socket]
    cmd+=['vipuser@'+a.host,'python3 -']
    try:
        r=subprocess.run(cmd,input=REMOTE_CODE,text=True,capture_output=True,timeout=30)
        code=r.returncode
    except subprocess.TimeoutExpired:
        code=None
        result={'status':'OBSERVATION_UNAVAILABLE','ssh_exit_code':None,
                'stderr':'Read-only SSH observation timed out','job_state':'UNKNOWN','resubmit':False}
    if code:
        # Preserve observation failure without translating it into solver failure.
        result={'status':'OBSERVATION_UNAVAILABLE','ssh_exit_code':r.returncode,
                'stderr':r.stderr[-1000:],'job_state':'UNKNOWN','resubmit':False}
    elif code==0:result={'status':'OBSERVED','remote':json.loads(r.stdout),'resubmit':False}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result));sys.exit(0 if code==0 else 2)

if __name__=='__main__':main()
