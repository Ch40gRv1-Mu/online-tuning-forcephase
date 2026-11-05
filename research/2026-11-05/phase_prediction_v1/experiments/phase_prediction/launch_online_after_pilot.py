"""One guarded transition; no duplicate pilot, no silent retries on failure."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);a=p.parse_args()
    base=a.base.resolve();code=Path(__file__).parent;start=time.monotonic()
    marker=base/'results/online_transition.json'
    if marker.exists():raise ValueError('online transition has already been attempted')
    print('Waiting for immutable complete P1 matrix; no overlapping solver phase',flush=True)
    while not (base/'results/runs.jsonl').exists():
        if time.monotonic()-start>7200:raise TimeoutError('P1 did not complete within transition wait')
        time.sleep(15)
    # One announced verification-only extension for original proof timeouts.
    # The helper refuses existing attempts, different failure types or >4 cases.
    subprocess.run([sys.executable,str(code/'certify_pilot_pending.py'),'--root',str(base)],check=True)
    # This strict import rejects missing parents, errors, verification failures
    # and contention before any online measurements can be launched.
    subprocess.run([sys.executable,str(code/'analyze_pilot.py'),'--root',str(base),
                    '--out',str(base/'results/p1_analysis_verified')],check=True)
    receipt={'status':'P1_valid_online_launch','wait_wall_s':time.monotonic()-start,
             'stage':'online16','note':'Frozen development-only cohort; no final test data.'}
    marker.write_text(json.dumps(receipt,indent=2)+'\n')
    os.execvp('/usr/bin/time',['/usr/bin/time','-v','-o',str(base/'logs/online16.resources.txt'),
        sys.executable,str(code/'run_matrix.py'),'--base',str(base),'--stage','online16',
        '--spec',str(base/'metadata/online16_spec.json'),'--cohort',str(base/'metadata/online16.csv')])


if __name__=='__main__':main()
