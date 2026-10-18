# 最终研究报告：CaDiCaL 何时该用原生相位策略、何时该强制负分支？

<!-- M4/M5 sections are filled from reports/M4_report.md and reports/M5_report.md -->

## English abstract

(filled after M5)

## 0. 表述约定

**[源码]** 固定源码已证实；**[实验]** 本项目实验已观察（给出数据范围）；**[假说]** 尚待检验。所有表和图都由仓库脚本从运行记录生成；运行记录可通过 `run_id` 追溯到 `$FP_DATA/runs/` 下的原始日志。

## 1. 研究问题与回答（摘要）

(filled after M5)

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

详见 [M3_report.md](M3_report.md)。在 4,233 个同状态重放（digest 一致 4,230）上，静态、time-only 与在线一次选择器（K = 1e3/1e4/1e5；D 或 I− prefix）在家族分组嵌套 CV 中都没有超过“从不切换”；在线特征模型比不切换差 1–3.5%，与 shuffled-label 对照相当；单变量信号几乎全部是家族间差异。RQ3：21% 的实例在不同 K 的同状态偏好不同；反向固定调度 F−→D@1e4 在 dev 上优于 D 与 I−。

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

(filled from M5_report.md)

## 8. 成本

(filled at the end from COMPUTE_LEDGER.md)

## 9. 反例与局限

**反例（[实验]）**
- F− 并非“总是更差”：brent-equations（19 例中 F− 多数更快）、cryptography-ascon（F− 多解 4 例）、polynomial-multiplication、fpga-routing 等家族上 F− 占优；但其中极性驱动的家族在符号翻转后反转（brent-equations 原编码 log2 比 −2.5，全局翻转后 +10.2）。
- F− 在 set-covering 上灾难性（D 解 23/25，F− 解 5），且与编码方向无关。
- 静态 oracle 与切换时机 oracle 都显示存在“该用 F−”的实例（D/F− 静态 oracle 比 D 低 5%），但没有可迁移的特征能找出它们。
- 候选 F−→D @1e4 在 dev 上相对 I− 的最大回退出现在 hamiltonian 实例（单例 PAR2 增加至多约 600 s），说明它不是对每个实例都安全的改进。

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

**已知（本数据、本版本、300 s）**：强制负分支整体有害且主要伤 SAT；损失可分解为关闭 rephase 与忽略 saved/target；F− 的获胜家族由编码极性驱动；简单静态/在线特征无法在家族外预测何时切换；“开始时短暂强制负”优于 stock default，但不优于仅初始相位为负。

**未知**：更长 cutoff 下的结论；在 Kissat 等求解器中是否相同；是否存在更强（但仍廉价）的在线信号（如 target/best 赋值的变化轨迹、局部搜索探测）能在家族外预测切换；负 prefix 的收益究竟来自学习子句、变量活性还是早期 saved 相位（M4 的 rephase/I− 变体只排除了一部分解释）。

**可验证的下一步**：
1. 在 5000 s cutoff 的小测试集上重测 D、I−、F−→D@1e4（需要约 10× compute）。
2. 用轨道 P 和 `fpcrlim` 组合，分离“负 prefix 学到的子句”与“saved 相位”的作用（例如负 prefix 后清空 saved 的消融）。
3. 把动作从全局方向改为“按变量的极性先验”（例如由静态出现次数或 prefix 中的 saved 统计给出），检验极性信息是否能以变量粒度利用。
4. 用更大的家族数量（加入 2017–2022 年份）重估在线特征的家族外可迁移性，因为当前 89 个家族组限制了统计功效。
