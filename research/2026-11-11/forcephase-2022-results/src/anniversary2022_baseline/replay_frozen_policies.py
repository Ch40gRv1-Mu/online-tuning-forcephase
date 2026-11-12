"""Evaluate unchanged archived CaDiCaL policies on the retained4719 T600 matrix.

Reuse public GBD raw clause statistics; never fit thresholds or infer identities.
Unknown feature coverage stays unknown instead of triggering a missing branch.
"""
import argparse
import collections
import csv
import hashlib
import html
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import time

ACTIONS = ("D", "Fplus", "Fminus")
ROOT = Path(__file__).resolve().parents[2]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
def readcsv(path): return list(csv.DictReader(Path(path).open()))


def csvwrite(path, rows):
    if not rows: return
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def needs(tree):
    if "action" in tree: return set()
    return {tree["feature"]} | needs(tree["left"]) | needs(tree["right"])


def leaves(tree):
    return {tree["action"]} if "action" in tree else leaves(tree["left"]) | leaves(tree["right"])


def main():
    p = argparse.ArgumentParser(); p.add_argument("--db", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cache-only", action="store_true"); a = p.parse_args()
    start = time.monotonic(); cpu = time.process_time(); a.out.mkdir(parents=True, exist_ok=False)
    registry_path = ROOT / "configs/anniversary2022_baseline/frozen_policy_replay_20261110/registry.json"
    registry = json.loads(registry_path.read_text())
    matrix_path = ROOT / "outputs/anniversary2022_baseline/raw_data_20261110/matrix.csv"
    rows = readcsv(matrix_path); assert len(rows) == 4719
    ids = {r["instance_key"] for r in rows}
    manifest_path = ROOT / "configs/anniversary2022_baseline/manifest.official-solvable.v1.csv"
    assert ids == {r["instance_key"] for r in readcsv(manifest_path)}
    policy_source = ROOT / "work/phase_prediction_20261104/project/experiments/phase_prediction/policy.py"
    module = importlib.util.spec_from_file_location("original_frozen_policy", policy_source)
    policy = importlib.util.module_from_spec(module); module.loader.exec_module(policy)
    # Only raw structure fields are selected; no family, SAT answer, or metadata routing.
    db = sqlite3.connect("file:" + str(a.db.resolve()) + "?mode=ro", uri=True); db.row_factory = sqlite3.Row
    fields = ["hash", "clauses", "cls1", "cls2", "cls3", "cls4", "cls5", "cls6", "cls7", "cls8", "cls9", "cls10p", "vcg_cdegree_mean"]
    base = {r["hash"]: dict(r) for r in db.execute("SELECT " + ",".join(fields) + " FROM features") if r["hash"] in ids}; db.close()
    vectors = {}; feature_rows = []; source_comparisons = []
    oldcache_path = ROOT / "work/expanded_parents/results/parent_features.csv"
    cached = {r["id"]: r for r in readcsv(oldcache_path) if r["id"] in ids}
    for key, g in base.items():
        m = int(g["clauses"]); assert m > 0
        lengths = {i: int(g["cls" + str(i)]) for i in range(1, 10)}
        length10 = int(g["cls10p"])
        empty = m - sum(lengths.values()) - length10; assert empty >= 0
        f = {"s_mean_length": float(g["vcg_cdegree_mean"]), "s_binary_fraction": lengths[2] / m,
             "s_long_fraction": (sum(lengths[i] for i in range(5, 10)) + length10) / m}
        assert all(math.isfinite(v) and v >= 0 for v in f.values())
        if key in cached:
            c = cached[key]
            for new, old in [("s_mean_length", "mean_clause_length"), ("s_binary_fraction", "binary_fraction")]:
                error = abs(f[new] - float(c[old])); assert math.isclose(f[new], float(c[old]), rel_tol=1e-9, abs_tol=1e-9)
                source_comparisons.append({"instance_key": key, "feature": new, "gbd_value": f[new], "old_value": float(c[old]), "abs_error": error})
        if a.cache_only:
            if key not in cached: continue
            # The existing138 cache does not contain the length>=5 histogram.
            f = {"s_mean_length": float(cached[key]["mean_clause_length"]), "s_binary_fraction": float(cached[key]["binary_fraction"])}
        vectors[key] = f; feature_rows.append({"instance_key": key, **f})
    csvwrite(a.out / "features.csv", feature_rows)
    csvwrite(a.out / "feature_crosschecks.csv", source_comparisons)
    controls = [{"id": "fixed_" + x, "policy": {"action": x}} for x in ACTIONS]
    all_scores = []; prediction_rows = []; bounds = []
    for spec in controls + registry["candidates"]:
        tree = spec["policy"]; digest = policy.validate(tree)
        if "source_policy_sha256" in spec: assert digest == spec["source_policy_sha256"]
        req = needs(tree); supported = []; missing = []
        for r in rows:
            f = vectors.get(r["instance_key"], {})
            if req <= set(f): supported.append((r, f))
            else: missing.append(r)
        costs = []; dcosts = []; chosen = collections.Counter(); solved = 0; solved_D = 0; helped = harmed = 0
        for r, f in supported:
            x = policy.decide(tree, f)
            value = float(r[x + "_par2"]); basecost = float(r["D_par2"])
            costs.append(value); dcosts.append(basecost); chosen[x] += 1
            solved += r[x + "_status"] in {"SAT", "UNSAT"}; solved_D += r["D_status"] in {"SAT", "UNSAT"}
            helped += value < basecost; harmed += value > basecost
            prediction_rows.append({"policy_id": spec["id"], "instance_key": r["instance_key"], "action": x, "selected_par2": value,
                                    "D_par2": basecost, "gain_vs_D_s": basecost - value})
        n = len(supported); total = sum(costs); baseline = sum(dcosts)
        score = {"policy_id": spec["id"], "policy_sha256": digest, "features": "|".join(sorted(req)), "covered_parents": n, "total_parents": len(rows),
                 "scope": "FULL4719_FREE_FEATURE_REPLAY" if n == len(rows) else "COVERED_SUBSET_ONLY" if n else "UNSCORABLE_EXACT_FEATURE_UNAVAILABLE",
                 "mean_par2_s": total/n if n else None, "matched_D_mean_par2_s": baseline/n if n else None,
                 "relative_gain_vs_D": 1-total/baseline if baseline else None, "solved": solved if n else None, "matched_D_solved": solved_D if n else None,
                 "selected_D": chosen["D"], "selected_Fplus": chosen["Fplus"], "selected_Fminus": chosen["Fminus"], "helped_parents": helped, "harmed_parents": harmed,
                 "new_fit": False, "feature_runtime_measured": False}
        all_scores.append(score)
        if missing:
            possible = leaves(tree)
            best = total + sum(min(float(r[x + "_par2"]) for x in possible) for r in missing)
            worst = total + sum(max(float(r[x + "_par2"]) for x in possible) for r in missing)
            bounds.append({"policy_id": spec["id"], "unknown_feature_parents": len(missing), "optimistic_full_mean_par2": best/len(rows), "pessimistic_full_mean_par2": worst/len(rows),
                           "scope": "bounds only, not an evaluated original policy"})
    vbs = [min(float(r[x + "_par2"]) for x in ACTIONS) for r in rows]
    all_scores.append({**all_scores[0], "policy_id": "VBS", "policy_sha256": None, "mean_par2_s": sum(vbs)/len(rows),
                       "relative_gain_vs_D": 1-sum(vbs)/sum(float(r["D_par2"]) for r in rows),
                       "solved": sum(min(float(r[x+"_par2"]) for x in ACTIONS) < 1200 for r in rows), "selected_D": None, "selected_Fplus": None, "selected_Fminus": None,
                       "helped_parents": sum(v < float(r["D_par2"]) for v,r in zip(vbs,rows)), "harmed_parents": 0, "scope": "FULL4719_ORACLE_NOT_POLICY"})
    csvwrite(a.out / "scores.csv", all_scores); csvwrite(a.out / "predictions.csv", prediction_rows); dump(a.out / "missing_feature_bounds.json", bounds)
    summary = {"scope": "EXPLORATORY_TRANSFER_NO_REFIT_NO_DEPLOYMENT", "data": "official_all_tracks_unsolved_v1 retained4719 T600 seed0",
               "source_evaluation_commit": "0d82f6ed932e3f5ad0bde8d96d847dadc9ee8aa0", "covered_structure_parents": len(vectors), "new_solver_calls": 0, "new_fit": False,
               "cost": "Features treated as free for optimistic replay, not measured zero. Actual runtime/deployment net cost unmeasured.", "scores": all_scores,
               "feature_mapping": {"s_mean_length": "vcg_cdegree_mean: raw literals per original clause", "s_binary_fraction": "cls2/clauses", "s_long_fraction": "(cls5+cls6+cls7+cls8+cls9+cls10p)/clauses"},
               "graph_feature": "Unavailable: raw literal occurrences are not necessarily distinct variable-clause incidences; no approximation inserted.",
               "old_cache_crosschecks": len(source_comparisons), "gbd_url": "https://benchmark-database.de/getdatabase/base", "gbd_db_sha256": sha(a.db),
               "registry_sha256": sha(registry_path), "matrix_sha256": sha(matrix_path), "policy_interpreter_sha256": sha(policy_source), "analysis_source_sha256": sha(__file__),
               "process_cpu_s": time.process_time()-cpu, "wall_s": time.monotonic()-start}
    dump(a.out / "summary.json", summary)
    body = "".join("<tr>" + "".join("<td>"+html.escape(str(v))+"</td>" for v in [r["policy_id"], r["covered_parents"], f'{r["mean_par2_s"]:.3f}' if r["mean_par2_s"] is not None else "未评分",
                      f'{r["relative_gain_vs_D"]:+.2%}' if r["relative_gain_vs_D"] is not None else "—", r["solved"], r["scope"]]) + "</tr>" for r in all_scores)
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>旧policy在Anniversary4719上的冻结回放</title><style>body{font:16px/1.6 system-ui;color:#172a3c;background:#f4f6f9}main{max-width:1200px;margin:35px auto;padding:28px;background:white;border-radius:14px}table{border-collapse:collapse;font-size:14px;width:100%}td,th{padding:9px;border-bottom:1px solid #dde4eb;text-align:right}td:first-child,th:first-child{text-align:left}a{color:#315c9b}</style><main><h1>旧policy原样迁移：4719题T600</h1><p>不调整阈值或动作，不训练新模型，不重跑SAT。正收益表示优于固定D；负值表示变差。特征免费是乐观回放，不是部署收益。</p><table><tr><th>冻结policy</th><th>覆盖题数</th><th>平均PAR2/秒</th><th>相对同集合D的收益</th><th>解出</th><th>口径</th></tr>'''+body+'''</table><p>legacy_round1_length_stump：平均子句长≤3.67724选D，否则F−。legacy_round1_binary_stump：二元比例≤0.362327选F+，否则D。</p><p>formal_round2_0（保留的失败候选）：长度≥5的子句比例≤0.00977806038068选F+，否则D。formal_round4_0/_1：阈值0.024555309337，其余相同。formal_round3_0：cycle excess per distinct incidence≤0.495248812203选F+，否则D；本次缺该精确特征，不以原始文字数冒充。其余formal候选退化为固定F+。</p><p>公开GBD原始子句统计用于只读特征复用；old138缓存中可对照的平均长度与二元比例共276项一致。当前GBD快照未附提取版本身份，映射是根据公开源代码与交集检查建立，原始集群输入receipt未重新核验。</p><p>TA的MiniSAT true/false策略没有已验证的CaDiCaL动作映射；前缀切换/条件子题策略没有兼容轨迹/延续列，因此不混算。I−没有本次基线列，不声称超过该对照。</p><p><a href="scores.csv">汇总CSV</a> · <a href="predictions.csv">逐题动作与得失</a> · <a href="features.csv">实际结构输入</a> · <a href="summary.json">来源及口径</a> · <a href="missing_feature_bounds.json">未评分候选的成本界</a> · <a href="https://udopia.github.io/gbdc/doc/extractors/CNFBaseFeatures.html">GBD特征定义</a></p><p>全部为已曝光开发数据；单seed，非独立测试。费用与最终策略验证另计。</p></main></html>'''
    (a.out / "report.html").write_text(page)
    for r in all_scores:
        print(json.dumps({k:r[k] for k in ["policy_id","covered_parents","mean_par2_s","relative_gain_vs_D","solved","selected_D","selected_Fplus","selected_Fminus","scope"]}, ensure_ascii=False))


if __name__ == "__main__": main()
