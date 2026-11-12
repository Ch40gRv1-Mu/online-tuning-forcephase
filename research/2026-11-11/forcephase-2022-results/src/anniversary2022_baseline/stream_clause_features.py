"""R53 owner: bounded public-input streaming, exact R50 table, immutable receipts."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import fcntl
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .measure_compact_prefetch import atomic, wait4
from .structural_clusters import DATA, ROOT, read_csv

OUT = DATA / 'mechanism_R53_streaming_20261111'
COHORT = ROOT / 'configs/anniversary2022_baseline/R53_streaming_20261111/cohort.json'
SOURCE = Path(__file__).with_name('stream_clause_table.cpp')
GIB = 1024 ** 3
FLOOR = 2 * GIB


def initialize_worker():
    global _thread_limit
    _thread_limit = threadpool_limits(limits=1)


def build(out):
    tick = resource.getrusage(resource.RUSAGE_CHILDREN); began = time.monotonic()
    binary = out / 'stream_clause_table'
    command = [shutil.which('clang++') or shutil.which('g++'), '-O3', '-std=c++17', str(SOURCE), '-o', str(binary)]
    r = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (out / 'build.log').write_text(r.stdout + r.stderr)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    atomic(out / 'build_receipt.json', {'command': command, 'exit': r.returncode,
        'native_source_sha256': sha(SOURCE), 'binary_sha256': sha(binary) if binary.exists() else None,
        'child_CPU_s': after.ru_utime + after.ru_stime - tick.ru_utime - tick.ru_stime,
        'wall_s': time.monotonic() - began, 'included_in_owner_CPU': True})
    assert r.returncode == 0 and binary.exists(), 'R53 build failed'
    return binary


def wire_bound(row):
    return min(GIB, max(16 * 1024 ** 2, 2 * row.get('old_wire_bytes', 0)))


def download(row, root):
    began, cpu = time.monotonic(), time.thread_time()
    old = Path(row['old_wire_path'])
    if old.is_file():
        assert sha(old) == row['old_wire_sha256'], 'old readonly wire cache changed'
        return old, {'reused_download': True, 'wire_bytes': old.stat().st_size,
            'wire_sha256': row['old_wire_sha256'], 'CPU_s': time.thread_time() - cpu,
            'wall_s': time.monotonic() - began, 'owned_wire': False}
    assert row['url'].startswith('https://benchmark-database.de/file/')
    dest = root / 'wire' / (row['instance_key'] + '.input')
    temporary = dest.with_suffix('.part')
    digest, total = hashlib.sha256(), 0
    try:
        request = urllib.request.Request(row['url'], headers={'User-Agent': 'forcephase-R53-static-feature/1'})
        with urllib.request.urlopen(request, timeout=20) as stream, temporary.open('xb') as target:
            while True:
                if time.monotonic() - began > 180: raise TimeoutError('R53 transfer180wall')
                block = stream.read(1 << 20)
                if not block: break
                total += len(block)
                if total > wire_bound(row): raise OSError('R53 per-input compressed reservation exceeded')
                if shutil.disk_usage(root).free < FLOOR: raise OSError('R53 disk floor')
                target.write(block); digest.update(block)
        temporary.replace(dest)
        return dest, {'reused_download': False, 'wire_bytes': total, 'wire_sha256': digest.hexdigest(),
            'CPU_s': time.thread_time() - cpu, 'wall_s': time.monotonic() - began, 'owned_wire': True}
    finally:
        temporary.unlink(missing_ok=True)


def open_plain(path):
    with path.open('rb') as f: magic = f.read(6)
    return lzma.open(path, 'rb') if magic == b'\xfd7zXZ\x00' else gzip.open(path, 'rb') if magic[:2] == b'\x1f\x8b' else path.open('rb')


def native_profile(row, wire, binary, root):
    began, parent = time.monotonic(), time.thread_time()
    key = row['instance_key']
    packed = root / 'bins' / (key + '.bin')
    log = root / 'native_logs' / (key + '.json')
    error_log = root / 'native_logs' / (key + '.stderr')
    child = None; reaped = False; native_cpu = 0.; hash_cpu = 0.; total = 0
    binary_sha = sha(binary)
    try:
        with log.open('xb') as stdout, error_log.open('xb') as stderr:
            child = subprocess.Popen([str(binary), str(packed)], stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
            def kill_owned():
                try: child.kill()
                except ProcessLookupError: pass
            timer = threading.Timer(180, kill_owned); timer.daemon = True; timer.start()
            try:
                digest = hashlib.sha256()
                with open_plain(wire) as stream:
                    while True:
                        block = stream.read(1 << 20)
                        if not block: break
                        total += len(block)
                        if total > min(4 * GIB, row['raw_bytes']): raise ValueError('R53 raw byte bound')
                        tick = time.thread_time(); digest.update(block); hash_cpu += time.thread_time() - tick
                        child.stdin.write(block)
                        if time.thread_time() - parent > 16: raise TimeoutError('R53 ingestion16CPU')
                        if time.monotonic() - began > 180: raise TimeoutError('R53 profile180wall')
                child.stdin.close()
                code, native_cpu, rss = wait4(child); reaped = True
            finally:
                timer.cancel()
        assert code == 0, f'R53 native exit{code}: {error_log.read_text(errors="replace")[-1000:]}'
        assert sha(binary) == binary_sha, 'R53 native binary changed during profile'
        assert total == row['raw_bytes'] and digest.hexdigest() == row['raw_sha256'], 'R53 raw identity changed'
        a = json.loads(log.read_text())
        assert a['schema'] == 'forcephase.stream_clause_table.R53.v1' and a['SAT_calls'] == 0
        m = a['clauses']; counts = np.array(a['counts'], np.int64).reshape(9, 7)
        bins = np.fromfile(packed, np.uint8).reshape(m, 2)
        assert packed.stat().st_size == 2 * m and counts.sum() == m
        actual_counts = np.bincount(7 * bins[:, 0] + bins[:, 1], minlength=63).reshape(9, 7)
        assert np.array_equal(counts, actual_counts)
        # Int64 matches the frozen original numpy permutation path exactly.
        shuffled = np.random.default_rng(20261150).permutation(bins[:, 1].astype(np.int64))
        null = np.bincount(7 * bins[:, 0] + shuffled, minlength=63).reshape(9, 7)
        assert np.array_equal(counts.sum(axis=0), null.sum(axis=0))
        assert np.array_equal(counts.sum(axis=1), null.sum(axis=1))
        h = counts / max(m, 1)
        independent = np.outer(counts.sum(axis=0), counts.sum(axis=1)).T / max(m * m, 1)
        vectors = [np.sqrt(h).ravel(), np.sqrt(independent).ravel(), np.sqrt(null / max(m, 1)).ravel()]
        used = h > 0
        mi = float((h[used] * np.log(h[used] / independent[used])).sum()) if m else 0.
        assert all(v.shape == (63,) and np.isfinite(v).all() for v in vectors)
        elapsed = time.thread_time() - parent + native_cpu
        if elapsed > 32: raise TimeoutError('R53 combined profile32CPU')
        return vectors, {'native_exit': code, 'native_CPU_s': native_cpu, 'native_max_RSS_platform_units': rss,
            'native_binary_sha256': binary_sha,
            'profile_parent_CPU_s': elapsed - native_cpu, 'identity_hash_CPU_s': hash_cpu,
            'feature_fee_CPU_s': max(0, elapsed - hash_cpu), 'profile_wall_s': time.monotonic() - began,
            'raw_sha256': digest.hexdigest(), 'raw_bytes': total, 'clauses': m, 'literals': a['literals'],
            'MI_nats': max(mi, 0), 'informative': bool(m >= 40 and mi > .01 and np.linalg.norm(vectors[0] - vectors[2]) > 1e-6)}
    except BaseException:
        if child is not None and not reaped:
            try: child.kill()
            except ProcessLookupError: pass
            try: _, native_cpu, _ = wait4(child)
            except ChildProcessError: pass
        raise
    finally:
        packed.unlink(missing_ok=True)


def collect_one(job):
    row, binary, root = job
    began, cpu = time.monotonic(), time.process_time()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    wire, got, record = None, None, {}
    try:
        if row['upstream_feature_failed']:
            return {'instance_key': row['instance_key'], 'ordinal': row['ordinal'],
                'status': 'UPSTREAM_FEATURE_FAILURE_PAID_D', 'feature_fee_CPU_s': 0., 'physical_CPU_s': 0.,
                'informative': False, 'new_download': False, 'wall_s': time.monotonic() - began}
        wire, got = download(row, root)
        vectors, details = native_profile(row, wire, binary, root)
        record = {'instance_key': row['instance_key'], 'ordinal': row['ordinal'], 'status': 'ok',
            'vectors': {k: v.tolist() for k, v in zip(('joint', 'marginal', 'decoupled'), vectors)},
            'transfer': got, **details}
    except Exception as e:
        record = {'instance_key': row['instance_key'], 'ordinal': row['ordinal'], 'status': 'ERROR',
            'error': repr(e), 'transfer': got, 'informative': False}
    finally:
        if wire is not None and got is not None and got['owned_wire']: wire.unlink(missing_ok=True)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    elapsed = time.process_time() - cpu + after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
    record.update(physical_CPU_s=elapsed, wall_s=time.monotonic() - began,
        worker_cumulative_peak_RSS_platform_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        new_download=bool(got is not None and not got['reused_download']))
    if record['status'] != 'ok': record['feature_fee_CPU_s'] = max(0, elapsed - (got['CPU_s'] if got else 0))
    return record


def compatibility(binary, root):
    from .clause_polarity_table import extract
    raw = b'c embedded syntax checks\np cnf 40 6\n0\n+1 0\n-1 2 0\n1 -2 3 0\n1 2 -3 -4 0\n1 2 3 4 -5 -6 -7 -8 -9 0\n'
    path = root / 'fixture.cnf'; path.write_bytes(raw)
    row = {'instance_key': 'fixture', 'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest()}
    values, details = native_profile(row, path, binary, root)
    reference = extract(raw)[:3]
    assert all(np.array_equal(a, b) for a, b in zip(values, reference)), 'Streaming differs from frozen R50 table'
    path.unlink()
    atomic(root / 'compatibility.json', {'native_fixture_calls': 1, 'exact_all_three_vectors': True,
        'empty_plus_sign_comments': True, 'resources': details, 'SAT_calls': 0})


def total_cpu():
    p, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return p.ru_utime + p.ru_stime + c.ru_utime + c.ru_stime


def collect(scoring_out):
    """Read a complete frozen stage only; never consume an active partial block."""
    stage = int(os.environ['FORCEPHASE_R53_STAGE'])
    assert stage in (512, 1876)
    barrier = json.loads((OUT / f'stage_{stage}.json').read_text())
    assert barrier['through'] == stage and barrier['all_fixed_units_attempted'] and barrier['no_native_worker_running']
    rows = json.loads(COHORT.read_text())['rows'][:stage]
    old = DATA / 'mechanism_R52_20261111'
    with np.load(old / 'features.npz') as z:
        keys, eligible, valid = z['keys'].tolist(), z['eligible'].copy(), z['valid'].copy()
        views = {k: z[k].copy() for k in ('joint', 'marginal', 'decoupled')}
        fees = {k: z[k + '_fee'].copy() for k in views}
    index = {k: i for i, k in enumerate(keys)}
    informative = np.zeros(len(keys), bool)
    records, successes, errors, upstream = [], 0, 0, 0
    binary_sha = sha(OUT / 'stream_clause_table')
    for row in rows:
        path = OUT / 'records' / (row['instance_key'] + '.json')
        r = json.loads(path.read_text()); i = index[row['instance_key']]
        assert r['ordinal'] == row['ordinal'] and r['instance_key'] == row['instance_key']
        eligible[i] = True
        records.append({'key': row['instance_key'], 'receipt_sha256': sha(path)})
        if r['status'].startswith('UPSTREAM'):
            assert row['upstream_feature_failed']; upstream += 1
            continue
        valid[i] = r['status'] == 'ok'
        for kind in views:
            fees[kind][i] = r['feature_fee_CPU_s']
            if valid[i]: views[kind][i, 43:] = r['vectors'][kind]
        if valid[i]:
            assert r['raw_sha256'] == row['raw_sha256'] and r['raw_bytes'] == row['raw_bytes']
            assert r['native_binary_sha256'] == binary_sha
            informative[i] = r['informative']; successes += 1
        else: errors += 1
    with np.load(old / 'features.npz') as z:
        prior = z['eligible']
        for kind in views:
            assert np.array_equal(views[kind][prior], z[kind][prior])
            assert np.array_equal(views[kind][:, :43], z[kind][:, :43])
            assert np.array_equal(fees[kind][prior], z[kind + '_fee'][prior])
    np.savez_compressed(scoring_out / 'features.npz', keys=np.array(keys), eligible=eligible, valid=valid,
        informative=informative, **views, **{k + '_fee': v for k, v in fees.items()})
    atomic(scoring_out / 'collection.json', {'stage': stage, 'fixed_all_stage_units_attempted': True,
        'new_success': successes, 'new_errors': errors, 'upstream_feature_failures': upstream,
        'new_informative': int(informative.sum()), 'reused_old_profiles': int(prior.sum()),
        'input_receipts': records, 'native_binary_sha256': binary_sha, 'cohort_sha256': sha(COHORT),
        'old_features_sha256': sha(old / 'features.npz'), 'new_solver_calls': 0,
        'scope': '512stage is predeclared intermediate development diagnostic,1876 is final full-coverage attempt; neither independent confirmation',
        'cost_note': 'Old2843 expenses logically reused, acquisition owner physical ledger includes this child scoring cost exactly once.'})
    return keys, eligible, valid, informative, views, fees


def main():
    began, cpu = time.monotonic(), total_cpu()
    OUT.mkdir(exist_ok=False)
    lock = (OUT / 'owner.lock').open('w'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rows = json.loads(COHORT.read_text())['rows']
    for name in ('wire', 'bins', 'native_logs', 'records'): (OUT / name).mkdir()
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'started_UTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'source_sha256': sha(__file__), 'native_source_sha256': sha(SOURCE), 'cohort_sha256': sha(COHORT),
        'parents': 1876, 'upstream_failures': 25, 'max_workers': 2, 'no_resubmission': True})
    status, completed, scoring = 'running', [], []
    try:
        assert len(rows) == 1876 and [r['ordinal'] for r in rows] == list(range(1, 1877))
        binary = build(OUT); compatibility(binary, OUT)
        with ProcessPoolExecutor(max_workers=2, initializer=initialize_worker) as pool:
            position = 0
            for boundary in (64, 512, 1876):
                pending, reserved = {}, 0
                while position < boundary or pending:
                    while position < boundary and len(pending) < 2:
                        row = rows[position]
                        amount = 0 if row['upstream_feature_failed'] or Path(row['old_wire_path']).is_file() else wire_bound(row)
                        if reserved + amount > GIB: break
                        if shutil.disk_usage(OUT).free < FLOOR + amount + 80 * 1024 ** 2:
                            if pending: break
                            raise OSError('R53 disk cannot admit next fixed input')
                        open_cpu = total_cpu() - cpu + sum(r['physical_CPU_s'] for r in completed)
                        if open_cpu + 40 * (len(pending) + 1) + 300 > 6 * 3600 or time.monotonic() - began > 4 * 3600:
                            raise TimeoutError('R53 owner planning resource ceiling')
                        transferred = sum(r.get('transfer', {}).get('wire_bytes', 0) for r in completed
                            if r.get('transfer') and not r['transfer']['reused_download'])
                        if transferred + reserved + amount > 16 * GIB:
                            raise OSError('R53 cumulative transfer ceiling')
                        future = pool.submit(collect_one, (row, binary, OUT))
                        pending[future] = amount; reserved += amount; position += 1
                    if not pending: raise RuntimeError('R53 no admissible fixed input')
                    done, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
                    for future in done:
                        reserved -= pending.pop(future)
                        record = future.result(); completed.append(record)
                        atomic(OUT / 'records' / (record['instance_key'] + '.json'), record)
                    if done and len(completed) % 16 == 0:
                        print(f'R53 attempted{len(completed)}/1876, valid{sum(r["status"]=="ok" for r in completed)}', flush=True)
                    atomic(OUT / 'progress.json', {'stage': 'collecting', 'completed': len(completed), 'expected': 1876,
                        'valid_new_profiles': sum(r['status'] == 'ok' for r in completed),
                        'failed_new_profiles': sum(r['status'] == 'ERROR' for r in completed),
                        'upstream_failed_paidD': sum(r['status'].startswith('UPSTREAM') for r in completed),
                        'active_workers': len(pending), 'wall_s': time.monotonic() - began,
                        'open_CPU_partial_s': total_cpu() - cpu + sum(r['physical_CPU_s'] for r in completed),
                        'open_CPU_excludes_inflight_and_worker_import_not_closed': True})
                assert len(completed) == boundary
                if boundary == 64:
                    attempted = [r for r in completed if not r['status'].startswith('UPSTREAM')]
                    okay = [r for r in attempted if r['status'] == 'ok']
                    identity_errors = [r for r in attempted if 'identity' in r.get('error', '').lower()]
                    median = float(np.median([r['feature_fee_CPU_s'] for r in okay])) if okay else None
                    peak = max((r.get('worker_cumulative_peak_RSS_platform_units', 0) for r in attempted), default=0)
                    peak_bytes = peak if sys.platform == 'darwin' else 1024 * peak
                    passed = bool(len(okay) >= .9 * len(attempted) and not identity_errors and median is not None and median <= 8 and peak_bytes <= GIB)
                    atomic(OUT / 'first64.json', {'passed': passed, 'attempted': len(attempted), 'valid': len(okay),
                        'identity_errors': len(identity_errors), 'median_feature_CPU_s': median,
                        'worker_peak_RSS_bytes': peak_bytes,
                        'wall_s': time.monotonic() - began, 'CPU_s_open_not_closed': total_cpu() - cpu})
                    if not passed: raise RuntimeError('R53 fixed engineering continuation gate failed')
                if boundary in (512, 1876):
                    atomic(OUT / f'stage_{boundary}.json', {'through': boundary, 'all_fixed_units_attempted': True,
                        'no_native_worker_running': True, 'source_sha256': sha(__file__)})
                    env = dict(os.environ, FORCEPHASE_R53_STAGE=str(boundary))
                    with (OUT / f'score_{boundary}.log').open('xb') as log:
                        subprocess.run([sys.executable, '-m', 'src.anniversary2022_baseline.score_streamed_clause_table'],
                            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
                    scoring.append(boundary)
        status = 'complete'
        atomic(OUT / 'completion.json', {'status': status, 'attempted': len(completed), 'scored_stages': scoring,
            'physical_CPU_s': total_cpu() - cpu, 'wall_s': time.monotonic() - began, 'new_solver_calls': 0})
    except BaseException as e:
        status = 'failed'
        atomic(OUT / 'failure.json', {'error': repr(e), 'attempted': len(completed), 'scored_stages': scoring,
            'reward': None, 'physical_CPU_s': total_cpu() - cpu, 'wall_s': time.monotonic() - began})
        raise
    finally:
        atomic(OUT / 'resources.json', {'status': status, 'physical_owner_tree_CPU_s': total_cpu() - cpu,
            'wall_s': time.monotonic() - began, 'attempted': len(completed), 'new_solver_calls': 0,
            'includes_compiler_native_and_scoring_do_not_charge_children_twice': True})


if __name__ == '__main__':
    main()
