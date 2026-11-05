"""Actual development-only static JSON-policy deployment with a total CPU budget.

This is a new execution path. It never resumes or mutates long600_fit16 and
cannot evaluate a gate/test row. Formal use requires a frozen deployment spec.
"""
import argparse,json,math,re,shutil,time,signal
from pathlib import Path
from analyze_matrix import deployed_cost
import policy
import run_pilot as common

FLAGS={**common.FLAGS,'Iminus':['--phase=0','--forcephase=0']}

def execution_identity(spec):
    result={k:spec[k] for k in ('solver_sha256','checker_sha256','extractor_sha256','policy_sha256')}
    result.update(deployment_runner_sha256=common.sha(Path(__file__)),
        common_runner_sha256=common.sha(Path(common.__file__)),
        policy_evaluator_sha256=common.sha(Path(policy.__file__)),
        scoring_code_sha256=common.sha(Path(__file__).with_name('analyze_matrix.py')),
        cutoff_s=spec['total_cpu_budget_s'],seed=spec['seed'],memory_bytes=3*1024**3,
        proof_file_limit_bytes=spec.get('proof_file_limit_bytes',4*1024**3),
        verification='timed_binary_LRAT_lrat_trim',checker_options=['--no-trim'])
    if spec.get('cpu_budget_executor'):
        result.update(cpu_budget_executor_sha256=spec['cpu_budget_executor_sha256'],
            cpu_budget_gate_sha256=spec['cpu_budget_qualification_sha256'],
            budget_mode='fractional_process_CPU_and_native_wall_T')
    return result

def validated_features(raw):
    if not isinstance(raw,dict) or not set(raw)<=policy.STATIC|{'feature_wall_s'}:
        raise ValueError('extractor returned forbidden metadata')
    result={k:v for k,v in raw.items() if k in policy.STATIC}
    for v in result.values():
        if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)):
            raise ValueError('invalid numeric formula feature')
    return result

