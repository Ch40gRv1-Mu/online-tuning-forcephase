"""Export existing policy rankings and rules; never fit or score a model."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def leaves(node, conditions=()):
    if "action" in node:
        return [(conditions, node["action"])]
    f, t = node["feature"], repr(node["threshold"])
    return leaves(node["left"], conditions+(f"{f} <= {t}",)) + leaves(
        node["right"], conditions+(f"{f} > {t}",))


def main():
    records = list(csv.DictReader((OUT/"LEADERBOARD.csv").open()))
    catalogue = json.loads((OUT/"FEATURE_CATALOGUE.json").read_text())
    definitions = {column: {k: c[k] for k in ("plain_definition", "formula", "conditioning")}
                   for c in catalogue["candidates"] for column in c["columns"]}
    groups, ordered = {}, []
    for row in records:
        source = ROOT / row["result_path"]
        if sha(source) != row["result_sha256"]:
            raise ValueError("source result differs from existing ranking identity")
        r = json.loads(source.read_text())
        policy = {k: r["policy"].get(k) for k in ("baseline_action", "tree", "fallback_policy", "required_dynamic_features")}
        if policy["fallback_policy"] is not None:
            raise ValueError("this export expects the observed no-nested-fallback policies")
        key = json.dumps(policy,sort_keys=True,separators=(",", ":"))
        if key not in groups:
            g = {"rank": len(ordered)+1, "representative_round": row["round"], "members": [],
                "policy": policy, "gain_vs_old_static": float(row["feedback_gain_vs_old_static"]),
                "gain_vs_fixed_true": float(row["feedback_gain_vs_fixed_true"]),
                "exploratory_interval95_vs_old_static": [float(row["exploratory_ci_low"]),float(row["exploratory_ci_high"])],
                "result_path": row["result_path"], "result_sha256": row["result_sha256"],
                "fit_group_cv_gain": float(row["fit_group_cv_gain"])}
            groups[key] = g; ordered.append(g)
        groups[key]["members"].append(row["round"])
    payload = {"schema": "ta100.top10_distinct_policies.v1", "unique_policy_count": len(ordered),
        "source_ranking_sha256": sha(OUT/"LEADERBOARD.csv"),
        "ranking": "Existing full60 exploratory feedback gain vs frozen old static policy; exact functional-tree duplicates merged, preserving existing order.",
        "cost_note": "PAR2 on TA timing scale; acquisition cost excluded, no new evaluation.",
        "missing": "Resource-ineligible or missing/nonfinite required feature on reached branch => true.",
        "feature_definitions": definitions, "policies": ordered[:10]}
    (OUT/"TOP10_POLICIES.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    parts = ["# 前10种不同策略", "", "从已有100轮排名只读导出；88轮产生同一旧静态规则，合并后共有13种不同规则。没有重新拟合、评分或开启gate/test。", "",
        "按同一60题开发反馈上的成本增量排序；成本含PAR2超时罚分，未扣提取/探针费用。以下为原始精度阈值。", "",
        "所有策略：资源资格不满足，或当前实际访问分支所需字段缺失/非有限时，返回phase=true；不默认回退另一棵静态树。", "",
        "基础字段：s_positive_fraction=正文字出现占比；s_mean_length=平均子句长度；s_length_std=子句长度标准差；g_cycle_excess_per_incidence=按incidence归一化环冗余。", ""]
    for g in ordered[:10]:
        parts += [f"## {g['rank']}. {g['representative_round']}"+(f"（{len(g['members'])}轮相同规则）" if len(g['members'])>1 else ""), "",
            f"相对旧静态：{100*g['gain_vs_old_static']:+.4f}%；相对固定true：{100*g['gain_vs_fixed_true']:+.4f}%。", ""]
        used = set()
        for conditions, action in leaves(g["policy"]["tree"]):
            parts.append("- `"+" and ".join(conditions)+f"` → **{action}**")
            for condition in conditions:
                used.add(condition.split()[0])
        for column in sorted(used & definitions.keys()):
            d = definitions[column]
            parts += ["", f"`{column}`：{d['plain_definition']}", "", f"公式：`{d['formula']}`；条件：{d['conditioning']}。"]
        parts += ["", f"原始结果：`{g['result_path']}`；SHA256：`{g['result_sha256']}`。", ""]
    (OUT/"TOP10_POLICIES.md").write_text("\n".join(parts)+"\n")
    data = json.dumps(ordered[:10],ensure_ascii=False,indent=2)
    code = '''"""Exact existing top10 policy trees. Features must use original extractor definitions.
Acquisition is external; no claim of end-to-end benefit. Rank includes old static.
"""
import json
import math

POLICIES = json.loads(r\'\'\'\n'''+data+'''\n\'\'\')

def choose_phase(rank, features, eligible=True):
    if type(rank) is not int or not 1 <= rank <= 10:
        raise ValueError("rank must be1..10")
    policy = POLICIES[rank-1]["policy"]
    if not eligible:
        return policy["baseline_action"]
    node = policy["tree"]
    while "action" not in node:
        value = features.get(node["feature"])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return policy["baseline_action"]
        node = node["left"] if value <= node["threshold"] else node["right"]
    return node["action"]
'''
    compile(code,"top10_policies.py","exec")
    (OUT/"top10_policies.py").write_text(code)
    print(json.dumps({"unique_policies":len(ordered),"top10":[g['representative_round'] for g in ordered[:10]],"same_old_policy_rounds":len(ordered[1]['members'])}))


if __name__ == "__main__":
    main()
