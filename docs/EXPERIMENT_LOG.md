# 实验日志（预注册决定与变更记录）

本文件按时间记录协议的具体化与变更。每条注明**是在接触哪些结果之前**作出的决定。所有时间为 UTC。

## 2026-10-18 19:20 — 运行前的协议具体化（未接触任何 benchmark 求解结果）

此前只运行过：M0 正确性套件（随机/构造的小 CNF）、smoke（20 个 train 实例 × 4 配置 × 10 s，只用于验证 runner/证明/校验流水线）。没有查看任何 300 s 结果。

**求解器与构建**
- CaDiCaL 固定提交 `c60730422e758ef1cebe7aeddf2dda31c996bf04`（3.0.1），子模块 `third_party/cadical`。研究补丁 `patches/cadical-fpc.patch` + `solver/fpcontrol.{hpp,cpp}`。
- 正式实验的二进制在 gs-srun 容器（Ubuntu 22.04，g++ 13.4）内由 `scripts/build_solver.sh` 构建，`-O3 -DNDEBUG -static`。所有配置统一使用打补丁二进制（`build/fpc`）；M0/M1 证明 controller 关闭和 telemetry-only 时搜索统计与上游二进制完全相同。

**数据**
- 候选池：GBD `main_2023`–`main_2026`（meta.db/base.db 于 2026-10-18 19:02 下载，SHA-256 见 `benchmarks/SOURCES.md`）。纳入规则：GBD `bytes`（解压后 sanitized CNF）≤ 100 MB。
- 家族组：GBD family 经保守别名合并（`scripts/build_manifest.py` 中 `ALIASES`），再按 isohash 并查集合并；`unknown` 按 author 分组。
- 开发池（2023–2025）按家族组用种子 20261018 贪心随机分配 train/val/test ≈ 60/20/20：train 612 例 / 67 组，val 205 / 22，test 204 / 21。2026 年池中不与开发池重复（hash/isohash）的 304 例为年份外推集 `t2026`，标记 seen（107）/ devtest（49）/ new（148）。
- **test 与 t2026 在 M5 冻结前不运行任何求解器配置。**

**运行与计时**
- 主 cutoff：T = 300 s 单核 CPU 时间（user+sys，wait4）；开发与最终主表使用同一 T。内存上限 RLIMIT_AS 16 GB。
- runner 轮询 CPU 时间，到 T 发送 SIGTERM（CaDiCaL 优雅结束并写出统计）；答案只有在 CPU ≤ T 且通过验证时记为 solved。
- 证明政策（协议 8.1 默认方案）：所有配置统一 `--lrat=1`（二进制 LRAT），写入节点本地 tmpfs，生成成本计入求解时间；UNSAT 用 lrat-trim（固定提交 b30f400）检查，SAT 用独立 `tools/checkmodel` 对求解器实际读取的 CNF 检查；checker 时间单列。
- 并发：Slurm `cpu-low` 独占节点，每节点 48 个求解进程，绑定到间隔的物理核（SMT 兄弟核空闲）。
- seed：seed 0 为原始 CNF；seed s>0 为 `cnfscramble perm s`（变量重命名+子句/文字顺序打乱，保持符号，因此保持编码的极性偏置）。说明：CaDiCaL 的 `--seed` 在 F− 下几乎不改变轨迹（禁 rephase、walk 不运行），所以用 scrambling 作为重复测量。
- 遥测：所有运行开启 telemetry（`--fpc=1`，窗口 1e4 冲突，检查点 1e3…1e6）；开销在 M1 单独测量并披露。

**M2**
- 主静态配置：D=(forcephase 0, phase 1)、I−=(0,0)、F−=(1,0)、F+=(1,1)，在 train+val、seed 0 上运行。
- validation-SBS：在 **val** split 上按 PAR2 从 {D, I−, F−, F+} 中选；另报告 train+val 上的结果和 D/F− 二动作 SBS。
- 诊断配置 D/no-R、I−/no-R、S（纯 saved）和轨道 P 固定负决策在 train+val 上运行。

