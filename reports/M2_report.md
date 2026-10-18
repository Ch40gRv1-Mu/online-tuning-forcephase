# M2 报告：静态互补性与机制诊断（开发集 train+val）

状态：完成（2026-10-18）。数据：train 612 例 / 67 个家族组，val 205 例 / 22 组；T = 300 s CPU；seed 0；所有配置统一输出二进制 LRAT 证明（计入时间），所有 solved 结果均已验证（SAT：`checkmodel`；UNSAT：lrat-trim）。**test 与 t2026 未运行。** 全部数字由 `scripts/analyze_m2.py` / `scripts/analyze_encoding.py` 从 `results/m2_census/runs.csv`、`results/m2_diag/runs.csv`、`results/m2_encoding/runs.csv` 生成，完整表见 [m2/tables.md](m2/tables.md) 与 [m2/encoding.md](m2/encoding.md)。

命令：`scripts/slurm_submit.sh configs/experiments/m2_census.json 6`（同理 `m2_diag`、`m2_encoding`），`scripts/collect.py`，`scripts/analyze_m2.py --runs results/m2_census/runs.csv --diag results/m2_diag/runs.csv --out reports/m2`。实际 compute 见 [COMPUTE_LEDGER.md](COMPUTE_LEDGER.md)。

## 1. 主要静态配置

| 配置 | 有效值对 / 选项 | solved（SAT/UNSAT） | 平均 PAR2 | 相对 D 的 PAR2 降低 [95% 家族 cluster CI] |
|---|---|---|---|---|
| D（stock） | (0,1) | 363（197/166） | 361.5 | — |
| I−（仅初始负） | (0,0) | **377**（208/169） | **351.9** | +2.7% [+0.3, +5.6] |
| F−（强制负） | (1,0) | 305（143/162） | 400.7 | −10.8% [−20.9, −4.3] |
| F+（强制正） | (1,1) | 292（125/167） | 409.3 | −13.2% [−26.4, −4.4] |

所有 3,268 次运行：1,337 solved、1,931 timeout，0 crash/memout/wrong/unverified；不同配置的 SAT/UNSAT 答案无冲突。

**[实验]** 在本数据（SAT Competition 2023–2025 主赛道，≤100 MB，300 s）上：
1. 强制负分支整体明显劣于原生策略，损失集中在可满足实例（SAT：143 vs 197），不可满足实例接近持平（162 vs 166）。
2. 强制正分支几乎同样差：损失主要来自“强制 + 关闭 rephase”，而不是“负”这个方向本身。
3. 只把初始相位设为负（保留 target / rephase）在 dev 上略优于 stock default，且 **I− 是按预注册规则选出的 validation-SBS**（val PAR2：I− 401.1、D 415.4、F+ 419.0、F− 432.2）。最终主比较对象因此是 I−；另报 D。

## 2. 互补性与 oracle 差距（诊断，使用未来信息）

| 范围 | 组合 | SBS | PAR2 SBS → VBS | 差距 [95% CI] | solved SBS → VBS |
|---|---|---|---|---|---|
| train+val | D, F− | D | 361.5 → 343.5 | 5.0% [2.5, 8.0] | 363 → 388 |
| train+val | D, I−, F−, F+ | I− | 351.9 → 321.5 | 8.6% [4.7, 13.6] | 377 → 417 |
| val | D, F− | D | 415.4 → 390.0 | 6.1% [1.4, 12.4] | 72 → 82 |

D 与 F− 互有胜负：F− 更快 151 例（≥2× 更快 57 例），更慢 234 例（≥2× 更慢 142 例），429 例双方超时；只有 F− 解出 25 例，只有 D 解出 83 例。

**[实验]** D/F− 的静态互补空间存在但不大：理想 oracle 比 D 低 5%，比 I− 只低约 2.4%（343.5 vs 351.9）。若要在部署时相对 I− 获得 ≥5% 收益，仅在 {D, F−} 间做实例级静态选择在 oracle 意义下也达不到；这在 M3 前就说明预设的实用目标很难达成。

## 3. 家族结构

![F− vs D per family](m2/figures/family_log2ratio.png)

