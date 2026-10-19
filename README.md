# Online Tuning of Forcephase

Research question: **When should a CDCL SAT solver use its native phase policy, and when should it force negative decision literals? Which observations available during solving predict that choice?**

本仓库是科研项目 **Online Tuning Forcephase H:1** 的完整研究记录：固定版本 CaDiCaL 上的最小研究补丁、可复现的实验流水线、全部运行记录的汇总、分阶段报告和最终中文研究报告。

**最终报告：[reports/FINAL_REPORT.md](reports/FINAL_REPORT.md)**（含英文 abstract）。

## 结论速览

状态：第一轮 M0–M5 于 2026-10-19 完成；同日按 [Agent Goal v2](docs/AGENT_GOAL.md) 完成**审计修正与科研收尾**（[纠正协议](docs/CORRECTION_PROTOCOL.md)、[逐项关闭记录](reports/AUDIT_CLOSURE.md)）。结论是**有边界的负结果**。数据：SAT Competition 2023–2026 主赛道（≤100 MB），CaDiCaL 3.0.1，T = 300 s，所有 solved 结果经模型检查或 LRAT 证明检查。原始任务：[AGENT_GOAL_INITIAL.md](docs/AGENT_GOAL_INITIAL.md)；第一轮最终报告存档：[FINAL_REPORT_round1.md](reports/FINAL_REPORT_round1.md)。

- **强制负分支整体有害**：dev 上比 stock default 少解 58 个（PAR2 −10.8%），冻结的 family-disjoint test 上 −29%；损失主要在可满足实例。
- **机制（单因素配对）**：关闭 rephase（forcephase 隐含）有清楚的损害（dev −10.0% [−21.7, −2.0]，主要在 SAT）；在 rephase 已关闭时，强制负代替 target/saved 的点估计更差但区间跨 0。
- **编码相关**：经符号翻转检验的 F− 获胜家族（如 brent-equations）在全局翻转后变为大幅劣势，随机翻转后优势消失。
- **不可预测**：同状态确定性重放标签（5,887 次重放、5,884 个有效配对）上，静态、time-only 与在线一次选择器在家族外都没有超过“不切换”；审计发现一个极性特征（saved 翻转率）计算有误，修复控制器并排除该特征后在同一数据与 folds 上重算，结论不变。
- **冻结评估**：预注册候选“先强制负 1e4 冲突再原生”在 family-disjoint test 上相对 validation-SBS（仅初始负）为 −1.0% [−3.4, +1.7]，**未达到 ≥5% 的预设目标**；在 2026 年实例上比 stock default 好 1.3% [+0.2, +2.5]，但不优于仅初始负。
- **工程**：控制器关闭 / telemetry-only 与上游搜索逐项相同；低噪声复测中 telemetry 开销中位 +0.05%、p95 +0.35%；第一轮 36,157 次运行（2,117 CPU 小时）与本轮审计（约 23.8 CPU 小时）均有账本，全账本完整性审计 0 问题。
- **未做 / 未知**：基于内容观测的重复切换控制器（门槛未满足，未继续）、正确 flip 特征的全集重采、长 cutoff 与其它求解器。

## 文档

| 文档 | 内容 |
| --- | --- |
| [研究计划](docs/RESEARCH_PLAN.md)、[实验协议](docs/EXPERIMENT_PROTOCOL.md)、[Agent Goal](docs/AGENT_GOAL.md) | 预先给定的问题、协议与交付标准 |
| [相关工作](docs/RELATED_WORK.md)、[源码审计](docs/SOURCE_AUDIT.md) | 文献与固定源码事实 |
| [实现设计](docs/DESIGN.md) | 补丁、控制器语义、切换状态处理、遥测 schema、策略文件格式 |
| [实验日志](docs/EXPERIMENT_LOG.md) | 预注册决定与每次协议具体化（含时间与“已接触哪些结果”） |
| [M0–M1 报告](reports/M0_M1_report.md) | 语义、正确性、确定性、观测开销 |
| [M2 报告](reports/M2_report.md) | 静态互补性、机制诊断、编码敏感性 |
| [M3 报告](reports/M3_report.md) | 同状态重放、一次选择、RQ3 时间变化 |
| [M4 报告](reports/M4_report.md) | 门槛判断、无观测固定调度、M5 候选 |
| [M5 报告](reports/M5_report.md) | 冻结后的 held-out 评估 |
| [算力账本](reports/COMPUTE_LEDGER.md)、[audit v2 账本](reports/audit_v2/COMPUTE_AUDIT_V2.md) | 所有尝试的 CPU 时间 |
| [纠正协议](docs/CORRECTION_PROTOCOL.md)、[审计关闭记录](reports/AUDIT_CLOSURE.md) | audit v2：缺陷、固定的纠正方案、修复与验证证据 |
| [数据位置](DATA_LOCATION.md)、[benchmark 来源](benchmarks/SOURCES.md) | 大文件位置、下载与校验 |

## 仓库结构

