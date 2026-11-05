"""Bounded direct public downloads, verified atomically before pilot launch."""
import argparse
import csv
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root
    with (root/'metadata/pilot_frozen.csv').open() as f:rows=list(csv.DictReader(f))
    assert len(rows)==48 and all(r['role']=='development_fit' for r in rows)
    assert not (root/'PUBLIC_CNF_CACHE_MANIFEST.json').exists()
    def one(r):
        dst=root/'data'/(r['hash']+'.cnf.xz')
        if not dst.exists() or sha(dst)!=r['expected_sha256_xz']:
            partial=root/'data'/(r['hash']+'.http.part')
            subprocess.run(['curl','-fsSL','--connect-timeout','20','--max-time','1800',
                            '--max-filesize','100000000','https://benchmark-database.de/file/'+r['hash'],
                            '-o',str(partial)],check=True)
            if sha(partial)!=r['expected_sha256_xz']:raise ValueError('public input checksum mismatch')
            partial.replace(dst)
        return {'hash':r['hash'],'sha256_xz':sha(dst),'bytes':dst.stat().st_size}
    verified=[]
    with ThreadPoolExecutor(8) as ex:
        futures=[ex.submit(one,r) for r in rows]
        for future in as_completed(futures):
            verified.append(future.result())
            print(f'public files verified {len(verified)}/48',flush=True)
    value={'purpose':'Public GBD direct download, complete frozen fit cohort; no user attachments',
           'inputs':verified}
    tmp=root/'PUBLIC_CNF_CACHE_MANIFEST.tmp'
    tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.rename(root/'PUBLIC_CNF_CACHE_MANIFEST.json')
    print('All public inputs atomically staged; entering guarded pilot',flush=True)
    os.execvp('bash',['bash',str(root/'src/launch_when_cache_ready.sh'),str(root)])


if __name__=='__main__':main()
