"""One-owner, checkpointed execution of the predeclared eight development units.

Never imports gate/test rows, chooses a policy, or resumes an incomplete unit.
Requires frozen policy/spec and a complete source development matrix.
"""
import argparse,csv,fcntl,io,json,os,re,resource,time
from pathlib import Path
import deploy_static
import deployment_consistency
import policy
import run_pilot as common

def selected_parents(parents):
    if len(parents)!=40 or len({r['hash'] for r in parents})!=40:
        raise ValueError('complete frozen forty-parent source required')
    if any(r['role'] not in ('development_fit','development_feedback') for r in parents):
        raise ValueError('protected role cannot enter development deployment')
    if any(not re.fullmatch('[0-9a-f]{32}',r['hash']) for r in parents):
        raise ValueError('invalid parent association key')
    fit=[r for r in parents if r['role']=='development_fit']
    feedback=[r for r in parents if r['role']=='development_feedback']
    if len(fit)!=24 or len(feedback)!=16:raise ValueError('wrong frozen source split')
    return fit[:4]+feedback[:4]

def cohort_bytes(parents):
    buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=['hash','role','path','sha256','header_variables'])
    writer.writeheader();writer.writerows({k:r[k] for k in writer.fieldnames} for r in parents)
    return buf.getvalue().encode()

def child_cpu():
    r=resource.getrusage(resource.RUSAGE_CHILDREN);return r.ru_utime+r.ru_stime

