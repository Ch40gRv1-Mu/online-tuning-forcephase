"""One predeclared structural-predicate association, no policy fitting."""
import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path
from professor_depth_rules import label, quantile, sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--receipts', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    base = root/'results/phase_prediction_v1'
    with (root/'configs/experiments/phase_prediction_v1/implication_feedback48_v1.csv').open() as f:
        cohort = list(csv.DictReader(f))
    ids = {r['hash'] for r in cohort}
    if len(ids) != 48 or any(r['role'] != 'development_feedback' for r in cohort):
        raise ValueError('changed development feedback cohort')
    with (base/'professor_pairs.csv').open() as f:
        original = {r['hash']: r for r in csv.DictReader(f) if r['hash'] in ids}
    completion = json.loads((a.receipts/'results/completion.json').read_text())
    if completion['parents'] != 48:
        raise ValueError('incomplete feature stage')
    rows = []
    for item in cohort:
        r = json.loads((a.receipts/'results'/(item['hash']+'.json')).read_text())
        if r['role'] != 'development_feedback' or r['identity'] != completion['identity']:
            raise ValueError('changed receipt identity')
        if r['status'] == 'VALID' and r['input_sha256'] != item['sha256']:
            raise ValueError('changed input')
        features = r.get('features', {})
        lab, weight, reason = label(original[item['hash']])
        eligible = lab is not None and features.get('b_exact') == 1 and features.get('b_scc_cyclic_fraction') is not None
        old = json.loads((base/'depth192_imported/phases/depth192_v1/results'/(item['hash']+'.json')).read_text())['features']
        rows.append({'hash': item['hash'], 'label': lab, 'eligible': eligible, 'cycle': features.get('b_scc_cyclic_fraction', 0.) > 0 if features.get('b_scc_cyclic_fraction') is not None else None,
                     'feature_status': r['status'], 'label_reason': reason, 'log_variables': old['s_log_variables'], 'log_clauses': old['s_log_clauses']})
    def counts(rr):
        return [[sum(r['eligible'] and r['cycle'] == cycle and r['label'] == lab for r in rr) for lab in ('false', 'true')] for cycle in (True, False)]
    table = counts(rows)
    def contrast(t):
        return t[0][0]/sum(t[0])-t[1][0]/sum(t[1]) if all(map(sum, t)) else None
    point = contrast(table)
    rng = random.Random(20261105)
    draws = []
    for _ in range(2000):
        value = contrast(counts([rows[rng.randrange(48)] for _ in rows]))
        if value is not None:
            draws.append(value)
    # Hypergeometric tail conditional on both margins, alternative='greater'.
    n = sum(map(sum, table)); success = table[0][0]+table[1][0]; group = sum(table[0])
    fisher = sum(math.comb(success, x)*math.comb(n-success, group-x)/math.comb(n, group)
                 for x in range(table[0][0], min(success, group)+1) if 0 <= group-x <= n-success) if n else None
    groups = {}
    for cycle in (True, False):
        rr = [r for r in rows if r['eligible'] and r['cycle'] == cycle]
        groups[str(cycle)] = {'parents': len(rr), 'median_log_variables': statistics.median(r['log_variables'] for r in rr) if rr else None,
                              'median_log_clauses': statistics.median(r['log_clauses'] for r in rr) if rr else None}
    interval = [quantile(draws, .025), quantile(draws, .975)] if draws else None
    result = {'scope': 'One frozen SCC-cycle association on already-seen development_feedback, exploratory only.',
              'all_feedback_parents': 48, 'eligible_supported_preferences': n,
              'feature_valid': sum(r['feature_status'] == 'VALID' for r in rows),
              'table_rows': ['cycle', 'no_cycle'], 'table_columns': ['false_preferred', 'true_preferred'], 'table': table,
              'false_preference_proportion_difference': point, 'descriptive_parent_bootstrap95': interval,
              'bootstrap_valid_draws': len(draws), 'fisher_greater_descriptive_p': fisher, 'group_size_diagnostics': groups,
              'support_requires_positive_point_and_interval': bool(point is not None and point > 0 and interval and interval[0] > 0),
              'protocol_sha256': sha(root/'docs/IMPLICATION_CYCLE_ASSOCIATION_PROTOCOL_20261105.md'), 'source_sha256': sha(Path(__file__)),
              'rows': rows, 'gate_read': 0, 'final_test_read': 0, 'new_RICL_rewards': 0, 'new_solver_calls': 0,
              'limitation': 'No new action selector, no independent confirmation, no modernF transfer or causation; size diagnostics are not causal adjustment.'}
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    text = f'''# 二元蕴含循环：冻结方向的开发反馈核对

全48feedback，结构有效{result['feature_valid']}，支持偏好且有非空精确图{n}。

| 图结构 | 原表false较快 | 原表true较快 |
|---|---:|---:|
| 有非平凡SCC | {table[0][0]} | {table[0][1]} |
| 无非平凡SCC | {table[1][0]} | {table[1][1]} |

false偏好比例差={point}；描述性95%区间={interval}；单侧Fisher p={fisher}。

不拟合新policy，不新增RICL reward，不使用gate/test；原相位语义未核实。
'''
    (a.out/'RESULT.md').write_text(text)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
