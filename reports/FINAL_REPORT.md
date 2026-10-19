# 最终研究报告：CaDiCaL 何时该用原生相位策略、何时该强制负分支？

状态：完成（2026-10-19）。分支 `research/forcephase-study`；冻结点 tag `m5-freeze`。各阶段细节见 [M0_M1](M0_M1_report.md)、[M2](M2_report.md)、[M3](M3_report.md)、[M4](M4_report.md)、[M5](M5_report.md) 报告与 [实验日志](../docs/EXPERIMENT_LOG.md)。

## English abstract

We study when CaDiCaL 3.0.1 should use its native phase policy (saved/target phases with rephasing) and when it should force negative decision literals (`--forcephase=1 --phase=0`), and whether cheap observations available during search predict the choice. We added a ~100-line research hook that applies the effective (forcephase, phase) pair at natural restarts (track C) or overrides only free-decision signs (track P), with JSONL telemetry and state digests; controller-off and telemetry-only runs reproduce upstream search exactly. On 817 development instances from the SAT Competition 2023–2025 main tracks (300 s, LRAT proofs checked for every UNSAT answer, every model checked), forced negative branching solves 58 fewer instances than the stock default (−10.8% PAR2), almost entirely on satisfiable instances. Factor experiments attribute most of the loss to disabling rephasing; forcing a fixed sign is additionally worse than using saved phases; and the families where forced-negative wins (e.g. Brent equations) lose that advantage when variable signs are flipped, so the gain is a property of the encoding's polarity. Deterministic same-state replays (4,233 forks; 4,230 with verified identical prefix digests, the other 3 censored timeouts) show a static/one-shot oracle headroom of about 5%. However, family-grouped nested cross-validation finds no static, time-only, or online one-shot selector (shallow trees or logistic models over polarity, learning-quality and search-shape features) that beats never switching; the online signal is almost entirely between families. A pre-registered, observation-free schedule, forced-negative for the first 10^4 conflicts and then native, was the best policy on development data. On the frozen family-disjoint test set (204 instances, 21 families, 3 seeds) it changed PAR2 by −1.0% [−3.4, +1.7] relative to the validation-selected best static configuration (negative initial phase only), so the pre-registered target of ≥5% improvement was not met; on 2026 instances it was 1.3% better than the stock default but not better than the negative initial phase. We conclude that, for this solver and benchmark distribution, forced negative branching is useful only on polarity-matched encodings, and we found no cheap online observation that tells a solver when to switch.

## 0. 表述约定

**[源码]** 固定源码已证实；**[实验]** 本项目实验已观察（给出数据范围）；**[假说]** 尚待检验。所有表和图都由仓库脚本从运行记录生成；运行记录可通过 `run_id` 追溯到 `$FP_DATA/runs/` 下的原始日志。

## 1. 研究问题与回答（摘要）

