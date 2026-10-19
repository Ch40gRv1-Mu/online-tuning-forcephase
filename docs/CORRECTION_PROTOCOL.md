# 纠正协议（Audit v2）：forcephase 研究的审计修正与收尾

**性质声明**：本文件写于 2026-10-19，在第一轮 M0–M5 全部完成、**test 与 t2026 均已看过**之后。它是事后审计的纠正协议，不是事前预注册，也不回填或改写第一轮日志。它在本轮任何新分析、新代码运行或新求解之前提交（见本文件所在提交）。执行目标：[docs/AGENT_GOAL_AUDIT_V2.md](AGENT_GOAL_AUDIT_V2.md)（v2）。

## 1. 证据保护

- 第一轮终点提交：`c2380c0974dfe8d8a51048b2e8c25a870d5ce6c5`；goal v2 提交：`6e77ece`；冻结 tag `m5-freeze` = `74e44372931740a255d8a81faaec28ca2cfb337e`（不移动、不改写）。
- 证据快照：`results/audit_v2/evidence_snapshot.json`（`scripts/audit_v2/evidence_snapshot.py` 生成）记录 100 个第一轮文件的 SHA-256（run CSV、M3 数据集/folds/selectors、策略、冻结文件、实验定义、manifest、报告表与 numbers）、5 个构建的 BUILDINFO 与二进制实测哈希、外部记录数（36,157 个结果记录）。关键哈希：
  - `results/m3/dataset.csv` `5da02af797633637…`；`reports/m3/folds.csv` `3c3a035374522c7c…`；
  - 二进制：upstream `250220f9c8b6…`、fpc（v1 控制器，所有第一轮实验）`6cf084699e87…`、upstream-check `57e2295de802…`、fpc-check `0f6e892be8e7…`。
- 第一轮文件保持原位不改；本轮新产物只写入 `results/audit_v2/`、`reports/audit_v2/`、`configs/policies/audit_v2/`、`benchmarks/derived/audit_v2/`、`scripts/audit_v2/`、`tests/audit_v2/`。对第一轮报告的文字更正只以“更正记录”形式追加并保留原数字可追溯（第 9 节）。
- `build/fpc` 等第一轮二进制不重建、不覆盖（第一轮 run id 含其哈希）。修复后的控制器构建为新变体 **`fpc2` / `fpc2-check`**，遥测 schema 版本 **2**；第一轮控制器源码原样保存在 `solver/v1/`，变体 `fpc`/`fpc-check` 改为从 `solver/v1/` 构建，以便从干净 checkout 重建出与第一轮相同的代码。

## 2. 已看过的评估集

test（204 例）与 t2026（304 例）在第一轮 M5 中都已看过，标记为**已见评估集**。本轮不得用它们选择特征删除、K、阈值、模型、家族或规则；第一轮主假设失败（候选 F−→D @1e4 相对 I− −1.0% [−3.4, +1.7]）保留，不通过改名或换指标改写。本轮对 M5 只做**独立重算汇总记录**（第 7 节），不重新运行 M5 求解。

## 3. 已知缺陷（审查发现，修复与验收待执行）

| 编号 | 缺陷 | 影响范围 |
|---|---|---|
| D1 | `m3_build.py` 把“遥测文件缺失”当作“没有决策点”；`m3_train.py` 只统计 digest 不一致而继续训练，缺失的 replay 会以 baseline 成本回填（`ca = where(has, alt, base)`） | M3 数据门禁；可能把数据错误静默混入分数 |
| D2 | `fpcontrol.cpp` 中 checkpoint 与 window 共用一份 `sample_saved`（两类记录交替时 flip 实际比较的是不同类记录）；compaction 重新编号后样本身份未维护；同一 hook 中 checkpoint 先于 window 计算、oneshot 动作夹在中间；样本与随机动作共用一个 RNG | `x_saved_flip_frac` 失效；P 组与 all 组在 M3 中使用了它 |
| D3 | M3 报告写“4,233 个重放、4,230 digest 一致”；实际八组为 5,887 / 5,884，训练用六组为 4,391 / 4,388 | 报告分母 |
| D4 | M1 telemetry p95 slowdown 4.16% > 3% 目标，只以噪声解释，未证实 | 开销声明 |
| D5 | README/最终报告称“全部完成”，上述问题未披露 | 完成声明 |
| D6 | （快照时新发现）M0_M1 报告把 upstream 二进制哈希写成 `57e2295d…`（实为 upstream-check） | 报告标识 |

## 4. P0 数据门禁：异常分类（固定规则）

审计脚本 `scripts/audit_v2/integrity.py` 对所有实验检查：计划 run 集合与记录一一对应、唯一键 `(experiment-spec key: config, instance, variant, seed, repeat)`、键中二进制哈希等于构建哈希、实例在 manifest/checksums 中、T 与内存限制等于实验定义、状态类别、solved ⇒ 验证通过、遥测（开启时）文件存在、可解析、schema=1、有 header 与 final 记录、header 中模式/轨道/动作/fpcat 与配置参数一致、实际动作（固定动作 0 次切换；schedule 在到达阈值的检查点处恰好 1 次且方向正确；未到达则 0 次）。

