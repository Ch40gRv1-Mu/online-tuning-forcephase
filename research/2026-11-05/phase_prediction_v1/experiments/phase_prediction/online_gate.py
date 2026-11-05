"""New-host deterministic no-op, action semantics and common-prefix gate.

Uses only synthetic formulas. Numeric search counters and prefix state digests
are compared; time/rate fields are deliberately excluded from equality checks.
The digest is a diagnostic fingerprint of the documented state, not a complete
serialized solver checkpoint or a mathematical proof of state equality.
"""
import argparse
import json
import random
import re
from pathlib import Path

import run_pilot as common

ACTION_CODES = {'D': 0, 'Fplus': 3, 'Fminus': 1}
ACTION_NAMES = {'D': 'NATIVE', 'Fplus': 'POSITIVE', 'Fminus': 'NEGATIVE'}


def online_flags(action):
    return ['--phase=1', '--forcephase=0', '--fpc=3', '--fpctrack=0',
            '--fpca0=0', f'--fpca1={ACTION_CODES[action]}', '--fpcinit=0',
            '--fpcat=1000', '--fpcperiod=0', '--fpcmaxsw=1', '--fpcrlim=0',
            '--fpcwin=2000000000']


def telemetry(path):
    with path.open() as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if not rows or rows[0].get('schema') != 2 or rows[0].get('controller') != 'v2':
        raise ValueError('unsupported telemetry header')
    if not any(r['type'] == 'final' for r in rows):
        raise ValueError('incomplete telemetry')
    return rows


def first_checkpoint(rows, K=1000):
    return next((r for r in rows if r['type'] == 'checkpoint' and
                 r['crossed'][0] <= K <= r['crossed'][1]), None)


def check_prefix(records):
    """Require all three observations before their continuation actions."""
    checkpoints = {a: first_checkpoint(rs) for a, rs in records.items()}
    reached = [c is not None for c in checkpoints.values()]
    if any(reached) and not all(reached):
        raise ValueError('continuations disagree on prefix reachability')
    if not any(reached):
        for rows in records.values():
            if any(r['type'] == 'switch' for r in rows):
                raise ValueError('switch without prefix observation')
        return {'reached': False}
    base = checkpoints['D']
    numeric = {k: v for k, v in base['f'].items() if k not in
               {'r_time', 'c_conf_per_sec', 'w_conf_per_sec'}}
    for action, rows in records.items():
        cp = checkpoints[action]
        if (cp['digest'], cp['conflicts'], cp['decisions']) != (
                base['digest'], base['conflicts'], base['decisions']):
            raise ValueError('prefix state fingerprint mismatch')
        if {k: v for k, v in cp['f'].items() if k in numeric} != numeric:
            raise ValueError('pre-action numeric observation mismatch')
        if cp['action'] != 'NATIVE':
            raise ValueError('prefix is not the declared common D action')
        switches = [r for r in rows if r['type'] == 'switch']
        if len(switches) != 1:
            raise ValueError('expected exactly one scheduled continuation action')
        sw = switches[0]
        if rows.index(sw) <= rows.index(cp) or sw['conflicts'] != cp['conflicts']:
            raise ValueError('action precedes observation or uses another hook')
        if sw['action'] != ACTION_NAMES[action] or sw['requested'] != 1000:
            raise ValueError('wrong continuation action')
    return {'reached': True, 'conflicts': base['conflicts'], 'digest': base['digest'],
            'features': numeric, 'prefix_cpu_s_D_diagnostic': base['time']}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    a = p.parse_args(); root = a.root.resolve(); work = root/'data/online-gate'
    work.mkdir(parents=True, exist_ok=True)
    inputs = []
    for holes in (6, 8):
        var = lambda x, y: x*holes+y+1
        clauses = [[var(x,y) for y in range(holes)] for x in range(holes+1)]
        clauses += [[-var(x,y),-var(z,y)] for y in range(holes)
                    for x in range(holes+1) for z in range(x+1,holes+1)]
        path = work/f'php{holes}.cnf'; nv = holes*(holes+1)
        path.write_text(f'p cnf {nv} {len(clauses)}\n'+''.join(
            ' '.join(map(str,c))+' 0\n' for c in clauses))
        inputs.append((path,nv))
    rng = random.Random(20261104); path = work/'random3.cnf'; nv=200; nc=852
    path.write_text(f'p cnf {nv} {nc}\n'+''.join(' '.join(str(v if rng.random()<.5 else -v)
        for v in rng.sample(range(1,nv+1),3))+' 0\n' for _ in range(nc)))
    inputs.append((path,nv)); checks=[]; total_cpu=0.; reached=0
    def run(label,path,nv,binary,flags,log_telemetry=False):
        nonlocal total_cpu
        proof=work/(label+'.lrat'); tel=work/(label+'.jsonl')
        cmd=[str(binary),*flags,'--seed=0','--stats','--lrat','--binary=false',
             '-c','2500','-t','30',str(path),str(proof)]
        if log_telemetry:cmd=['env',f'FPC_LOG={tel}',*cmd]
        rec,text=common.child(cmd,work/(label+'.log'),30,4)
        total_cpu+=rec['cpu_s']
        assert rec['exit_code'] in (0,10,20),rec
        if rec['exit_code']==10:assert common.check_model(path,text,nv)
        if rec['exit_code']==20:
            ck,ct=common.child([root/'bin/lrat-check',path,proof],work/(label+'.check.log'),30,4)
            total_cpu+=ck['cpu_s']
            assert ck['exit_code']==0 and re.search(r'^[cs] VERIFIED',ct,re.M)
        proof.unlink(missing_ok=True)
        counters={k:rec.get(k) for k in ('exit_code','conflicts','decisions','propagations','restarts','rephased')}
        return counters,telemetry(tel) if log_telemetry else None
    for path,nv in inputs:
        # Check all three fixed-action mappings against the pristine binary.
        for action,flags in common.FLAGS.items():
            upstream,_=run(path.stem+action+'up',path,nv,root/'bin/cadical',flags)
            patched,_=run(path.stem+action+'off',path,nv,root/'bin/cadical-fpc2',[*flags,'--fpc=0'])
            observed,_=run(path.stem+action+'tel',path,nv,root/'bin/cadical-fpc2',[*flags,'--fpc=1'],True)
            fixed,_=run(path.stem+action+'fixed',path,nv,root/'bin/cadical-fpc2',[
                '--phase=1','--forcephase=0','--fpc=2','--fpctrack=0',f'--fpca0={ACTION_CODES[action]}'],True)
            assert upstream==patched==observed==fixed,(path,action,upstream,patched,observed,fixed)
            checks.append({'input':path.stem,'check':'no_op_and_fixed_'+action,'passed':True})
        streams={}
        for action in ACTION_CODES:
            _,streams[action]=run(path.stem+action+'schedule',path,nv,root/'bin/cadical-fpc2',online_flags(action),True)
        prefix=check_prefix(streams); reached+=prefix['reached']
        checks.append({'input':path.stem,'check':'three_continuation_prefix','passed':True,
                       'reached':prefix['reached'],'conflicts':prefix.get('conflicts')})
    assert reached,'gate did not exercise the K=1000 checkpoint'
    result={'status':'PASS','tests':checks,'cpu_s':total_cpu,'checkpoint_inputs':reached,
            'binary_sha256':common.sha(root/'bin/cadical-fpc2'),
            'controller_sha256':common.sha(root/'src/fpcontrol.cpp'),
            'gate_sha256':common.sha(Path(__file__)),
            'scope':'Synthetic deterministic conflict-limited engineering checks; no performance claim.'}
    common.write(root/'results/online_gate.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
