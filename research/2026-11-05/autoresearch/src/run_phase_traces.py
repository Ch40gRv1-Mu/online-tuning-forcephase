"""H05: reuse H04 formal execution and verification with new phase jobs only."""
from pathlib import Path
import json,os,time
import run_short_traces as execution

execution.CAMPAIGN=execution.ROOT/'autoresearch/H05_relative_phase_response'
execution.CONFIGS={'Fplus':['--phase=1','--forcephase=1'],'Fminus':['--phase=0','--forcephase=1']}
base_work=execution.work

def phase_work(job):
    p,config,budget=job
    start=time.process_time();size=Path(p['path']).stat().st_size;stat_cpu=time.process_time()-start
    assert size==p['input_bytes']
    r=base_work(job)
    if 'file_bytes' not in r:
        r.update(file_bytes=size,stat_cpu_s=stat_cpu,charged_gate_cpu_s=max(.001,stat_cpu))
        r['feature_cpu_s']+=stat_cpu
        out=execution.CAMPAIGN/'records'/f"{p['id']}.{config}.b{int(budget*1000)}.json"
        tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(r)+'\n');tmp.rename(out)
    return r

execution.work=phase_work

if __name__=='__main__':
    execution.CAMPAIGN.mkdir(parents=True,exist_ok=True)
    with (execution.CAMPAIGN/'WRAPPER_IDENTITY.json').open('x') as f:
        json.dump(dict(source_sha256=execution.sha(__file__),base_source_sha256=execution.sha(execution.__file__),pid=os.getpid()),f,indent=2)
    execution.main()