**M3（预先限定）**
- prefix 长度候选：1e3、1e4、1e5 冲突（在之后第一个自然 restart 处决定）；标签来自同一 prefix 的确定性重放（`sw{K}_C`，NATIVE→NEGATIVE），NATIVE 分支即 D 运行本身；以检查点 digest 验证 prefix 相同。
- 模型：深度 ≤ 3 的树或 L2 正则 logistic；在 train∪val 上按家族组交叉验证选择；比较 static（`cnffeatures`，成本计入）、time-only（r_ 组）、online（全部）三类特征。

## 2026-10-18 20:25 — M2 census 完成后的开发集决定（未接触 test / t2026）

- M2 census（train+val，D/I−/F−/F+，T=300 s）完成：3,268 次运行，1,337 次 solved（全部验证通过），1,931 次 timeout，无 crash/memout/wrong。
- 按预注册规则，validation-SBS = **I−**（val 上 PAR2：I− 401.1 < D 415.4 < F+ 419.0 < F− 432.2）。两动作 SBS（D/F−）= D。最终主比较对象因此是 I−，并另报 D。
- 在开发集上观察到 {D, F−} 的静态 oracle 只比 I− 低约 2.4% PAR2。因此在主轨道 C（NATIVE prefix → NEGATIVE）之外，**新增目标明确的次要变体** NATIVE_INIT_NEG（phase 固定 0，只切换 forcephase）：I− prefix 在 K∈{1e3,1e4,1e5} 后切换到 NEGATIVE（配置 `sw*_Cin`，实验 `m3in_replay_*`）。这是目标文件允许的、必须单独命名的设计；它与 D 基础的结果分开报告，并与 stock default 对比。该决定只基于开发集数据。
- M3 的其余预注册内容不变（K 候选、模型族、分组 CV）。

## 2026-10-18 22:15 — M3 结果与 M4 门槛决定（只用开发集；未接触 test / t2026）

M3（开发集 out-of-fold，家族分组 5 折嵌套 CV）：
- 静态选择器（cnffeatures，D/F− 与 I−/F−）、time-only 一次选择、在线一次选择（C+R、C+R+P、C+R+Q、C+R+T、all；K = 1e3/1e4/1e5；D prefix 与 I− prefix）**都没有超过“永不切换”**（D 或 I−）。含在线内容特征的模型比不切换差 1–3.5%，shuffled-label 对照与之相当。重放 prefix digest 一致（3 例在 1e5 未到达检查点：双方均 timeout，标签被删失）。
- 结论：在本数据与模型容量下，**没有可迁移的在线信息**用于“何时切到 F−”。
- 同状态 RQ3：在三个 K 都有未删失偏好的 269 例中 21% 偏好随 K 改变；按切换时机的 oracle（D prefix 最佳单次切换时间）比 D 低 7.5%，高于静态 oracle 的 5.0%。反向固定调度 F−→D@1e4（无观测）在 dev 上 PAR2 349.2，低于 D 361.5 和 I− 351.9。

M4 门槛决定：
- **不实现基于特征的重复切换控制器**（M3 否定了在线特征的可迁移性；同样特征的重复控制器没有依据）。
- 由于 RQ3 显示动作时序有价值，做一个**小而预先固定**的“无观测固定调度”集合（M4-lite，只在 dev 上，seed 0，T=300 s）：
  F−→D @1e3、@1e5（@1e4 已有）；F−→I− @1e3、@1e4、@1e5（`fpca0=2`，返回 NATIVE_INIT_NEG）；
  F−→D @1e4 + `fpcrlim=1`（返回时推迟过期 rephase 的机制消融）；
  mode-only：focused 时 NEGATIVE / stable 时 NATIVE，及其反向（repeat 策略只用 `r_stable`，窗口 1e3 冲突）。
  共 8 个配置，不再扩展。

M5 唯一主要候选的选择规则（在看到 M4-lite 结果之前固定）：在所有可部署、在 dev 上评估过的策略（M3 的 OOF 选择器；M4-lite 固定调度与 F−→D@1e4）中，取 **dev（train+val）平均 PAR2 最低者**；若它是固定调度，就以该调度为主要候选。M3 最佳在线选择器（与 time-only 选择器）作为次要报告。M5 基线：D、I−（validation-SBS）、F−、F+、静态选择器（D/F−）、主要候选同 K 的对应 D→F− 调度，及 M5 冻结文件列出的其他项；cutoff 300 s；seed 0/1/2（perm scramble）；family-disjoint test 与 t2026 分别报告。