| 问题 | 回答（数据范围：CaDiCaL 3.0.1，SAT Competition 主赛道，≤100 MB，T = 300 s） |
|---|---|
| **RQ1 互补性**：原生与强制负各在哪里占优？ | **[实验]** 强制负整体显著更差：dev −10.8% PAR2 [−20.9, −4.3]、held-out test −29.2%、2026 年持平；损失集中在 SAT（dev：143 vs 197 solved）。互补存在但小：D/F− 静态 oracle 比 D 低 5.0%，比 validation-SBS（I−，仅初始负）低 2.4%。F− 获胜家族：brent-equations、cryptography-ascon、polynomial-multiplication、fpga-routing 等；大幅失利：set-covering、heule-nol、scheduling、hardware 等。 |
| **RQ2 可预测性**：求解中可得的观测能否在未见家族上预测选择？在线是否超过静态/时间基线？ | **[实验] 否。** 静态特征、time-only 与包含极性/学习质量/搜索形态的在线一次选择器（K = 1e3/1e4/1e5，深度 ≤3 树或 L2 logistic，家族分组嵌套 CV）都不优于“从不切换”；在线特征模型比不切换差 1–3.5%，与 shuffled-label 对照相当；单变量信号几乎全来自家族间差异（家族内 |ρ| ≲ 0.1）。冻结的在线选择器在 test 上比 D 差 2.5%。 |
| **RQ3 时间变化**：同一实例是否需要多次切换？重复切换是否超过一次选择和固定调度？ | **[实验]** 同状态重放显示偏好随时间改变的实例只占少数（21%，其中稳健的 7%）；按切换时机的 oracle（7.5%）高于静态 oracle（5.0%），但没有可迁移的观测能利用它，因此按预注册门槛**没有构建重复切换控制器**。无观测的固定调度“先强制负 1e4 冲突再原生”在 dev 上优于 D（+3.4%），但在冻结 test 上与 D、I− 均无差异（相对 I− −1.0% [−3.4, +1.7]）；在 2026 年实例上相对 D +1.3% [+0.2, +2.5]、相对 I− −0.7%。 |
| **RQ4 机制与成本**：收益来自符号、禁用 rephase、还是模式交互？成本是否被覆盖？ | **[实验]** 分解：关闭 rephase 使 SAT 少解 61、UNSAT 多解 11（dev）；在同样关闭 rephase 时强制方向比 saved 更差（−10 SAT、−14 UNSAT）；只强制决策符号而保留 rephase（轨道 P）同样差。F− 的获胜在全局符号翻转后反转、随机翻转后消失（编码极性驱动）。按模式调度不优于 D。观测成本极低（hook 时间中位 0.01% CPU；telemetry 中位 slowdown 0.08%），不是失败原因。 |

**一句话结论**：在本数据与版本上，“何时用强制负分支”的可靠回答是“几乎不用；只在编码极性与模型匹配的家族上有利”，而本项目检验的廉价在线观测不能在家族外识别这些情况。可靠的负结果之外，最强的可部署策略仍是静态配置（I− 或 stock D），二者在 held-out 上无显著差异。

## 2. 方法

### 2.1 求解器与动作语义

- 固定 CaDiCaL `c60730422e758ef1cebe7aeddf2dda31c996bf04`（3.0.1）。补丁约 100 行（`patches/cadical-fpc.patch`）+ 控制器源文件（`solver/fpcontrol.*`），设计见 [docs/DESIGN.md](../docs/DESIGN.md)。
- **配置轨道 C**：动作为有效值对 `(forcephase, phase)`：NATIVE=(0,1)、NEGATIVE=(1,0)、NATIVE_INIT_NEG=(0,0)、POSITIVE=(1,1)；所有上游读取这两个选项的位置（决策相位、likely_phase/GC 布局、rephase 门控、rephase original/inverted、变量创建时的 saved 初值，以及 walk/warmup/condition 的初始相位）一致使用有效值。固定动作在变量创建前生效，与命令行配置逐项等价（M0 证明）。
- **极性轨道 P**：只把自由 CDCL 决策的符号设为负（优先级与 forcephase 相同，低于 API phase），其余原生路径不变。
- 切换只发生在自然 restart 之后；不新增 restart，不清空/复制 saved/target/best；强制期间 rephase 计时停住，返回 NATIVE 时过期的 rephase 会立即发生（主语义），`fpcrlim` 为推迟它的消融。
- 默认 `phase=1`：裸 `--forcephase` 强制**正**方向（M0 用 API 与决策计数验证）。

### 2.2 正确性与可复现性

- 所有 solved 结果都经验证：SAT 用独立的 `tools/checkmodel` 对求解器实际读入的 CNF 校验模型；UNSAT 用二进制 LRAT 证明（所有配置统一开启，生成成本计入求解时间）由 lrat-trim 检查，checker 时间单列。验证失败记为 wrong，checker 超资源记为 unverified（本项目两者都为 0）。
- 运行由 `scripts/fprun.py` 以内容寻址 run id 管理（含二进制和策略文件哈希），结果不可覆盖，可断点续跑；所有尝试（包括被中断的）写入 attempts 日志，汇总为 [COMPUTE_LEDGER.md](COMPUTE_LEDGER.md)。
- 运行环境：gs-srun 容器（Ubuntu 22.04，g++ 13.4，静态链接），Slurm `cpu-low` 独占节点（AMD EPYC 9454），每节点 48 个求解进程绑定到间隔物理核；CPU 时间（user+sys）计时，T = 300 s，内存上限 16 GB。

