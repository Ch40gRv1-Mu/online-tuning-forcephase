# 最终研究报告（v2，经审计修正）：CaDiCaL 何时该用原生相位策略、何时该强制负分支？

状态：第一轮 M0–M5 于 2026-10-19 完成；同日按 [Agent Goal v2](../docs/AGENT_GOAL_AUDIT_V2.md) 完成事后审计与收尾（[纠正协议](../docs/CORRECTION_PROTOCOL.md)、[逐项关闭记录](AUDIT_CLOSURE.md)）。第一轮原文存档：[FINAL_REPORT_round1.md](FINAL_REPORT_round1.md)。分支 `research/forcephase-study`；冻结点 tag `m5-freeze`（未改动）。阶段报告：[M0_M1](M0_M1_report.md)、[M2](M2_report.md)、[M3](M3_report.md)、[M4](M4_report.md)、[M5](M5_report.md)；审计产物：[reports/audit_v2/](audit_v2/)、[results/audit_v2/](../results/audit_v2/)。

## English abstract

We study when CaDiCaL 3.0.1 should use its native phase policy (saved/target phases with rephasing) and when it should force negative decision literals (`--forcephase=1 --phase=0`), and whether cheap observations available during search predict that choice. A ~100-line hook applies the effective (forcephase, phase) pair at natural restarts (track C) or overrides only free-decision signs (track P), with JSONL telemetry and state digests; with the controller off or only observing, search is identical to upstream. On 817 development instances from the SAT Competition 2023–2025 main tracks (300 s CPU, every model checked, every UNSAT answer certified by a checked LRAT proof), forced negative branching solves 58 fewer instances than the stock default (−10.8% PAR2 [−20.9, −4.3]), mostly on satisfiable instances. Among single-factor comparisons, disabling rephasing (which forcephase implies) is the step with clear evidence (−10.0% PAR2 [−21.7, −2.0]; 61 fewer SAT, 11 more UNSAT solved); forcing the negative sign instead of using target/saved phases with rephasing already off has a worse point estimate (−3.8% [−7.7, +0.2]) but an interval that includes zero. In the families where forced-negative wins, the advantage reverses when every variable sign is flipped and vanishes under random flips, i.e. it is a property of the encoding. Deterministic same-state replays (5,887 forks; 5,884 with verified identical prefixes and an applied switch, 3 censored budget-boundary timeouts) give an oracle headroom of about 5% for one switch, but family-grouped nested cross-validation found no static, time-only or online one-shot selector that beats never switching. A post-hoc audit found that one polarity feature (saved-phase flip rate) had been computed incorrectly; after fixing the controller and excluding that feature, the model comparison was rerun on the same data and folds, and the conclusion is unchanged. The pre-registered observation-free schedule (forced negative for the first 10^4 conflicts, then native) changed PAR2 on the frozen family-disjoint test set by −1.0% [−3.4, +1.7] relative to the validation-selected static configuration (negative initial phase), so the ≥5% target was not met. A low-noise retest shows telemetry overhead of +0.05% median and +0.35% at the 95th percentile. For this solver, benchmark distribution and cutoff, forced negative branching helps only on polarity-matched encodings, and the observations, models and budget used here found no transferable signal for when to switch.

## 0. 表述约定

- **[源码]** 固定源码已证实；**[实验]** 本项目实验已观察（给出数据范围）；**[假说]** 尚待检验。
- 结果来源标注：**【第一轮冻结】** M5 预注册 held-out 结果（冻结后未改）；**【纠正后开发】** 开发集（train+val）结果，经 audit v2 门禁核实、必要时按纠正协议重算；**【事后探索】** 看过结果后才定义的分析（含看过 test 之后的分层），只作描述与假说来源。
- 所有表图由仓库脚本从运行记录生成；运行记录可通过 `run_id` 追溯到 `$FP_DATA/runs/`。

## 1. 研究问题与回答（有边界的结论）

数据范围（全部问题）：CaDiCaL 3.0.1 固定提交；SAT Competition 2023–2026 主赛道、解压后 ≤100 MB；T = 300 s CPU；所有配置统一输出 LRAT 证明。

