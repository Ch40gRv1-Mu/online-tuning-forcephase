"""Audit teacher-provided phase observations and protect the Anniversary test pool.

Identifiers and source paths are used only for joins and leakage checks. They
are deliberately separate from the numeric feature contract used by policies.
"""

import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/phase_prediction_v1"
REPORT = ROOT / "reports/phase_prediction_v1"
HASH = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")
URI = re.compile(r"https?://benchmark-database\.de/file/([0-9a-f]{32})")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows, fields):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def summarize(pairs, label):
    group = [r for r in pairs if label in {v["result"] for v in r.values()}]
    result = {"instances": len(group), "both_solved": sum(all(v["result"] == label for v in r.values()) for r in group)}
    if not group:
        return result
    for timing in ["wall_time_s", "cpu_time_s"]:
        rr = [(float(r["false"][timing]), float(r["true"][timing])) for r in group
              if all(r[m][timing] for m in ["false", "true"])]
        result[timing] = {"complete_timing_pairs": len(rr),
                          "true_faster": sum(b < a for a, b in rr),
                          "false_faster": sum(a < b for a, b in rr),
                          "ties": sum(a == b for a, b in rr)}
        for factor in [1.1, 2, 10]:
            # A timeout can support a directional lower-bound comparison, but
            # never substitute for an observed completion time or exact ratio.
            result[timing][f"true_faster_{factor:g}x_observed_or_bound"] = sum(
                float(r["false"][timing]) > factor * float(r["true"][timing])
                for r in group if all(r[m][timing] for m in ["false", "true"])
                and r["true"]["result"] == label)
            result[timing][f"false_faster_{factor:g}x_observed_or_bound"] = sum(
                float(r["true"][timing]) > factor * float(r["false"][timing])
                for r in group if all(r[m][timing] for m in ["false", "true"])
                and r["false"]["result"] == label)
    return result