### 2.3 数据与划分

- SAT Competition 2023–2026 主赛道（GBD 元数据与文件），纳入解压后 ≤100 MB 的实例。
- 家族组：GBD 家族名经保守别名合并（如 graph-coloring/coloring、多个 multiplier 家族、hardware 系列），再按 isohash 合并同构副本。
- 开发池（2023–2025）按家族组分为 train 612 例 / 67 组、val 205 / 22、test 204 / 21（种子 20261018，运行任何求解器之前固定）。2026 年中与开发池不重复的 304 例为年份外推集 t2026（seen 107 / devtest 49 / new 148）。
- 编码变体（全局翻转、随机翻转、变量置换+子句打乱）与原实例同组；seed 1、2 定义为变量置换+子句/文字打乱（保持符号）。

### 2.4 统计

PAR2（solved 且已验证记 CPU 秒，否则 2T）；每个实例先对 seed 平均；相对差的 95% 区间用以家族组为单位的 cluster bootstrap（10,000 次，种子 12345）；timeout 是右删失，不当作精确运行时间；oracle/VBS 只作诊断。

## 3. M0–M1：语义、正确性与开销

详见 [M0_M1_report.md](M0_M1_report.md)。要点：
- 7,604 次 M0 运行（带断言构建）0 失败；154 组上游/补丁搜索统计逐项相同；32 个同 prefix 重放 digest 一致；选项真值表与 API 优先级全部符合源码。
- M1（292 个实例 × 3 配置 × 3 次重复）：上游 / 控制器关闭 / telemetry 的搜索统计在 289 个全解实例上 0 差异；telemetry 相对控制器关闭的中位 slowdown 0.08%（目标 ≤1%，达到），p95 4.16%（目标 ≤3%，未证明；同配置重复之间 p95 噪声 5.77%，hook 实测时间 p95 0.07%）。

## 4. M2：静态互补性与机制（dev）

详见 [M2_report.md](M2_report.md)。

| 配置 | solved（SAT/UNSAT） | PAR2 | 相对 D |
|---|---|---|---|
| D（stock） | 363（197/166） | 361.5 | — |
| I−（仅初始负；validation-SBS） | 377（208/169） | 351.9 | +2.7% [+0.3, +5.6] |
| F−（强制负） | 305（143/162） | 400.7 | −10.8% [−20.9, −4.3] |
| F+（强制正） | 292（125/167） | 409.3 | −13.2% |
| D/no-R | 313（136/177） | 397.6 | −10.0% |
| I−/no-R | 329（153/176） | 386.2 | −6.8% |
| S（纯 saved） | 319（135/184） | 394.2 | −9.0% |
| P−（轨道 P） | 302（145/157） | 403.4 | −11.6% |

- 互补：D/F− 静态 oracle 比 D 低 5.0% [2.5, 8.0]，比 I− 只低 2.4%。
- 机制：关闭 rephase 是 SAT 损失的主因，在 UNSAT 上略有收益；同样关闭 rephase 时，强制方向比用 saved 更差；只强制决策而保留 rephase（P−）同样差。
- 编码：F− 获胜的家族（brent-equations、polynomial-multiplication 等）在全局符号翻转后变为大幅劣势，随机翻转后优势消失；随机翻转也让 stock D 的 PAR2 从 97.9 升到 167.0（388 例子集）。

## 5. M3：一次选择（dev）