**RQ1：何时负分支有利 / 有害？**
- 【纠正后开发】要区分五种干预：仅初始负 I−（只改初始 / original 方向）、全程强制负 F−（同时关闭 rephase）、仅决策强制负 P−（rephase 照常运行但无法影响自由决策）、关闭 rephase（D/no-R、I−/no-R）、早期负 prefix（F−→D：前 1e4 冲突强制负后交还原生）。在 817 个 dev 实例上相对 stock D：I− +2.7% PAR2 [+0.3, +5.6]；F− −10.8% [−20.9, −4.3]；P− −11.6% [−21.7, −5.3]；D/no-R −10.0% [−21.7, −2.0]；F−→D@1e4 +3.4% [+0.9, +6.6]（[M2](M2_report.md)、[M4](M4_report.md)）。
- 【纠正后开发】全部 89 个家族组的效果见 [audit_v2/family_effects.md](audit_v2/family_effects.md)：相对 D 明显更好 / 更差（|log2 PAR2 比| > 0.1）的家族数，F− 16 / 31，I− 22 / 9，P− 13 / 35，F−→D 24 / 11。F− 占优的例子：brent-equations、cryptography-ascon、polynomial-multiplication、fpga-routing；大幅失利：set-covering（D 解 23/25，F− 5）、heule-nol、scheduling、hardware、random-circuits。
- 【纠正后开发】符号翻转只在“原编码下 D 或 F− 解出”的 388 个实例上做过（[encoding.md](m2/encoding.md)）：在其中 F− 占优的家族，优势在全局翻转后反转（brent-equations：log2 比 −2.50 → +10.20）、随机翻转后消失；随机翻转也让 stock D 变差（PAR2 97.9 → 167.0）。这说明**这些家族**的 F− 收益是编码极性的性质，但不能推广为所有 F− 获胜家族的原因（multiplier、cryptography-ascon、fpga-routing 在随机翻转后仍有较小优势）。
- 【第一轮冻结】held-out：F− 在 family-disjoint test 上相对 D −29.2% PAR2，在 2026 年实例上 −0.1%。
- 【事后探索】按事后观察到的答案分层：F− 的损失主要在 SAT 上（dev：143 vs 197；test：25.3 vs 60.0 平均 solved）；SAT/UNSAT 部署时未知，不能作为输入。

**RQ2：哪些在线观测有用？**
- 【纠正后开发】在同状态重放标签（8 组 5,887 次重放中 5,884 个有效配对）上，按预注册的递增特征组（静态 C、进度/机制 R、极性 P、学习质量 Q、搜索形态 T、全部）、K ∈ {1e3, 1e4, 1e5}、D 或 I− prefix、深度 ≤ 3 树或 L2 logistic，做家族分组嵌套交叉验证（外层 folds 固定为 `reports/m3/folds.csv`）。**排除失效的 `x_saved_flip_frac` 后重算**：没有一个可部署选择器（静态、time-only 或在线）的 out-of-fold PAR2 优于“从不切换”；含 P/Q/T 组的 D prefix 模型比不切换差 0.4–3.5%，与 shuffled-label 对照处于同一水平（[audit_v2/m3/comparison.md](audit_v2/m3/comparison.md)）。
- 【纠正后开发】区分三种层面：单变量 Spearman 相关在所有实例上最高 |ρ| ≈ 0.27（家族**之间**的差异），扣除家族组均值后基本消失（|ρ_within| ≲ 0.1，个别 0.18–0.25）；在**未见家族**上的预测（OOF）没有可用收益（[audit_v2/m3/feature_signal.md](audit_v2/m3/feature_signal.md)）。
- 结论措辞：**在这些数据、预算（300 s）、特征与模型容量下，没有找到可在家族外迁移的在线信号**；这不表示在线信息普遍不存在。正确实现的 flip 特征没有在全集上重新采集，其价值未知。

**RQ3：是否需要反复切换？**
- 【纠正后开发】同状态重放：在三个 K 都有未删失偏好的 269 个实例中，偏好随 K 改变的有 56 个（21%），其中差异双向都 ≥ 1.41× 的稳健改变只有 19 个（7%，阈值为事后选定）。按切换时机的 oracle 比 D 低 7.5%，高于静态 D/F− oracle 的 5.0%（诊断量）。
- 【纠正后开发】一次选择（M3）没有超过不切换；**无观测**的固定调度（M4，预先固定的 8 个）中，“早期负 prefix 再交还原生”在 dev 上优于 D，但与 I− 不可区分（F−→D@1e4 相对 I− +0.8% [−0.7, +2.2]）；按模式调度（只在 focused 或只在 stable 时强制负）不优于 D。
- **基于内容观测的重复切换控制器没有实施**：M3 门槛（在线观测须有可迁移价值）未满足，因此按协议不继续该分支。这是“未继续”，不是“已被否定”。
- 【第一轮冻结】held-out 上，预注册候选 F−→D@1e4 相对 I− −1.0% [−3.4, +1.7]（test），相对 D +1.3% [+0.2, +2.5]（t2026）；随机切换时机基线与候选无显著差异。

