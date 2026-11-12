"""R35 one-owner, checkpointed, same-host solver-seed replication (stdlib only)."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import csv
import fcntl
import gzip
import hashlib
import json
import lzma
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid

from helpers import ACTIONS, check_model, fingerprint, parse_stats, process_state, read, sha, utc, write


def physical_cpu():
    a = resource.getrusage(resource.RUSAGE_SELF)
    b = resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime+a.ru_stime+b.ru_utime+b.ru_stime


def limited_process(command, log, cpu_limit, wall_limit, memory, file_limit,
                    affinity, active_path, grace=5, output_paths=()):
    """Authoritative baseline timer with the original CPU-backstop margin.

    wait4 applies to this thread's specific direct child; no global child reaper.
    A checker/stager is another bounded direct process, never an unbounded parent task.
    """
    backstop = math.ceil(cpu_limit*1.02)+5
    actual = ['prlimit', f'--as={memory}', f'--fsize={file_limit}',
              f'--cpu={backstop}:{backstop+5}', '--', 'taskset', '-c', str(affinity),
              *map(str, command)]
    began = time.monotonic()
    reason, stop_at, hard_kill = None, None, False
    with Path(log).open('xb') as stream:
        child = subprocess.Popen(actual, stdout=stream, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        state = process_state(child.pid)
        write(active_path, {'pid': child.pid, 'start_ticks': state['start_ticks'] if state else None,
                            'command': actual, 'started_UTC': utc()})
        while True:
            pid, status, usage = os.wait4(child.pid, os.WNOHANG)
            if pid:
                break
            now, current = time.monotonic(), process_state(child.pid)
            if reason is None:
                output_size = 0
                for output in output_paths:
                    try:
                        output_size += Path(output).stat().st_size
                    except FileNotFoundError:
                        pass
                if output_paths and output_size >= file_limit:
                    reason, stop_at = 'OUTPUT_LIMIT', now
                elif current and current['cpu_s'] >= cpu_limit:
                    reason, stop_at = 'CPU_LIMIT', now
                elif now-began >= wall_limit:
                    reason, stop_at = 'WALL_WATCHDOG', now
                if reason:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            elif not hard_kill and now-stop_at >= grace:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                hard_kill = True
            time.sleep(.02)
        child.returncode = os.waitstatus_to_exitcode(status)
    Path(active_path).unlink(missing_ok=True)
    return {'command': actual, 'exit_code': child.returncode, 'cpu_user_s': usage.ru_utime,
            'cpu_system_s': usage.ru_stime, 'cpu_s': usage.ru_utime+usage.ru_stime,
            'wall_s': time.monotonic()-began, 'maxrss_kib': usage.ru_maxrss,
            'stop_reason': reason, 'hard_kill': hard_kill, 'cpu_affinity': affinity}


def bounded(spec, command, directory, name, cpu, wall, affinity):
    outputs = [directory/'solver.lrat', directory/'solver.log'] if name == 'solver' else []
    return limited_process(command, directory/(name+'.log'), cpu, wall, spec['memory_bytes'],
                           spec['proof_limit_bytes'], affinity, directory/(name+'_active.json'),
                           spec['termination_grace_s'], output_paths=outputs)


def stage_child(root, row):
    """Bounded public download then streaming decompression and original raw SHA check."""
    directory = root/'staging'/row['instance_key']
    wire, raw = directory/'download.part', directory/'input.cnf'
    expected = int(row['raw_bytes'])
    maximum_wire = min(2*1024**3, 2*expected+64*1024**2)
    if shutil.disk_usage(root).free < 1024**3+maximum_wire+expected:
        raise OSError('insufficient disk for bounded staging and reserve')
    url = row['url']
    if not url.startswith('https://benchmark-database.de/file/'):
        raise ValueError('input URL outside frozen public source')
    wire_hash, total = hashlib.sha256(), 0
    request = urllib.request.Request(url, headers={'User-Agent': 'forcephase-R35-public-benchmark/1'})
    with urllib.request.urlopen(request, timeout=40) as response, wire.open('xb') as dest:
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            total += len(block)
            if total > maximum_wire:
                raise ValueError('bounded wire size exceeded')
            dest.write(block)
            wire_hash.update(block)
    with wire.open('rb') as stream:
        magic = stream.read(6)
    opener = gzip.open if magic.startswith(b'\x1f\x8b') else lzma.open if magic == b'\xfd7zXZ\x00' else open
    raw_hash, count = hashlib.sha256(), 0
    with opener(wire, 'rb') as stream, raw.open('xb') as dest:
        while True:
            block = stream.read(1 << 20)
            if not block:
                break
            count += len(block)
            if count > expected:
                raise ValueError('raw input exceeds frozen size')
            raw_hash.update(block)
            dest.write(block)
    if count != expected or raw_hash.hexdigest() != row['raw_sha256']:
        raise ValueError('original raw input SHA/size mismatch')
    raw.chmod(0o444)
    write(directory/'input_identity.json', {'row': row, 'raw_sha256': raw_hash.hexdigest(),
          'raw_bytes': count, 'wire_bytes': total, 'wire_sha256': wire_hash.hexdigest(),
          'verified_UTC': utc(), 'stat': stat_identity(raw)})
    wire.unlink()


def stat_identity(path):
    st = path.stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode]


def run_unit(root, spec, row, action, seed, affinity, identity):
    key = {'measurement_identity': identity, 'raw_sha256': row['raw_sha256'],
           'action': action, 'seed': seed}
    run_id = fingerprint(key)
    directory = root/'runs'/run_id
    destination = directory/'result.json'
    if destination.exists():
        existing = read(destination)
        if existing['measurement_key'] != key:
            raise ValueError('measurement identity collision')
        return existing
    directory.mkdir()  # An interrupted attempt is never silently overwritten/restarted.
    began_cpu, began = time.thread_time(), time.monotonic()
    started = utc()
    cnf = root/'staging'/row['instance_key']/'input.cnf'
    input_receipt = read(cnf.parent/'input_identity.json')
    if input_receipt['raw_sha256'] != row['raw_sha256'] or stat_identity(cnf) != input_receipt['stat']:
        raise ValueError('staged readonly input identity changed')
    proof, log = directory/'solver.lrat', directory/'solver.log'
    command = [spec['solver_path'], *ACTIONS[action], f'--seed={seed}', '--stats', '--lrat',
               '--binary=true', '-t', str(spec['wall_watchdog_s']), str(cnf), str(proof)]
    measured = bounded(spec, command, directory, 'solver', spec['cutoff_s'],
                       spec['wall_watchdog_s'], affinity)
    with log.open(errors='replace') as stream:
        tail = ''.join(deque(stream, maxlen=1000))
    (directory/'last1000.log').write_text(tail)
    answer = {10: 'SAT', 20: 'UNSAT'}.get(measured['exit_code'])
    if measured['stop_reason'] == 'CPU_LIMIT':
        status = 'CPU_TIMEOUT'
    elif measured['stop_reason'] == 'WALL_WATCHDOG':
        status = 'WALL_WATCHDOG'
    elif measured['stop_reason'] == 'OUTPUT_LIMIT':
        status = 'FILE_LIMIT'
    elif answer:
        status = answer if measured['cpu_s'] <= spec['cutoff_s'] else 'CPU_TIMEOUT'
    elif measured['exit_code'] == 0:
        status = 'UNKNOWN'
    elif measured['exit_code'] == -signal.SIGXFSZ:
        status = 'FILE_LIMIT'
    elif measured['exit_code'] == -signal.SIGXCPU:
        status = 'CPU_BACKSTOP_ERROR'
    else:
        status = 'ERROR'
    checker, verification = None, 'NOT_ANSWERED'
    if status in {'SAT', 'UNSAT'}:
        check_command = [sys.executable, str(Path(__file__).resolve()), 'check-model',
                         '--cnf', str(cnf), '--log', str(log)] if status == 'SAT' else [
                         spec['checker_path'], '--no-trim', str(cnf), str(proof)]
        checker = bounded(spec, check_command, directory, 'checker', spec['checker_cpu_s'],
                          spec['checker_wall_s'], affinity)
        with (directory/'checker.log').open(errors='replace') as stream:
            verified = any(line.strip() == 's VERIFIED' for line in stream)
        verification = ('VERIFIED_MODEL' if status == 'SAT' else 'VERIFIED_LRAT') if (
            checker['exit_code'] == 20 and verified and checker['stop_reason'] is None
        ) else 'INVALID_OR_RESOURCE_FAILED_CHECK'
    resolved = status in {'SAT', 'UNSAT'} and verification.startswith('VERIFIED_')
    valid = resolved or status in {'CPU_TIMEOUT', 'UNKNOWN'}
    proof_bytes = proof.stat().st_size if proof.exists() else 0
    proof_digest = sha(proof) if proof.exists() else None
    # All owned traces are hashed before reclamation; resource-failed traces stay recorded.
    if proof.exists():
        proof.unlink()
    log_digest = sha(log)
    with log.open('rb') as stream, gzip.open(directory/'solver.log.gz', 'wb') as compressed:
        shutil.copyfileobj(stream, compressed)
    log.unlink()
    result = {**measured, **parse_stats(tail), 'schema': 'forcephase.R35.run.v1',
        'measurement_key': key, 'run_id': run_id, 'physical_execution_id': str(uuid.uuid4()),
        'instance_key': row['instance_key'], 'ordinal': int(row['ordinal']),
        'action': action, 'seed': seed, 'started_UTC': started, 'finished_UTC': utc(),
        'status': status, 'answer_reported': answer, 'verification_status': verification,
        'checker': checker, 'resolved': resolved, 'valid_measurement': valid,
        'cutoff_s': spec['cutoff_s'], 'par2': measured['cpu_s'] if resolved else (
             2*spec['cutoff_s'] if valid else None),
        'conflicts_observation': 'termination' if measured['stop_reason'] else 'terminal',
        'proof_bytes': proof_bytes, 'proof_sha256': proof_digest,
        'log_sha256': log_digest, 'compressed_log_sha256': sha(directory/'solver.log.gz'),
        'tail_log_sha256': sha(directory/'last1000.log'),
        'unit_wall_s': time.monotonic()-began, 'unit_parent_CPU_s': time.thread_time()-began_cpu}
    result['physical_CPU_s'] = result['unit_parent_CPU_s']+measured['cpu_s']+(
        checker['cpu_s'] if checker else 0.)
    write(destination, result)
    return result


def available_cores(root, spec, running):
    free_disk = shutil.disk_usage(root).free
    # Running proof files already occupy disk; reserve their full remaining allowance,
    # plus each new task's full allowance before admitting it.
    owned_proofs = 0
    for p in (root/'runs').glob('*/solver.lrat'):
        try:
            owned_proofs += p.stat().st_size
        except FileNotFoundError:
            pass
    reserved_remaining = max(0, len(running)*spec['proof_limit_bytes']-owned_proofs)
    disk_slots = max(0, (free_disk-spec['disk_reserve_bytes']-reserved_remaining)//spec['proof_limit_bytes'])
    fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(fields['MemAvailable'].split()[0])*1024
    # Existing children consume memory already. Reserve their unconsumed AS allowance.
    active_rss = 0
    for active in (root/'runs').glob('*/*active.json'):
        try:
            state = read(active)
            status = Path(f'/proc/{state["pid"]}/status').read_text().splitlines()
            active_rss += sum(int(s.split()[1])*1024 for s in status if s.startswith('VmRSS:'))
        except FileNotFoundError:
            pass
    memory_remaining = max(0, len(running)*spec['memory_bytes']-active_rss)
    mem_slots = max(0, (available-spec['memory_reserve_bytes']-memory_remaining)//spec['memory_bytes'])
    used = set(running.values())
    unused = [cpu for cpu in spec['timing_cpus'] if cpu not in used]
    slots = min(len(unused), int(disk_slots), int(mem_slots))
    return unused[:slots], {'disk_free_bytes': free_disk, 'mem_available_bytes': available,
            'running_units': len(running), 'disk_new_slots': int(disk_slots),
            'memory_new_slots': int(mem_slots), 'idle_reason': 'proof_disk_or_memory_reservation'
            if slots < len(unused) else 'all_available_cores_admissible'}


def owner(root):
    began, cpu0 = time.monotonic(), physical_cpu()
    spec = read(root/'metadata/spec.json')
    lock = (root/'owner.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (root/'owner.json').exists():
        raise RuntimeError('existing owner receipt: inspect it; never auto-resubmit')
    if sha(root/'metadata/manifest.csv') != spec['manifest_sha256']:
        raise ValueError('frozen manifest identity mismatch')
    for relative, digest in spec['bound_file_hashes'].items():
        if sha(root/relative) != digest:
            raise ValueError('bound source/binary identity mismatch: '+relative)
    identity = fingerprint(spec)
    rows = list(csv.DictReader((root/'metadata/manifest.csv').open()))
    if len(rows) != 32 or len({r['instance_key'] for r in rows}) != 32:
        raise ValueError('R35 requires the frozen32 unique parents')
    for name in ['runs', 'staging', 'parents']:
        (root/name).mkdir(exist_ok=True)
    state = process_state(os.getpid())
    write(root/'owner.json', {'pid': os.getpid(), 'start_ticks': state['start_ticks'],
          'started_UTC': utc(), 'measurement_identity': identity, 'spec_sha256': sha(root/'metadata/spec.json'),
          'total_parents': 32, 'total_runs': 192, 'no_automatic_resubmission': True})
    results, parents, admission_stopped = [], [], False

    def snapshot(phase, **extra):
        write(root/'progress.json', {'observed_UTC': utc(), 'phase': phase,
            'completed_units': len(results), 'total_units': 192, 'completed_parents': len(parents),
            'valid_units': sum(r.get('valid_measurement', False) for r in results),
            'resolved_units': sum(r.get('resolved', False) for r in results),
            'physical_CPU_s': physical_cpu()-cpu0+spec['preparation_CPU_s'],
            'wall_s': time.monotonic()-began, 'measurement_identity': identity, **extra})

    def room_for_worst_case(units):
        used = physical_cpu()-cpu0+spec['preparation_CPU_s']+spec['unmetered_preparation_CPU_reserve_s']
        return used+units*(spec['cutoff_s']+spec['checker_cpu_s']+30) <= spec['CPU_ceiling_s']

    try:
        with ThreadPoolExecutor(max_workers=len(spec['timing_cpus'])) as pool:
            for row in rows:
                if not room_for_worst_case(1) or physical_cpu()-cpu0+spec['preparation_CPU_s']+(
                    spec['unmetered_preparation_CPU_reserve_s']+spec['staging_cpu_s']
                ) > spec['CPU_ceiling_s']:
                    admission_stopped = True
                    break
                directory = root/'staging'/row['instance_key']
                directory.mkdir()  # Staging is also a single preserved attempt.
                write(directory/'row.json', row)
                snapshot('staging', current_parent=int(row['ordinal']))
                stage = bounded(spec, [sys.executable, str(Path(__file__).resolve()), 'stage',
                    '--root', str(root), '--row', str(directory/'row.json')], directory, 'stage',
                    spec['staging_cpu_s'], spec['staging_wall_s'], spec['timing_cpus'][0])
                write(directory/'stage_result.json', stage)
                jobs = [(a, s) for a in ACTIONS for s in spec['solver_seeds']]
                jobs.sort(key=lambda pair: fingerprint({'order_seed': spec['order_seed'],
                         'instance_key': row['instance_key'], 'action': pair[0], 'seed': pair[1]}))
                if stage['exit_code'] != 0 or stage['stop_reason']:
                    parent = {'row': row, 'stage': stage, 'status': 'INPUT_PREPARATION_FAILED',
                              'units': [], 'finished_UTC': utc()}
                else:
                    running, per_parent = {}, []
                    while jobs or running:
                        cores, resources = available_cores(root, spec, running)
                        if jobs and not running and not cores:
                            raise RuntimeError('no resource-admissible slot; preserve staged input')
                        for core in cores:
                            if not jobs:
                                break
                            if not room_for_worst_case(len(running)+1):
                                admission_stopped = True
                                break
                            action, seed = jobs.pop(0)
                            future = pool.submit(run_unit, root, spec, row, action, seed, core, identity)
                            running[future] = core
                        snapshot('solving', current_parent=int(row['ordinal']), pending_in_parent=len(jobs),
                                 active_cores=list(running.values()), resource_admission=resources)
                        if not running:
                            break
                        done, _ = wait(running, timeout=15, return_when=FIRST_COMPLETED)
                        for future in done:
                            del running[future]
                            result = future.result()
                            results.append(result)
                            per_parent.append(result['run_id'])
                        if admission_stopped and not running:
                            break
                    parent = {'row': row, 'stage': stage, 'units': per_parent,
                              'status': 'COMPLETE' if len(per_parent) == 6 else 'BUDGET_INCOMPLETE',
                              'finished_UTC': utc()}
                write(root/'parents'/(row['ordinal'].zfill(2)+'.json'), parent)
                parents.append(parent)
                # Delete only this owner's raw/wire data; keep receipts and every failure.
                for name in ['input.cnf', 'download.part']:
                    (directory/name).unlink(missing_ok=True)
                snapshot('parent_complete', last_parent=int(row['ordinal']))
                if admission_stopped:
                    break
        complete = len(parents) == 32 and len(results) == 192
        write(root/'completion.json', {'finished_UTC': utc(), 'complete_matrix': complete,
            'parents_attempted': len(parents), 'completed_units': len(results),
            'admission_stopped_for_budget': admission_stopped, 'physical_CPU_s': physical_cpu()-cpu0,
            'preparation_CPU_s': spec['preparation_CPU_s'], 'wall_s': time.monotonic()-began,
            'measurement_identity': identity, 'incomplete_is_not_final_analysis': not complete})
        snapshot('complete' if complete else 'terminal_incomplete')
    except BaseException:
        write(root/'failure.json', {'UTC': utc(), 'traceback': traceback.format_exc(),
              'physical_CPU_s': physical_cpu()-cpu0, 'wall_s': time.monotonic()-began,
              'completed_units': len(results), 'measurement_identity': identity})
        snapshot('failed')
        raise


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run'); run.add_argument('--root', type=Path, required=True)
    stage = sub.add_parser('stage'); stage.add_argument('--root', type=Path, required=True)
    stage.add_argument('--row', type=Path, required=True)
    check = sub.add_parser('check-model'); check.add_argument('--cnf', required=True)
    check.add_argument('--log', required=True)
    args = p.parse_args()
    if args.action == 'run':
        owner(args.root.resolve())
    elif args.action == 'stage':
        stage_child(args.root.resolve(), read(args.row))
    elif args.action == 'check-model':
        good = check_model(args.cnf, args.log)
        print('s VERIFIED' if good else 's INVALID', flush=True)
        sys.exit(20 if good else 1)


if __name__ == '__main__':
    main()
