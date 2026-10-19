# Audit v2 closure（逐项关闭记录）

执行目标：[docs/AGENT_GOAL_AUDIT_V2.md](../docs/AGENT_GOAL_AUDIT_V2.md)（v2）。协议：[docs/CORRECTION_PROTOCOL.md](../docs/CORRECTION_PROTOCOL.md)（提交 `9e2ac23`，先于任何新分析；附录 A 于首次运行门禁后、任何修订 M3 分析前加入，提交 `48f7850`）。本轮是**看过第一轮 test/t2026 之后的事后审计**；没有用 test/t2026 做任何选择，第一轮冻结结果（tag `m5-freeze`）未改动。算力：约 23.8 CPU 核时（上限计入），见 [audit_v2/COMPUTE_AUDIT_V2.md](audit_v2/COMPUTE_AUDIT_V2.md)。

| 编号 | 发现 | 修复 / 处理（提交） | 验证命令 | 证据 | 状态 |
|---|---|---|---|---|---|
| D1 数据门禁 | `m3_build.py` 把缺失遥测当作无决策点；`m3_train.py` 只计数 digest 不一致，缺失 replay 被 base 成本回填 | 严格门禁 `scripts/audit_v2/gate.py`、`m3_build_strict.py`（逐行类别，数据错误硬失败）；全账本完整性审计 `integrity.py`；修订训练只接受门禁通过的数据（`48f7850`、`5dd8411`） | `python tests/audit_v2/test_gate.py`；`scripts/audit_v2/m3_build_strict.py ...`；`scripts/audit_v2/integrity.py --out results/audit_v2/integrity` | [gate_summary.md](../results/audit_v2/m3/gate_summary.md)、[integrity/summary.md](../results/audit_v2/integrity/summary.md)、`exceptions.csv` | **关闭**。17 个回归用例通过（缺文件、截断、重复键、缺 alt、digest 不同、方向错、应切未切、预处理解出、阈值前解出、预算边界双超时等）；36,077 次运行 0 问题，1,325 个 CNF 哈希通过；M3 6,536 行 0 数据错误、3 行 `censored_unmatched`；严格数据集与第一轮数据集逐值相同（D1 在本数据中未造成实际污染，但旧代码会掩盖它） |
| D1a（新发现） | 6 次运行（同一实例、都含 F− 阶段）在 CPU 到 T 后未响应 SIGTERM，被 SIGKILL，遥测缺 final 记录 | 协议附录 A：有界类别 `killed_after_cutoff`（仅限 timeout + exit −9 + CPU ≥ T + 只缺 final），用于决策点/配对检查；不补跑（同一 runner 会再次 SIGKILL） | 同上 | gate_summary 中 4 行单列；integrity 中 6 条 note | **关闭（披露）**。受影响 M3 行均为双超时或无决策点超时，对权重与 PAR2 无影响；runner 10 s 宽限期列为局限 |
| D2 flip 特征 | v1 控制器 checkpoint/window 共用相位历史；compaction 重编号未处理；同 hook 观测夹着动作；RNG 共用；P 组与 all 组用了该特征 | 控制器 v2（`solver/`，变体 `fpc2`，schema 2；v1 源码原样保存在 `solver/v1/`）（`1d8bfcd`）；M3 唯一纠正：统一排除 `x_saved_flip_frac`（`5dd8411`） | `build/controller_unit`（11 个单元用例）；`python3 tests/audit_v2/test_controller_v2.py`；`M0_FPC=fpc2 python3 tests/m0_suite.py`；`scripts/audit_v2/run_m3_revision.sh` | [controller_v2/report.json](../results/audit_v2/controller_v2/report.json)、[m0_fpc2](../results/audit_v2/m0_fpc2/m0_report.json)、[m3/comparison.md](audit_v2/m3/comparison.md)、[m3/feature_signal.md](audit_v2/m3/feature_signal.md)、[policy_consistency.md](audit_v2/m3/policy_consistency.md) | **关闭**。v2：100 项 v1/v2/上游等价检查与 40 项记录语义检查全过（10 个运行触发 compaction）；M0 套件 7,838 项 0 失败；API 优先级 10/10。M3：第一轮表精确复现（68 个选择器差 0），修订后 50 个不受影响的选择器不变，18 个受影响的选择器小幅变化，结论不变（无在线选择器优于不切换）。导出策略与第一轮模型参数相同；Python/C++ 分数差 ≤ 3.3e−7、动作 0 分歧。**限制**：正确的 flip 没有在全集上重新采集（本轮非必需），因此 flip 是否有预测价值仍未知 |
| D3 报告分母 | M3 报告写 4,233/4,230 | 由门禁脚本生成的逐组计数替换：8 组 5,887 次重放 / 5,884 有效 / 3 censored；训练 6 组 4,391 / 4,388 / 3（`7dc1cf6`；最终报告 v2） | `scripts/audit_v2/m3_build_strict.py ... --report` | [gate_summary.md](../results/audit_v2/m3/gate_summary.md) | **关闭**（M3 报告与最终报告中以“更正”标注，原文保留；第一轮最终报告存档为 [FINAL_REPORT_round1.md](FINAL_REPORT_round1.md)） |
| D4 开销 | 第一轮 p95 4.16% > 3%，未证实 | 按协议一次低噪声复测：48 个分层实例 × 3 配置 × 6 次，独占节点 16 进程（每 CCD 一核），同实例同核平衡随机顺序（`0c25f84`、`dcd89f7`） | `scripts/audit_v2/submit_retest.sh`；`scripts/audit_v2/analyze_retest.py ...` | [m1/retest.md](audit_v2/m1/retest.md)、`results/audit_v2/m1/runs.csv`、`schedule.csv` | **关闭（限定范围）**。telemetry vs 关闭：中位 +0.05%，p95 +0.35% [+0.28, +0.52]；补丁关闭 vs 上游中位 +0.30%；重复噪声 p95 ≤ 0.43%。p95 ≤ 3% 在这 48 例上达到；不改写第一轮 292 例在高并发下的数值 |
| D5 完成声明 | README/最终报告称全部完成而未披露上述问题 | README、最终报告 v2 改为三类标注（第一轮冻结 / 纠正后开发 / 事后探索），列出未通过项与未实施扩展 | — | [README.md](../README.md)、[FINAL_REPORT.md](FINAL_REPORT.md) | **关闭** |
| D6（新发现） | M0_M1 报告把 upstream 二进制哈希写成 upstream-check 的 | 报告中以更正标注（`7dc1cf6`） | `sha256sum build/upstream/cadical` | [evidence_snapshot.json](../results/audit_v2/evidence_snapshot.json) | **关闭** |
| 机制措辞 | “同样关闭 rephase 时强制方向比 saved 更差”只有点估计 | 只比较单因素配对并给出区间（`bff55ca`）：I−/no-R → F− −3.8% [−7.7, +0.2]；在 M2 与最终报告中收窄 | `scripts/audit_v2/ablation_pairs.py` | [ablation_pairs.md](audit_v2/ablation_pairs.md) | **关闭（收窄措辞）** |
| M5 独立复算 | 目标要求独立重算 | 不复用 `m5_eval.py`，直接从 13,716 个原始 JSON 记录重算（`a8e4631`） | `scripts/audit_v2/m5_recheck.py` | [m5_recheck.md](audit_v2/m5_recheck.md) | **关闭**。覆盖完整、0 缺失/重复；点估计差 ≤ 1.4e−6，独立 bootstrap 区间差 ≤ 0.26 个百分点；冻结提交 23:31:04Z 早于第一条 M5 运行 23:31:45Z |
| 复现链 | 目标要求从干净 checkout 实际执行 | 干净 clone `a94a989`，容器内 `repro_small.sh` + `run_m3_revision.sh`（`0d16e38`） | 见 [results/audit_v2/repro/README.md](../results/audit_v2/repro/README.md) | `repro_chain.log` | **关闭**。快速 M0 0 失败；smoke 29/51 与原结果一致；修订 M3 输出与已提交结果一致（仅诊断量 wAUC 因 BLAS 线程差 ≤ 0.0023） |
| 首次 smoke 日志 | 第一轮首次 smoke 尝试的 attempts 日志已删除 | 继续在 [COMPUTE_LEDGER.md](COMPUTE_LEDGER.md) 中披露，不补造 | — | — | **披露** |

**未实施 / 未通过（如实列出）**
- 预设的实用目标（相对 validation-SBS ≥ 5%）在第一轮冻结评估中未达成，保留。
- 正确的 flip 特征未在全集上重新采集；其预测价值未知。
- 基于内容特征的重复切换控制器、bandit/RL 未实施（M3 门槛未满足，未继续该分支）；不能视为已被否定。
- 长 cutoff（5000 s）、其他求解器未做。
- 本轮没有新的独立评估集；纠正后没有出现可能改变结论的开发集收益，因此也不需要。

**修订流程的一条命令**：`scripts/audit_v2/run_m3_revision.sh [outdir]`（M3 门禁 → 复现第一轮 → 修订 → 对比 → 信号 → 策略一致性）；开销复测：`scripts/audit_v2/submit_retest.sh` 后 `scripts/audit_v2/analyze_retest.py`；完整性：`scripts/audit_v2/integrity.py`；M5 复算：`scripts/audit_v2/m5_recheck.py`。