**RQ4：机制与开销解释得住吗？**
- 【纠正后开发】只比较仅差一个因素的配置对（[audit_v2/ablation_pairs.md](audit_v2/ablation_pairs.md)；因素按固定源码定义）：

  | 配对（只改一个因素） | Δ PAR2 [95% CI] | Δ SAT / UNSAT solved |
  |---|---|---|
  | D → D/no-R：关闭 rephase（及其触发的 walk/warmup） | −10.0% [−21.7, −2.0] | −61 / +11 |
  | D/no-R → I−/no-R：初始方向（rephase 关） | +2.9% [−0.4, +7.3] | +17 / −1 |
  | I−/no-R → F−：强制负代替 target/saved（rephase 均关、初始均负） | −3.8% [−7.7, +0.2] | −10 / −14 |
  | I−/no-R → S：关闭 target | −2.1% [−7.3, +1.2] | −18 / +8 |
  | D → P−：只强制自由决策为负 | −11.6% [−21.7, −5.3] | −52 / −9 |
  | F+ → F−：强制方向的符号 | +2.1% [−3.6, +9.5] | +18 / −5 |
  | D → I−：初始 / original 方向 | +2.7% [+0.3, +5.6] | +11 / +3 |

  可靠的说法：关闭 rephase 有清楚的整体损害、主要在 SAT 上，对 UNSAT 略有帮助；在 rephase 已关闭时，强制负相对 target/saved 的点估计更差，但区间跨 0，**证据不足**（第一轮报告“强制方向比 saved 更差”的说法已收窄）；只强制决策符号（P−）有清楚的损害。沿 D → D/no-R → I−/no-R → F− 这一条路径，SAT 解出数变化为 −61、+17、−10；分解依赖路径，交互未检验；SAT/UNSAT 分层为事后描述，不作因果结论。
- 【纠正后开发】开销：低噪声复测（48 个分层 dev 实例 × 6 次重复，同核、平衡随机顺序）中，telemetry 相对控制器关闭中位 +0.05%、p95 +0.35% [+0.28, +0.52]；补丁关闭相对上游中位 +0.30%（始终开启的计数器）。第一轮高并发下 p95 4.16% 的超标主要是计时噪声（[audit_v2/m1/retest.md](audit_v2/m1/retest.md)）。开销不是负结果的原因。

**一句话结论**：在本数据、版本与 300 s cutoff 下，强制负分支只在编码极性与模型匹配的家族上有利；本项目使用的廉价观测与浅层模型没有找到能在家族外识别这些情况的信号；可部署的最佳选择仍是静态配置（I− 或 stock D），二者在 held-out family-disjoint test 上无显著差异。

## 2. 方法

### 2.1 求解器与动作语义
- 固定 CaDiCaL `c60730422e758ef1cebe7aeddf2dda31c996bf04`（3.0.1）；补丁 `patches/cadical-fpc.patch`（约 100 行）+ 控制器 `solver/`；第一轮全部实验使用 v1 控制器（`solver/v1/`，构建变体 `fpc`），audit v2 修复后为 v2（`fpc2`，schema 2）。二者补丁相同；控制器关闭、telemetry、fixed、冻结调度与 oneshot 下搜索逐项相同（[DESIGN §5a](../docs/DESIGN.md)）。
- 轨道 C：动作是有效值对 `(forcephase, phase)`：NATIVE=(0,1)、NEGATIVE=(1,0)、NATIVE_INIT_NEG=(0,0)、POSITIVE=(1,1)，在所有读取这两个选项的位置一致生效；固定动作在变量创建前生效，与命令行逐项等价。轨道 P：只覆盖自由决策符号。切换只在自然 restart 之后；不新增 restart、不清空 saved/target/best；返回 NATIVE 时过期 rephase 立即发生（`fpcrlim` 为推迟它的消融）。
- 默认 `phase=1`，裸 `--forcephase` 强制正方向（M0 已用 API 与决策计数验证）。