def main():
    inputs = OUT / "inputs"
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    raw = list(csv.DictReader((inputs / "professor_minisat.csv").open()))
    if not raw:
        raise ValueError("empty professor CSV")
    file_key = "file" if "file" in raw[0] else "ile"
    pairs = defaultdict(dict)
    source_paths = {}
    for r in raw:
        found = HASH.findall(r[file_key])
        if len(found) != 1 or r["polarity_mode"] not in ["false", "true"]:
            raise ValueError("invalid identifier or mode")
        h = found[0]
        mode = r["polarity_mode"]
        if mode in pairs[h]:
            raise ValueError(f"duplicate observation: {h}/{mode}")
        if r["result"] not in ["SAT", "UNSAT", "TIMEOUT"]:
            raise ValueError("unknown result")
        for timing in ["wall_time_s", "cpu_time_s"]:
            if r[timing] and (not math.isfinite(float(r[timing])) or float(r[timing]) < 0):
                raise ValueError("invalid timing")
        pairs[h][mode] = r
        source_paths[h] = r[file_key]
    if any(set(rr) != {"false", "true"} for rr in pairs.values()):
        raise ValueError("incomplete pair")
    if any({r["result"] for r in rr.values()} == {"SAT", "UNSAT"} for rr in pairs.values()):
        raise ValueError("inconsistent SAT/UNSAT answers")
    urls = [s.strip() for s in (inputs / "track_anni_2022.uri").read_text().splitlines() if s.strip()]
    if not all(URI.fullmatch(u) for u in urls):
        raise ValueError("unexpected test URI; never execute attached URI text")
    test = {URI.fullmatch(u).group(1) for u in urls}
    if len(test) != len(urls):
        raise ValueError("duplicate test candidate")

    # Opaque historical identifier scan: no application/family metadata is used.
    # New inputs and this audit's own manifests must never mark the whole test
    # pool as historical exposure merely because their URI list was copied.
    historical = set()
    scanned = []
    for folder in [ROOT / "results", ROOT / "output/figures", ROOT / "output/reports"]:
        for path in sorted(folder.rglob("*")) if folder.exists() else []:
            if not path.is_file() or path.suffix not in {".csv", ".json", ".jsonl"}:
                continue
            if OUT in path.parents:
                continue
            text = path.read_text(errors="replace")
            ids = set(HASH.findall(text))
            historical.update(ids)
            scanned.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
                            "test_identifier_matches": len(ids & test)})
    old_man = list(csv.DictReader((ROOT / "benchmarks/manifest.csv").open()))
    legacy_used = {r["hash"] for r in old_man if r["split"] != "excluded"}
    historical.update(legacy_used)
    exposed = (historical | set(pairs)) & test
    clean = test - exposed
    data = {
        "date": "2026-11-03", "original_solver_code": "not provided",
        "source_sha256": {p.name: sha(p) for p in inputs.iterdir() if p.is_file()},
        "header_normalization": {file_key: "file_identifier_only"},
        "professor_rows": len(raw), "professor_instances": len(pairs),
        "results": dict(Counter(r["result"] for r in raw)),
        "missing_cpu_rows": sum(not r["cpu_time_s"] for r in raw),
        "double_timeouts": sum(all(r["result"] == "TIMEOUT" for r in rr.values()) for rr in pairs.values()),
        "per_mode": {m: dict(Counter(rr[m]["result"] for rr in pairs.values())) for m in ["false", "true"]},
        "SAT": summarize(list(pairs.values()), "SAT"),
        "UNSAT": summarize(list(pairs.values()), "UNSAT"),
        "test_candidates": len(test), "professor_test_overlap": len(set(pairs) & test),
        "legacy_manifest_test_overlap": len(legacy_used & test),
        "historical_and_professor_exposed_test": len(exposed),
        "provisional_clean_exact_hash": len(clean),
        "professor_development_outside_test": len(set(pairs) - test),
        "canonical_equivalence_status": "PENDING; exact-hash separation does not establish absence of renamed/equivalent duplicates",
        "historical_sources": scanned,
        "warnings": ["timeouts are censored; do not calculate exact speedup using their wall values",
                     "CPU timing is incomplete, including some solved rows",
                     "source code, compiler, seed and execution commands are unavailable",
                     "SAT/UNSAT strata are descriptive and are forbidden deployment inputs",
                     "CSV terminal search statistics are outcomes, not valid pre-action features"],
    }
    (OUT / "input_audit.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    write_csv(OUT / "exposed_identifiers.csv", [{"hash": h} for h in sorted(historical | set(pairs))], ["hash"])
    candidates = []
    for h in sorted(test):
        reasons = []
        if h in pairs:
            reasons.append("professor_csv_exposed")
        if h in historical:
            reasons.append("historical_identifier_exposed")
        candidates.append({"hash": h, "url": f"https://benchmark-database.de/file/{h}",
                           "role": "exposed_diagnostic" if reasons else "protected_candidate",
                           "reason": ";".join(reasons)})
    fields = ["hash", "url", "role", "reason"]
    write_csv(OUT / "test_candidates.csv", candidates, fields)
    write_csv(OUT / "test_exposed.csv", [r for r in candidates if r["role"] == "exposed_diagnostic"], fields)
    write_csv(OUT / "test_provisional_clean.csv", [r for r in candidates if r["role"] == "protected_candidate"], fields)
    write_csv(OUT / "development_candidates.csv", [
        {"hash": h, "url": f"https://benchmark-database.de/file/{h}", "role": "development"}
        for h in sorted(set(pairs) - test)], ["hash", "url", "role"])
    write_csv(OUT / "professor_pairs.csv", [
        {"hash": h, "role": "exposed_diagnostic" if h in test else "development",
         "false_result": rr["false"]["result"], "true_result": rr["true"]["result"],
         "false_wall_s": rr["false"]["wall_time_s"], "true_wall_s": rr["true"]["wall_time_s"],
         "false_cpu_s": rr["false"]["cpu_time_s"], "true_cpu_s": rr["true"]["cpu_time_s"]}
        for h, rr in sorted(pairs.items())],
        ["hash", "role", "false_result", "true_result", "false_wall_s", "true_wall_s", "false_cpu_s", "true_cpu_s"])
    sat, unsat = data["SAT"], data["UNSAT"]
    lines = ["# 教授 MiniSAT 数据及测试集隔离审计", "", "日期：2026-11-03。状态：仅附件描述性审计，不是求解器复现。", "",
             f"CSV 共 {len(raw)} 行、{len(pairs)} 个完整 false/true 配对；{data['double_timeouts']} 对双超时。",
             f"图中 SAT n={sat['instances']}、UNSAT n={unsat['instances']} 与 CSV 至少一侧 solved 的实例数一致。", "",
             "| 原始标签 | SAT solved | UNSAT solved | TIMEOUT |", "|---|---:|---:|---:|"]
    for m in ["false", "true"]:
        counts = data["per_mode"][m]
        lines.append(f"| {m} | {counts.get('SAT',0)} | {counts.get('UNSAT',0)} | {counts.get('TIMEOUT',0)} |")
    lines += ["", f"CPU 字段缺失 {data['missing_cpu_rows']}/{len(raw)}，不能把所有缺失值当作 5000 CPU 秒。",
              "false/true 标签未获源代码核实，不能未经验证映射为 CaDiCaL F−/F+ 或真实赋值符号。", "",
              "| 至少一侧 solved 的分层 | true 至少快 2× | false 至少快 2× | true 至少快 10× | false 至少快 10× |",
              "|---|---:|---:|---:|---:|"]
    for name, group in [("SAT", sat), ("UNSAT", unsat)]:
        r = group["wall_time_s"]
        lines.append(f"| {name} | {r['true_faster_2x_observed_or_bound']} | {r['false_faster_2x_observed_or_bound']} | {r['true_faster_10x_observed_or_bound']} | {r['false_faster_10x_observed_or_bound']} |")
    lines += ["", "若慢侧超时，上表只表示速度差的下界。不能从这些选择性完成样本推断所有公式的精确平均加速。",
              "UNSAT 上 true 的 2× 获益更集中；SAT 上两端都有重要反例，不能直接制定‘SAT 选 false’规则。", "",
              f"2022 Anniversary：{len(test)} 个候选；教授 CSV 重叠 {data['professor_test_overlap']}；旧 manifest 已用实例重叠 {data['legacy_manifest_test_overlap']}。",
              f"合并历史标识扫描后隔离 {len(exposed)} 个已曝光候选；剩余 {len(clean)} 个仅通过 exact-hash 检查，仍须等价去重。",
              f"教授 CSV 中 {data['professor_development_outside_test']} 个实例在整个测试候选集之外，可作为开发候选。", "",
              "整个测试候选集（含已曝光部分）均不得参与开发、policy 更新或阈值选择。已曝光部分只在冻结后作为诊断集单列。",
              "不得把 filename/hash/year/family/author/URI、SAT/UNSAT 真值或终局统计作为模型特征。", ""]
    (REPORT / "INPUT_AUDIT.md").write_text("\n".join(lines))
    print(json.dumps({k: data[k] for k in ["professor_rows", "professor_instances", "double_timeouts", "test_candidates", "historical_and_professor_exposed_test", "provisional_clean_exact_hash", "professor_development_outside_test"]}))


if __name__ == "__main__":
    main()
