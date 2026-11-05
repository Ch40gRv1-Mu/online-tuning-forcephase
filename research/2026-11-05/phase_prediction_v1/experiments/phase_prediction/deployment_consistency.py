"""Independent action/command/evidence and h+t replay check; never reruns a solver."""
import argparse,hashlib,json,math,re
from pathlib import Path,PurePosixPath
import policy

FLAGS={'D':('--phase=1','--forcephase=0'),'Fplus':('--phase=1','--forcephase=1'),
       'Fminus':('--phase=0','--forcephase=1')}

def check_evidence(root,r):
    for name,digest in r['evidence_sha256'].items():
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='logs':raise ValueError('invalid evidence path')
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('changed raw log')
    if 'feature' in r['policy'] and 'logs/features.log' not in r['evidence_sha256']:
        raise ValueError('missing feature observation evidence')

def check(root):
    root=Path(root);r=json.loads((root/'record.json').read_text())
    if r.get('role') not in ('development_fit','development_feedback'):
        raise ValueError('protected deployment cannot enter development comparison')
    if not r.get('performance_valid') or not r.get('training_eligible'):
        raise ValueError('engineering/verification failure cannot become a performance label')
    if set(r['features'])-policy.STATIC:raise ValueError('forbidden feature input')
    if policy.validate(r['policy'])!=r['identity']['policy_sha256']:raise ValueError('policy identity changed')
    if policy.decide(r['policy'],r['features'])!=r['action']:raise ValueError('executed action disagrees with frozen policy')
    if r.get('solver') is None:
        check_evidence(root,r)
        h=r['feature_and_decision_cpu_s'];T=r['cutoff_s']
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (h,T)) or T<=0:
            raise ValueError('invalid time values')
        if r['status']!='OBSERVATION_BUDGET_EXHAUSTED' or h<T or r['resolved'] or r['par2']!=2*T or \
                r['verify']!='NOT_ANSWERED' or r['solver_invocation']:
            raise ValueError('invalid exhausted-observation scoring')
        return {'status':'ACTION_AND_COST_CONSISTENT','action':r['action'],'par2':2*T,
                'resolved':False,'scope':'Actual observation exhausted total budget; no solver launched.'}
    cmd=r['solver_invocation']
    for prefix,flag in zip(('--phase=','--forcephase='),FLAGS[r['action']]):
        if [x for x in cmd if x.startswith(prefix)]!=[flag]:raise ValueError('wrong executed option pair')
    if [x for x in cmd if x.startswith('--seed=')]!=[f"--seed={r['identity']['seed']}"]:
        raise ValueError('wrong seed')
    if '--lrat' not in cmd or '--binary=true' not in cmd:raise ValueError('wrong proof timing mode')
    if r['solver']['command'][-len(cmd):]!=cmd:raise ValueError('child command disagrees with reported invocation')
    if r['identity'].get('budget_mode')=='fractional_process_CPU_and_native_wall_T':
        executed=r['budget_executor_invocation']
        if len(executed)!=len(cmd)+2 or executed[2:]!=cmd or r['solver']['command'][-len(executed):]!=executed:
            raise ValueError('missing actual fractional CPU executor')
        if abs(float(executed[1])-(r['cutoff_s']-r['feature_and_decision_cpu_s']))>1e-7:
            raise ValueError('wrong remaining CPU budget')
        pos=cmd.index('-t')
        if int(cmd[pos+1])!=math.ceil(r['cutoff_s']):raise ValueError('native solver wall cap changed')
    if r['identity']['verification']!='timed_binary_LRAT_lrat_trim':raise ValueError('wrong verification semantics')
    check_evidence(root,r)
    if 'logs/solver.log' not in r['evidence_sha256']:raise ValueError('missing solver log binding')
    h=r['feature_and_decision_cpu_s'];t=r['solver']['cpu_s'];T=r['cutoff_s']
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in (h,t,T)) or T==0:
        raise ValueError('invalid time values')
    if r['verify']=='VERIFIED_LRAT':
        if r['solver']['exit_code']!=20 or r['checker']['exit_code']!=20:
            raise ValueError('binary checker/solver exit semantics mismatch')
        if 'logs/checker.log' not in r['evidence_sha256'] or not re.search(r'^s VERIFIED', (root/'logs/checker.log').read_text(),re.M):
            raise ValueError('missing independent binary proof verification')
    elif r['verify']=='VERIFIED_MODEL':
        if r['solver']['exit_code']!=10:raise ValueError('wrong SAT return code')
    elif r['verify']!='NOT_ANSWERED':raise ValueError('unknown verification status')
    resolved=r['verify'].startswith('VERIFIED_') and not r['contended'] and h+t<=T
    expected=h+t if resolved else 2*T
    if resolved!=r['resolved'] or abs(expected-r['par2'])>1e-8:raise ValueError('deployment and replay scoring disagree')
    return {'status':'ACTION_AND_COST_CONSISTENT','action':r['action'],'par2':expected,
            'resolved':resolved,'scope':'One actual record; does not establish generalization or a policy reward'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    print(json.dumps(check(a.root)))

if __name__=='__main__':main()
