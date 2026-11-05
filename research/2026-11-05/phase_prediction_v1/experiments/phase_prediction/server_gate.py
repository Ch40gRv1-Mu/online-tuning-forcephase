"""Small independent model/proof and structure gate before server measurements."""
import argparse
import json
import re
from pathlib import Path

import run_pilot


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root;gate=root/'data/gate';gate.mkdir(parents=True,exist_ok=True)
    sat=gate/'sat.cnf';unsat=gate/'unsat.cnf';tree=gate/'tree.cnf';cycle=gate/'cycle.cnf'
    sat.write_text('p cnf 3 3\n1 2 0\n-1 3 0\n-2 -3 0\n')
    unsat.write_text('p cnf 2 4\n1 2 0\n1 -2 0\n-1 2 0\n-1 -2 0\n')
    tree.write_text('p cnf 3 2\n1 2 0\n2 3 0\n')
    cycle.write_text('p cnf 3 3\n1 2 0\n2 3 0\n3 1 0\n')
    rows=[]
    for action,flags in run_pilot.FLAGS.items():
        rec,text=run_pilot.child([root/'bin/cadical',*flags,'--stats','--seed=0',sat],gate/(action+'.sat.log'),5,0)
        assert rec['exit_code']==10 and run_pilot.check_model(sat,text,3),(action,rec)
        rows.append({'action':action,'test':'SAT_model','passed':True,'cpu_s':rec['cpu_s']})
        proof=gate/(action+'.lrat')
        rec,_=run_pilot.child([root/'bin/cadical',*flags,'--stats','--seed=0','--lrat','--binary=false',unsat,proof],gate/(action+'.unsat.log'),5,0)
        check,text=run_pilot.child([root/'bin/lrat-check',unsat,proof],gate/(action+'.check.log'),5,0)
        assert rec['exit_code']==20 and check['exit_code']==0 and re.search(r'^[cs] VERIFIED',text,re.M),(action,rec,check,text[-500:])
        rows.append({'action':action,'test':'UNSAT_LRAT','passed':True,'cpu_s':rec['cpu_s']+check['cpu_s']})
    for path,expected in [(tree,0),(cycle,1)]:
        rec,text=run_pilot.child([root/'bin/cnf_structure',path],gate/(path.stem+'.features.log'),5,0)
        assert rec['exit_code']==0 and json.loads(text)['g_cycle_excess']==expected
        rows.append({'test':'structure_'+path.stem,'passed':True,'cpu_s':rec['cpu_s']})
    result={'status':'PASS','tests':rows,'test_count':len(rows),'cpu_s':sum(r['cpu_s'] for r in rows),
            'note':'Synthetic gate inputs only; no development or final test performance used.'}
    run_pilot.write(root/'results/gate.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
