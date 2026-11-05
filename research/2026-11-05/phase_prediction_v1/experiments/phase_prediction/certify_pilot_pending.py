"""One bounded proof-budget extension; never replaces a P1 measurement.

Only timed UNSAT answers whose original proof replay exhausted T are eligible.
The extension must reproduce the original deterministic final counters and pass
the same independent checker. All failed attempts and their costs are retained.
"""
import argparse
import json
import re
from pathlib import Path

import run_pilot as common


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve()
    if not (root/'results/runs.jsonl').exists():raise ValueError('P1 is still running')
    directory=root/'results/certification_extensions';directory.mkdir(exist_ok=True)
    records=[(p,json.loads(p.read_text())) for p in (root/'results/runs').glob('*.json')]
    pending=[(p,r) for p,r in records if r['verify']=='UNVERIFIED_CERTIFICATION']
    if len(pending)>4:raise ValueError('proof extension cap exceeded; manual engineering review required')
    for original_path,r in pending:
        out=directory/(r['run_id']+'.json')
        if out.exists():raise ValueError('extension already attempted; do not silently retry')
        if r['status']!='UNSAT' or r['certification']['exit_code']!=0:
            raise ValueError('this failure is not an exhausted original proof replay')
        binary=root/'bin/cadical';checker=root/'bin/lrat-check'
        path=root/'data'/(r['hash']+'.cnf')
        if common.sha(binary)!=r['identity']['binary_sha256'] or common.sha(checker)!=r['identity']['checker_sha256']:
            raise ValueError('changed verifier or solver')
        if common.sha(path)!=r['input_sha256']:raise ValueError('changed input')
        proof=root/'logs'/(r['run_id']+'.extended.lrat')
        cert,_=common.child([binary,*common.FLAGS[r['action']],'--stats','--seed=0','--lrat',
            '--binary=false','-t','120',path,proof],root/'logs'/(r['run_id']+'.extended.cert.log'),120,0)
        result={'original_run_id':r['run_id'],'original_record_sha256':common.sha(original_path),
            'input_sha256':r['input_sha256'],'binary_sha256':common.sha(binary),'checker_sha256':common.sha(checker),
            'script_sha256':common.sha(Path(__file__)),'certification':cert,'verify':'UNVERIFIED_EXTENSION',
            'verification_cpu_s':cert['cpu_s'],'measurement_changed':False,
            'reason':'Original proof replay reached its 60s cap; one separate 120s verification attempt.'}
        same=all(k in cert and k in r and cert[k]==r[k] for k in
                 ('conflicts','decisions','propagations','restarts','rephased'))
        result['same_final_search_counters']=same
        if cert['exit_code']==20 and same:
            ck,text=common.child([checker,path,proof],root/'logs'/(r['run_id']+'.extended.check.log'),120,0)
            result['checker']=ck;result['verification_cpu_s']+=ck['cpu_s']
            result['checker_verified']=bool(ck['exit_code']==0 and re.search(r'^[cs] VERIFIED',text,re.M))
            result['proof_sha256']=common.sha(proof)
            if result['checker_verified']:result['verify']='VERIFIED_LRAT_EXTENSION';proof.unlink()
        common.write(out,result);print(json.dumps(result),flush=True)
        if not result['verify'].startswith('VERIFIED_'):raise ValueError('proof extension did not validate the measurement')


if __name__=='__main__':main()
