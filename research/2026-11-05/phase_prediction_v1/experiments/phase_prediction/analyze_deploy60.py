"""Compare actual deployment evidence with the frozen rule and source matrix."""
import argparse
import json
import statistics
from pathlib import Path
import deployment_consistency
import policy
import run_pilot as common


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--expected', type=Path, required=True)
    p.add_argument('--spec', type=Path, required=True)
    p.add_argument('--policy', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    completed = json.loads((a.root/'results/completion.json').read_text())
    expected = json.loads(a.expected.read_text())
    spec = json.loads(a.spec.read_text())
    tree = json.loads(a.policy.read_text())
    if completed['status'] != 'COMPLETE' or completed['runs'] != 8 or completed['parents'] != 8 or len(expected) != 8:
        raise ValueError('incomplete actual deployment')
    identity = completed['identity']
    if identity['spec_sha256'] != common.sha(a.spec) or identity['policy_file_sha256'] != common.sha(a.policy):
        raise ValueError('changed frozen policy/spec')
    if spec['policy_sha256'] != policy.validate(tree) or spec['total_cpu_budget_s'] != 60:
        raise ValueError('wrong policy/budget contract')
    rows = []
    for i, e in enumerate(expected):
        unit = a.root/'results/units'/f"{i:02d}_{e['hash']}"
        r = json.loads((unit/'record.json').read_text())
        binding = json.loads((unit/'batch_binding.json').read_text())
        if binding['record_sha256'] != common.sha(unit/'record.json') or r['identity'] != identity['unit_identity']:
            raise ValueError('changed actual unit or source identity')
        if r['features'] != e['source_features'] or r['action'] != e['expected_action'] or r['policy'] != tree:
            raise ValueError('source features/frozen action mismatch')
        checked = deployment_consistency.check(unit)
        rows.append({'hash': e['hash'], 'role': r['role'], 'action': r['action'],
                     'status': r['status'], 'verify': r['verify'], 'resolved': r['resolved'],
                     'feature_and_decision_cpu_s': r['feature_and_decision_cpu_s'],
                     'solver_cpu_s': r['solver']['cpu_s'] if r['solver'] else 0.,
                     'checker_or_model_cpu_s': r.get('verification_cpu_s', 0.),
                     'remaining_solver_budget_s': r.get('remaining_solver_cpu_budget_s'),
                     'par2': r['par2'], 'independent_replay_par2': checked['par2'],
                     'source_seed0_solver_cpu_s': e['source_seed0_cpu_s'],
                     'source_seed0_par2_with_old_feature_fee': e['source_seed0_par2_with_observed_old_feature_fee'],
                     'record_sha256': common.sha(unit/'record.json'), 'consistency': checked['status']})
    result = {'status': 'EIGHT_ACTUAL_DEPLOYMENTS_ACTION_FEATURE_AND_COST_CONSISTENT',
              'units': 8, 'features_equal_source_matrix': 8, 'actions_equal_frozen_policy': 8,
              'actual_replay_cost_equal': 8, 'verified_solved': sum(r['resolved'] for r in rows),
              'mean_actual_par2': statistics.mean(r['par2'] for r in rows), 'rows': rows,
              'completion_sha256': common.sha(a.root/'results/completion.json'),
              'expected_source_sha256': common.sha(a.expected),
              'analysis_source_sha256': common.sha(Path(__file__)),
              'gate_used': 0, 'final_test_used': 0,
              'scope': 'Required actual engineering consistency on seen development parents; no new generalization or positive policy claim.',
              'accounting': 'Per-record values explain costs. Outer GNU-time alone bills physical stage; never sum it again with these nested values.'}
    a.out.mkdir(parents=True, exist_ok=False)
    common.write(a.out/'summary.json', result)
    lines = ['# 八次实际部署一致性', '', '冻结的最佳失败候选；仅在已见开发题核对执行和费用，不是新的泛化证据。', '',
             '| 序号 | 动作 | 特征＋决策CPU秒 | 求解CPU秒 | 验证 | 实际PAR2 | 独立回放PAR2 |',
             '|---|---|---:|---:|---|---:|---:|']
    for i, r in enumerate(rows):
        lines.append(f"| {i+1} | {r['action']} | {r['feature_and_decision_cpu_s']:.6f} | {r['solver_cpu_s']:.6f} | {r['verify']} | {r['par2']:.6f} | {r['independent_replay_par2']:.6f} |")
    lines += ['', '8/8特征与原矩阵相同、动作与冻结规则相同、总CPU计费与独立回放相同。',
              '单次重新运行的耗时可波动；与旧矩阵耗时差异完整保存在summary.json，不能当新的赢家准确率。',
              '开发候选尚未胜过固定D/I−；本阶段不改变这一结论，不打开gate或最终测试。']
    (a.out/'RESULT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
