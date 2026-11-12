"""Render the professor's baseline figures from a published complete evaluation.

No solver calls, input selection, fitting or smoothing. The source checkout is
read only; all new figures and byte-identical CSV copies go to --out.
"""
import argparse
import base64
import collections
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import shutil
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

ACTIONS = ("D", "Fplus", "Fminus")
LABEL = {"D": "D", "Fplus": "F+", "Fminus": "F−", "VBS": "VBS"}
COLORS = {"D": "#315c9b", "Fplus": "#20816b", "Fminus": "#d28132", "VBS": "#172a3c"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_and_check(repo):
    snap = repo / "outputs/anniversary2022_baseline/cluster_v3/analysis"
    summary = json.loads((snap / "summary.json").read_text())
    assert summary["status"] == "COMPLETE_VALID_MATRIX"
    T = summary["cutoff_s"]
    matrix = list(csv.DictReader((snap / "matrix.csv").open()))
    runs = list(csv.DictReader((snap / "runs.csv").open()))
    manifest = list(csv.DictReader((repo / "configs/anniversary2022_baseline/manifest.official-solvable.v1.csv").open()))
    # Association only: identities and answers never become selection features.
    ids = {r["instance_key"] for r in matrix}
    manifest_key = "instance_key" if "instance_key" in manifest[0] else "hash"
    assert ids == {r[manifest_key] for r in manifest}
    assert len(ids) == len(matrix) == summary["full_cohort"] == 4719
    assert len(runs) == summary["valid_runs"] == summary["expected_runs"] == len(ids) * 3
    indexed = {}
    for r in runs:
        key = (r["instance_key"], r["action"])
        assert key not in indexed and r["seed"] == "0"
        solved = r["resolved"] == "True"
        assert (solved and r["status"] in {"SAT", "UNSAT"}) or r["status"] == "CPU_TIMEOUT"
        if solved:
            assert r["verification_status"] == ("VERIFIED_MODEL" if r["status"] == "SAT" else "VERIFIED_LRAT")
            assert 0 <= float(r["cpu_s"]) <= T
        assert (r["conflicts"] != "" and int(r["conflicts"]) >= 0) or not solved
        indexed[key] = r
    cases = []
    for r in matrix:
        assert r["complete"] == "True"
        c = {"id": r["instance_key"], "outcomes": {}}
        for a in ACTIONS:
            v = indexed[(c["id"], a)]
            assert r[a + "_status"] == v["status"]
            assert float(r[a + "_cpu_s"]) == float(v["cpu_s"])
            assert r[a + "_conflicts"] == v["conflicts"]
            c["outcomes"][a] = {"solved": v["resolved"] == "True", "cpu_s": float(v["cpu_s"]),
                                    "conflicts": int(v["conflicts"]) if v["conflicts"] else None,
                                    "par2": float(v["par2"]), "status": v["status"]}
        answers = {x["status"] for x in c["outcomes"].values() if x["solved"]}
        assert len(answers) <= 1
        cases.append(c)
    curves = {}
    for metric in ("cpu_s", "conflicts"):
        d = {a: sorted(c["outcomes"][a][metric] for c in cases if c["outcomes"][a]["solved"]) for a in ACTIONS}
        d["VBS"] = sorted(min(x[metric] for x in c["outcomes"].values() if x["solved"])
                          for c in cases if any(x["solved"] for x in c["outcomes"].values()))
        curves[metric] = d
    published = json.loads((snap / "curve_data.json").read_text())
    assert all(curves[m][a] == sorted(published[m][a]) for m in curves for a in (*ACTIONS, "VBS"))
    for a in ACTIONS:
        assert len(curves["cpu_s"][a]) == summary["solved"][a]
        assert math.isclose(sum(c["outcomes"][a]["par2"] for c in cases) / len(cases), summary["mean_par2"][a], rel_tol=1e-12)
    assert len(curves["cpu_s"]["VBS"]) == summary["solved_union"]
    return snap, summary, cases, curves


def save(fig, out, name):
    fig.savefig(out / (name + ".png"), dpi=180, facecolor="white")
    fig.savefig(out / (name + ".pdf"), facecolor="white")
    fig.savefig(out / (name + ".svg"), facecolor="white")
    plt.close(fig)


def cumulative(out, summary, curves, metric):
    fig, ax = plt.subplots(figsize=(10.6, 6.4))
    fig.subplots_adjust(left=.095, right=.96, top=.82, bottom=.17)
    fig.text(.095, .94, "2022 Anniversary · CaDiCaL raw baseline", fontsize=19, weight="bold", color="#172a3c")
    fig.text(.095, .89, "4,719 retained formulas  ·  D / F+ / F−  ·  seed 0  ·  600 CPU-second limit", fontsize=10.5, color="#526273")
    data = curves[metric]
    endpoint = summary["cutoff_s"] if metric == "cpu_s" else max(max(v) for v in data.values()) * 1.1
    for a in (*ACTIONS, "VBS"):
        xs, counts = np.unique(data[a], return_counts=True)
        ys = counts.cumsum()
        ax.step(np.r_[0, xs, endpoint], np.r_[0, ys, len(data[a])], where="post", color=COLORS[a],
                linewidth=2.3 if a in {"D", "VBS"} else 1.9, linestyle="--" if a == "VBS" else "-",
                label=f"{LABEL[a]}  ·  {len(data[a]):,} solved", zorder=5 if a == "VBS" else 3)
    ax.set_ylim(0, summary["full_cohort"])
    ax.set_yticks([0, 1000, 2000, 3000, 4000, 4719], ["0", "1,000", "2,000", "3,000", "4,000", "4,719"])
    ax.set_xlim(0, endpoint)
    ax.set_ylabel("Number of verified instances solved", labelpad=10)
    if metric == "cpu_s":
        ax.set_xlabel("Solver CPU time per instance (seconds)", labelpad=10)
        ax.set_xticks([0, 60, 120, 240, 360, 480, 600])
    else:
        ax.set_xscale("symlog", linthresh=1)
        ticks = [0, 1, 10, 100, 1000, 10000, 100000, 1000000, 10000000]
        ax.set_xticks(ticks, ["0", "1", "10", "100", "1k", "10k", "100k", "1m", "10m"])
        ax.set_xlabel("Conflicts to a verified solution (symlog scale; zero retained)", labelpad=10)
    ax.grid(alpha=.17)
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="#dde4eb", fontsize=10.5, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    footer = ("VBS chooses the fastest verified action separately for each formula. It is an oracle, not a deployed policy."
              if metric == "cpu_s" else
              "Only solutions verified within 600 CPU seconds contribute. Conflict-VBS minimizes conflicts, independently of time-VBS.")
    fig.text(.095, .055, footer, fontsize=9, color="#526273")
    fig.text(.095, .025, "Official all-track-unsolved filter: 636 excluded from the preserved 5,355-formula master. No smoothing or fitted model.", fontsize=8.3, color="#637286")
    save(fig, out, "cumulative_" + metric)


def scatter(out, cases, metric):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))
    fig.subplots_adjust(left=.055, right=.985, top=.78, bottom=.21, wspace=.27)
    fig.text(.055, .95, "Raw paired measurements · 4,719 formulas", fontsize=19, weight="bold", color="#172a3c")
    is_time = metric == "cpu_s"
    fig.text(.055, .90, "One dot = one formula. Ratio lines are 1× / 2× / 10× in both directions. 600 CPU-second limit.", fontsize=10.5, color="#526273")
    pair_counts = {}
    for ax, (a, b) in zip(axes, itertools.combinations(ACTIONS, 2)):
        both = [c for c in cases if c["outcomes"][a]["solved"] and c["outcomes"][b]["solved"]]
        only_a = [c for c in cases if c["outcomes"][a]["solved"] and not c["outcomes"][b]["solved"]]
        only_b = [c for c in cases if c["outcomes"][b]["solved"] and not c["outcomes"][a]["solved"]]
        neither = len(cases) - len(both) - len(only_a) - len(only_b)
        pair_counts[a + "_vs_" + b] = {"both_solved": len(both), "only_" + a: len(only_a), "only_" + b: len(only_b), "neither_solved": neither}
        maximum = 600 if is_time else max(max(c["outcomes"][a][metric], c["outcomes"][b][metric]) for c in both) * 1.1
        lo = .005 if is_time else 0
        values = np.geomspace(.005 if is_time else 1e-3, maximum, 1000)
        for f, style in [(1, "-"), (2, "--"), (.5, "--"), (10, ":"), (.1, ":")]:
            y = f * values
            mask = (y <= maximum) & (y >= lo)
            ax.plot(values[mask], y[mask], style, color="#8793a3", lw=.7, zorder=1)
        ax.scatter([c["outcomes"][a][metric] for c in both], [c["outcomes"][b][metric] for c in both], s=10, alpha=.4, c="#315c9b", edgecolors="none", rasterized=True, zorder=2)
        if is_time:
            rail = 900
            ax.axhspan(650, 1100, color="#f0f3f6", zorder=0)
            ax.axvspan(650, 1100, color="#f0f3f6", zorder=0)
            ax.scatter([c["outcomes"][a][metric] for c in only_a], [rail] * len(only_a), marker="^", s=17, alpha=.55, color="#20816b", edgecolors="none", rasterized=True)
            ax.scatter([rail] * len(only_b), [c["outcomes"][b][metric] for c in only_b], marker=">", s=17, alpha=.55, color="#d28132", edgecolors="none", rasterized=True)
            ax.scatter([rail], [rail], marker="x", s=30, color="#172a3c")
            ax.set_xscale("log"); ax.set_yscale("log")
            ticks = [.01, .1, 1, 10, 100, 900]
            ax.set_xticks(ticks, ["0.01", "0.1", "1", "10", "100", "TO"])
            ax.set_yticks(ticks, ["0.01", "0.1", "1", "10", "100", "TO"])
            maximum = 1100
        else:
            ax.set_xscale("symlog", linthresh=1); ax.set_yscale("symlog", linthresh=1)
        ax.set(xlim=(lo, maximum), ylim=(lo, maximum), xlabel=LABEL[a] + (" CPU seconds" if is_time else " conflicts"),
               ylabel=LABEL[b] + (" CPU seconds" if is_time else " conflicts"))
        ax.set_title(f"{LABEL[a]} vs {LABEL[b]}\nBoth solved: {len(both):,}", fontsize=12)
        ax.grid(alpha=.15)
        ax.text(.02, -.24, f"Only {LABEL[a]}: {len(only_a)}  ·  only {LABEL[b]}: {len(only_b)}  ·  neither: {neither:,}", transform=ax.transAxes, fontsize=8.2, color="#526273")
        ax.set_aspect("equal", adjustable="box")
    foot = ("Circles: both solved. ▲ / ▶: only one solved. TO is a categorical timeout rail, not a measured solve time; neither-solved counts shown below each panel."
            if is_time else "Conflicts panels show both-solved pairs only. One-sided and neither-solved counts are explicit; timeout conflicts are not solution costs.")
    fig.text(.055, .025, foot, fontsize=9, color="#526273")
    save(fig, out, "scatter_" + metric)
    return pair_counts