def run_one(spec,parent,tree,root):
    parent_cpu0=time.thread_time()
    if parent['role'] not in ('development_fit','development_feedback'):
        raise ValueError('gate/test requires its separately frozen controller')
    policy_sha=policy.validate(tree)
    if spec['policy_sha256']!=policy_sha:raise ValueError('policy changed after freeze')
    T=spec['total_cpu_budget_s']
    if not isinstance(T,(int,float)) or isinstance(T,bool) or not math.isfinite(T) or T<=0:
        raise ValueError('invalid total budget')
    proof_cap=spec.get('proof_file_limit_bytes',4*1024**3)
    if proof_cap not in (4*1024**3,8*1024**3):raise ValueError('unfrozen proof file cap')
    wrapper=Path(spec['cpu_budget_executor']) if spec.get('cpu_budget_executor') else None
    if wrapper:
        gate_path=Path(spec['cpu_budget_qualification_path']);gate=json.loads(gate_path.read_text())
        if common.sha(wrapper)!=spec['cpu_budget_executor_sha256'] or common.sha(gate_path)!=spec['cpu_budget_qualification_sha256']:
            raise ValueError('CPU budget helper identity changed')
        if gate['status']!='PASS' or gate['wrapper_sha256']!=spec['cpu_budget_executor_sha256'] or \
                gate['solver_sha256']!=spec['solver_sha256'] or gate['checker_sha256']!=spec['checker_sha256']:
            raise ValueError('CPU timer/native solver qualification not passed')
    root=Path(root)
    if root.exists():raise ValueError('immutable deployment output exists')
    if shutil.disk_usage(root.parent).free<12*1024**3+proof_cap:
        raise RuntimeError('insufficient disk for reserve plus the full proof cap')
    root.mkdir(parents=True)
    logs=root/'logs';logs.mkdir();path=Path(parent['path'])
    binary=Path(spec['solver']);checker=Path(spec['checker']);extractor=Path(spec['extractor'])
    identity=execution_identity(spec)
    for tool,key in ((binary,'solver_sha256'),(checker,'checker_sha256'),(extractor,'extractor_sha256')):
        if common.sha(tool)!=spec[key]:raise ValueError('tool identity mismatch')
    if common.sha(path)!=parent['sha256']:raise ValueError('input identity mismatch')
    # Input/tool identity is research preparation for every configuration. The
    # deployed h starts at feature extraction and the actual policy decision.
    cpu0=time.thread_time();begin=time.monotonic()
    feature_cpu=0.;features={}
    if 'feature' in tree:
        extracted,text=common.child([extractor,path],logs/'features.log',30,spec['cpu'])
        feature_cpu=extracted['cpu_s']
        if extracted['exit_code']!=0:
            h=feature_cpu+time.thread_time()-cpu0
            record={'status':'FEATURE_ERROR','resolved':False,'par2':2*T,'feature_child':extracted,
                    'feature_and_decision_cpu_s':h,'identity':identity,
                    'physical_cpu_s':feature_cpu+time.thread_time()-parent_cpu0,
                    'input_sha256':parent['sha256'],'role':parent['role'],'cutoff_s':T,
                    'performance_valid':False,'training_eligible':False}
            common.write(root/'record.json',record);return record
        features=validated_features(json.loads(text))
    action=policy.decide(tree,features)
    h=feature_cpu+time.thread_time()-cpu0
    if h>=T:
        record={'status':'OBSERVATION_BUDGET_EXHAUSTED','resolved':False,'par2':2*T,
                'verify':'NOT_ANSWERED','action':action,'features':features,'policy':tree,
                'solver':None,'checker':None,'solver_invocation':[],'contended':False,
                'feature_and_decision_cpu_s':h,'identity':identity,
                'physical_cpu_s':feature_cpu+time.thread_time()-parent_cpu0,
                'input_sha256':parent['sha256'],'role':parent['role'],'cutoff_s':T,
                'evidence_sha256':{str(p.relative_to(root)):common.sha(p) for p in logs.glob('*.log')},
                'performance_valid':True,'training_eligible':True}
        common.write(root/'record.json',record);return record
    remaining=T-h;proof=logs/'solver.lrat'
    native_limit=math.ceil(T) if wrapper else max(1,math.ceil(remaining))
    cmd=[binary,*FLAGS[action],f"--seed={spec['seed']}",'--stats','--lrat','--binary=true',
         '-t',str(native_limit),path,proof]
    executed=[wrapper,f'{remaining:.9f}',*cmd] if wrapper else cmd
    run,text=common.child(executed,logs/'solver.log',native_limit,spec['cpu'],
                          file_limit_bytes=proof_cap)
    status={0:'UNKNOWN',10:'SAT',20:'UNSAT'}.get(run['exit_code'],'ERROR')
    cpu_expired=bool(wrapper and run['exit_code']==-signal.SIGPROF)
    if cpu_expired:status='TIMEOUT'
    if run['watchdog_killed']:status='TIMEOUT'
    verify='NOT_ANSWERED';verification_cpu=0.;check=None
    if status=='SAT':
        t=time.thread_time();ok=common.check_model(path,text,parent['header_variables'])
        verification_cpu=time.thread_time()-t;verify='VERIFIED_MODEL' if ok else 'INVALID_MODEL'
    elif status=='UNSAT':
        check,txt=common.child([checker,'--no-trim',path,proof],logs/'checker.log',120,spec['cpu'])
        verification_cpu=check['cpu_s']
        verify='VERIFIED_LRAT' if check['exit_code']==20 and re.search(r'^s VERIFIED',txt,re.M) else 'UNVERIFIED_CHECKER'
    valid=verify.startswith('VERIFIED_')
    contention=run['cpu_s']>1 and run['wall_s']/run['cpu_s']>1.10
    outcome={'resolved':valid and not contention,'cpu_s':run['cpu_s'],'cutoff_s':T}
    score=deployed_cost(outcome,h)
    proof_bytes=proof.stat().st_size if proof.exists() else 0
    proof_sha=common.sha(proof) if proof.exists() and valid else None
    remove_proof=proof.exists() and (valid or status in ('UNKNOWN','TIMEOUT'))
    if remove_proof:proof.unlink()
    record={'status':status,'verify':verify,'resolved':valid and not contention and h+run['cpu_s']<=T,
            'par2':score,'action':action,'features':features,'policy':tree,'identity':identity,
            'input_sha256':parent['sha256'],'role':parent['role'],'solver':run,'checker':check,
            'solver_invocation':list(map(str,cmd)),
            'budget_executor_invocation':list(map(str,executed)) if wrapper else None,
            'cpu_budget_expired':cpu_expired,
            'remaining_solver_cpu_budget_s':remaining,
            'solver_integer_limit_s':native_limit,
            'budget_rounding_scope':'Native wallT retained; fractional remaining CPU timer; actual h+t strict.' if wrapper else
                'Legacy prototype: integer wall limit rounds up; actual h+t>T receives2T. Not the formal deployment mode.',
            'proof_bytes':proof_bytes,'proof_sha256':proof_sha,'proof_removed_after_validation_or_unknown':remove_proof,
            'cutoff_s':T,'feature_and_decision_cpu_s':h,'verification_cpu_s':verification_cpu,
            'contended':contention,'wall_s':time.monotonic()-begin,
            'performance_valid':not contention and status!='ERROR' and (status not in ('SAT','UNSAT') or valid),
            'training_eligible':not contention and status!='ERROR' and (status not in ('SAT','UNSAT') or valid),
            'offline_replay_cost_from_actual_observation':deployed_cost(outcome,h),
            'physical_cpu_s':feature_cpu+run['cpu_s']+(check['cpu_s'] if check else 0.)+time.thread_time()-parent_cpu0,
            'physical_cpu_scope':'Unit timed parent-thread and child CPU; use phase GNU-time for complete physical billing',
            'evidence_sha256':{str(p.relative_to(root)):common.sha(p) for p in logs.glob('*.log')}}
    common.write(root/'record.json',record);return record

def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--parent',type=Path,required=True);p.add_argument('--policy',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run_one(json.loads(a.spec.read_text()),json.loads(a.parent.read_text()),
                             json.loads(a.policy.read_text()),a.out)))

if __name__=='__main__':main()