详见 [M3_report.md](M3_report.md)。在 4,233 个同状态重放（digest 一致 4,230）上，静态、time-only 与在线一次选择器（K = 1e3/1e4/1e5；D 或 I− prefix）在家族分组嵌套 CV 中都没有超过“从不切换”；在线特征模型比不切换差 1–3.5%，与 shuffled-label 对照相当；单变量信号几乎全部是家族间差异。特征消融：按预注册的递增组（C → C+R → C+R+P / C+R+Q / C+R+T → all）比较，没有一组带来稳定增益；由于最终候选是不使用任何特征的固定调度，对候选做逐组 leave-one-out 消融不适用。RQ3：21% 的实例在不同 K 的同状态偏好不同，其中稳健（双向差异 ≥ 1.41×）的只有 7%；反向固定调度 F−→D@1e4 在 dev 上优于 D，与 I− 不可区分。

## 6. M4：门槛判断与无观测固定调度（dev）

详见 [M4_report.md](M4_report.md)。M3 否定了在线特征的可迁移价值，因此**没有实现基于特征的重复切换控制器或 bandit**；RQ3 显示时序本身有价值，于是预先固定地评估了 8 个无观测固定调度：

| 策略（dev，817 例） | PAR2 | solved（SAT/UNSAT） | 相对 D | 相对 I− |
|---|---|---|---|---|
| F−→D @1e4（M5 候选） | 349.2 | 382（210/172） | +3.4% [+0.9, +6.6] | +0.8% [−0.7, +2.2] |
| F−→D @1e3 | 351.1 | 380（206/174） | +2.9% [+0.3, +6.2] | +0.2% |
| F−→D @1e5 | 353.9 | 375（201/174） | +2.1% [+0.2, +4.3] | −0.6% |
| F−→I− @1e4 | 351.6 | 380（207/173） | +2.8% | +0.1% |
| F−→D @1e4，推迟 rephase | 352.4 | 379（208/171） | +2.5% | −0.1% |
| focused 时 NEG | 361.0 | 368（210/158） | +0.2% | −2.6% |
| stable 时 NEG | 368.8 | 354（183/171） | −2.0% | −4.8% |
| D→F− @1e4 | 398.8 | 306 | −10.3% | −13.3% |

“开始时短暂强制负、之后交还原生策略”在 dev 上稳定优于 stock default，但与“仅初始相位为负”（I−）不可区分；反方向（后期强制负）大幅有害。按预注册规则，F−→D @1e4 成为唯一主要候选并在 `m5-freeze` 冻结。

## 7. M5：冻结后的 held-out 评估

详见 [M5_report.md](M5_report.md)。冻结于 tag `m5-freeze`（任何 held-out 运行之前）；13,716 次运行全部完成，3,942 solved 全部验证，0 wrong/crash/memout。

**family-disjoint test（204 例，21 组，3 seed）**：

| 策略 | PAR2 | 平均 solved | 相对 I−（SBS） | 相对 D |
|---|---|---|---|---|
| F−→D @1e4（唯一主要候选） | 363.8 | 95.0 | −1.0% [−3.4, +1.7] | −0.9% [−4.8, +2.1] |
| I−（validation-SBS） | 360.3 | 97.3 | — | +0.1% |
| D（stock） | 360.5 | 98.3 | −0.1% | — |
| F− | 465.6 | 56.7 | −29.2% [−70.4, −9.7] | −29.2% |
| F+ | 433.1 | 70.0 | −20.2% | −20.2% |
| 静态选择器 | 361.0 | 98.0 | −0.2% | −0.1% |
| M3 在线一次选择器 | 369.5 | 94.0 | −2.5% | −2.5% [−5.7, −0.3] |
| F−→D @1e3 / @1e5 | 357.9 / 379.8 | 98.3 / 90.0 | +0.7% / −5.4% | +0.7% / −5.4% |
| 随机切换时机 | 365.6 | 95.3 | −1.5% | −1.4% |
| D→F− @1e4 | 458.2 | 59.7 | −27.2% | −27.1% |

