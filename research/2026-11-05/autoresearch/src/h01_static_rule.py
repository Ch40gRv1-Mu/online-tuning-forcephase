"""Frozen H01: family-held-out cost-sensitive stumps; existing data only."""
from pathlib import Path
import csv, hashlib, json, time, sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work/expanded_parents/results'
OUT = ROOT / 'experiments/H01_cost_aware_static_rule/results'
CONFIGS = ['D', 'Fplus', 'Fminus']
SEED = 'forcephase-autoresearch-h01-v1'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    with p.open(newline='') as f:
        return list(csv.DictReader(f))

def save_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

def fit(X, costs, descriptor, family, features, charge):
    baseline = float(costs[:, 0].sum())
    best, rule = baseline, None
    for j, feature in enumerate(features):
        for t in np.unique(np.quantile(X[:, j], np.arange(1, 10) / 10)):
            pred = np.zeros(len(X), dtype=int)
            leafs = []
            for mask in (X[:, j] <= t, X[:, j] > t):
                c = 0
                if mask.sum() >= 8 and len(set(family[mask])) >= 4:
                    sums = costs[mask].sum(axis=0)
                    winner = int(sums.argmin())
                    if winner and sums[winner] <= .95 * sums[0]:
                        c = winner
                pred[mask] = c
                leafs.append(CONFIGS[c])
            if not pred.any():
                continue
            score = float(costs[np.arange(len(X)), pred].sum())
            if charge:
                score += float(descriptor.sum())
            if score < best - 1e-10:
                best = score
                rule = dict(feature=feature, threshold=float(t), left=leafs[0], right=leafs[1])
    return rule

def predict(rule, X, features):
    if rule is None:
        return np.zeros(len(X), dtype=int)
    left = X[:, features.index(rule['feature'])] <= rule['threshold']
    return np.where(left, CONFIGS.index(rule['left']), CONFIGS.index(rule['right']))

def boot_indices(families, rng):
    groups = sorted(set(families))
    index = {g: np.flatnonzero(families == g) for g in groups}
    return [np.concatenate([index[g] for g in rng.choice(groups, len(groups), replace=True)]) for _ in range(2000)]

