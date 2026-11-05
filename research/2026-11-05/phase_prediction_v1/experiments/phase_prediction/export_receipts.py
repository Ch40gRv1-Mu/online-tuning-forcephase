"""Export completed stage receipts without CNFs, proofs or credentials."""
import argparse
import json
import tarfile
from pathlib import Path

import run_pilot as common


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--pilot',action='store_true');a=p.parse_args()
    root=a.root.resolve()
    if a.out.exists():raise ValueError('immutable export already exists')
    if a.pilot:
        analysis='p1_analysis_verified' if (root/'results/p1_analysis_verified').exists() else 'p1_analysis'
        integrity=json.loads((root/'results'/analysis/'integrity.json').read_text())
        if not integrity['complete_and_valid']:raise ValueError('P1 analysis did not pass')
    else:
        if json.loads((root/'results/completion.json').read_text())['status']!='COMPLETE':
            raise ValueError('stage not complete')
    files=[]
    for top in ('metadata','results'):
        for path in (root/top).rglob('*'):
            if path.is_file() and path.suffix in ('.json','.jsonl','.csv'):
                files.append(path)
    # Online raw telemetry is necessary for independent local prefix checking.
    if not a.pilot:files.extend((root/'logs').glob('*.jsonl'))
    manifest={'root_role':'completed_development_stage','files':[
        {'path':str(p.relative_to(root)),'sha256':common.sha(p)} for p in sorted(set(files))]}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    temporary=a.out.with_suffix('.part')
    with tarfile.open(temporary,'w:gz') as archive:
        for path in sorted(set(files)):archive.add(path,arcname=str(path.relative_to(root)))
        import io
        data=(json.dumps(manifest,indent=2)+'\n').encode();info=tarfile.TarInfo('RECEIPT_MANIFEST.json');info.size=len(data)
        archive.addfile(info,io.BytesIO(data))
    temporary.rename(a.out);print(json.dumps({'archive':str(a.out),'bytes':a.out.stat().st_size,
                                               'sha256':common.sha(a.out),'files':len(files)}))


if __name__=='__main__':main()
