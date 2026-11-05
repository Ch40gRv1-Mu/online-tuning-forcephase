"""Prespecified original-label structure check; fit only, no new SAT runs."""
import csv
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path

FEATURES = ['g_cycle_excess_per_incidence', 'g_leaf_variable_fraction', 'g_gate_motif_fraction']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + j - 1) / 2 + 1
        for k in range(i, j):
            result[order[k]] = rank
        i = j
    return result


def spearman(x, y):
    if len(x) != len(y) or len(x) < 3:
        return None
    a, b = ranks(x), ranks(y)
    am, bm = statistics.mean(a), statistics.mean(b)
    aa, bb = sum((v-am)**2 for v in a), sum((v-bm)**2 for v in b)
    return sum((u-am)*(v-bm) for u, v in zip(a, b))/math.sqrt(aa*bb) if aa and bb else None


def main():
    start = time.process_time()
    root = Path(__file__).resolve().parents[2]
    base = root/'results/phase_prediction_v1'
    cohort_path = base/'pilot_frozen.csv'
    with cohort_path.open() as f:
        cohort = list(csv.DictReader(f))
    ids = {r['hash'] for r in cohort}
    if len(ids) != 48 or any(r['role'] != 'development_fit' for r in cohort):
        raise ValueError('not the fixed48 fit panel')
    with (base/'test_candidates.csv').open() as f:
        protected = {r['hash'] for r in csv.DictReader(f)}
    if ids & protected:
        raise ValueError('protected identifier in development')
    with (base/'professor_pairs.csv').open() as f:
        original = {r['hash']: r for r in csv.DictReader(f) if r['hash'] in ids}
    feature_paths = list((base/'server_p1/results').glob('*.features.json'))
    features = {json.loads(p.read_text())['hash']: json.loads(p.read_text())['features'] for p in feature_paths}
    if set(original) != ids or set(features) != ids:
        raise ValueError('incomplete feature/original-label join')
    counts = {'both_solved_positive_time': 0, 'one_solved': 0, 'neither_solved': 0,
              'both_solved_invalid_time': 0}
    complete = []
    for h in sorted(ids):
        row = original[h]
        solved = [row[m+'_result'] in ('SAT', 'UNSAT') for m in ('false', 'true')]
        if all(solved):
            if row['false_result'] != row['true_result']:
                raise ValueError('contradictory original answers')
            a, b = float(row['false_wall_s']), float(row['true_wall_s'])
            if a > 0 and b > 0 and math.isfinite(a) and math.isfinite(b):
                complete.append((h, math.log2(a/b)))
                counts['both_solved_positive_time'] += 1
            else:
                counts['both_solved_invalid_time'] += 1
        elif any(solved):
            counts['one_solved'] += 1
        else:
            counts['neither_solved'] += 1
    # Numerical identities required by the executed statistic, not a pilot run.
    assert abs(spearman([1, 2, 3], [3, 2, 1]) + 1) < 1e-12
    assert spearman([0, 0, 0], [1, 2, 3]) is None
    assert ranks([2, 2, 4]) == [1.5, 1.5, 3.]
    findings = []
    for name in FEATURES:
        pairs = [(features[h].get(name), y) for h, y in complete
                 if isinstance(features[h].get(name), (int, float)) and math.isfinite(features[h][name])]
        x, y = [p[0] for p in pairs], [p[1] for p in pairs]
        rho = spearman(x, y)
        draws = []
        if rho is not None:
            rng = random.Random(20261105)
            for _ in range(2000):
                idx = [rng.randrange(len(pairs)) for _ in pairs]
                value = spearman([x[i] for i in idx], [y[i] for i in idx])
                if value is not None:
                    draws.append(value)
        draws.sort()
        interval = [draws[len(draws)*25//1000], draws[len(draws)*975//1000]] if draws else None
        findings.append({'feature': name, 'all_fit_parents': 48, 'effective_both_solved_n': len(pairs),
                         'missing_features_in_both_solved': len(complete)-len(pairs),
                         'spearman_rho': rho, 'descriptive_parent_bootstrap_95pct': interval,
                         'valid_bootstrap_draws': len(draws),
                         'constant_bootstrap_draws': 2000-len(draws) if rho is not None else None,
                         'interval_stable_draw_count': len(draws) >= 1800,
                         'undefined_reason': 'insufficient_or_zero_variance' if rho is None else None})
    report = {'target': 'original labels only: log2(false_wall/true_wall), positive means original true faster',
              'scope': 'Exploratory48fit conditional-on-both-solved subset; no classifier or predictive confirmation.',
              'protocol_sha256': sha(root/'docs/PROFESSOR_STRUCTURE_DIRECT_CHECK_20261105.md'),
              'source_sha256': sha(Path(__file__)), 'cohort_sha256': sha(cohort_path),
              'original_table_sha256': sha(base/'professor_pairs.csv'),
              'feature_receipt_sha256': {p.name: sha(p) for p in feature_paths},
              'coverage': counts, 'strict_incidence_forests': sum(features[h]['g_cycle_excess'] == 0 for h in ids),
              'findings': findings, 'formula_depth_tested': False, 'gate_cases_used': 0,
              'protected_final_cases_used': 0, 'new_solver_runs': 0,
              'new_D_F_policy_rewards': 0,
              'caveats': ['Already seen development data; three descriptive comparisons, no multiplicity correction.',
                          'Censored parents retained in coverage, not imputed as exact runtime.',
                          'Original solver/version/phase semantics remain unverified.',
                          'Association is not an action selector, net benefit, or CaDiCaL transfer.']}
    out = base/'professor_structure_direct'
    out.mkdir(exist_ok=False)
    (out/'summary.json').write_text(json.dumps(report, indent=2))
    lines = ['# Direct structure check using original professor labels', '',
             f'Fixed48fit: {counts}. No new SAT solving. Response is log2(false/true wall time).', '',
             '| Feature | Effective n | Spearman rho | Descriptive95% interval |',
             '|---|---:|---:|---|']
    for r in findings:
        lines.append(f"| {r['feature']} | {r['effective_both_solved_n']} | {r['spearman_rho']} | {r['descriptive_parent_bootstrap_95pct']} |")
    lines += ['', 'All48 are non-forest incidence graphs; strict forest membership cannot distinguish this panel.',
              'Formula depth was not measured. These conditional, already-seen data do not establish prediction or net savings.',
              'All three associations and coverage are retained; no timeout imputation, gate/test feedback or new policy reward.']
    (out/'RESULT.md').write_text('\n'.join(lines)+'\n')
    cost = {'local_process_cpu_s': time.process_time()-start,
            'scope': 'Actual local descriptive analysis; included in existing new engineering reserve; no solver expense.'}
    (out/'cost.json').write_text(json.dumps(cost, indent=2))
    print(json.dumps({'coverage': counts, 'findings': findings, 'local_cpu_s': cost['local_process_cpu_s'],
                      'new_solver_runs': 0}))


if __name__ == '__main__':
    main()
