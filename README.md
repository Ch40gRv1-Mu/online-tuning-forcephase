# Online Tuning of Forcephase

Research question: **When should a CDCL SAT solver use its native phase policy, and when should it force negative decision literals? Which observations available during solving predict that choice?**

本仓库是科研项目 **Online Tuning Forcephase H:1** 的完整研究记录：固定版本 CaDiCaL 上的最小研究补丁、可复现的实验流水线、全部运行记录的汇总、分阶段报告和最终中文研究报告。

**最终报告：[reports/FINAL_REPORT.md](reports/FINAL_REPORT.md)**（含英文 abstract）。

## 结论速览

<!-- results summary (filled after M5) -->

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
| [算力账本](reports/COMPUTE_LEDGER.md) | 所有尝试的 CPU 时间 |
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