def main():
    p = argparse.ArgumentParser(); p.add_argument("--repo", type=Path, required=True); p.add_argument("--out", type=Path, required=True); a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    snap, s, cases, curves = load_and_check(a.repo)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.labelcolor": "#344658", "xtick.color": "#526273", "ytick.color": "#526273", "pdf.fonttype": 42})
    for metric in ("cpu_s", "conflicts"):
        cumulative(a.out, s, curves, metric)
        pairs = scatter(a.out, cases, metric)
    for name in ("matrix.csv", "runs.csv"):
        shutil.copyfile(snap / name, a.out / name)
    dump(a.out / "curve_data.json", curves)
    with (a.out / "curve_points.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["metric", "action", "raw_value", "cumulative_solved"])
        for metric, d in curves.items():
            for action, values in d.items():
                counts = collections.Counter(values); total = 0
                for x, count in sorted(counts.items()):
                    total += count; w.writerow([metric, action, x, total])
    vbs = s["time_vbs_mean_par2"]; gain = 1 - vbs / s["mean_par2"]["D"]
    stats = {"cohort": len(cases), "runs": s["valid_runs"], "cutoff_cpu_s": 600, "solved": {**s["solved"], "VBS": s["solved_union"]},
             "mean_par2_s": {**s["mean_par2"], "VBS": vbs}, "oracle_gain_over_D": gain, "all_timeout": s["all_censored"], "pair_counts": pairs}
    stats["missing_conflicts_timeout_runs"] = sum(x["conflicts"] is None for c in cases for x in c["outcomes"].values())
    dump(a.out / "statistics.json", stats)
    rows = "".join(f'<tr><td>{LABEL[x]}</td><td>{stats["solved"][x]:,}</td><td>{len(cases)-stats["solved"][x]:,}</td><td>{stats["mean_par2_s"][x]:.2f}</td></tr>' for x in (*ACTIONS, "VBS"))
    embed = lambda n: '<img alt="' + n + '" src="data:image/png;base64,' + base64.b64encode((a.out / (n + '.png')).read_bytes()).decode() + '">'
    source = "https://github.com/Roushelfy/online-tuning-forcephase/tree/0d82f6ed932e3f5ad0bde8d96d847dadc9ee8aa0"
    body = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Force-phase · 教授要求的 raw data 图</title>
    <style>body{{margin:0;background:#f4f6f9;color:#172a3c;font:16px/1.65 system-ui,-apple-system,sans-serif}}main{{max-width:1160px;margin:40px auto;padding:0 24px 50px}}h1{{font-size:32px;line-height:1.3}}h2{{font-size:23px}}.muted,small{{color:#526273}}.card{{background:white;border:1px solid #dde4eb;border-radius:14px;padding:24px;margin:22px 0}}img{{width:100%;height:auto}}.stats{{display:flex;gap:32px;flex-wrap:wrap}}.stats b{{font-size:30px;display:block}}table{{border-collapse:collapse;width:100%;text-align:right}}td,th{{padding:10px 14px;border-bottom:1px solid #e2e7ed}}td:first-child,th:first-child{{text-align:left}}a{{color:#315c9b}}code{{font-size:13px}}.pill{{color:#20816b;font-weight:600}}@media print{{body{{background:white}}.card{{break-inside:avoid;border:0}}main{{margin:0}}}}</style></head><body><main>
    <p class="pill">COMPLETE · 4,719 / 4,719 题 · 14,157 / 14,157 次运行</p><h1>Force-phase 的原始基线：<br>D、F+、F− 与 VBS 之间还有多大空间？</h1>
    <p class="muted">2022 Anniversary，经用户指定的官方全赛道未解筛选后保留 4,719 题；主名单 5,355 题、排除 636 题。CaDiCaL 3.0.1，seed 0，每次 600 CPU 秒。数据于 11 月 9 日完成；本页于 2026-11-10 取回并从逐题 CSV 重新绘制。</p>
    <div class="card stats"><div><b>3,385</b>D 解出题数</div><div><b>3,547</b>三配置 VBS 解出题数</div><div><b>+162</b>事先知道赢家可多解的题</div><div><b>{gain:.1%}</b>VBS 相对 D 的平均 PAR2 降幅</div></div>
    <section class="card"><h2>1 · 教授要求的累计解题图</h2><p>横轴：每题求解 CPU 时间。纵轴：在该时间内通过验证的题数。曲线越高越好。VBS 对每一道题取 D/F+/F− 中最快的已验证结果；三种都超时的 1,172 题始终不进入解出曲线。</p>{embed('cumulative_cpu_s')}<p><strong>D 是当前最强固定配置；D 与 VBS 之间的差距，是值得尝试选择策略的空间。</strong>VBS 是不用支付判断成本的事后上界，不代表已经实现了 10.9% 的改进。</p></section>
    <section class="card"><h2>2 · 用 conflicts 看搜索工作量</h2><p>只统计在 600 CPU 秒内验证解出的轨迹。横轴为解出前 conflicts，保留真实 0；使用 symlog 显示。这里的 VBS 单独最小化 conflicts，可能与时间 VBS 选择不同动作。超时轨迹已发生的 conflicts 并不是解完所需 conflicts。8 条超时轨迹没有终止统计，仍保留为空值；所有已解出轨迹的 conflicts 均完整，曲线不受影响。</p>{embed('cumulative_conflicts')}</section>
    <section class="card"><h2>3 · 哪些题受相位影响大？</h2><p>每个圆点是一道两边都解出的题，位于对角线下方表示纵轴动作更快，上方表示横轴动作更快。1×、2×、10× 线帮助定位大幅差异。TO 灰带是“600 秒未解”的类别位置，不是运行时间；单侧解出和双超时数均保留。</p>{embed('scatter_cpu_s')}<p>conflicts 配对图限定双方均解出；未解计数列在每幅图下方。</p>{embed('scatter_conflicts')}</section>
    <section class="card"><h2>逐题数据汇总</h2><table><tr><th>配置</th><th>验证解出</th><th>未解</th><th>平均 PAR2 / 秒</th></tr>{rows}</table><p class="muted">PAR2：已验证解出记实际 solver CPU；未解记 1,200 秒。罚分不是物理 CPU 消耗。求解期间的 LRAT 生成已计入 solver 时间；独立 checker 费用另计。单 seed、单次测量；本页未重跑求解器、未拟合选择策略。</p></section>
    <section class="card"><h2>来源与下载</h2><p><a href="{source}">Zhaofeng 推送的 evaluation，固定提交 0d82f6e</a> · <a href="{source}/reports/anniversary2022_baseline/BASELINE_RESULTS_20261109.md">运行报告</a></p><p><a href="matrix.csv">逐题三配置 matrix.csv</a> · <a href="runs.csv">逐次测量 runs.csv</a> · <a href="curve_points.csv">未平滑的曲线点 CSV</a> · <a href="cumulative_cpu_s.pdf">时间图 PDF</a> · <a href="cumulative_conflicts.pdf">conflicts 图 PDF</a> · <a href="scatter_cpu_s.pdf">时间散点 PDF</a> · <a href="plot_receipt.json">来源与文件 SHA</a></p><small>图与统计从拉取的 runs.csv / matrix.csv 重新计算，并与冻结名单、已发布 curve_data 和汇总逐项核对。原始 result.json、完整日志及证明核验过程仍保存在协作者集群；本页没有冒称重新核验全部证明。最终测试集需另行选择。</small></section>
    </main></body></html>'''
    (a.out / "raw_data.html").write_text(body)
    commit = subprocess.check_output(["git", "-C", str(a.repo), "rev-parse", "HEAD"], text=True).strip()
    dump(a.out / "plot_receipt.json", {"source_repository": "Roushelfy/online-tuning-forcephase", "source_branch": "anni2022-cluster-run", "source_commit": commit,
        "source_files": {n: sha(snap / n) for n in ["matrix.csv", "runs.csv", "summary.json", "curve_data.json"]},
        "generator_sha256": sha(__file__), "matplotlib": matplotlib.__version__, "numpy": np.__version__, "generated_date": "2026-11-10",
        "checks": ["exact frozen retained cohort", "one run per action and parent; seed 0", "resolved status and verification metadata", "matrix agrees with runs", "computed curves equal published raw curves", "PAR2 agrees with published summary"],
        "source_raw_logs_or_proofs_reverified": False, "new_solver_calls": 0, "statistics": stats,
        "files": {f.name: sha(f) for f in sorted(a.out.iterdir()) if f.is_file() and f.name != "plot_receipt.json"}})
    print(json.dumps({"out": str(a.out), "source_commit": commit, **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