- F− 明显占优（log2 比 < −0.3，n ≥ 3）：polynomial-multiplication（val, 4）、fpga-routing（3）、brent-equations（19）、cryptography-ascon（26，F− 多解 4 例）、risc-instruction-removal（val, 4）。
- F− 明显劣势：set-covering（25 例中 D 解 23、F− 解 5）、heule-nol（5 vs 0）、random-circuits、hardware（18 vs 15）、independent-set（7 vs 3）、scheduling（30 vs 23）、influence-maximization、pythagorean-triples 等。
- 多数大家族（miter、cryptography-simon、multiplier、hamiltonian、coloring、tseitin）差异小或双方大量超时。图着色（文献 R9 的动机家族）在本数据的 `coloring` 组（val, 29 例）中 F− 并不占优（D 4 解，F− 3 解）。

![D vs F− scatter](m2/figures/scatter_D_Fminus.png) ![cactus](m2/figures/cactus_main.png)

## 4. 机制诊断（RQ4）

| 配置 | 含义 | SAT solved | UNSAT solved | PAR2 |
|---|---|---|---|---|
| D | stock：target + rephase，正初始 | 197 | 166 | 361.5 |
| D/no-R | 仅关 rephase | 136 | 177 | 397.6 |
| I−/no-R | 负初始、关 rephase（F− 的 rephase 匹配对照） | 153 | 176 | 386.2 |
| S | 纯 saved（无 target、无 rephase，负 fallback） | 135 | **184** | 394.2 |
| F− | 强制负（同时关 rephase） | 143 | 162 | 400.7 |
| P− | 轨道 P：仅自由决策强制负，rephase/target 保留 | 145 | 157 | 403.4 |

（观察到的答案按任一配置的已验证结果分层：SAT 235，UNSAT 192，全部配置均未解 390。）

**[实验]** 分解：
1. **关闭 rephase 是 SAT 损失的主因**：D → D/no-R 少解 61 个 SAT，但多解 11 个 UNSAT。
2. **在同样关闭 rephase 的条件下，强制方向比使用 saved 相位更差**：F− 比 I−/no-R 少解 10 个 SAT、14 个 UNSAT。
3. **仅强制决策方向而保留 rephase（P−）同样差**（SAT 145、UNSAT 157）：被强制的决策不再读取 rephase 写入的 saved/target，rephase 的作用实际失效；P− 在 UNSAT 上甚至更差，可能因为它仍执行 rephase/walk 的成本却得不到收益（[假说]）。
4. **UNSAT 上“不 rephase、用 saved”最好**（S 184、D/no-R 177 vs D 166）：stock 默认的 rephase 调度对 UNSAT 有净成本（[实验]，本数据与 cutoff 下）。这与 forcephase 的 UNSAT 表现无关：F− 并未获得这部分收益。

因此“F− 的好坏”不能归因于“负方向”：它是“关闭 rephase”（对 SAT 大负面、对 UNSAT 小正面）与“忽略 saved/target 相位”（对两类都负面）的组合；只有少数家族（见第 3 节）在组合后仍净受益。

## 5. 编码敏感性（H1）

实验 `m2_encoding`：dev 中 D 或 F− 解出的 388 个实例；每个实例生成两种保持可满足性的变体（`tools/cnfscramble`）：**flipall**（每个变量换成其否定）和 **flipr:1**（每个变量以 1/2 概率换号，种子 1）；运行 D 与 F−。变体与原实例属于同一组，只用于分析，不增加独立样本。详表 [m2/encoding.md](m2/encoding.md)。

| 编码 | PAR2 D | PAR2 F− | solved D / F− | F− 更快 / D 更快 |
|---|---|---|---|---|
| 原始 | 97.9 | 180.4 | 363 / 305 | 151 / 234 |
| flipall | 98.6 | 214.2 | 359 / 280 | 140 / 225 |
| flipr:1 | 167.0 | 228.8 | 314 / 272 | 138 / 191 |

（此子集按“原编码下至少一方解出”选出，因此原编码的 PAR2 偏低；比较只在编码之间、配置之间进行。）

