"""Render completed exploratory results; no fitting or solver calls."""
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render():
    root, out = Path("outputs/ta100"), Path("reports/ta100")
    state = json.loads((root / "STATE.json").read_text())
    if state["completed_rounds"] != 100 or state["workflow_revisions"] != 10:
        raise ValueError("final report requires100 actual rounds and10 workflow records")
    rows = []
    for complete in sorted(root.glob("B??/COMPLETE.json")):
        block = json.loads(complete.read_text())
        if block["status"] != "COMPLETE" or block["terminal_rounds"] != 10:
            raise ValueError("incomplete block")
        for path in sorted(complete.parent.glob("I???/result.json")):
            if block["members"].get(str(path.relative_to(complete.parent))) != sha(path):
                raise ValueError("changed formal result")
            r = json.loads(path.read_text())
            proposal_path = path.parent / "proposal.json"
            proposal_export = {"schema": "ta100.frozen_proposal_export.v1", "proposal": r["proposal"],
                "original_preexecution_config": f"configs/ta100/{complete.parent.name}.json",
                "original_config_sha256": r["bindings"]["block_sha256"],
                "registry_sha256": r["bindings"]["registry_sha256"],
                "note": "Post-execution export of original frozen references; not a new preregistration."}
            exported = json.dumps(proposal_export,ensure_ascii=False,indent=2)+"\n"
            if proposal_path.exists() and proposal_path.read_text() != exported:
                raise ValueError("changed proposal export")
            proposal_path.write_text(exported)
            m, fixed = r["evaluation"]["metrics"], r["vs_fixed_control"]["metrics"]
            folds = [f["vs_static_control"]["metrics"] for f in r["fit_group_cv"]]
            cv_base = sum(f["baseline_total_cost_s"] for f in folds)
            ci = m["bootstrap"]["improvement_95"]
            rows.append({"round": path.parent.name, "block": complete.parent.name,
                "mechanism": r["proposal"]["mechanism_key"], "columns": ";".join(r["proposal"]["columns"]),
                "status": r["status"], "new_field_selected": bool(r["used_new_columns"]),
                "fit_observed": min(r["coverage"]["development_fit"].values()),
                "feedback_observed": min(r["coverage"]["development_feedback"].values()),
                "fit_group_cv_gain": 1-sum(f["policy_total_cost_s"] for f in folds)/cv_base,
                "feedback_gain_vs_old_static": m["relative_improvement"],
                "exploratory_ci_low": ci[0], "exploratory_ci_high": ci[1],
                "feedback_gain_vs_fixed_true": fixed["relative_improvement"],
                "switches_vs_old_static": m["switches"], "clear_switches_vs_old_static": m["clear_switches"],
                "worst_loss_TA_cost_s": m["max_regression_s"], "gross_gain_TA_cost_s": m["gross_gain_s"],
                "gross_loss_TA_cost_s": m["gross_loss_s"], "cost_TA_s": m["policy_total_cost_s"],
                "old_static_cost_TA_s": m["baseline_total_cost_s"],
                "diagnostics": ";".join(sorted({x["kind"] for x in r["numeric_diagnostics_fit_only"]})),
                "result_path": str(path), "result_sha256": sha(path)})
    if len(rows) != 100 or {r["round"] for r in rows} != {f"I{i:03d}" for i in range(1,101)}:
        raise ValueError("must contain exact100 terminal rounds")
    ranked = sorted(rows, key=lambda r: (-r["feedback_gain_vs_old_static"], r["round"]))
    out.mkdir(parents=True, exist_ok=True)
    with (out / "LEADERBOARD.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(ranked)
    selected = [r for r in rows if r["new_field_selected"]]
    positive = [r for r in selected if r["feedback_gain_vs_old_static"] > 0]
    low_coverage = [r["round"] for r in rows if r["fit_observed"] < 24]
    constants = [r["round"] for r in rows if "observed_constant" in r["diagnostics"]]
    reference = json.loads(Path("outputs/ta_feature_discovery/TA_R01/matched_simple_tree.json").read_text())["evaluation"]["metrics"]
    headroom = 1-reference["oracle_total_cost_s"]/reference["policy_total_cost_s"]
    summary = {"schema": "ta100.final_summary.v1", "rounds": 100, "workflow_revisions": 10,
        "input_side_structural_or_auxiliary_mechanisms": 70, "native_solver_dynamic_mechanisms": 30,
        "static_label_note": "input-side70 includes bounded auxiliary local-search trajectories RA16/17",
        "fit_observations_below_two_leaf_minimum": low_coverage, "observed_constant_rounds": constants,
        "selected_new_field_rounds": len(selected),
        "positive_selected_rounds": len(positive), "negative_selected_rounds": sum(r["feedback_gain_vs_old_static"]<0 for r in selected),
        "new_field_not_selected_rounds": 100-len(selected),
        "positive_exploratory_interval_lower_bound_rounds": [r["round"] for r in positive if r["exploratory_ci_low"]>0],
        "best_exploratory_round": ranked[0], "no_confirmation_claim": True,
        "feedback_free_oracle_gain_over_old_static": headroom,
        "feedback_clear_parents": reference["clear_parents"],
        "no_gate_or_test_evaluation": True, "state_sha256": sha(root/"STATE.json"),
        "leaderboard_sha256": sha(out/"LEADERBOARD.csv"), "complete_markers": {
            str(p):sha(p) for p in sorted(root.glob("B??/COMPLETE.json"))}}
    (out/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    lines = ["# TA100：100轮相位特征探索结果", "",
        "已完成100轮实际探索评分：70项输入端结构/辅助计算、30项原生求解器轨迹机制；"
        "前70项含两项有界局部搜索轨迹，并非全是纯静态计数。每10轮执行一次workflow修订，共10次。"
        "已消费gate及最终测试均未用于本阶段。", "",
        f"新增字段在{len(selected)}轮进入最终fit策略；其中{len(positive)}轮feedback点估计改善，"
        f"{summary['negative_selected_rounds']}轮变差，{100-len(selected)}轮未被选择。"
        "未入选、恒定、缺失和被选后退化分别记录，不能合称所有特征无用。", "",
        f"其中{len(constants)}列在当前可观测fit上恒定；{len(low_coverage)}列fit观测少于两个12题叶子所需的24题。"
        "后三项理由图机制各只有1题feedback观测，结论是覆盖不足，不能视为充分否定检验。", "",
        "仅复用原180fit/60feedback和TA false/true计时；192合格题采集新字段，完整240父题保留缺失回退。"
        "TIMEOUT按原5000秒预算的PAR2=10000记分，不是真实运行时间。"
        "每轮旧10字段加1个机制、树深至多2、至多2个不同字段，固定5折组外诊断与完整feedback。", "",
        "## 所有被选中的新增机制", "",
        "|轮次|新增字段|fit组外CV增量|feedback相对旧静态增量|探索性95%区间|fit/feedback可观测|最大单题误选成本|",
        "|---|---|---:|---:|---|---|---:|"]
    pct = lambda x: f"{100*x:+.4f}%"
    for r in sorted(selected,key=lambda r:-r["feedback_gain_vs_old_static"]):
        lines.append(f"|{r['round']}|{r['columns']}|{pct(r['fit_group_cv_gain'])}|"
            f"{pct(r['feedback_gain_vs_old_static'])}|[{pct(r['exploratory_ci_low'])}, {pct(r['exploratory_ci_high'])}]|"
            f"{r['fit_observed']}/180；{r['feedback_observed']}/60|{r['worst_loss_TA_cost_s']:.3f}|")
    lines += ["", "## 结论边界", "",
        "主增量参照是冻结的旧10项静态规则。该规则原有的约5.29%开发点估计收益不是新增特征的贡献。"
        "100次重复使用开发反馈后的最高分仍是探索结果；配对区间未校正整个自适应搜索，不能称独立显著或部署成功。", "",
        f"此60题feedback只有{reference['clear_parents']}题有明确方向标签；旧静态成本{reference['policy_total_cost_s']:.3f}、"
        f"免费oracle成本{reference['oracle_total_cost_s']:.3f}，继续改善的理论空间仅{100*headroom:.4f}%。"
        "这是固定面板上的成本上界诊断，不用它改动既定100轮、指标或成功定义。", "",
        "新动态量来自同一CaDiCaL原生D短前缀，用作TA MiniSAT标签的预测变量，存在solver差异；"
        "没有补造D标签，也没有重建完整SAT相位耗时矩阵。新observer独立记录单字段缺失，"
        "2CPU秒含解析及observer计算，早解答案不采纳为新增标签。", "",
        "物理CPU、复用逻辑费用和TA硬件wall单位分别列于[资源账本](RESOURCE_COSTS.md)。"
        "有用的免费预测信号也必须另证其能支付实际提取/探针费用，当前不声称端到端加速。", "",
        "## 可复现记录", "",
        "- [100项定义、来源及去重](FEATURE_CATALOGUE.md)",
        "- [全100轮排序CSV](LEADERBOARD.csv)；[机器摘要](SUMMARY.json)",
        "- [逐轮完整进展与覆盖](PROGRESS.md)",
        "- 冻结协议：`refine-logs/ta100/PROTOCOL.md`；10次修订：`refine-logs/ta100/workflow_revision_01.md` 至 `_10.md`。",
        "- 逐轮原始结果、逐题预测、五折与身份：`outputs/ta100/B01` 至 `B10`。旧结果不覆写；`history.jsonl`追加记录。", "",
        "## 研究来源与自己的推断", "",
        "结构与短探针设计参考[SATzilla官方特征项目](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/)、"
        "[工业SAT社区结构研究](https://arxiv.org/abs/1606.03329)和"
        "[相位选择与chronological backtracking研究](https://arxiv.org/abs/2005.04850)。"
        "这些来源支持候选机制背景，不证明它们在本面板能选择相位；具体有界标量、组合与预测用途属于本次提案。"
        "更多每项来源及语义反例见目录。"]
    (out/"REPORT.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({k:v for k,v in summary.items() if k not in ('best_exploratory_round','complete_markers')},ensure_ascii=False))


if __name__ == "__main__":
    render()
