"""Build only the two pinned public tools; no benchmark or solver invocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import tarfile
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    config = json.loads((root/'metadata/build_sources.json').read_text())
    started, cpu = time.monotonic(), time.process_time()
    receipt = {'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'build_source_sha256': sha(__file__), 'tools': {}}
    (root/'build').mkdir(exist_ok=True)
    for name, tool in config.items():
        archive = root/'sources'/tool['archive']
        if sha(archive) != tool['archive_sha256']:
            raise ValueError('public source archive identity mismatch')
        directory = root/'build'/tool['directory']
        if directory.exists():
            raise RuntimeError('preserve existing build; do not overwrite')
        with tarfile.open(archive) as tf:
            # CaDiCaL includes legitimate relative links. Admit only archive-local links.
            for member in tf.getmembers():
                dest = (root/'build'/member.name).resolve()
                if root/'build' not in dest.parents or not (
                    member.isfile() or member.isdir() or member.issym() or member.islnk()
                ):
                    raise ValueError('unsafe archive member')
                if member.issym() or member.islnk():
                    target = (dest.parent/member.linkname).resolve() if member.issym() else (
                        root/'build'/member.linkname).resolve()
                    if root/'build' not in target.parents:
                        raise ValueError('archive link escapes build directory')
            tf.extractall(root/'build')
        commands = [['./configure', '-static'], ['make', '-j8']] if name == 'cadical' else [
            ['./configure'], ['make', '-j8']]
        with (root/'build'/f'{name}.log').open('xb') as log:
            for command in commands:
                subprocess.run(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                               timeout=1200, check=True)
        binary = directory/tool['binary']
        receipt['tools'][name] = {**tool, 'binary_path': str(binary), 'binary_sha256': sha(binary)}
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt.update(parent_CPU_s=time.process_time()-cpu,
                   children_CPU_s=usage.ru_utime+usage.ru_stime,
                   wall_s=time.monotonic()-started,
                   compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                   complete=True, new_solver_calls=0)
    path = root/'metadata/build_receipt.json'
    with path.open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