**主假设（≥5% 且 CI 不含 0、solved 不降）未成立。** 2026 年外推（304 例）：候选相对 D +1.3% [+0.2, +2.5]，相对 I− −0.7% [−2.0, +0.4]；新家族上相对 I− −1.8% [−3.6, −0.6]。事后分层发现强制正在 UNSAT 上最好（test 40.7 vs D 38.3 solved），与“关闭 rephase 有利于 UNSAT”的 M2 机制一致，作为待验证假说记录。

## 8. 成本

[COMPUTE_LEDGER.md](COMPUTE_LEDGER.md)：全部 36,157 次求解运行（每次都有记录，含 timeout），求解器 CPU 2,117 h（含 LRAT 证明输出），证明/模型检查 7.7 CPU h；Slurm 独占节点 56.9 node-hours。按阶段：M1 51 h、M2 426 h、M3 同状态重放 375 h、M4 固定调度 348 h、M5 held-out 918 h。M3 模型训练与特征提取为分钟级。没有购买算力或使用外部配额。

部署成本：控制器 hook 时间中位 0.010%、p95 0.071% 的运行 CPU；telemetry 相对控制器关闭中位 slowdown 0.08%（p95 4.2%，与同配置重复噪声 5.8% 同量级）；静态特征提取在 held-out 上每实例中位 0.02 s、最大 0.93 s CPU（计入静态选择器成本）。LRAT 证明输出对所有配置统一计入，约占 5–10% 时间。

## 9. 反例与局限

**反例（[实验]）**
- F− 并非“总是更差”：brent-equations（19 例中 F− 多数更快）、cryptography-ascon（F− 多解 4 例）、polynomial-multiplication、fpga-routing 等家族上 F− 占优；但其中极性驱动的家族在符号翻转后反转（brent-equations 原编码 log2 比 −2.5，全局翻转后 +10.2）。
- F− 在 set-covering 上灾难性（D 解 23/25，F− 解 5），且与编码方向无关。
- 静态 oracle 与切换时机 oracle 都显示存在“该用 F−”的实例（D/F− 静态 oracle 比 D 低 5%），但没有可迁移的特征能找出它们。
- 候选 F−→D @1e4 在 dev 上相对 I− 的最大回退出现在 hamiltonian 实例（单例 PAR2 增加至多约 600 s），说明它不是对每个实例都安全的改进。

- dev 上选出的固定调度相对 D 的 +3.4% 在 family-disjoint test 上消失（−0.9%）；I− 相对 D 的 dev 优势（+2.7%）在 test 上也消失（+0.1%），但在 2026 年实例上重现（+1.9% [+0.7, +3.5]）。小效应对家族组成高度敏感，在 9 个调度中按 dev 取最优也带来乐观偏差。
- 冻结的 M3 在线选择器在 test 上比 D 显著更差（−2.5%），尽管它在 dev 的 out-of-fold 评估中与 D 持平；其输入含 CPU 时间，部署决策受计时噪声影响。

**局限**
- 单一 cutoff（300 s CPU），远低于竞赛 5000 s；短 cutoff 下的结论不能直接外推到长时间求解。只在 dev 上做了 seed 0；held-out 用 3 个 seed（变量置换 + 子句打乱）。
- 单一求解器版本（CaDiCaL 3.0.1 固定提交）；其它求解器（Kissat 等）的 phase 栈不同。
- 家族组来自 GBD 家族名的保守合并，部分组很粗（hardware、cryptography），也可能仍有未识别的同源实例跨 split；isohash 不是完整同构判定。
- 48 进程并发下单次 CPU 计时噪声 p95 约 ±9%；telemetry 的 p95 开销目标（≤3%）未能在此噪声下证明。
- M3 只尝试了浅树与 L2 logistic、三个 prefix 长度和预定义特征组；更强模型或更丰富的特征（如图结构、局部搜索探测）没有尝试，因此“在线信息无用”的结论只适用于这一模型容量与特征集合。
- 同状态标签依赖确定性重放；3 个重放因计时波动未到达 1e5 检查点（双方 timeout，不影响成本）。
- 主表所有配置统一生成 LRAT 证明（约 5–10% 时间开销），绝对时间与无证明运行不同。

