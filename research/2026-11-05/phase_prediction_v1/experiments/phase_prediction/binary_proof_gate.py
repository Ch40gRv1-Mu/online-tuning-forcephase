"""Check the pinned standalone lrat-trim verifier before binary-proof runs.

Only generated formulas are used. ASCII/binary solver trajectories must agree;
both formats are independently checked, and malformed/unfinished proofs must
not be accepted as UNSAT. The live online16_v2 stage is never modified.
"""
import argparse
import json
import random
import re
from pathlib import Path

import run_pilot as common


def accepted(record,text):
    return record['exit_code']==20 and bool(re.search(r'^s VERIFIED$',text,re.M))


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);a=p.parse_args()
    base=a.base.resolve();work=base/'data/binary-gate';work.mkdir(parents=True,exist_ok=True)
    receipt=base/'results/binary_gate.json'
    if receipt.exists():raise ValueError('binary checker gate already recorded')
    inputs=[];holes=6;var=lambda x,y:x*holes+y+1
    clauses=[[var(x,y) for y in range(holes)] for x in range(holes+1)]
    clauses += [[-var(x,y),-var(z,y)] for y in range(holes)
                for x in range(holes+1) for z in range(x+1,holes+1)]
    path=work/'php6.cnf';nv=holes*(holes+1)
    path.write_text(f'p cnf {nv} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
    inputs.append((path,nv))
    sat=work/'sat.cnf';sat.write_text('p cnf 3 3\n1 2 0\n-1 3 0\n-2 -3 0\n')
    inputs.append((sat,3));tests=[];cpu=0.
    for path,nv in inputs:
        for action,flags in common.FLAGS.items():
            modes={}
            for fmt,binary_flag in [('ascii','false'),('binary','true')]:
                name=f'{path.stem}_{action}_{fmt}';proof=work/(name+'.lrat')
                r,text=common.child([base/'bin/cadical',*flags,'--seed=0','--stats','--lrat',
                    f'--binary={binary_flag}','-t','30',path,proof],work/(name+'.solver.log'),30,4)
                cpu+=r['cpu_s'];assert r['exit_code'] in (10,20),r
                modes[fmt]={k:r.get(k) for k in ('exit_code','conflicts','decisions','propagations','restarts','rephased')}
                if r['exit_code']==10:assert common.check_model(path,text,nv)
                else:
                    ck,ct=common.child([base/'bin/lrat-trim','--no-trim',path,proof],work/(name+'.check.log'),30,4)
                    cpu+=ck['cpu_s'];assert accepted(ck,ct),(ck,ct)
                    if fmt=='ascii':
                        ck,ct=common.child([base/'bin/lrat-check',path,proof],work/(name+'.second-check.log'),30,4)
                        cpu+=ck['cpu_s'];assert ck['exit_code']==0 and re.search(r'^[cs] VERIFIED',ct,re.M)
                    else:
                        short=work/(name+'.truncated');data=proof.read_bytes();short.write_bytes(data[:len(data)//2])
                        ck,ct=common.child([base/'bin/lrat-trim','--no-trim',path,short],work/(name+'.reject.log'),30,4)
                        cpu+=ck['cpu_s'];assert not accepted(ck,ct),'unfinished binary proof accepted'
                        tests.append({'test':name+'_unfinished_rejected','passed':True})
                tests.append({'test':name+'_answer_independently_checked','passed':True})
            assert modes['ascii']==modes['binary'],(path,action,modes)
            tests.append({'test':path.stem+'_'+action+'_same_search_counts','passed':True})
    fake=work/'fake-empty.lrat';fake.write_text('4 0 1 0\n')
    ck,ct=common.child([base/'bin/lrat-trim','--no-trim',sat,fake],work/'fake-empty.check.log',30,4)
    cpu+=ck['cpu_s'];assert not accepted(ck,ct),'false UNSAT proof accepted on satisfiable input'
    tests.append({'test':'false_empty_clause_rejected_on_SAT','passed':True})
    result={'status':'PASS','tests':tests,'test_count':len(tests),'cpu_s':cpu,
        'solver_sha256':common.sha(base/'bin/cadical'),'checker_sha256':common.sha(base/'bin/lrat-trim'),
        'checker_source_sha256':common.sha(base/'vendor/lrat-trim.c'),
        'gate_sha256':common.sha(Path(__file__)),
        'source':'Standalone checker test/cnf/lrat-trim.c from pinned CaDiCaL commit c60730422e758ef1cebe7aeddf2dda31c996bf04',
        'scope':'Synthetic engineering validation only; binary versus ASCII time is not a performance estimate.'}
    common.write(receipt,result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
