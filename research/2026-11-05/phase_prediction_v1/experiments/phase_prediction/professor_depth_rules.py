"""Fit the two frozen structural stumps on original-table development labels."""
import argparse
import csv
import hashlib
import json
import math
import random
import time
from pathlib import Path
from policy import STATIC

GEOMETRY = ['d_leaf_peeling_rounds', 'd_core_vertex_fraction',
            'd_core_edge_fraction', 'd_incidence_geometry_exact']
GATES = ['d_gate_condensation_depth', 'd_gate_cyclic_variable_fraction',
         'd_gate_variable_coverage', 'd_gate_output_positive_fraction', 'd_gate_depth_exact']


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def label(row):
    a, b = float(row['false_wall_s']), float(row['true_wall_s'])
    if not all(math.isfinite(x) and x > 0 for x in (a, b)):
        return None, 0., 'invalid_time'
    sa, sb = (row[m+'_result'] in ('SAT', 'UNSAT') for m in ('false', 'true'))
    if sa and sb:
        if row['false_result'] != row['true_result']:
            raise ValueError('contradictory original answers')
        if abs(a-b) < max(.02, .1*min(a, b)):
            return None, 0., 'near_tie'
        return ('false' if a < b else 'true'), max(.1, min(10., abs(math.log2(a/b)))), 'both_solved_clear'
    if sa != sb:
        solved, censored = (a, b) if sa else (b, a)
        if row[('true' if sa else 'false')+'_result'] != 'TIMEOUT':
            return None, 0., 'other_failure'
        if censored < 2*solved:
            return None, 0., 'one_solved_weak_bound'
        return ('false' if sa else 'true'), min(10., math.log2(censored/solved)), 'one_solved_supported_bound'
    return None, 0., 'neither_solved'


def quantile(values, q):
    values = sorted(values)
    pos = (len(values)-1)*q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def predict(model, features):
    if 'action' in model:
        return model['action']
    v = features.get(model['feature'])
    side = model['missing'] if v is None else ('left' if v <= model['threshold'] else 'right')
    return model[side]['action']


def error(rows, action):
    return sum(r['weight'] for r in rows if r['label'] is not None and r['label'] != action)


def best_action(rows):
    return min(('false', 'true'), key=lambda a: (error(rows, a), a))


def fit(rows, names):
    base_action = best_action(rows)
    base_error = error(rows, base_action)
    winner, winner_error = {'action': base_action}, base_error
    for name in sorted(names):
        values = [r['features'][name] for r in rows if r['features'].get(name) is not None]
        if not values:
            continue
        for threshold in sorted({quantile(values, k/8) for k in range(1, 8)}):
            for missing in ('left', 'right'):
                model = {'feature': name, 'threshold': threshold, 'missing': missing}
                left, right = [], []
                for r in rows:
                    v = r['features'].get(name)
                    side = missing if v is None else ('left' if v <= threshold else 'right')
                    (left if side == 'left' else right).append(r)
                if min(len(left), len(right)) < 12 or min(sum(r['label'] is not None for r in x) for x in (left, right)) < 4:
                    continue
                la, ra = best_action(left), best_action(right)
                loss = error(left, la)+error(right, ra)
                if loss < winner_error-1e-12 and loss <= .99*base_error:
                    winner = {**model, 'left': {'action': la}, 'right': {'action': ra}}
                    winner_error = loss
    return {'model': winner, 'fit_weighted_error': winner_error,
            'fit_constant_weighted_error': base_error, 'allowed_features': sorted(names)}


def metrics(rows, preds):
    labelled = [i for i, r in enumerate(rows) if r['label'] is not None]
    total_weight = sum(rows[i]['weight'] for i in labelled)
    return {'all_parents': len(rows), 'labelled_parents': len(labelled),
            'labelled_coverage': len(labelled)/len(rows),
            'correct': sum(preds[i] == rows[i]['label'] for i in labelled),
            'accuracy': sum(preds[i] == rows[i]['label'] for i in labelled)/len(labelled) if labelled else None,
            'weighted_error': sum(rows[i]['weight'] for i in labelled if preds[i] != rows[i]['label']),
            'weighted_error_rate': sum(rows[i]['weight'] for i in labelled if preds[i] != rows[i]['label'])/total_weight if total_weight else None,
            'prediction_counts_all_parents': {a: preds.count(a) for a in ('false', 'true')}}


