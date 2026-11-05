#!/usr/bin/env bash
# Public source build in one isolated, user-owned experiment directory.
set -euo pipefail
FPP_ROOT="${1:?experiment directory required}"
cd "$FPP_ROOT"
mkdir -p bin build/upstream-source logs results
python3 - <<'PY'
import hashlib,json
from pathlib import Path
manifest=json.loads(Path('PUBLIC_EXECUTION_MANIFEST.json').read_text())
for item in manifest['files']:
    path=Path(item['archive_path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],path
print('execution manifest verified',flush=True)
PY
command -v prlimit
command -v taskset
g++ -O3 -std=c++17 src/cnf_structure.cpp -o bin/cnf_structure
cc -O2 vendor/lrat-check.c -o bin/lrat-check
if [ ! -x bin/cadical ]; then
  tar -xzf vendor/cadical-src.tar.gz --strip-components=1 -C build/upstream-source
  (
    cd build/upstream-source
    ./configure > ../../logs/configure.log 2>&1
    make -j4 > ../../logs/make.log 2>&1
  )
  cp build/upstream-source/build/cadical bin/cadical
fi
python3 - <<'PY'
import hashlib,json,os,platform,subprocess
from pathlib import Path
from datetime import datetime,timezone
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
version=subprocess.check_output(['bin/cadical','--version'],text=True).strip()
assert version=='3.0.1',version
info={'created_utc':datetime.now(timezone.utc).isoformat(),'host':platform.node(),
      'platform':platform.platform(),'available_cpus':sorted(os.sched_getaffinity(0)),
      'cadical_version':version,'cadical_source_commit':'c60730422e758ef1cebe7aeddf2dda31c996bf04',
      'build_info':subprocess.check_output(['bin/cadical','--build'],text=True),
      'binary_sha256':{p:sha(p) for p in ['bin/cadical','bin/cnf_structure','bin/lrat-check']},
      'vendor_sha256':sha('vendor/cadical-src.tar.gz'),'status':'built; correctness gate still required',
      'privacy':'professor CSV/image and local performance records were not transferred'}
Path('results/environment.json').write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(info),flush=True)
PY
python3 src/server_gate.py --root "$FPP_ROOT"
