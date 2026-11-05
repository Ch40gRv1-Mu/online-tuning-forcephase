"""Bounded public-source staging with prior SHA checks and atomic readiness.

Does not run solvers, read outcomes, overwrite verified inputs, or accept final
test roles. A separate checksum sidecar adds provenance without changing the
already frozen cohort, order, roles, or eligibility rules.
"""
import argparse
import csv
import json
import lzma
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

import run_pilot as common


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True)
    p.add_argument('--cohort',type=Path,required=True);p.add_argument('--checksums',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();base=a.base.resolve()
    with a.cohort.open() as f:rows=list(csv.DictReader(f))
    checks=json.loads(a.checksums.read_text())
    if set(checks)!={r['hash'] for r in rows}:raise ValueError('checksum matrix differs from cohort')
    if any(r['role'] not in {'development_fit','development_feedback'} or
           not re.fullmatch('[0-9a-f]{32}',r['hash']) or int(r['bytes'])>100000000 or
           int(r['variables'])>5000000 for r in rows):raise ValueError('protected or oversized cohort')
    if a.receipt.exists():raise ValueError('staging receipt is immutable')
    def one(r):
        if shutil.disk_usage(base).free<12*1024**3:raise RuntimeError('disk reserve reached')
        h=r['hash'];dst=base/'data'/(h+'.cnf.xz');expected=checks[h]['sha256_xz']
        if dst.exists():
            if common.sha(dst)!=expected:raise ValueError('existing input differs from expected SHA')
        else:
            partial=base/'data'/(h+'.cohort-http.part')
            subprocess.run(['curl','-fsSL','--connect-timeout','20','--max-time','1800',
                '--max-filesize','100000000',f'https://benchmark-database.de/file/{h}','-o',str(partial)],check=True)
            if common.sha(partial)!=expected:raise ValueError('public download SHA mismatch')
            partial.replace(dst)
        cnf=base/'data'/(h+'.cnf')
        if not cnf.exists():
            partial=base/'data'/(h+'.plain-cohort.part');size=0
            with lzma.open(dst,'rb') as src,partial.open('wb') as target:
                for chunk in iter(lambda:src.read(1<<20),b''):
                    size+=len(chunk)
                    if size>100000000:raise ValueError('plain input size cap exceeded')
                    target.write(chunk)
            if common.sha(partial)!=checks[h]['sha256_cnf']:raise ValueError('plain source SHA mismatch')
            partial.replace(cnf)
        if common.sha(cnf)!=checks[h]['sha256_cnf']:raise ValueError('existing plain input SHA mismatch')
        return {'hash':h,'sha256_xz':expected,'expected_sha256_cnf':checks[h]['sha256_cnf'],
                'compressed_bytes':dst.stat().st_size}
    verified=[]
    with ThreadPoolExecutor(8) as ex:
        futures=[ex.submit(one,r) for r in rows]
        for future in as_completed(futures):
            verified.append(future.result());print(f'public cohort verified {len(verified)}/{len(rows)}',flush=True)
    common.write(a.receipt,{'cohort_sha256':common.sha(a.cohort),'checksums_sha256':common.sha(a.checksums),
        'source':'public GBD; no professor attachments or performance records','inputs':verified})


if __name__=='__main__':main()