```text
third_party/   cadical（固定 c607304）、lrat-trim、drat-trim 子模块
patches/       cadical-fpc.patch（对上游的 hook，约 100 行）
solver/        fpcontrol.{hpp,cpp}：控制器、遥测、策略求值
tools/         checkmodel.c（模型检查）、cnffeatures.c（静态特征）、cnfscramble.c（变换/seed）
scripts/       构建、下载、运行（fprun.py + slurm_submit.sh）、汇总与分析
configs/       solver_configs.json、experiments/*.json、policies/、m5_freeze.json
benchmarks/    manifest.csv、family_groups.csv、checksums.csv、derived/（派生实例清单）
analysis/      fpstats.py（PAR2、cluster bootstrap、作图约定）
tests/         m0_suite.py、api_phase_test.cpp
results/       每个实验的 runs.csv（一行一次计划运行，含 run_id）、静态特征
reports/       分阶段报告、表格与图（全部由脚本生成）
```

## 复现

小型全流程（干净 checkout，约 10–20 分钟，8–16 核）：

```bash
git clone -b research/forcephase-study https://github.com/Roushelfy/online-tuning-forcephase.git
cd online-tuning-forcephase
FP_DATA=/path/to/data scripts/repro_small.sh /path/to/out
```

它会初始化子模块、构建四个求解器变体与检查工具、运行快速 M0 套件、下载 20 个 smoke 实例、以 10 s cutoff 运行 D/I−/F−/F+（带 LRAT 证明与验证）、汇总并生成 M2 风格的表和图。分析步骤需要 `pyproject.toml`/`uv.lock` 中的 Python 环境（通过 `FP_PY` 指定解释器）。

审计修订流程（读取已提交的运行汇总与 `$FP_DATA` 下的原始遥测，只读）：

```bash
scripts/build_solver.sh fpc2                       # v2 控制器（仅用于 C++ 一致性检查）
scripts/audit_v2/run_m3_revision.sh reports/audit_v2/m3_rerun   # 门禁 → 复现第一轮 → 修订 M3 → 对比 → 信号 → 策略一致性
scripts/audit_v2/integrity.py --out results/audit_v2/integrity  # 全账本完整性审计
scripts/audit_v2/m5_recheck.py --out reports/audit_v2/m5_recheck.md
```

完整实验（Genesis Slurm 集群，gs-srun 容器内）：

```bash
scripts/build_solver.sh && scripts/build_tools.sh                 # 容器内构建
scripts/build_manifest.py --gbd $FP_DATA/benchmarks/gbd --out benchmarks
scripts/fetch_benchmarks.py --splits train,val,test,t2026
scripts/slurm_submit.sh configs/experiments/m2_census.json 6       # 其余实验同理
scripts/collect.py --exp configs/experiments/m2_census.json --out results/m2_census/runs.csv
$FP_PY scripts/analyze_m2.py --runs results/m2_census/runs.csv --diag results/m2_diag/runs.csv --out reports/m2
```

各报告开头列出了对应的实验配置、命令和分析脚本。运行结果按内容寻址（二进制哈希、参数、实例、seed、cutoff、证明政策），重复提交只会补齐缺失的运行，不会覆盖已有结果。

## 关键语义（已由 M0 验证）

- 默认 `phase=1`：裸 `--forcephase` 强制**正**方向；负分支是 `--forcephase=1 --phase=0`。
- stock 默认包含 target phase 与 rephasing，不是“纯 phase saving”；`--forcephase` 同时关闭 rephasing。
- 强制负只作用于自由决策，单位传播仍产生正文字。

## 依赖与许可证

| 依赖 | 固定版本 | 许可证 | 用途 |
|---|---|---|---|
| [CaDiCaL](https://github.com/arminbiere/cadical) | `c60730422e758ef1cebe7aeddf2dda31c996bf04`（3.0.1） | MIT（`third_party/cadical/LICENSE`） | 求解器；`patches/` 与 `solver/` 是对它的修改，构建产物保留上游许可证文本 |
| [lrat-trim](https://github.com/arminbiere/lrat-trim) | `b30f400f4ee5c32b77ee566a7c006081b521534f` | MIT 型（`third_party/lrat-trim/LICENSE`） | LRAT 证明检查 |
| [drat-trim](https://github.com/marijnheule/drat-trim) | `2e3b2dc0ecf938addbd779d42877b6ed69d9a985` | MIT 型（`third_party/drat-trim/LICENSE`） | 备用 DRAT 检查（主流程未使用） |
| Python 分析环境 | `pyproject.toml` + `uv.lock`（numpy 1.26.4、scipy 1.13.1、pandas 2.2.2、matplotlib 3.9.2、scikit-learn 1.5.2） | 各自开源许可证 | 汇总、统计、作图、M3 模型 |
| benchmark | GBD / SAT Competition 2023–2026（见 `benchmarks/SOURCES.md`） | 按竞赛与 GBD 发布条款 | 不提交 CNF，只提交 manifest 与校验和 |

运行器 `scripts/fprun.py`、校验与变换工具 `tools/*.c` 只依赖 C/C++ 编译器与 Python 标准库。