M3 同状态配对（`scripts/audit_v2/m3_build_strict.py`）按以下互斥类别分类，每行一个 `(instance, base, alt, K, track, direction)`：

| 类别 | 判定 | 处理 |
|---|---|---|
| `valid_pair` | base 与 alt 记录与遥测完整；alt 在 K 的检查点 digest 等于 base 的；alt 恰有 1 次 `schedule` 切换，发生在该检查点的同一冲突数，动作与方向、轨道符合配置；final 切换数 = 1 | 可产生标签；双 timeout 时权重 0 |
| `solved_before_K` | base 遥测完整、无 K 检查点、base solved | 合法未到决策点：部署成本 = base；无标签 |
| `budget_before_K` | base 遥测完整、无 K 检查点、base timeout | 同上 |
| `censored_unmatched` | base 有 K 检查点；alt 无该检查点；**base 与 alt 均 timeout**（终端罚分 600） | 预算边界例外：训练权重 0、部署成本按观测罚分；不声称 digest 已通过；不得推广到其它情形 |
| `base_missing` / `alt_missing` | 应有记录而无 | **数据错误** |
| `telemetry_missing` / `telemetry_corrupt` / `telemetry_incomplete` | 文件缺失、JSON 损坏、缺 header 或 final | **数据错误** |
| `digest_mismatch` / `switch_error` / `direction_error` / `duplicate_key` | 不符合上述配对规则 | **数据错误** |

正式分析（修订 M3）在出现任何数据错误时**硬性失败**；唯一允许的例外类别是 `censored_unmatched`。不回填、不删除不利样本。输出逐组清单：总实例、合法未到达（两类）、有效配对、双超时无匹配前缀、各类错误、实际切换、正权重标签，以及每个报告使用的分母。

回归验证（`tests/audit_v2/test_gate.py`）用人工构造的记录覆盖：缺文件、截断 JSONL、重复键、缺 alt、digest 不同、方向错误、应切未切、预处理解出、阈值前解出、预算边界双超时；断言错误路径阻止正式分析。

### 4.1 附录 A（2026-10-19 03:05 UTC，首次运行严格门禁之后、任何修订 M3 分析之前）

首次运行 `m3_build_strict.py`（只读第一轮记录）报告 4 行 `telemetry_incomplete`，全部来自同一实例 `4106867bc76b8794330a205cf8a303ad`。全账本中共有 6 次运行 exit code −9（都是该实例、都含 F− 阶段：census F−、sw1k_C、sw10k_Cin、sw100k_Cin、sw1k_Crev、sw1k_CrevIn；M5 中没有）：runner 在 CPU 达到 T 时发送 SIGTERM，求解器 10 s 内未退出（推测处于不检查终止标志的长阶段），runner 改发 SIGKILL，因此遥测没有 final 记录；遥测每条记录写后立即 flush，被杀之前的记录完整。

新增**有界类别** `killed_after_cutoff`：仅当运行记录同时满足 status = timeout、terminated_by = cpu、exit code = −9、CPU ≥ T，且遥测可解析、有 header、只缺 final 记录时成立。此时：
- 该运行的终端成本按运行记录（timeout，PAR2 = 2T）；
- 遥测用于判断是否到达检查点与核对 prefix digest / 切换记录（切换记录必须恰好 1 条且位于检查点；不再要求 final 中的切换计数）；
- 其余规则不变；任何其它缺 final、损坏或缺失的遥测仍是数据错误。
这不是对旧日志的回填：这些运行的结果（timeout）由运行记录直接给出。受影响的 M3 行全部是双方 timeout 或无决策点的 timeout，对训练权重与 PAR2 无影响；仍在门禁报告中单独列出。补跑无法改变结果（同一 runner 会再次在同一处 SIGKILL），因此不补跑；runner 的 10 s 宽限期作为局限披露。

## 5. P1 控制器修复规范（v2）与 M3 科学纠正

**控制器 v2**（`solver/fpcontrol.*`，变体 `fpc2`，schema 2）：
1. checkpoint 与 window 各自维护上一条同类记录的样本相位历史；flip 分母只计前后两次都有效（同一变量身份、仍活跃、两次 saved 都非 0）的样本；无可比较历史时为 `null`。
2. 同一 restart 两类记录同时触发时，先对同一份 pre-action 状态计算两类特征并各自更新一次历史，再按模式执行至多一次动作；记录中的 `action` 为 pre-action 动作。
3. 检测 `stats.compacts` 变化：重建固定大小样本，并使两个流的历史失效；压缩后各流第一条记录的 flip 为 `null`。
4. 样本 RNG 与动作 RNG（random 模式）分离，均与求解器 RNG 无关；特征开销保持 O(256)。
5. 验证（`tests/audit_v2/test_controller_v2.py` 与 M0 子集）：同 hook 两记录、连续同类记录、人工可控的真实翻转与不翻转、压缩后失效与重建、各种记录组合；controller-off、telemetry-only、fixed、第一轮冻结 schedule（`sw10k_Crev`）在 v2 下与 v1/上游的搜索统计逐项相同；API phase 优先级、传播、LRAT 证明不变。