def compare(rows, a, b):
    # All parents, including unlabelled ones, are the resampling units.
    rng = random.Random(20261105)
    accuracy, weighted = [], []
    for _ in range(2000):
        ix = [rng.randrange(len(rows)) for _ in rows]
        rr, aa, bb = [rows[i] for i in ix], [a[i] for i in ix], [b[i] for i in ix]
        am, bm = metrics(rr, aa), metrics(rr, bb)
        if am['accuracy'] is not None:
            accuracy.append(am['accuracy']-bm['accuracy'])
            weighted.append(bm['weighted_error_rate']-am['weighted_error_rate'])
    def interval(v):
        return [quantile(v, .025), quantile(v, .975)] if v else None
    am, bm = metrics(rows, a), metrics(rows, b)
    return {'accuracy_delta': am['accuracy']-bm['accuracy'] if am['accuracy'] is not None else None,
            'accuracy_delta_parent_bootstrap_95pct': interval(accuracy),
            'weighted_error_rate_reduction': bm['weighted_error_rate']-am['weighted_error_rate'] if am['accuracy'] is not None else None,
            'weighted_error_rate_reduction_parent_bootstrap_95pct': interval(weighted),
            'bootstrap_valid_draws': len(accuracy), 'bootstrap_parent_draws': 2000}


