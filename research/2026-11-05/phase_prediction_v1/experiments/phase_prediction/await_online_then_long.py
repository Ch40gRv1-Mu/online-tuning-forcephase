"""Guard one transition from the exact live online handle to a frozen screen.

The previous phase must be complete and pass strict prefix/proof analysis.
Missing/terminal handles without completion are failures, not reasons to retry.
No protected test input is supplied to either stage.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True)
    p.add_argument('--online-pid',type=int,required=True);a=p.parse_args();base=a.base.resolve()
    marker=base/'results/long_screen_transition.json'
    if marker.exists():raise ValueError('this transition has already been attempted')
    finished=base/'phases/online16_v2/results/completion.json';start=time.monotonic()
    while not finished.exists():
        proc=Path('/proc')/str(a.online_pid)
        cmd=(proc/'cmdline').read_bytes() if (proc/'cmdline').exists() else b''
        if b'online16_v2' not in cmd:
            raise RuntimeError('previous live handle is terminal/missing without complete evidence; no new run launched')
        if time.monotonic()-start>7200:
            raise TimeoutError('observation wait expired; do not infer that the original job stopped')
        time.sleep(15)
    # Use the untouched analysis corresponding to the previous stage's code.
    subprocess.run([sys.executable,str(base/'src/formal_v4/analyze_matrix.py'),
        '--root',str(base/'phases/online16_v2'),'--out',str(base/'results/online16_v2_analysis')],check=True)
    result={'status':'online16_v2_valid_start_long_screen','wait_wall_s':time.monotonic()-start,
        'next_stage':'long600_fit16','reason':'P1 has 35/48 triple-censored parents; one larger-budget check before a broad negative conclusion.'}
    marker.write_text(json.dumps(result,indent=2)+'\n')
    code=Path(__file__).parent
    os.execvp('/usr/bin/time',['/usr/bin/time','-v','-o',str(base/'logs/long600_fit16.resources.txt'),
        sys.executable,str(code/'run_matrix.py'),'--base',str(base),'--stage','long600_fit16',
        '--spec',str(base/'metadata/long600_fit16_spec.json'),'--cohort',str(base/'metadata/online16.csv')])


if __name__=='__main__':main()