**[实验]**
1. **对称性检查**：flipall 上的 F− 等价于原编码上的“强制正”，flipall 上的 D 等价于原编码上的 I−（初始负）。聚合结果吻合（F− on flipall PAR2 214.2 vs F+ on 原编码 217.8；D on flipall 98.6 vs I− 98.4），但逐实例轨迹只在极少数实例上完全相同（265 个双解实例中 5 个），说明 CaDiCaL 的搜索在符号上不是逐步对称的（变量序、平局打破等依赖文字编号），只是在统计意义上近似对称。
2. **编码极性本身携带信息**：随机翻转一半变量的符号后，**stock D 也明显变差**（PAR2 97.9 → 167.0），说明原生相位启发式（正初始相位、target/rephase original 方向）同样受益于编码的极性结构。
3. **F− 的获胜家族主要由编码极性驱动**（家族组平均 log2(PAR2 F−/PAR2 D)，负数为 F− 更好）：brent-equations −2.50（原）→ +10.20（flipall）→ 0.00（flipr）；polynomial-multiplication −0.72 → +4.37 → +0.62；profitable-robust-production −0.15 → +2.18 → +0.41；maxsat-optimum −0.18 → +1.00 → +0.07。翻转全部符号后这些家族上 F− 变成明显劣势（即“强制正”很差），随机翻转后优势消失。
4. **少数家族的 F− 优势不依赖方向**：multiplier（−1.39 / −0.26 / −0.74）、cryptography-ascon（−0.45 / +0.25 / −0.42）、fpga-routing（−0.44 / −0.20 / −0.31）。这与第 4 节“关闭 rephase 对 UNSAT 有利”一致（[假说]：这些家族得益于“固定方向 + 无 rephase”，而不是“负”）。
5. **F− 的失利家族与方向无关**：set-covering（+4.28 / +4.41 / +3.79）、heule-nol、subsumptiontest、random-circuits、scheduling 在三种编码下都大幅不利，来源是“强制 + 关闭 rephase”而非极性。
6. 逐实例 F− 相对优势在原编码与随机翻转之间相关 r = 0.48（同号 57%），与全局翻转之间 r = 0.09。

**结论**：H1（“负分支收益与编码赋值偏好有关”）在 F− 获胜的家族上得到支持，且这种收益是编码相关的，不是逻辑问题的性质；但 F− 的整体劣势主要来自与方向无关的机制（第 4 节）。

## 5b. 代表性实例轨迹（按固定规则选取）

`scripts/plot_trajectories.py` 用固定规则选出 4 个 dev 实例并画出遥测轨迹（CPU 时间、窗口平均 glue、负自由决策比例、best 赋值比例随冲突数变化），见 [trajectories/trajectories.md](trajectories/trajectories.md)：
- **A：F− 相对 D 加速最大**——brent-equations（SAT）：D 257.8 s，F− 1.4 s，I− 0.3 s。仅把初始方向设为负已足够，说明收益来自编码中“多数变量为假”的模型结构（与第 5 节全局翻转后的大幅反转一致）。
- **B：F− 相对 D 损失最大**——scheduling（SAT）：D 0.1 s，F− 超时，F−→D@1e4 0.9 s。强制负使原本几乎立即可解的实例变得不可解；只要在 1e4 冲突后交还原生策略就几乎恢复。
- C、D 见 [M4 报告](M4_report.md) §3。

## 6. 结论、未通过项与下一步

- RQ1（互补性）：D/F− 的实例级互补存在（oracle 5%），集中在少数家族；F− 整体劣势显著，且在 SAT 上更明显。
- 预设门槛（SBS–VBS < 2% 时先做机制分析）未触发；但 oracle 相对 validation-SBS（I−）只有约 2.4%，相对 I− 达到 5% 的实用目标在静态意义下不可能，M3/M4 主要回答“能否预测、在线信息是否有用”。
- 新增次要变体（开发集决定，见 EXPERIMENT_LOG 20:25）：I− prefix → NEGATIVE（NATIVE_INIT_NEG，phase 固定 0 只切 forcephase），与 D prefix 结果分开报告。
- 局限：单一 cutoff 300 s；seed 0；family 组是保守别名 + isohash 合并，部分 GBD 家族本身较粗（如 `hardware`、`cryptography`）。
