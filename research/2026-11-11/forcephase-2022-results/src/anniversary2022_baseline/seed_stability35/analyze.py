"""Whole-panel R35 diagnostic only. Never fit or select a policy from partial runs."""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import random
import statistics
import time

from helpers import ACTIONS, fingerprint, read, sha, write


def ranks(values):
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result = [0.]*len(values)
    first = 0
    while first < len(ordered):
        end = first+1
        while end < len(ordered) and values[ordered[end]] == values[ordered[first]]:
            end += 1
        for i in ordered[first:end]:
            result[i] = (first+end-1)/2
        first = end
    return result


def correlation(a, b):
    if len(a) < 3:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    var = sum((x-ma)**2 for x in a)*sum((x-mb)**2 for x in b)
    return sum((x-ma)*(y-mb) for x, y in zip(a, b))/math.sqrt(var) if var > 0 else None


def estimate(rows, statistic):
    if not rows:
        return {'n_parents': 0, 'point': None, 'nominal_parent_bootstrap_95': None}
    rng = random.Random(2026111135)
    samples = []
    for _ in range(2000):
        point = statistic([rows[rng.randrange(len(rows))] for _ in rows])
        if point is not None and math.isfinite(point):
            samples.append(point)
    samples.sort()
    return {'n_parents': len(rows), 'point': statistic(rows),
            'nominal_parent_bootstrap_95': [samples[int(.025*(len(samples)-1))],
                                          samples[int(.975*(len(samples)-1))]] if samples else None,
            'valid_bootstraps': len(samples), 'bootstrap_repetitions': 2000}


def winner(matrix, seed):
    runs = [matrix[(a, seed)] for a in ACTIONS]
    if not all(r['valid_measurement'] for r in runs):
        return None
    ordered = sorted(runs, key=lambda r: r['par2'])
    fastest, second = ordered[:2]
    if fastest['resolved'] and min(second['par2'], 600)-fastest['par2'] > max(.02, .1*fastest['par2']):
        return fastest['action']
    return None


