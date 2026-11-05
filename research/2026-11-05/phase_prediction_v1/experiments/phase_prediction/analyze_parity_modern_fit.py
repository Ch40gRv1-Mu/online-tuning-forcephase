"""Modern-action fit-only comparison reusing all actual runtime measurements."""
import argparse
import json
import random
import statistics
from pathlib import Path
import policy
from policy_fit_total_budget import train
from analyze_matrix import deployed_cost
from analyze_parity_cv import GEOMETRY, DIRECTION
from professor_depth_rules import quantile, sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--receipts', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    base = root/'results/phase_prediction_v1'
    rows = [json.loads(x) for x in (base/'fast60_analysis/cases.jsonl').read_text().splitlines() if x]
    rows = [r for r in rows if r['role'] == 'development_fit']
    if len(rows) != 24:
        raise ValueError('changed fixed modernfit panel')
    prepared = {r['hash']: r for r in json.loads((base/'fast60_imported/results/prepared.json').read_text())}
    original_pool = set(policy.STATIC)
    full_pool = original_pool | set(GEOMETRY) | set(DIRECTION) | {'p_exact'}
    policy.STATIC.update(full_pool)
    for r in rows:
        rec = json.loads((a.receipts/'results'/(r['hash']+'.json')).read_text())
        if rec['status'] != 'VALID' or rec['role'] != 'development_fit' or rec['input_sha256'] != prepared[r['hash']]['sha256']:
            raise ValueError('invalid or changed feature/input join')
        r['features'].update(rec['features'])
        r['old_fee'], r['new_fee'] = r['feature_cpu_s'], rec['feature_cpu_s']
    informative = sum(r['features'].get('p_exact') == 1 and (r['features'].get('p_parity_variable_fraction') or 0.) > 0 for r in rows)
    if informative < 10:
        a.out.mkdir(parents=True, exist_ok=False)
        result = {'status': 'INSUFFICIENT_PARITY_FEATURE_COVERAGE_FOR_PRESPECIFIED_MODEL', 'modern_fit_parents': 24,
                  'informative_parity_parents': informative, 'required': 10, 'models_fitted': 0, 'new_solver_calls': 0,
                  'feedback_used': 0, 'gate_used': 0, 'final_test_used': 0,
                  'protocol_sha256': sha(root/'docs/PARITY_FEATURE_PROTOCOL_20261105.md')}
        (a.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
        (a.out/'RESULT.md').write_text('# 现代配置fit检查\n\n完整奇偶模板覆盖'+str(informative)+'/24，未达到预设10题覆盖条件；不拟合模型，不把证据不足称无效。\n')
        print(json.dumps(result));return
    costs = {n: [None]*24 for n in ('constant3', 'strong_static4', 'parity_participation', 'parity_orientation', 'old34_control', 'full41_control')}
    details = []
    def cost(r, action, fee=0.):
        return statistics.mean(deployed_cost(x, fee) for x in r['outcomes'][action])
    for fold in range(5):
        train_rows = [r for i, r in enumerate(rows) if i % 5 != fold]
        validation = [i for i in range(24) if i % 5 == fold]
        references = {name: min(actions, key=lambda a: (sum(cost(r, a) for r in train_rows), a))
                      for name, actions in (('constant3', ['D', 'Fplus', 'Fminus']), ('strong_static4', ['D', 'Fplus', 'Fminus', 'Iminus']))}
        models = {}
        for name, fields, fee_name in (('parity_participation', GEOMETRY, 'new_fee'), ('parity_orientation', DIRECTION, 'new_fee'),
                                     ('old34_control', original_pool, 'old_fee'), ('full41_control', full_pool, 'both')):
            rr = [{**r, 'feature_cpu_s': r['old_fee']+r['new_fee'] if fee_name == 'both' else r[fee_name]} for r in train_rows]
            tree = train(rr, sorted(fields), 1, 8)
            models[name] = tree
            for i in validation:
                row = rows[i]
                fee = (row['old_fee']+row['new_fee'] if fee_name == 'both' else row[fee_name]) if 'feature' in tree else 0.
                costs[name][i] = cost(row, policy.decide(tree, row['features']), fee)
        for name, action in references.items():
            for i in validation:
                costs[name][i] = cost(rows[i], action)
        details.append({'fold': fold, 'training_parents': len(train_rows), 'validation_parents': len(validation), 'models': models, 'references': references})
    scores = {}
    for name, values in costs.items():
        comparisons = {}
        for reference in ('constant3', 'strong_static4', 'old34_control', 'full41_control'):
            base_costs = costs[reference]
            rng = random.Random(20261105)
            draws = []
            for _ in range(2000):
                indices = [rng.randrange(24) for _ in range(24)]
                draws.append(1-sum(values[i] for i in indices)/sum(base_costs[i] for i in indices))
            comparisons[reference] = {'relative_par2_reduction': 1-sum(values)/sum(base_costs),
                                      'descriptive_parent_bootstrap95': [quantile(draws, .025), quantile(draws, .975)]}
        scores[name] = {'mean_par2': statistics.mean(values), 'comparisons': comparisons}
    result = {'scope': 'Only24fit modernT60, two seeds averaged; fixed5fold diagnostic, no feedback or confirmation.',
              'protocol_sha256': sha(root/'docs/PARITY_FEATURE_PROTOCOL_20261105.md'), 'source_sha256': sha(Path(__file__)),
              'parents': 24, 'all_four_censored': sum(all(not x['resolved'] for values in r['outcomes'].values() for x in values) for r in rows),
              'scores': scores, 'folds': details, 'out_of_fold_parent_costs': costs,
              'new_solver_calls': 0, 'new_RICL_rewards': 0, 'feedback_used': 0, 'gate_used': 0, 'final_test_used': 0,
              'limitations': 'Already-seen fit panel and little headroom; intervals condition on CV predictions. No strong predictive or deployment claim.'}
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    lines = ['# 新奇偶模板特征：现代D/F配置fit内验证', '', '24fit、两seed、固定五折；16题四配置均删失，不新增求解或读取新反馈。', '',
             '| 规则 | OOF平均PAR2秒 | 相对强静态对照改善 | 描述性95%区间 |', '|---|---:|---:|---|']
    for n, s in scores.items():
        d = s['comparisons']['strong_static4']
        lines.append(f"| {n} | {s['mean_par2']:.6f} | {d['relative_par2_reduction']:+.4%} | {d['descriptive_parent_bootstrap95']} |")
    lines += ['', result['limitations'], '特征费按实际解析器执行一次计入h+t≤60；full41控制需支付两个解析器，不冒称免费。']
    (a.out/'RESULT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'parents': 24, 'all_four_censored': result['all_four_censored'], 'scores': scores, 'new_solver_calls': 0}))


if __name__ == '__main__':
    main()