## 2026-10-18 23:35 — M5 冻结（此前没有任何 test / t2026 求解器运行）

- M4-lite 完成（[reports/M4_report.md](../reports/M4_report.md)）。按 22:15 预注册规则，dev 平均 PAR2 最低的可部署非静态策略为 **F−→D @1e4**（`sw10k_Crev`，dev PAR2 349.2；相对 D +3.4% [+0.9, +6.6]，相对 I− +0.8% [−0.7, +2.2]）。它是唯一主要候选。
- 冻结文件 `configs/m5_freeze.json`，held-out 实验 `configs/experiments/m5_heldout.json`：test（204 例，21 组）+ t2026（304 例）× seed 0/1/2 × {D, I−, F−, F+, F−→D @1e3/@1e4/@1e5, D→F− @1e4, M3 一次选择器（time-only）}，共 13,716 次运行，T = 300 s，LRAT 证明；静态选择器（`configs/policies/static_selector_DF.json`）与随机切换时机基线由分支运行派生；分析脚本 `scripts/m5_eval.py`（已在 dev 数据上干跑）。
- 主假设（只对候选检验）：family-disjoint test 上相对 validation-SBS（I−）mean PAR2 降低 ≥ 5%，95% 家族组 cluster bootstrap CI 不含 0，且每 seed 平均 solved 不低于 I−。根据 dev，预计**不会**达到。次要比较见冻结文件。
- 冻结提交打 git tag `m5-freeze`。之后若发现错误需要重跑，将在此记录原因与新的冻结点；不会根据 test 结果修改候选、阈值或指标。

## 2026-10-19 02:00 — M5 完成

- held-out 运行 13,716 次全部完成（Slurm 727087，10 个节点），3,942 solved 全部验证，0 wrong/crash/memout/unverified。
- 评估严格按冻结文件与 tag `m5-freeze` 的脚本执行（`git diff m5-freeze` 对冻结文件、实验定义、策略与评估脚本为空）。之后只修改了 `scripts/m5_eval.py` 中两幅图的配色与坐标标签（数值输出不变），并新增描述性事后分层脚本 `scripts/m5_posthoc.py`。
- 主假设未成立：候选 F−→D @1e4 相对 I− 为 −1.0% [−3.4, +1.7]（test），平均 solved 95.0 vs 97.3。没有根据 test 结果修改候选、阈值、指标或数据。

## 2026-10-19 — 第一轮测试已见后的审计修正目标（尚未执行）

- 用户要求写入新的 goal 以完成研究。活动目标更新为 `docs/AGENT_GOAL.md`（v2），原始版本保留为 `docs/AGENT_GOAL_INITIAL.md`。
- 本次只设定后续工作，不声称已经修复或重新实验。已知待关闭项：M3 遥测/配对/prefix/switch 门禁、`x_saved_flip_frac` 的流历史与 compaction 身份错误、报告分母、M1 尾部开销未证明达标。
- 新 goal 要求执行 agent 在任何修订分析之前提交 `docs/CORRECTION_PROTOCOL.md`。本轮唯一预定的旧数据纠正是统一排除失效 flip 特征，保留数据、原 fold、K、模型网格和评分方式；它是看过 test 之后的更正，不冒称事前预注册。
- 保留 `m5-freeze`、原测试结果与原始记录。test/t2026 均标为已见，不能继续用于选择规则。主候选为不使用该特征的固定调度，其冻结主负结果保留。
- 默认新增总预算上限 100 CPU 核时，优先复用既有轨迹；可靠负结果可以完成研究，不以找到正结果为结束条件。具体范围、交付与停止条件以 Goal v2 为准。

## 2026-10-19 02:45 — Audit v2 开始：提交纠正协议（任何新分析之前）

