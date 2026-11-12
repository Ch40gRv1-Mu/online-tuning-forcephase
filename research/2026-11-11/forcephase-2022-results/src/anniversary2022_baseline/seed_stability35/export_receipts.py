"""Export only recorded R35 evidence, never input CNFs or unrelated files."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from helpers import sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    root = a.root.resolve()
    if not (root/'completion.json').exists() and not (root/'failure.json').exists():
        raise ValueError('export terminal queue only; progress checks remain read-only')
    files = []
    for pattern in ['metadata/*.json', 'metadata/*.csv', 'code/*.py', 'owner.json',
                    'progress.json', 'completion.json', 'failure.json', 'analysis.json',
                    'runs/*/*.json', 'runs/*/*.log', 'runs/*/*.log.gz',
                    'parents/*.json', 'staging/*/*.json', 'staging/*/stage.log',
                    'build-owner*.log', 'build/*.log', 'owner.log']:
        files.extend(p for p in root.glob(pattern) if p.is_file() and not p.is_symlink())
    files = sorted(set(files))
    receipts = {str(p.relative_to(root)): sha(p) for p in files}
    manifest = root/'RECEIPT_SHA256.json'
    manifest.write_text(json.dumps(receipts, indent=2, sort_keys=True)+'\n')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(a.out, 'x:gz') as tf:
        for path in [*files, manifest]:
            tf.add(path, arcname=str(path.relative_to(root)), recursive=False)
    print(json.dumps({'archive': str(a.out), 'sha256': sha(a.out), 'files': len(files)+1,
                      'not_proofs_or_raw_inputs': True}), flush=True)


if __name__ == '__main__':
    main()