### 2.2 正确性、数据门禁与可复现性
- 全部 solved 结果经验证（SAT：独立模型检查；UNSAT：二进制 LRAT + lrat-trim）；wrong / unverified 均为 0。
- audit v2 全账本完整性审计：36,077 次运行 0 问题、1,325 个 CNF 哈希通过；6 次运行在 cutoff 后被 SIGKILL（只缺遥测 final 记录，按协议附录 A 处理并披露）。M3 数据经严格门禁逐行分类，0 个数据错误（[gate_summary](../results/audit_v2/m3/gate_summary.md)）。
- 内容寻址 run id、不可覆盖的结果、断点续跑、完整尝试日志；从干净 clone 实际复现了小型全流程与修订 M3 分析（[repro](../results/audit_v2/repro/README.md)）。

### 2.3 数据、划分与统计
- 开发池 2023–2025 按家族组划分：train 612 / 67 组、val 205 / 22、test 204 / 21（运行前固定）；2026 年不重复的 304 例为年份外推集 t2026。test 与 t2026 在第一轮 M5 中已见，audit v2 未用于任何选择。
- PAR2（solved 且验证通过记 CPU 秒，否则 2T）；先对 seed 平均；相对差的 95% 区间为家族组 cluster bootstrap（10,000 次）；timeout 为右删失；oracle 只作诊断。

## 3. M0–M1：语义、正确性与开销

【纠正后开发】M0：7,604 次运行（含带断言构建）0 失败，154 组上游/补丁搜索统计逐项相同，32 个重放 digest 一致；audit v2 在 v2 控制器上重跑同一套件 0 失败。M1：第一轮 292 例 × 3 配置 × 3 次（48 进程并发）中位 0.08%、p95 4.16%（未证明 ≤ 3%）；audit v2 低噪声复测 48 例 × 3 × 6：中位 +0.05%、p95 +0.35%（这 48 例上达到目标；不改写第一轮数值）。更正：upstream 二进制哈希应为 `250220f9…`（[M0_M1 报告](M0_M1_report.md)）。

## 4. M2：静态互补性、机制与编码（dev）

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

【纠正后开发】静态 D/F− oracle 比 D 低 5.0% [2.5, 8.0]，比 I− 只低 2.4%。机制配对与编码结论见第 1 节 RQ1、RQ4。

## 5. M3：一次选择（dev，经纠正）

【纠正后开发】数据：严格门禁后的同状态配对（训练用 6 组：4,391 次重放，4,388 个有效配对，3 个预算边界双超时 `censored_unmatched`；另有 P 轨道与反向各 1 组）。纠正：排除失效的 `x_saved_flip_frac`，其余（数据、folds、网格、权重、bootstrap）不变；第一轮表先被精确复现（68 个选择器差 0），不使用该特征的 50 个选择器修订后不变。修订后关键行（out-of-fold，817 例）：

| 选择器 | PAR2 | solved | 相对 D [CI] | 相对 I− [CI] |
|---|---|---|---|---|
| D（不切换） | 361.5 | 363 | — | −2.7% [−6.0, −0.3] |
| I−（validation-SBS） | 351.9 | 377 | +2.7% [+0.3, +5.6] | — |
| 静态选择器 D/F− | 364.2 | 360 | −0.7% [−2.4, +0.2] | −3.5% |
| 一次选择 @1e3 [time] | 361.3 | 364 | +0.1% [−0.7, +0.9] | −2.7% |
| 一次选择 @1e3 [C+R] | 364.6 | 360 | −0.8% [−2.5, +0.2] | −3.6% |
| 一次选择 @1e3 [C+R+P]（修订） | 370.9 | 350 | −2.6% [−5.2, −0.5] | −5.4% |
| 一次选择 @1e3 [all]（修订） | 369.6 | 351 | −2.2% [−4.4, −0.3] | −5.0% |
| 一次选择 @1e3 [all] shuffled（修订） | 365.6 | 356 | −1.1% [−2.5, +0.1] | −3.9% |
| 一次选择 @1e4 [C+R+P]（修订） | 363.1 | 360 | −0.4% [−2.1, +0.8] | −3.2% |
| 一次选择 @1e4 [all]（修订） | 364.8 | 357 | −0.9% [−2.5, +0.6] | −3.7% |
| 一次选择 @1e5 [all]（修订） | 366.0 | 357 | −1.2% [−3.8, +0.5] | −4.0% |
| I− prefix 一次选择 @1e3 [all]（修订） | 356.2 | 371 | +1.5% | −1.2% [−2.6, −0.3] |
| I− prefix 一次选择 @1e4 [all]（修订） | 352.4 | 376 | +2.5% | −0.1% [−0.5, −0.0] |
| *oracle* 一次选择 @1e3（D / I− prefix） | 342.3 / 335.1 | 389 / 403 | +5.3% / +7.3% | +2.7% / +4.8% |

