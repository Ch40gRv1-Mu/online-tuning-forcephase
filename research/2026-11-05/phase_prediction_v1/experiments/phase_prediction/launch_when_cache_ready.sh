#!/usr/bin/env bash
# Gate the scientific process on complete verified public-data staging.
set -euo pipefail
FPP_ROOT="${1:?experiment directory required}"
cd "$FPP_ROOT"
deadline=$((SECONDS + 7200))
echo "Waiting for the complete public CNF cache manifest"
while [ ! -f PUBLIC_CNF_CACHE_MANIFEST.json ]; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "Cache staging deadline reached; no timing measurements started" >&2
    exit 2
  fi
  sleep 5
done
python3 - <<'PY'
import csv,hashlib,json
from pathlib import Path
with Path('metadata/pilot_frozen.csv').open() as f:rows=list(csv.DictReader(f))
manifest=json.loads(Path('PUBLIC_CNF_CACHE_MANIFEST.json').read_text())
assert len(rows)==48 and all(r['role']=='development_fit' for r in rows)
assert {r['hash'] for r in rows}=={r['hash'] for r in manifest['inputs']}
for row in rows:
    path=Path('data')/(row['hash']+'.cnf.xz')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['expected_sha256_xz'],path
assert json.loads(Path('results/gate.json').read_text())['status']=='PASS'
print('All 48 public CNFs match frozen checksums; correctness gate PASS',flush=True)
PY
exec python3 src/run_pilot.py all --root "$FPP_ROOT" --pilot metadata/pilot_frozen.csv \
  --timeout 60 --workers 4 --max-cpu-hours 8