def run_batch(spec_path,parents_path,policy_path,root):
    start_cpu=time.process_time();start_children=child_cpu()
    spec_path=Path(spec_path);parents_path=Path(parents_path);policy_path=Path(policy_path);root=Path(root)
    spec=json.loads(spec_path.read_text());parents=json.loads(parents_path.read_text());tree=json.loads(policy_path.read_text())
    chosen=selected_parents(parents)
    if common.sha(parents_path)!=spec['parent_manifest_sha256']:raise ValueError('changed parent manifest')
    if [r['hash'] for r in chosen]!=spec['selected_parent_hashes']:raise ValueError('changed fixed deployment subset')
    if policy.validate(tree)!=spec['policy_sha256']:raise ValueError('changed frozen policy')
    if spec['seed']!=0 or spec['total_cpu_budget_s']!=600 or spec['proof_file_limit_bytes']!=8*1024**3:
        raise ValueError('changed formal deployment settings')
    if not spec.get('cpu_budget_executor'):raise ValueError('qualified fractional CPU executor required for formal deployment')
    complete=Path(spec['source_completion_path'])
    source=json.loads(complete.read_text())
    if common.sha(complete)!=spec['source_completion_sha256'] or source['status']!='COMPLETE' or \
            source['parents']!=40 or source['runs']!=320:
        raise ValueError('source matrix incomplete or changed')
    integrity=Path(spec['source_integrity_path']);valid=json.loads(integrity.read_text())
    if common.sha(integrity)!=spec['source_integrity_sha256'] or not valid['complete_and_valid'] or \
            valid['parents']!=40 or valid['runs']!=320:
        raise ValueError('strict source matrix validation did not pass')
    nominal=len(chosen)*(spec['total_cpu_budget_s']+120)/3600
    if spec['max_new_physical_cpu_hours']<nominal:raise ValueError('deployment envelope cannot fit the fixed units')
    identity={'spec_sha256':common.sha(spec_path),'parents_sha256':common.sha(parents_path),
              'policy_file_sha256':common.sha(policy_path),'unit_identity':deploy_static.execution_identity(spec),
              'batch_runner_sha256':common.sha(Path(__file__)),
              'consistency_checker_sha256':common.sha(Path(deployment_consistency.__file__))}
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.owner.lock').open('a+') as owner:
        try:fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('deployment already has an active owner')
        prior=root/'results/identity.json'
        if prior.exists() and json.loads(prior.read_text())!=identity:raise ValueError('cannot resume changed identity')
        completed=root/'results/completion.json'
        if completed.exists():
            original=json.loads(completed.read_text())
            if original['status']!='COMPLETE' or original['identity']!=identity:
                raise ValueError('changed completed deployment')
            for index,parent in enumerate(chosen):
                unit=root/'results/units'/f"{index:02d}_{parent['hash']}"
                r=json.loads((unit/'record.json').read_text());binding=json.loads((unit/'batch_binding.json').read_text())
                expected={'parent_hash':parent['hash'],'record_sha256':common.sha(unit/'record.json'),
                          'spec_sha256':identity['spec_sha256'],'policy_sha256':spec['policy_sha256']}
                if r['identity']!=identity['unit_identity'] or binding!=expected:
                    raise ValueError('changed completed deployment unit')
                if r['input_sha256']!=parent['sha256'] or r['role']!=parent['role']:
                    raise ValueError('wrong completed deployment parent')
                deployment_consistency.check(unit)
            return {**original,'reused_existing_completed_stage':True,
                    'current_invocation_cpu_s':time.process_time()-start_cpu+child_cpu()-start_children}
        for name in ('metadata','results','results/units'):(root/name).mkdir(exist_ok=True)
        if not prior.exists():common.write(prior,identity)
        for name,value in [('spec',spec),('policy',tree)]:
            path=root/'metadata'/(name+'.json')
            if path.exists():
                if json.loads(path.read_text())!=value:raise ValueError('changed frozen deployment metadata')
            else:common.write(path,value)
        cohort=root/'metadata/cohort.csv';data=cohort_bytes(chosen)
        if cohort.exists():
            if cohort.read_bytes()!=data:raise ValueError('changed fixed deployment cohort')
        else:cohort.write_bytes(data)
        owner.seek(0);owner.truncate();owner.write(json.dumps({'pid':os.getpid(),'identity':identity}));owner.flush()
        receipts=[];new=0;reused=0
        def physical():return time.process_time()-start_cpu+child_cpu()-start_children
        try:
            for index,parent in enumerate(chosen):
                unit=root/'results/units'/f"{index:02d}_{parent['hash']}";path=unit/'record.json'
                reused_unit=path.exists()
                if not reused_unit:
                    if unit.exists():raise RuntimeError('incomplete unit preserved; authoritative process inspection and new recovery required')
                    if physical()+(spec['total_cpu_budget_s']+120)>spec['max_new_physical_cpu_hours']*3600:
                        raise RuntimeError('physical deployment envelope reached before next unit')
                    deploy_static.run_one(spec,parent,tree,unit);new+=1
                else:reused+=1
                r=json.loads(path.read_text())
                if r['identity']!=identity['unit_identity'] or r['input_sha256']!=parent['sha256'] or r['role']!=parent['role']:
                    raise ValueError('unit does not belong to frozen identity and parent')
                binding=unit/'batch_binding.json'
                expected={'parent_hash':parent['hash'],'record_sha256':common.sha(path),
                          'spec_sha256':identity['spec_sha256'],'policy_sha256':spec['policy_sha256']}
                if binding.exists() and json.loads(binding.read_text())!=expected:raise ValueError('changed completed unit')
                checked=deployment_consistency.check(unit)
                if not binding.exists():common.write(binding,expected)
                receipts.append({**expected,'role':parent['role'],'consistency':checked,
                                 'reused_this_launch':reused_unit})
                common.write(root/'results/progress.json',{'completed':len(receipts),'scheduled':8,
                    'new_this_launch':new,'reused_this_launch':reused,'physical_this_launch_cpu_s':physical(),'stopped':False})
            result={'status':'COMPLETE','parents':8,'runs':8,'identity':identity,'receipts':receipts,
                    'new_this_launch':new,'reused_this_launch':reused,'physical_this_launch_cpu_s':physical(),
                    'accounting':'Current process and waited children only. Sum all outer GNU-time attempts once for final physical cost.'}
            common.write(root/'results/completion.json',result);return result
        except BaseException as error:
            failure={'status':'STOPPED_ERROR','error':type(error).__name__+': '+str(error),
                     'completed':len(receipts),'new_this_launch':new,'reused_this_launch':reused,
                     'physical_this_launch_cpu_s':physical(),'identity':identity,
                     'note':'No retry of an incomplete/failed unit and no ordinary timeout label inferred.'}
            with (root/'results'/f'failure_{time.time_ns()}.json').open('x') as f:json.dump(failure,f,indent=2)
            raise

def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--parents',type=Path,required=True);p.add_argument('--policy',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run_batch(a.spec,a.parents,a.policy,a.out)))

if __name__=='__main__':main()