def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=False)
    lab = read(SOURCE / 'labels.csv')
    feats = {r['id']: r for r in read(SOURCE / 'parent_features.csv')}
    features = json.loads((SOURCE / 'analysis_environment.json').read_text())['features']
    valid = [r for r in lab if r['reason'] not in ('unverified', 'contended', 'execution_error', 'missing')]
    assert len(lab) == 300 and len(valid) == 291
    assert len({r['id'] for r in valid}) == 291
    for r in valid:
        assert r['input_sha256'] == feats[r['id']]['cnf_sha256']
        for c in CONFIGS:
            assert r[c + '_contended'] == 'False'
            assert r[c + '_status'] in ('SAT', 'UNSAT', 'UNKNOWN', 'TIMEOUT')
            if r[c + '_status'] in ('SAT', 'UNSAT'):
                assert r[c + '_verified'] == 'True'
    X = np.array([[float(feats[r['id']][f]) for f in features] for r in valid])
    costs = np.array([[float(r[c + '_par2']) for c in CONFIGS] for r in valid])
    cpu = np.array([[float(r[c + '_cpu_s']) for c in CONFIGS] for r in valid])
    descriptor = np.array([float(feats[r['id']]['extraction_cpu_s']) for r in valid])
    family = np.array([r['family'] for r in valid])
    truth = np.array([CONFIGS.index(r['clear']) if r['clear'] else -1 for r in valid])
    assert (truth >= 0).sum() == 69
    groups = sorted(set(family), key=lambda s: hashlib.sha256((SEED + ':' + s).encode()).hexdigest())
    foldmap = {g: j % 5 for j, g in enumerate(groups)}
    folds = np.array([foldmap[g] for g in family])
    foldrows, predictions, metrics, fullrules = [], [], [], {}
    for name, charge in [('zero_cost_upper_bound', False), ('measured_full_extractor_cost', True)]:
        pred = np.zeros(len(valid), dtype=int)
        overhead = np.zeros(len(valid))
        for k in range(5):
            train, test = folds != k, folds == k
            assert not (set(family[train]) & set(family[test]))
            rule = fit(X[train], costs[train], descriptor[train], family[train], features, charge)
            pred[test] = predict(rule, X[test], features)
            if rule is not None and charge:
                overhead[test] = descriptor[test]
            foldrows.append(dict(path=name, fold=k, training_parents=int(train.sum()), testing_parents=int(test.sum()), rule=rule))
        selected = costs[np.arange(len(valid)), pred] + overhead
        actual = cpu[np.arange(len(valid)), pred] + overhead
        for i, r in enumerate(valid):
            predictions.append(dict(path=name, id=r['id'], family=r['family'], cohort=r['cohort'], fold=int(folds[i]), truth=r['clear'], prediction=CONFIGS[pred[i]], switched=bool(pred[i]), feature_cpu_s=float(overhead[i]), selected_PAR2_plus_feature_s=float(selected[i]), D_PAR2_s=float(costs[i, 0]), selected_actual_cpu_plus_feature_s=float(actual[i])))
        for cohort in ('combined300', 'original48', 'expanded252'):
            use = np.array([cohort == 'combined300' or r['cohort'] == cohort for r in valid])
            ix = np.flatnonzero(use)
            bi = boot_indices(family[ix], np.random.default_rng(20261029))
            ratios = [selected[ix[b]].sum() / costs[ix[b], 0].sum() for b in bi]
            cl = np.flatnonzero(use & (truth >= 0))
            bc = boot_indices(family[cl], np.random.default_rng(20261029))
            good = pred[cl] == truth[cl]
            gain = good.astype(float) - (truth[cl] == 0).astype(float)
            gainci = np.percentile([gain[b].mean() for b in bc], [2.5, 97.5])
            switched = pred[cl] != 0
            lo, hi = np.percentile(ratios, [2.5, 97.5])
            metrics.append(dict(path=name, cohort=cohort, cost_valid_n=len(ix), clear_n=len(cl), switch_n=int(switched.sum()), switch_coverage=float(switched.mean()), switch_accuracy=float(good[switched].mean()) if switched.any() else None, accuracy=float(good.mean()), D_accuracy=float((truth[cl] == 0).mean()), accuracy_gain=float(gain.mean()), accuracy_gain_ci_low=float(gainci[0]), accuracy_gain_ci_high=float(gainci[1]), cost_ratio=float(selected[ix].sum() / costs[ix, 0].sum()), cost_ratio_ci_low=float(lo), cost_ratio_ci_high=float(hi), physical_cpu_ratio=float(actual[ix].sum() / cpu[ix, 0].sum()), charged_descriptor_cpu_s=float(overhead[ix].sum()), root_UP_cost_included=False))
        fullrules[name] = fit(X, costs, descriptor, family, features, charge)
    save_csv(OUT / 'predictions.csv', predictions)
    save_csv(OUT / 'metrics.csv', metrics)
    (OUT / 'fold_rules.json').write_text(json.dumps(foldrows, indent=2) + '\n')
    (OUT / 'development_candidate.json').write_text(json.dumps(dict(role='EXPLORATORY_FULL_DEVELOPMENT_FIT_NOT_VALIDATION', rules=fullrules), indent=2) + '\n')
    (OUT / 'receipt.json').write_text(json.dumps(dict(status='EXECUTION_SUCCESS', scientific_role='EXPLORATORY', input_sha256={p.name: sha(p) for p in [SOURCE/'labels.csv', SOURCE/'parent_features.csv', SOURCE/'analysis_environment.json']}, source_sha256=sha(Path(__file__)), protocol_sha256=sha(OUT.parent/'protocol.md'), python=sys.version, numpy=np.__version__, family_fold_seed=SEED, bootstrap_seed=20261029, bootstrap=2000, wall_s=time.monotonic()-started), indent=2) + '\n')
    lines = ['# H01 正式探索结果', '', '已有300题已被观察；以下是按家族留出的新训练程序结果，不是新数据确认。', '', '|路径|成本比D|95%区间|明确题准确率|切换覆盖|切换精度|', '|---|---:|---|---:|---:|---:|']
    for r in metrics:
        if r['cohort'] == 'combined300':
            precision = '无切换' if r['switch_accuracy'] is None else f"{r['switch_accuracy']:.1%}"
            lines.append(f"|{r['path']}|{r['cost_ratio']:.4f}|[{r['cost_ratio_ci_low']:.4f}, {r['cost_ratio_ci_high']:.4f}]|{r['accuracy']:.1%}|{r['switch_coverage']:.1%}|{precision}|")
    lines += ['', '成本路径收取现有完整静态提取器的CPU，未包含单独根UP的成本，因此仍不构成最终端到端结论。实际solverCPU、全部分层和逐题预测保存在CSV。免费路径只衡量信号上界。', '', '下一步：无论本轮是否有候选，先将其作为探索证据保存；冻结H02符号不对称特征协议，禁止在同一组原始阈值上无上限搜索。']
    (OUT.parent/'analysis.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(status='H01_COMPLETE', metrics=[r for r in metrics if r['cohort']=='combined300'], candidates=fullrules), ensure_ascii=False))

if __name__ == '__main__':
    main()
