"""Predeclared fit-only out-of-fold feature characterization, no gate access."""
import argparse
import csv
import json
import time
from pathlib import Path
from professor_depth_rules import label, fit, best_action, predict, metrics, compare, sha
from policy import STATIC

GEOMETRY = ['p_parity_variable_fraction', 'p_templates_per_variable', 'p_shared_variable_fraction', 'p_max_template_degree', 'p_clause_coverage']
DIRECTION = ['p_forbidden_even_fraction', 'p_parity_variable_fraction']


def main():
    started = time.process_time()
    p = argparse.ArgumentParser()
    p.add_argument('--receipts', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    base = root/'results/phase_prediction_v1'
    cohort_path = root/'configs/experiments/phase_prediction_v1/parity_fit144_v1.csv'
    with cohort_path.open() as f:
        cohort = list(csv.DictReader(f))
    if len(cohort) != 144 or any(r['role'] != 'development_fit' for r in cohort):
        raise ValueError('not fixed144fit')
    ids = {r['hash'] for r in cohort}
    with (base/'professor_pairs.csv').open() as f:
        original = {r['hash']: r for r in csv.DictReader(f) if r['hash'] in ids}
    completed = json.loads((a.receipts/'results/completion.json').read_text())
    identity = json.loads((a.receipts/'results/identity.json').read_text())
    if completed['parents'] != 144 or identity['cohort_sha256'] != sha(cohort_path):
        raise ValueError('changed/incomplete feature stage')
    rows, equivalence_fold = [], {}
    for i, item in enumerate(cohort):
        h = item['hash']
        record = json.loads((a.receipts/'results'/(h+'.json')).read_text())
        old = json.loads((base/'depth192_imported/phases/depth192_v1/results'/(h+'.json')).read_text())
        if record['hash'] != h or record['role'] != 'development_fit' or record['identity'] != identity or old['input_sha256'] != item['sha256']:
            raise ValueError('changed parent or feature identity')
        if record['status'] == 'VALID' and record['input_sha256'] != item['sha256']:
            raise ValueError('new and cached features use different inputs')
        features = {k: v for k, v in old['features'].items() if k in STATIC}
        features.update(record.get('features', {}))
        lab, weight, why = label(original[h])
        fold = equivalence_fold.setdefault(item['isohash'], i % 5)
        rows.append({'hash': h, 'fold': fold, 'features': features, 'label': lab, 'weight': weight,
                     'reason': why, 'feature_status': record['status'], 'feature_cpu_s': record.get('feature_cpu_s', 0.)})
    predictions = {name: [None]*144 for name in ('constant', 'parity_participation', 'parity_orientation', 'old34_control')}
    folds = []
    for fold in range(5):
        train = [r for r in rows if r['fold'] != fold]
        validation = [i for i, r in enumerate(rows) if r['fold'] == fold]
        models = {'constant': {'action': best_action(train)},
                  'parity_participation': fit(train, GEOMETRY)['model'],
                  'parity_orientation': fit(train, DIRECTION)['model'],
                  'old34_control': fit(train, STATIC)['model']}
        for name, model in models.items():
            for i in validation:
                predictions[name][i] = predict(model, rows[i]['features'])
        folds.append({'fold': fold, 'training_parents': len(train), 'validation_parents': len(validation), 'models': models})
    scores = {}
    for name, values in predictions.items():
        scores[name] = {**metrics(rows, values),
                        'vs_fold_fit_constant': compare(rows, values, predictions['constant']),
                        'vs_old34_control': compare(rows, values, predictions['old34_control'])}
    exact_nonempty = sum(r['features'].get('p_exact') == 1 and (r['features'].get('p_parity_variable_fraction') or 0.) > 0 for r in rows)
    usable_labels = sum(r['label'] is not None and (r['features'].get('p_parity_variable_fraction') or 0.) > 0 for r in rows)
    positive = any(scores[n]['vs_fold_fit_constant']['accuracy_delta'] > 0 and scores[n]['vs_fold_fit_constant']['weighted_error_rate_reduction'] > 0 and len(set(predictions[n])) > 1 for n in ('parity_participation', 'parity_orientation'))
    continue_criteria = usable_labels >= 20 and positive
    result = {'scope': 'Fit-only prespecified5fold characterization; original-label target, no held-out feedback or RICL reward.',
              'protocol_sha256': sha(root/'docs/PARITY_FEATURE_PROTOCOL_20261105.md'),
              'source_sha256': sha(Path(__file__)), 'cohort_sha256': sha(cohort_path),
              'feature_identity': identity, 'all_fit_parents': 144,
              'labelled_fit_parents': sum(r['label'] is not None for r in rows),
              'informative_parity_parents': exact_nonempty, 'informative_labelled_parity_parents': usable_labels,
              'scores': scores, 'fold_models': folds,
              'continuation_criteria_met': continue_criteria,
              'feature_cpu_s_sum': sum(r['feature_cpu_s'] for r in rows),
              'local_analysis_cpu_s': time.process_time()-started,
              'feedback_read': 0, 'gate_read': 0, 'final_test_read': 0, 'new_RICL_rewards': 0, 'new_solver_calls': 0,
              'limitations': ['Already-seen fit data; intervals condition on out-of-fold predictions and are exploratory.',
                             'Original phase/version unverified; no automatic mapping to modernF±.',
                             'No cost comparison combining oldTA wall and featureCPU; no deployment claim.',
                             'No hidden reuse of another agent gate; later policy needs available shared8-round slot.']}
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    with (a.out/'oof_predictions.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=['hash', 'fold', 'label', 'weight', 'reason', *predictions])
        writer.writeheader()
        for i, r in enumerate(rows):
            writer.writerow({**{k: r[k] for k in ('hash', 'fold', 'label', 'weight', 'reason')}, **{n: v[i] for n, v in predictions.items()}})
    lines = ['# 完整奇偶约束模板：fit内五折验证', '', '全144fit，原表支持偏好标签；未读取feedback/gate/test，也未新增求解。', '',
             '| 特征规则 | 明确标签预测 | 加权错误率 | 相对固定准确率变化 | 描述性95%区间 |',
             '|---|---:|---:|---:|---|']
    for name, s in scores.items():
        d = s['vs_fold_fit_constant']
        lines.append(f"| {name} | {s['correct']}/{s['labelled_parents']} | {s['weighted_error_rate']:.4f} | {d['accuracy_delta']:+.4f} | {d['accuracy_delta_parent_bootstrap_95pct']} |")
    lines += ['', f'含完整奇偶模板{exact_nonempty}/144；可用偏好标签{usable_labels}；预设继续条件：{continue_criteria}。',
              '这是新特征的fit内筛查，不是独立验证或现代D/F选择收益。失败也保留，不扩同类变体。']
    (a.out/'RESULT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('fold_models', 'limitations')}))


if __name__ == '__main__':
    main()
