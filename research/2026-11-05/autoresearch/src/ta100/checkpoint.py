"""Append actual completed rounds and render progress. No model/solver work."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checkpoint(root, report):
    root = Path(root)
    history = root / "history.jsonl"
    old = [json.loads(line) for line in history.read_text().splitlines()] if history.exists() else []
    known = {x["round"]: x for x in old}
    if len(known) != len(old):
        raise ValueError("duplicate round history")
    records, blocks, fees, model_cpu = {}, [], {}, 0.0
    for complete in sorted(root.glob("B[0-9][0-9]/COMPLETE.json")):
        block = json.loads(complete.read_text())
        if block.get("status") != "COMPLETE" or block.get("terminal_rounds") != 10:
            raise ValueError("only complete10-round blocks can checkpoint")
        members = block["members"]
        items = sorted(complete.parent.glob("I[0-9][0-9][0-9]/result.json"))
        if len(items) != 10:
            raise ValueError("completed block lacks10 results")
        for path in items:
            digest = sha(path)
            if members.get(str(path.relative_to(complete.parent))) != digest:
                raise ValueError("round differs from completion binding")
            r = json.loads(path.read_text())
            metrics = r.get("evaluation", {}).get("metrics", {})
            entry = {"round": path.parent.name, "block": complete.parent.name,
                     "proposal": r["proposal"], "status": r["status"],
                     "primary_gain": metrics.get("relative_improvement"),
                     "primary_improvement95": metrics.get("bootstrap", {}).get("improvement_95"),
                     "used_new_columns": r.get("used_new_columns", []),
                     "coverage": r.get("coverage", {}), "result_path": str(path),
                     "result_sha256": digest, "process_cpu_s": r.get("process_cpu_s")}
            identifier = entry["round"]
            if identifier in records:
                raise ValueError("round appears in multiple blocks")
            if identifier in known and known[identifier]["result_sha256"] != digest:
                raise ValueError("append-only history would change a completed round")
            diagnostic_kinds = {d.get("kind") for d in r.get("numeric_diagnostics_fit_only", [])}
            if row_kind := ("无观测" if "no_observation" in diagnostic_kinds else
                            "训练中恒定" if "observed_constant" in diagnostic_kinds else
                            "被选中" if entry["used_new_columns"] else "可变但未选中"):
                entry["interpretation"] = row_kind
            records[identifier] = entry
            fold_metrics = [f["vs_static_control"]["metrics"] for f in r.get("fit_group_cv", [])]
            cv_reference = sum(f["baseline_total_cost_s"] for f in fold_metrics)
            entry["fit_group_cv_gain"] = (1 - sum(f["policy_total_cost_s"] for f in fold_metrics) / cv_reference
                                           if cv_reference else None)
        blocks.append(complete.parent.name)
        model_cpu += block.get("analysis_cpu_s_known", 0)
        feature_sha = block["bindings"]["features_sha256"]
        fee = block.get("cost_summary_shared_once", {})
        if not fee:
            # Legacy block02 used physical_costs instead of cost_summary; preserve
            # its immutable result, recover accounting from the bound raw table.
            for source in root.glob("features*.json"):
                if sha(source) == feature_sha:
                    payload = json.loads(source.read_text())
                    fee = payload.get("cost_summary", payload.get("physical_costs", {}))
                    break
        fees[feature_sha] = fee
    if set(known) - set(records):
        raise ValueError("previously checkpointed results disappeared")
    with history.open("a") as stream:
        for identifier, entry in sorted(records.items()):
            if identifier not in known:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    state_path = root / "STATE.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    remaining = [f"B{i:02d}" for i in range(1, 11) if f"B{i:02d}" not in blocks]
    next_action = (f"Execute frozen {remaining[0]} using its complete bound feature table; preserve gate/test seal."
                   if remaining else "Finalize100-round catalogue, costs and exploratory conclusions; no further scores.")
    terminal = not remaining and state.get("status") == "COMPLETE_SCOPED_NEGATIVE"
    if terminal:
        next_action = state["next_action"]
    state.update(status="ACTIVE" if remaining else state["status"] if terminal else "ANALYSIS_COMPLETE_REPORT_PENDING", target_rounds=100, completed_rounds=len(records),
                 completed_blocks=blocks, workflow_revisions=len(list(Path("refine-logs/ta100").glob("workflow_revision_*.md"))),
                 model_job_CPU_s_known=model_cpu, feature_table_costs_once=fees,
                 no_gate_or_test_evaluation=True, next_action=next_action)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    text = ["# TA100迭代记录", "", f"已完成 **{len(records)}/100** 轮；workflow复盘 **{state['workflow_revisions']}/10**。",
            "主收益为相对旧10项静态树的增量；所有比较仍是重复开发探索，gate/test禁止使用。", "",
            "|轮次|机制|fit/feedback可观测数|结果解释|fit组外CV增量|feedback增量|状态|", "|---|---|---|---|---:|---:|---|"]
    for identifier, row in sorted(records.items()):
        gain = row["primary_gain"]
        value = "未评分" if gain is None else f"{100*gain:+.4f}%"
        mechanism = row["proposal"].get("mechanism_key", "")
        cov = row.get("coverage", {})
        nfit = min(cov.get("development_fit", {}).values(), default=0)
        nfeedback = min(cov.get("development_feedback", {}).values(), default=0)
        cv_gain = row.get("fit_group_cv_gain")
        cv_text = "未评分" if cv_gain is None else f"{100*cv_gain:+.4f}%"
        text.append(f"|{identifier}|{mechanism}|{nfit}/180；{nfeedback}/60|{row['interpretation']}|{cv_text}|{value}|{row['status']}|")
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(text) + "\n")
    tracker = ["# TA100执行跟踪", "", f"状态：{state['status']}；{len(records)}/100实测轮；"
               f"{state['workflow_revisions']}/10 workflow复盘。Owner root。", "",
               "本表由正式完成标记和冻结配置生成；STATE.json是机器状态入口。", "",
               "|块|轮号|状态|冻结机制|", "|---|---|---|---|"]
    for i in range(1, 11):
        bid = f"B{i:02d}"
        config = Path("configs/ta100") / (bid + ".json")
        rounds = json.loads(config.read_text()).get("rounds", []) if config.exists() else []
        tracker.append(f"|{bid}|{10*i-9:03d}–{10*i:03d}|{'COMPLETE' if bid in blocks else 'FROZEN_PENDING'}|"
                       + ", ".join(r['registry_id'] for r in rounds) + "|")
    tracker += ["", "下一动作：" + next_action, "", "原gate已消费，本阶段禁止使用；5355最终测试封存。"]
    Path("refine-logs/ta100/TRACKER.md").write_text("\n".join(tracker) + "\n")
    return {"completed_rounds": len(records), "blocks": blocks, "workflow_revisions": state["workflow_revisions"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="outputs/ta100")
    parser.add_argument("--report", default="reports/ta100/PROGRESS.md")
    args = parser.parse_args()
    print(json.dumps(checkpoint(args.root, args.report)))