## 10. 与相关工作的差异

- **Phase saving 与 target/rephase（R1、R2）**：本项目没有提出新的相位启发式，而是在固定的现代 CaDiCaL 中**分解**了 forcephase 的作用：关闭 rephase 是 SAT 损失的主因，强制方向本身在 rephase 匹配后仍有害；这是对 Biere & Fleury “target/rephase 对 SAT 重要”这一观察在本数据上的独立定量印证，并补充了 UNSAT 上“无 rephase 反而更好”的现象。
- **负分支的应用证据（R4 Collatz、R9 图着色）**：我们复现了“负分支在某些编码上有效”，并用符号翻转实验表明这类收益是**编码相关**的；在 SAT Competition 2023–2025 的广泛家族上，强制负整体有害，图着色组（本数据）上也不占优。
- **在线 phase/rephase 选择（R5 MPhaseSAT、R6 Kissat-MAB-rephasing、R7 DynamicSAT、R8 duration-aware MAB）**：这些工作在线选择 rephase 或配置并报告收益；本项目针对“原生 vs 强制负”这一具体动作，用**同状态确定性重放**得到无混杂的反事实标签，在家族不相交的评估下发现简单在线特征**不能**预测切换收益（负结果），并给出 oracle 上界与时间变化的量化；没有重复 bandit 方法，因为其所需的观测信号在本动作空间上未通过门槛。
- **算法选择（R10 SATzilla 系）**：静态廉价特征的选择器在家族外同样失败，与 M3 的在线结果一致。
- **NeuroBack（R11）**：逐变量相位预测是不同的动作空间；本项目的结果（全局方向与编码极性强相关）与“学习变量相位”路线并不矛盾，反而提示：若要利用极性，应在变量层面而非全局 forcephase 层面学习（[假说]）。

## 11. 已知、未知与下一步

**已知（本数据、本版本、300 s）**：强制负分支整体有害且主要伤 SAT；损失可分解为关闭 rephase 与忽略 saved/target；F− 的获胜家族由编码极性驱动；简单静态/在线特征无法在家族外预测何时切换；“开始时短暂强制负再交还原生”在 dev（+3.4%）和 2026 年实例（+1.3%）上略优于 stock default，但在冻结的 family-disjoint test 上无差异（−0.9% [−4.8, +2.1]），且在任何集合上都不优于仅初始相位为负。

**未知**：更长 cutoff 下的结论；在 Kissat 等求解器中是否相同；是否存在更强（但仍廉价）的在线信号（如 target/best 赋值的变化轨迹、局部搜索探测）能在家族外预测切换；负 prefix 的收益究竟来自学习子句、变量活性还是早期 saved 相位（M4 的 rephase/I− 变体只排除了一部分解释）。

**可验证的下一步**：
1. 在 5000 s cutoff 的小测试集上重测 D、I−、F−→D@1e4（需要约 10× compute）。
2. 用轨道 P 和 `fpcrlim` 组合，分离“负 prefix 学到的子句”与“saved 相位”的作用（例如负 prefix 后清空 saved 的消融）。
3. 把动作从全局方向改为“按变量的极性先验”（例如由静态出现次数或 prefix 中的 saved 统计给出），检验极性信息是否能以变量粒度利用。
4. 用更大的家族数量（加入 2017–2022 年份）重估在线特征的家族外可迁移性，因为当前 89 个家族组限制了统计功效。
5. 检验 M5 事后分层中的意外观察：强制正（以及 M2 中的纯 saved / 无 rephase 配置）在 UNSAT 上最好（test 40.7 vs D 38.3 solved，t2026 30.7 vs 26.0）。可验证假说：“在线判断‘可能 UNSAT’时关闭 rephase”是否能在家族外获益；需要新的、事先固定的 held-out 集，不能在本 test 上再选择。
