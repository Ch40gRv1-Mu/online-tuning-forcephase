"""Carry R33 across the already-running native checkpoint without timing overlap."""
import os
from pathlib import Path
import subprocess
import sys
import time

from .measure_large_linear42 import atomic
from .structural_clusters import DATA


def main():
    start,cpu=time.monotonic(),time.process_time()
    out=DATA/'mechanism_R33_orchestration_20261111';out.mkdir(exist_ok=False)
    try:
        atomic(out/'owner.json',{'PID':os.getpid(),'status':'waiting_existing_native1024',
            'native_PID':60389,'native_session':95109,'duplicate_submission':False})
        while True:
            ps=subprocess.run(['ps','-p','60389','-o','command='],capture_output=True,text=True)
            if ps.returncode in (0,1):
                live='src.anniversary2022_baseline.measure_compact_prefetch' in ps.stdout
                if not live:
                    prefix=DATA/'linear42_compact_cost_v3_20261111/prefix_1024.json'
                    import json
                    assert prefix.exists(),'Original native job terminal without completed1024; preserve evidence, no restart'
                    receipt=json.loads(prefix.read_text())
                    assert receipt['status']=='complete_prefix' and receipt['through']==1024
                    break
            # A transient observation failure is not proof of job death.
            if time.monotonic()-start>2400:
                raise TimeoutError('R33 queue wait exceeded40min; healthy native worker left untouched')
            time.sleep(10)
        for module in ('build_preprocess_structure','preprocess_structure_features','score_preprocess_structure'):
            atomic(out/'owner.json',{'PID':os.getpid(),'status':'running','module':module,'native1024_observed_terminal':True})
            print('R33_STAGE',module,flush=True)
            subprocess.run([sys.executable,'-m','src.anniversary2022_baseline.'+module],check=True)
        atomic(out/'completion.json',{'status':'complete','owner_PID':os.getpid(),
            'own_CPU_s':time.process_time()-cpu,'wall_including_queue_s':time.monotonic()-start,
            'child_CPU_charged_here':False,'cost_note':'Build/extractor/scorer resources recorded by each child; do not double-charge their enclosing process tree'})
    except BaseException as exc:
        atomic(out/'failure.json',{'error':repr(exc),'own_CPU_s':time.process_time()-cpu,
            'wall_including_queue_s':time.monotonic()-start,'native_job_not_cancelled_or_restarted':True})
        raise


if __name__=='__main__':main()