导出的 time-only 与静态策略不含该特征，修订后与第一轮参数相同（冻结 M5 不受影响）；Python 与 C++ 分数差 ≤ 3.3e−7、动作 0 分歧；含 CPU 时间特征的 D prefix 策略在 dev 上只在 4.4% 的决策点切换，±5–10% 计时扰动改变 0.1–0.5% 的决策（[policy_consistency.md](audit_v2/m3/policy_consistency.md)）。

## 6. M4：门槛判断与无观测固定调度（dev）

【纠正后开发】（数据经门禁核实，未受 flip 影响）

| 策略 | PAR2 | solved（SAT/UNSAT） | 相对 D | 相对 I− |
|---|---|---|---|---|
| F−→D @1e4（M5 候选） | 349.2 | 382（210/172） | +3.4% [+0.9, +6.6] | +0.8% [−0.7, +2.2] |
| F−→D @1e3 | 351.1 | 380（206/174） | +2.9% [+0.3, +6.2] | +0.2% |
| F−→D @1e5 | 353.9 | 375（201/174） | +2.1% [+0.2, +4.3] | −0.6% |
| F−→I− @1e4 | 351.6 | 380（207/173） | +2.8% | +0.1% |
| F−→D @1e4，推迟 rephase | 352.4 | 379（208/171） | +2.5% | −0.1% |
| focused 时 NEG / stable 时 NEG | 361.0 / 368.8 | 368 / 354 | +0.2% / −2.0% | −2.6% / −4.8% |
| D→F− @1e4 | 398.8 | 306 | −10.3% | −13.3% |

## 7. M5：冻结后的 held-out 评估

【第一轮冻结】冻结于 `m5-freeze`（提交 23:31:04Z，早于第一条 M5 运行 23:31:45Z）；13,716 次运行全部完成并验证。audit v2 从原始记录独立重算，点估计一致（差 ≤ 1.4e−6）、区间差 ≤ 0.26 个百分点（[m5_recheck.md](audit_v2/m5_recheck.md)）。

**family-disjoint test（204 例，21 组，3 seed）**：

| 策略 | PAR2 | 平均 solved | 相对 I−（SBS） | 相对 D |
|---|---|---|---|---|
| F−→D @1e4（唯一主要候选） | 363.8 | 95.0 | −1.0% [−3.4, +1.7] | −0.9% [−4.8, +2.1] |
| I−（validation-SBS） | 360.3 | 97.3 | — | +0.1% |
| D（stock） | 360.5 | 98.3 | −0.1% | — |
| F− | 465.6 | 56.7 | −29.2% [−70.4, −9.7] | −29.2% |
| F+ | 433.1 | 70.0 | −20.2% | −20.2% |
| 静态选择器 | 361.0 | 98.0 | −0.2% | −0.1% |
| M3 在线一次选择器（time-only） | 369.5 | 94.0 | −2.5% | −2.5% [−5.7, −0.3] |
| F−→D @1e3 / @1e5 | 357.9 / 379.8 | 98.3 / 90.0 | +0.7% / −5.4% | +0.7% / −5.4% |
| 随机切换时机 | 365.6 | 95.3 | −1.5% | −1.4% |
| D→F− @1e4 | 458.2 | 59.7 | −27.2% | −27.1% |

**主假设（相对 I− ≥ 5%、CI 不含 0、solved 不降）未成立，保留。** t2026（304 例）：候选相对 D +1.3% [+0.2, +2.5]、相对 I− −0.7% [−2.0, +0.4]；新家族上相对 I− −1.8% [−3.6, −0.6]。冻结 M5 不依赖失效的 flip 特征（候选是无观测调度；M3 选择器为 time-only）。

【事后探索】强制正在 UNSAT 上最好（test 40.7 vs D 38.3 平均 solved；t2026 30.7 vs 26.0），与“关闭 rephase 对 UNSAT 略有利”的开发集观察方向一致；部署时 UNSAT 未知，只作为待独立检验的假说。

## 8. 成本

- 第一轮：36,157 次求解运行，求解器 CPU 2,117 h（含 LRAT 输出），检查 7.7 h（[COMPUTE_LEDGER.md](COMPUTE_LEDGER.md)）。首次 smoke 尝试的 attempts 日志已删除，继续披露。
- audit v2：约 23.8 CPU 核时（预算 100），其中开销复测 17.1 h，其余为测试、重算与复现（含一次被中断的集成测试按上限 3.25 h 计）（[audit_v2/COMPUTE_AUDIT_V2.md](audit_v2/COMPUTE_AUDIT_V2.md)）。没有购买算力。

