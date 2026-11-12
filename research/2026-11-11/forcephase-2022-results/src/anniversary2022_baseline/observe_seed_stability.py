"""Read-only R35 recovery observation; never launches or mutates remote jobs."""
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/anniversary2022_baseline/solver_seed_stability_R35_20261111'
REMOTE = r'''
import collections, json, os, pathlib, shutil, time
r = pathlib.Path('/home/vipuser/forcephase_solver_seed_stability_20261111')
def read(path):
    return json.loads(path.read_text()) if path.exists() else None
o = read(r/'owner.json')
proc = pathlib.Path('/proc')/str(o['pid'])
owner_stat = (proc/'stat').read_text() if proc.exists() else None
owner_fields = owner_stat.rsplit(')',1)[1].split() if owner_stat else None
rs = [read(f) for f in (r/'runs').glob('*/result.json')]
invalid = []
for unit in rs:
    if unit['valid_measurement']:
        continue
    log = r/'runs'/unit['run_id']/'last1000.log'
    lines = log.read_text(errors='replace').splitlines() if log.exists() else []
    hints = [line for line in lines if any(word in line.lower() for word in (
        'memory', 'error', 'fatal', 'allocate', 'bad_alloc', 'terminate', 'abort', 'failed', 'limit'))]
    invalid.append({'run_id':unit['run_id'], 'ordinal':unit['ordinal'],
        'status':unit['status'], 'exit_code':unit['exit_code'], 'CPU_s':unit['cpu_s'],
        'maxrss_kib':unit['maxrss_kib'], 'proof_bytes':unit['proof_bytes'],
        'verification_status':unit['verification_status'], 'diagnostic_lines':hints[-10:]})
active = []
active_paths = [*((r/'runs').glob('*/*active.json')),
                *((r/'staging').glob('*/stage_active.json'))]
for f in active_paths:
    try:
        d = read(f)
        q = pathlib.Path('/proc')/str(d['pid'])
        fields = (q/'stat').read_text().rsplit(')',1)[1].split()
        active.append({'pid': d['pid'], 'command': d['command'],
            'kind': 'preparation' if 'staging' in f.parts else 'solver_or_checker',
            'current_CPU_s': (int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'),
            'live_start_ticks': fields[19], 'receipt_start_ticks': d['start_ticks'],
            'same_physical_process': fields[19] == d['start_ticks']})
    except FileNotFoundError:
        pass
groups = []
for path in sorted((r/'parents').glob('*.json')):
    p = read(path)
    units = [read(r/'runs'/k/'result.json') for k in p['units']]
    stage_log = r/'staging'/p['row']['instance_key']/'stage.log'
    failed_stage = p['stage']['exit_code'] != 0 or p['stage']['stop_reason'] is not None
    groups.append({'ordinal': int(p['row']['ordinal']), 'instance_key':p['row']['instance_key'],
        'parent_status':p['status'], 'units':len(units),
        'all_valid':len(units) == 6 and all(u['valid_measurement'] for u in units),
        'stage_failure_log_tail':stage_log.read_text(errors='replace').splitlines()[-25:] if failed_stage and stage_log.exists() else [],
        'solver_CPU_s':sum(u['cpu_s'] for u in units),
        'checker_CPU_s':sum(u['checker']['cpu_s'] for u in units if u['checker']),
        'finished_UTC':p['finished_UTC'], 'stage':p['stage']})
staging_files = []
for name in ('download.part', 'input.cnf'):
    for path in (r/'staging').glob('*/'+name):
        try:
            staging_files.append({'name':name, 'bytes':path.stat().st_size,
                                  'instance_key':path.parent.name})
        except FileNotFoundError:
            pass
print(json.dumps({'observed_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
    'owner':o, 'owner_process_cmdline':(proc/'cmdline').read_bytes().replace(bytes([0]),b' ').decode() if proc.exists() else None,
    'owner_process_stat':owner_stat,
    'same_owner_process': bool(owner_fields and owner_fields[19] == o['start_ticks']),
    'progress':read(r/'progress.json'), 'solver_attempt_directories':len(list((r/'runs').glob('*'))),
    'status_counts':dict(collections.Counter(z['status']+':'+z['verification_status'] for z in rs)),
    'invalid_units':invalid,
    'timeouts':[{'run_id':z['run_id'], 'CPU_s':z['cpu_s'], 'stop_reason':z['stop_reason'],
        'exit':z['exit_code'], 'valid':z['valid_measurement'], 'par2':z['par2']} for z in rs if z['status']=='CPU_TIMEOUT'],
    'active_children':active, 'completed_parent_resource_totals':groups,
    'staging_files':staging_files,
    'disk_free_bytes':shutil.disk_usage(r).free,
    'failure':read(r/'failure.json'), 'completion':read(r/'completion.json'),
    'scientific_preference_feedback_read':False}))
'''


def main():
    command = ['ssh', '-S', '/private/tmp/forcephase-anniversary-new-20261111.sock',
        '-p', '20728', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile='+str(ROOT/'data/anniversary2022_baseline/known_hosts_20261111'),
        'vipuser@223.109.239.11', 'python3 -']
    response = subprocess.run(command, input=REMOTE, text=True, capture_output=True, timeout=25)
    if response.returncode:
        raise RuntimeError('Observation failed; remote job state is unknown, never relaunch: '+response.stderr.strip())
    observation = json.loads(response.stdout)
    observation['observer_source'] = str(Path(__file__).relative_to(ROOT))
    path = OUT/'latest_observation.json'
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(observation,indent=2,sort_keys=True)+'\n')
    temp.replace(path)
    p = observation['progress']
    print(json.dumps({'observed_UTC':observation['observed_UTC'],
        'same_owner_live':observation['same_owner_process'],
        'completed_units':p['completed_units'], 'valid_units':p['valid_units'],
        'completed_parents':p['completed_parents'], 'phase':p['phase'],
        'parents_with_all_six_units':sum(g['units']==6 for g in observation['completed_parent_resource_totals']),
        'input_preparation_failures':sum(g['parent_status']=='INPUT_PREPARATION_FAILED' for g in observation['completed_parent_resource_totals']),
        'active_children':len(observation['active_children']),
        'active_preparation_children':sum(a['kind']=='preparation' for a in observation['active_children']),
        'active_CPU_sum_s':sum(a['current_CPU_s'] for a in observation['active_children']),
        'status_counts':observation['status_counts'], 'timeout_units':len(observation['timeouts']),
        'invalid_exit_codes':sorted(set(u['exit_code'] for u in observation['invalid_units'])),
        'disk_free_GiB':observation['disk_free_bytes']/1024**3,
        'staging_file_bytes':{a['name']:a['bytes'] for a in observation['staging_files']},
        'failure':observation['failure'], 'completion':observation['completion']}, indent=2))


if __name__ == '__main__':
    main()