def main():
    started = time.process_time()
    p = argparse.ArgumentParser()
    p.add_argument('--receipts', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    base = root/'results/phase_prediction_v1'
    cohort_path = root/'configs/experiments/phase_prediction_v1/depth192_v1.csv'
    with cohort_path.open() as f:
        cohort = list(csv.DictReader(f))
    ids = {r['hash'] for r in cohort}
    if len(ids) != 192 or sorted(r['role'] for r in cohort).count('development_fit') != 144 or sum(r['role'] == 'development_feedback' for r in cohort) != 48:
        raise ValueError('changed development cohort')
    with (base/'test_candidates.csv').open() as f:
        if ids & {r['hash'] for r in csv.DictReader(f)}:
            raise ValueError('protected input')
    completion = json.loads((a.receipts/'results/completion.json').read_text())
    identity = json.loads((a.receipts/'results/identity.json').read_text())
    if completion['parents'] != 192 or identity['cohort_sha256'] != sha(cohort_path):
        raise ValueError('incomplete or changed feature stage')
    with (base/'professor_pairs.csv').open() as f:
        original = {r['hash']: r for r in csv.DictReader(f) if r['hash'] in ids}
    rows, receipt_shas = [], {}
    for item in cohort:
        h = item['hash']
        path = a.receipts/'results'/(h+'.json')
        rec = json.loads(path.read_text())
        if rec['hash'] != h or rec['role'] != item['role'] or rec['identity'] != identity:
            raise ValueError('inconsistent parent identity')
        receipt_shas[h] = sha(path)
        features = rec.get('features', {}) if rec['status'] == 'VALID' else {}
        if features and set(features)-{'feature_wall_s'} != set(STATIC)|set(GEOMETRY)|set(GATES):
            raise ValueError('changed numeric feature pool')
        lab, weight, reason = label(original[h])
        rows.append({'hash': h, 'role': item['role'], 'label': lab, 'weight': weight,
                     'label_reason': reason, 'features': features, 'feature_status': rec['status'],
                     'feature_cpu_s': rec.get('feature_cpu_s'), 'input_sha256': rec.get('input_sha256')})
    fit_rows = [r for r in rows if r['role'] == 'development_fit']
    feedback_rows = [r for r in rows if r['role'] == 'development_feedback']
    # Freeze every fitted model before inspecting feedback scores.
    models = {'constant': {'model': {'action': best_action(fit_rows)}},
              'tree_geometry': fit(fit_rows, GEOMETRY),
              'gate_depth_polarity': fit(fit_rows, GATES),
              'matched_all43': fit(fit_rows, set(STATIC)|set(GEOMETRY)|set(GATES))}
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'fitted_models.json').write_text(json.dumps(models, indent=2)+'\n')
    predictions = {name: [predict(item['model'], r['features']) for r in feedback_rows] for name, item in models.items()}
    scores = {}
    for name, preds in predictions.items():
        scores[name] = {**metrics(feedback_rows, preds),
                        'vs_fit_selected_constant': compare(feedback_rows, preds, predictions['constant']),
                        'vs_matched_all43': compare(feedback_rows, preds, predictions['matched_all43'])}
    coverage = {}
    for role, rr in (('fit', fit_rows), ('feedback', feedback_rows)):
        counts = {}
        for r in rr:
            counts[r['label_reason']] = counts.get(r['label_reason'], 0)+1
        coverage[role] = {'parents': len(rr), 'label_counts': {x: sum(r['label'] == x for r in rr) for x in ('false', 'true')},
                          'reasons': counts, 'valid_features': sum(r['feature_status'] == 'VALID' for r in rr),
                          'missing_geometry': sum(r['features'].get('d_incidence_geometry_exact') != 1 for r in rr),
                          'missing_gate_depth': sum(r['features'].get('d_gate_condensation_depth') is None for r in rr)}
    result = {'scope': 'Original recorded/bounded false/true labels; exploratory development comparison only.',
              'protocol_sha256': sha(root/'docs/DEPTH_FEATURES_DIRECT_PROTOCOL_20261105.md'),
              'analysis_source_sha256': sha(Path(__file__)), 'cohort_sha256': sha(cohort_path),
              'original_table_sha256': sha(base/'professor_pairs.csv'), 'feature_identity': identity,
              'parent_receipt_sha256': receipt_shas, 'coverage': coverage, 'models': models, 'feedback': scores,
              'new_solver_runs': 0, 'gate_used': 0, 'final_test_used': 0,
              'modern_D_F_policy_reward': False,
              'cost': {'feature_stage_reported_process_and_waited_children_cpu_s': completion['actual_process_and_waited_children_cpu_s'],
                       'feature_stage_reported_wall_s': completion['wall_s'],
                       'feature_child_cpu_s_sum': sum(r['feature_cpu_s'] or 0 for r in rows),
                       'local_analysis_cpu_s': time.process_time()-started},
              'limitations': ['Original solver version, timeout semantics and phase-direction implementation are unknown.',
                             'Single-timeout labels/weights use recorded bounds, not exact runtime ratios.',
                             'Unknown labels remain in coverage; accuracy is conditional on supported preferences.',
                             'Recognized signed gates are a structural proxy, not a recovered original circuit.',
                             'Feedback is exploratory development; these scores are not deployment gains or confirmation.']}
    (a.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    with (a.out/'feedback_predictions.csv').open('w') as f:
        fields = ['hash', 'label', 'weight', 'label_reason', 'feature_status', *models]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, r in enumerate(feedback_rows):
            writer.writerow({**{k: r[k] for k in fields[:5]}, **{n: predictions[n][i] for n in models}})
    lines = ['# Original-table tree/depth rule comparison', '',
             'No new SAT solving; all144fit/48feedback parents retained. Original false/true labels have unverified solver semantics.', '',
             '| Model | Fit-only fitted rule | Feedback supported accuracy | Weighted error rate | Accuracy delta vs fixed | 95% paired interval |',
             '|---|---|---:|---:|---:|---|']
    for name, item in models.items():
        s = scores[name]
        lines.append(f"| {name} | {json.dumps(item['model'], separators=(',', ':'))} | {s['correct']}/{s['labelled_parents']} | {s['weighted_error_rate']} | {s['vs_fit_selected_constant']['accuracy_delta']} | {s['vs_fit_selected_constant']['accuracy_delta_parent_bootstrap_95pct']} |")
    lines += ['', 'Coverage: '+json.dumps(coverage), '', 'Feature-stage cost: '+json.dumps(result['cost']), '', *result['limitations']]
    (a.out/'RESULT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'coverage': coverage, 'models': {n: x['model'] for n, x in models.items()},
                      'feedback': scores, 'cost': result['cost']}))


if __name__ == '__main__':
    main()