**M3 唯一纠正**：在旧开发数据中统一**排除 `x_saved_flip_frac`**：P_GROUP、all、shuffled-label 对照、单变量信号/相关表与解释图。不由两个负比例之差补算 flip，不混合 v1/v2 遥测。其余全部固定不变：数据（第一轮 census + replay CSV，经严格门禁重建的数据集）、K ∈ {1e3,1e4,1e5}、D prefix 与 I− prefix、特征组定义（除去该特征）、模型网格（树深 1–3 × 叶子 10/30；logistic C ∈ {0.1,1}）、代价敏感权重、外层 folds（直接加载并核对 `reports/m3/folds.csv`，家族归属不变；零权重/删失行保留原 fold）、内层 fold 生成种子（100+f）、评分（OOF 平均 PAR2，cluster bootstrap 10,000 次，种子 12345）。缺失值填充与缩放只在训练折内拟合（与第一轮相同）。

执行顺序：(a) 用第一轮未改动代码在第一轮数据集上复现 `reports/m3/selectors.csv`；(b) 严格门禁重建数据集并与第一轮数据集逐列比对；(c) 修订流程输出全部预定组的原/修订 OOF PAR2、solved、家族区间、相对 D/I−/static/time-only/shuffled 的差异；(d) 修订策略导出到 `configs/policies/audit_v2/`，用 C++（链接 fpc2 库）与 Python 在 dev 特征上逐行比较分数、缺失处理与动作，并测定含 CPU 时间特征模型在 ±5%/±10% 计时扰动下的决策翻转率。不覆盖第一轮策略与冻结文件。

## 6. P2 开销复测（固定设计）

- 实例：`benchmarks/derived/audit_v2/m1_retest48.txt`（本提交固定）：来自 `m1_over1s.txt` 的 48 个 dev 实例，按第一轮上游中位 CPU 的四分位分层（切点 12.01/42.42/123.73 s），每层 12 个，`numpy.default_rng(20261019)` 无放回抽取；只用第一轮上游时间，不看 slowdown。
- 配置：upstream（`build/upstream`，无遥测）、patched-off（`build/fpc` v1，控制器关闭）、telemetry（`build/fpc` v1，`--fpc=1`）——与第一轮 M1 相同，因为所有第一轮实验使用 v1 遥测；各 6 次重复；全部带 LRAT 证明输出到节点本地 tmpfs，T = 300 s，16 GB。v2 遥测不做开销复测，其开销不得套用到第一轮结果。
- 执行：1 个独占节点，16 个工作进程、每个 CCD 一个物理核（核 0, 6, …, 90）；每个实例的 18 次运行在同一物理核上顺序执行，顺序为 6 个随机排列的 {U, O, T} 块（种子 20261019+实例序号），实例按预期负载 LPT 分配到工作进程。最坏求解预算 48×3×6×300 s = 72 CPU 小时；预期约 18 CPU 小时。
- 分析：每实例每配置取 6 次中位数；报告 telemetry/off、off/upstream、telemetry/upstream 的 median 与 p95 slowdown、按实例 bootstrap 95% 区间（10,000 次）；重复噪声用同样聚合：同配置重复 {0,2,4} 中位数对 {1,3,5} 中位数。近 cutoff 的不对称超时单列，不删除。并说明 `hook_time` 未覆盖的每决策/每冲突计数开销。
- 停止条件：一次复测。若 p95 ≤ 3% 仍未证明，如实记为“未达/未证实”，不追加复测；48 例子集结论不冒称第一轮 292 例整体结论。

## 7. 复现链与 M5 独立重算

- 从干净 clone 实际执行 `scripts/repro_small.sh` 与修订 M3 入口（`scripts/audit_v2/run_m3_revision.sh`）。
- `scripts/audit_v2/m5_recheck.py`：不复用 `m5_eval.py`，直接从外部 JSON 结果记录独立重算 M5 的状态、配置覆盖、PAR2、solved、相对 I− 与 D 的点估计与 cluster bootstrap 区间，并与 `reports/m5/numbers.json` 比对；核对冻结 tag 提交时间早于第一条 M5 运行开始时间。这是“重新分析汇总记录”，不是重新运行求解器。

## 8. 预算与停止条件

- 本轮新增总预算上限 **100 CPU 核时**（求解、检查、分析都记账，账本 `reports/audit_v2/COMPUTE_AUDIT_V2.md`），优先复用记录；不购买资源，不删除失败记录。
- 若纠正后仍无可靠收益：以有边界的负结果结束研究。若出现可能改变结论的开发集收益，只称事后开发发现，记录候选与“未在独立数据上验证”状态；本轮不扩展新的独立评估。
- 不实现 bandit/RL，不重跑长 cutoff 全集。

## 9. 报告更正方式

在 `reports/AUDIT_CLOSURE.md` 中逐项给出发现、修复提交、验证命令、证据文件、关闭/限制状态；第一轮报告中错误的数字（D3、D6 等）以“更正”段落标注原文与更正值，计数由脚本生成；最终报告改为三类标注：第一轮冻结结果、纠正后开发结果、事后探索。