def preference(d, f):
    if not d['valid_measurement'] or not f['valid_measurement']:
        return None
    if not d['resolved'] and not f['resolved']:
        return None
    faster, slower = sorted((d, f), key=lambda r: r['par2'])
    if min(slower['par2'], 600)-faster['par2'] <= max(.02, .1*faster['par2']):
        return None
    return 'D' if faster['action'] == 'D' else 'F'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    args = p.parse_args()
    root = args.root.resolve()
    began, cpu0 = time.monotonic(), time.process_time()
    spec, complete = read(root/'metadata/spec.json'), read(root/'completion.json')
    if complete['parents_attempted'] != 32:
        raise ValueError('primary diagnostic requires all32 frozen parents attempted')
    if sha(root/'metadata/manifest.csv') != spec['manifest_sha256']:
        raise ValueError('manifest changed')
    identity = fingerprint(spec)
    rows = list(csv.DictReader((root/'metadata/manifest.csv').open()))
    matrices = {row['instance_key']: {} for row in rows}
    invalid = Counter()
    for path in sorted((root/'runs').glob('*/result.json')):
        r = read(path)
        row = next(row for row in rows if row['instance_key'] == r['instance_key'])
        key = {'measurement_identity': identity, 'raw_sha256': row['raw_sha256'],
               'action': r['action'], 'seed': r['seed']}
        if r['measurement_key'] != key or fingerprint(key) != r['run_id'] or path.parent.name != r['run_id']:
            raise ValueError('physical run identity mismatch')
        group = matrices[r['instance_key']]
        unit = (r['action'], r['seed'])
        if unit in group or unit[0] not in ACTIONS or unit[1] not in (0, 1):
            raise ValueError('duplicate or unapproved unit')
        if r['valid_measurement']:
            if r['resolved']:
                expected_verify = 'VERIFIED_MODEL' if r['status'] == 'SAT' else 'VERIFIED_LRAT'
                if r['status'] not in {'SAT', 'UNSAT'} or r['verification_status'] != expected_verify:
                    raise ValueError('unverified answer marked resolved')
                checker = r['checker']
                if checker['exit_code'] != 20 or checker['stop_reason'] is not None or r['cpu_s'] > 600:
                    raise ValueError('invalid proof/model/cutoff success')
                with (path.parent/'checker.log').open(errors='replace') as stream:
                    if not any(line.strip() == 's VERIFIED' for line in stream):
                        raise ValueError('checker success line missing')
                if r['par2'] != r['cpu_s']:
                    raise ValueError('inconsistent solved PAR2')
            elif r['status'] not in {'CPU_TIMEOUT', 'UNKNOWN'} or r['par2'] != 1200:
                raise ValueError('resource failure recoded as timeout')
        else:
            invalid[r['status']+':'+r['verification_status']] += 1
        for filename, digest in [('solver.log.gz', r['compressed_log_sha256']),
                                 ('last1000.log', r['tail_log_sha256'])]:
            if sha(path.parent/filename) != digest:
                raise ValueError('receipt/log identity mismatch')
        group[unit] = r
    all_units = [r for m in matrices.values() for r in m.values()]
    full = [m for m in matrices.values() if len(m) == 6 and all(r['valid_measurement'] for r in m.values())]
    if any(len({r['answer_reported'] for r in m.values() if r['resolved']}) > 1 for m in matrices.values()):
        raise ValueError('contradictory verified SAT/UNSAT answers')
    wins = {s: [winner(m, s) for m in full] for s in (0, 1)}
    clear_pairs = [(a, b) for a, b in zip(wins[0], wins[1]) if a is not None and b is not None]
    result = {'schema': 'R35.stability.v1', 'population': 'Fixed32 of retained4719 Anniversary2022 development',
        'independent_confirmation': False, 'new_policy_fits': 0, 'measurement_identity': identity,
        'parents': 32, 'actual_completed_solver_units': len(all_units), 'valid_full_matrices': len(full),
        'missing_units': 192-len(all_units), 'invalid_units': dict(invalid),
        'clear_seed0': sum(w is not None for w in wins[0]),
        'clear_seed1': sum(w is not None for w in wins[1]), 'clear_both': len(clear_pairs),
        'clear_winner_agreement': estimate(clear_pairs, lambda pairs: statistics.mean(a == b for a, b in pairs)),
        'winner_table': dict(Counter(str(a)+'->'+str(b) for a, b in clear_pairs)),
        'all_censored_per_seed': {str(s): sum(all(not m[(a, s)]['resolved'] for a in ACTIONS) for m in full)
                                  for s in (0, 1)},
        'bounded_clear_estimate_sufficient': len(clear_pairs) >= 8,
        'censoring': 'Unsolved valid unit PAR2=1200 at T600; ratios use censored PAR2, not latent runtimes. Near-ties/all-censored are never winner labels.',
        'pairwise': {}, 'controls': {}, 'seed0_oracle_replay': {},
        'physical_solver_CPU_s': sum(r['cpu_s'] for r in all_units),
        'physical_checker_CPU_s': sum(r['checker']['cpu_s'] for r in all_units if r['checker']),
        'owner_completion': complete}
    for action in ['Fplus', 'Fminus']:
        valid_pairs = []
        clear = []
        work = []
        for m in matrices.values():
            units = [('D', 0), (action, 0), ('D', 1), (action, 1)]
            if not all(k in m and m[k]['valid_measurement'] for k in units):
                continue
            d0, f0, d1, f1 = [m[k] for k in units]
            p0, p1 = preference(d0, f0), preference(d1, f1)
            if p0 is not None and p1 is not None:
                clear.append((p0, p1))
            # Both timeouts contribute coverage but no artificial ratio agreement.
            if (d0['resolved'] or f0['resolved']) and (d1['resolved'] or f1['resolved']):
                valid_pairs.append((math.log(max(f0['par2'], 1e-6)/max(d0['par2'], 1e-6)),
                                    math.log(max(f1['par2'], 1e-6)/max(d1['par2'], 1e-6))))
                if all(r['conflicts'] is not None for r in (d0, f0, d1, f1)):
                    work.append((math.log((1+f0['conflicts'])/(1+d0['conflicts'])),
                                 math.log((1+f1['conflicts'])/(1+d1['conflicts']))))
        pearson = lambda pairs: correlation([p[0] for p in pairs], [p[1] for p in pairs])
        spearman = lambda pairs: correlation(ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs]))
        result['pairwise'][action+'/D'] = {
            'clear_agreement': estimate(clear, lambda pairs: statistics.mean(a == b for a, b in pairs)),
            'logPAR2_ratio_Pearson': estimate(valid_pairs, pearson),
            'logPAR2_ratio_Spearman': estimate(valid_pairs, spearman),
            'log1p_conflicts_ratio_Pearson': estimate(work, pearson),
            'ratios_exclude_double_censored_per_seed': True}
    for seed in (0, 1):
        costs = {a: sum(m[(a, seed)]['par2'] for m in full) for a in ACTIONS}
        oracle = sum(min(m[(a, seed)]['par2'] for a in ACTIONS) for m in full)
        result['controls'][str(seed)] = {'N': len(full), 'sum_PAR2': costs, 'oracle_sum_PAR2': oracle,
            'solved': {a: sum(m[(a, seed)]['resolved'] for m in full) for a in ACTIONS},
            'oracle_gain_over_D_pct': 100*(costs['D']-oracle)/costs['D'] if costs['D'] else None}
    replay = []
    for m in full:
        # Frozen action order resolves exact seed0 ties; all seed0 timeouts route D.
        selected = min(ACTIONS, key=lambda a: m[(a, 0)]['par2'])
        replay.append((m[('D', 1)]['par2'], m[(selected, 1)]['par2'],
                       min(m[(a, 1)]['par2'] for a in ACTIONS)))
    result['seed0_oracle_replay'] = {
        'diagnostic_only_not_deployable': True,
        'gain_over_seed1_D_pct': estimate(replay, lambda v: 100*(sum(r[0]-r[1] for r in v))/sum(r[0] for r in v)),
        'seed1_oracle_sum_PAR2': sum(r[2] for r in replay),
        'replayed_sum_PAR2': sum(r[1] for r in replay)}
    result.update(analysis_CPU_s=time.process_time()-cpu0, analysis_wall_s=time.monotonic()-began)
    write(root/'analysis.json', result)
    print(root/'analysis.json')


if __name__ == '__main__':
    main()