## 9. 反例与局限

**反例**
- F− 并非总是更差：brent-equations、cryptography-ascon、polynomial-multiplication、fpga-routing 上占优；其中极性驱动的家族在符号翻转后反转。
- F− 在 set-covering 上灾难性，且与编码方向无关。
- 候选 F−→D@1e4 不是对每个实例都安全：dev 上相对 I− 的最大回退在 hamiltonian（单例约 600 s），test 上在 van-der-waerden、school-timetabling 等。
- dev 上选出的调度相对 D 的 +3.4% 与 I− 相对 D 的 +2.7% 都没有在 family-disjoint test 上复现（−0.9%、+0.1%），后者在 t2026 上复现（+1.9%）：小效应对家族组成敏感，在 9 个调度中按 dev 取最优有乐观偏差。
- 冻结的 M3 time-only 选择器在 test 上比 D 差 2.5%，而在 dev OOF 中与 D 持平。

**局限**
- 单一 cutoff 300 s、单一求解器版本；家族组为保守合并，isohash 不是完整同构判定。
- M3 只试了浅树与 L2 logistic、三个 prefix 长度与预定义特征组；正确实现的 flip 未重新采集。
- runner 在 SIGTERM 后 10 s 宽限期内未退出的运行被 SIGKILL（6 次，同一实例）。
- 开销复测只覆盖 48 个分层实例；第一轮 292 例的高并发 p95 仍为 4.16%。
- 主表统一输出 LRAT 证明（约 5–10% 时间），绝对时间与无证明运行不同。
- 部分 dev 机制差异的区间较宽（家族组 89 个、实例 817 个）。

## 10. 与相关工作的差异

- **Phase saving 与 target/rephase（R1、R2）**：本项目在固定的现代 CaDiCaL 中按单因素配对分解 forcephase：关闭 rephase 对 SAT 的损害有清楚证据，对 UNSAT 略有利；强制方向本身在 rephase 匹配后的附加损害只有点估计。这与 Biere & Fleury 关于 target/rephase 对可满足实例重要的观察方向一致。
- **负分支应用证据（R4、R9）**：复现了“负分支在某些编码上有效”，并用符号翻转表明这类收益是编码相关的；在 SAT Competition 2023–2025 的广泛家族上强制负整体有害。
- **在线 phase/rephase 选择（R5–R8）**：本项目用同状态确定性重放得到反事实标签，在家族不相交评估下发现简单在线特征不能预测切换收益；没有实施 bandit，因为门槛未满足（不是否定）。
- **算法选择（R10）**：静态廉价特征选择器在家族外同样无收益。
- **NeuroBack（R11）**：逐变量相位学习是不同动作空间；本项目结果提示若要利用极性，应在变量层面（[假说]）。

## 11. 已知、未被支持的假说与未回答的问题

**已验证（本数据、本版本、300 s）**：强制负整体有害，主要伤 SAT；关闭 rephase 是有清楚证据的单因素损害；F− 获胜家族中经翻转检验的那些是编码极性驱动；廉价静态/在线特征与浅层模型在家族外没有找到可用的切换信号；早期负 prefix 在 dev 与 2026 年实例上略优于 stock D，但在 family-disjoint test 上无差异，且从未优于仅初始负；控制器观测开销可忽略。

**被当前证据削弱的假说**：H2（原生 prefix 中负决策多就该强制负——方向反而相反）；“在线观测优于静态/时间基线”；“强制方向本身（在 rephase 匹配后）显著有害”（只剩点估计）；“早期负 prefix 优于仅初始负”。

**未回答**：长 cutoff 与其他求解器上的结论；正确实现的 flip 或更强的廉价在线信号能否在家族外预测切换；负 prefix 收益来自学习子句、变量活性还是早期 saved 相位；“可能 UNSAT 时关闭 rephase”能否在家族外获益（需新的、事先固定的 held-out 集）；基于内容的重复切换控制器（未实施）。

**可验证的下一步**：(1) 5000 s cutoff 的小测试集重测 D、I−、F−→D@1e4；(2) v2 控制器在开发集上重新采集正确 flip，按新协议检验；(3) 变量粒度的极性先验；(4) 加入 2017–2022 年份以增加家族数；(5) 在新的独立 held-out 上检验“无 rephase / 强制正对 UNSAT 有利”的事后观察。