- 按 Goal v2 提交 [CORRECTION_PROTOCOL.md](CORRECTION_PROTOCOL.md)：事后审计（test/t2026 已见），唯一的旧数据纠正为统一排除 `x_saved_flip_frac`；固定数据、folds、模型网格、K、门禁分类、开销复测设计（`benchmarks/derived/audit_v2/m1_retest48.txt`）、100 CPU 核时预算与停止条件。
- 证据快照 `results/audit_v2/evidence_snapshot.json`；第一轮控制器源码保存为 `solver/v1/`（SHA 与 `build/fpc` 的 BUILDINFO 一致：c23f03bf…）；构建脚本区分 v1（`fpc`）与修复版 v2（`fpc2`）。
- 快照时新发现 D6：M0_M1 报告中 upstream 二进制哈希写错（应为 250220f9…）。

## 2026-10-19 03:05 — 附录 A（首次运行严格门禁之后、任何修订 M3 分析之前）

- 严格门禁首次运行发现 4 行 `telemetry_incomplete`：同一实例的 6 次运行在 CPU 达到 T 后未在 10 s 内响应 SIGTERM，被 SIGKILL，遥测缺 final 记录。协议附录 A 增加有界类别 `killed_after_cutoff`（见 CORRECTION_PROTOCOL §4.1），不补跑。

## 2026-10-19 19:45 — Audit v2 完成（详见 reports/AUDIT_CLOSURE.md）

- P0：严格门禁与 17 个回归用例；全账本完整性审计 36,077 次运行 0 问题；M3 严格数据集与第一轮逐值相同（0 数据错误、3 个 censored_unmatched、4 行附录 A）。
- P1：控制器 v2（`fpc2`，schema 2）与行为/等价测试（100 + 40 项，M0 套件 0 失败）；第一轮 M3 精确复现；按协议排除 `x_saved_flip_frac` 后重算，结论不变；导出策略参数与第一轮相同，Python/C++ 一致。
- P2：低噪声开销复测（48 例 × 3 × 6，864 次全部解出）telemetry vs 关闭中位 +0.05%、p95 +0.35%；M5 从原始记录独立重算一致；从干净 clone 执行小型全流程与修订 M3 入口，结果一致（仅诊断量 wAUC ≤ 0.0023 的浮点差）。
- 新增事后与纠正后开发分析：单因素配对（收窄“强制方向比 saved 更差”的措辞为区间跨 0）、完整家族表。test/t2026 未用于任何选择；第一轮冻结主负结果保留。本轮算力约 23.8 CPU 核时（预算 100）。

## 2026-10-19 20:31 — 设定下一阶段 Goal v3（新实验尚未执行）

- 用户要求继续研究：上一轮候选未成功，不代表不存在更好的在线切换。活动目标改为 [AGENT_GOAL.md](AGENT_GOAL.md)（v3），上一轮 goal 原样存档为 [AGENT_GOAL_AUDIT_V2.md](AGENT_GOAL_AUDIT_V2.md)。本条记录目标设定，不声称已开始或完成新实验。
- 已接触第一轮及 audit v2 的结果，包含旧 test/t2026；保留原 M5 失败与全部历史证据。新阶段的正式规则须由执行 agent 在新分析/求解前另行提交 STAGE2_PROTOCOL.md。
- 先关闭复现门禁/导出模型检查/BUILDINFO 的小缺口，审计并分解已有约 4.8%/9% 的有限 oracle 结果，不重复从零建立已有证据，也不把有限候选 oracle 称为所有在线策略的全局上界。
- 按门槛决定补采：预选96个旧 dev、至少20组、2 seeds、10个完整配置，使用正确 v2 观测；可选32例、7条最多两次切换的真实路径。不得把不同历史的窗口成本拼接。
- 只在家族 OOF 和实际部署支持收益后冻结唯一候选；最终确认需真正未使用、去重且与接触过的开发/选择家族不相交的新数据。旧 test/t2026 不再充当独立测试。
- 总预算上限400 CPU核时，包含失败、重跑、证明/模型检查与开销。正结果、明确有限范围的负结果或统计证据不足均可结束；具体门槛、预算和交付以 Goal v3 为准。
