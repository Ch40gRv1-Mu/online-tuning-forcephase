# 研究计划：何时使用 forcephase，什么在线观测能够预测收益？

日期：2026-10-18。状态：调研与预注册计划，尚无本项目性能结果。执行细节见 [实验协议](EXPERIMENT_PROTOCOL.md)，源码事实见 [源码审计](SOURCE_AUDIT.md)，文献见 [相关工作](RELATED_WORK.md)。

## 1. 将课题描述转为可检验问题

CDCL 的 branching 包含两个选择：先挑变量，再挑这个变量的真假值，即 phase / polarity。本项目只主动控制后者，保持变量选择、重启、学习和简化等其余配置一致。不同 phase 会产生不同冲突、学习子句和后续变量排序，这是策略影响的自然结果，不要求两条完整轨迹保持相同。

Phase saving 通常保存变量最近一次赋值，在以后再次决策这个变量时复用。它有助于在回溯和重启后保留搜索方向；最近赋值包括决策与传播，并非仅 unit propagation。现代 CaDiCaL 还会利用 target/best assignments 和 rephasing。原题“All CDCL solvers use phase-saving”应理解为常见实践，不能作为没有例外的事实。[相关工作 R1–R4](RELATED_WORK.md)

Negative branching 指常规自由决策选择 `x=false`；BCP 仍必须执行逻辑蕴含，因此结果 trail 可以包含正 literal。它可能适合某些编码，但不存在对任意 CNF 都更好的符号方向：把变量 `x` 重命名为 `¬y` 就会交换相应真假偏好而保持可满足性。文献在图着色、Collatz 等实例中提供了应用证据，但不证明普遍最优。[相关工作 R4、R9](RELATED_WORK.md)

本项目依次回答：

1. **RQ1，互补性：** 原生策略与强制负分支各在哪些实例、家族和搜索模式上占优？与最佳静态策略相比，实例级选择还有多大空间？
2. **RQ2，可预测性：** 仅使用求解时可得的信息，能否在未见家族上预测该选择？在线轨迹特征是否超过静态 CNF 特征和 elapsed-time-only 策略？
3. **RQ3，时间变化：** 同一实例是否需要多次切换？反复切换是否超过使用同样观测预算的一次选择，以及无需观测的固定调度？
4. **RQ4，机制与成本：** 收益来自决策符号、禁用 rephasing、重启/回溯交互，还是它们的组合？总求解成本是否覆盖观测、推断和切换开销？

## 2. 科研范围与贡献边界

主任务限定 **一次性 DIMACS CNF、单进程单线程 CaDiCaL**。不以跨 solver 的任意配置调优、增量 SAT、MaxSAT、并行 portfolio 或逐变量 GNN 作为第一阶段任务。外部 benchmark 可以批量并行运行，但每个配置使用相同单核资源。

主要处理动作：`NATIVE` 和 `NEGATIVE`。文档中 NATIVE 是指定版本完整默认 phase policy，不能标为 SAVED。`POSITIVE`、纯 saved、rephase 控制组用于排除混杂，不先把动作空间扩成十几种策略。纯 saved 也必须给出可执行的定义，注明初始方向，避免把 `--target=0` 错当作关闭了 rephasing。

区分两个实验轨道，分别命名、分别报告：

- **配置轨道 C：** 比较实际原生 `forcephase/phase` 配置以及在内部安全位置应用等价配置的控制器；承认其包含 rephasing、`likely_phase` 等副作用。
- **极性轨道 P：** 添加研究 hook，只在自由 CDCL 决策位置覆盖符号，其余 phase 状态、rephasing 和 `likely_phase` 路径保留同一语义。它有助于解释机制，但不是原始 `--forcephase` 的完全等价实现。

不得跨轨道借用静态标签，也不得把 C 的配置收益全部归因于 P 的决策方向。先完成 C 的静态复现，再用 P 及少量因子消融解释关键结果；不要一开始做所有参数的笛卡尔积。

配置轨道 C 的主动作应显式定义成有效选项对：`NATIVE=(forcephase=0, phase=1)`、`NEGATIVE=(forcephase=1, phase=0)`。内部 controller 统一提供有效值，不绕过公开 API 的状态检查。若选择 `phase` 固定 0 而只切 `forcephase`，非强制动作须改名 `NATIVE_INIT_NEG`，与 stock default 分开。切换选项不会追溯重做变量创建时的 saved 初始化，因此固定配置从输入前启用，与原生 prefix 后切换，是不同实验条件；不能承诺历史状态相同。

已有 target phasing、动态 phase selection、Kissat-MAB-rephasing、DynamicSAT 和 duration-aware MAB 工作；本项目不能宣称首次在线调 phase。候选贡献是：**对强制负分支的严格条件研究；可解释在线观测在未见编码家族上的预测价值；剥离符号/调度副作用的因子实验；成本受限的原生/负分支切换。** 未完成邻近工作复查与实验前，不宣称 novel 或 SOTA。

## 3. 假说、观测与否证方式

以下是本项目提出的假说，不是文献已证明的结论。所有规则阈值只能在训练/验证集确定。

| 假说 | 可用观测或干预 | 什么证据会削弱它 |
| --- | --- | --- |
| H1：负分支收益与编码赋值偏好有关 | 正负 literal 分布、Horn/二元子句比例；同实例 sign-flip、变量置换；多种编码 | 只在训练家族有效，或改变编码符号后预测失效 |
| H2：原生 phase 与负分支的分歧能识别值得切换的状态 | 选中变量处原生建议为正的比例、saved phase 翻转率，结合窗口停滞指标 | 分歧特征在消融中没有增益，或者只是 elapsed conflicts 的替代 |
| H3：传播和学习质量变化比绝对计数更有用 | propagations/decision、决策/冲突、窗口 glue/LBD、回溯跨度、target/best trail 增长 | held-out 最终 PAR2 与这些 proxy 无关或方向反转 |
| H4：stable/focused 与 chronological/nonchronological backtrack 状态改变最佳动作 | 模式标签、分模式窗口、同一控制器的模式消融 | 按模式调度与无需观测的固定调度无区别 |
| H5：重复选择优于一次选择 | 相同预算的一次选择、固定调度、随机调度、重复控制器 | 收益被一次选择复现，或全部来自切换次数/时间安排 |

不能由“负 literal 更多”直接推出负决策更好；literal 出现频率不是完整语义。高 conflicts/s 可能只是更快地产生低价值冲突；低 LBD 可能由策略选择的子问题不同导致。特征解释必须建立在预测消融和最终求解结果上，而非图形相关性。

## 4. 最小研究路线

### M0：锁定源码与正确性（第一道门）

采用 README 的固定 SHA；记录编译器、构建命令、CPU、内存、OS、二进制 hash。阅读实际构建源码并复查 [源码审计](SOURCE_AUDIT.md)。可以以 submodule、锁定下载加补丁或清晰 vendor 方案接入；必须保留上游许可证，不提交 build、CNF 和巨型日志。

先构建未修改上游，确认 CLI、默认值与退出码，再实现最小 instrumentation/controller。`Solver::set` 不是求解过程中可任意修改选项的接口；不要用定时线程调用它。不能为实现在线策略而反复销毁求解器，丢失学习状态。

验收：小 CNF 枚举/随机公式与可信 solver 核对；SAT 检查原始 CNF 的完整 model，UNSAT 使用 proof checker；覆盖原生、正/负决策、切换、空子句、根层传播。测试应直接验证符号优先级、已保存 phase、rephase 行为、mode 交互和不修改传播/assumptions。当前研究不需要主动使用 external propagator，但不得破坏现有优先级。

### M1：最小观测与无操作对照

先使用已有统计计数，每个决策/冲突只增加少量常数工作，不扫描整个 CNF、trail 或 phase 数组。JSONL 每个 epoch 输出一行，包含 schema 版本、动作、模式、冲突/决策/传播增量、时间、事件及缺失特征标记。stdout 保持 solver 输出兼容，遥测写独立文件或明确隔离流。

比较原始上游、控制器关闭、观测开启但保持原生、原生配置固定的 controller、固定负配置 controller。关闭控制器应保持搜索轨迹；启用无操作观测也应在确定性条件下保持决策/冲突摘要一致。工程目标是运行超过 1 秒的配对实例 telemetry-only median slowdown ≤1%、p95 ≤3%，超限优化或披露，不删除慢样本。日志 I/O、推断和特征提取必须计入主要时间。

### M2：静态互补性与可解释现象

运行默认、仅初始负、强制负、强制正，以及机制用的纯 saved / rephase 诊断组。先看各家族 SAT/UNSAT 分层的 solved、PAR2、散点图和双方胜负，再计算诊断性的 virtual best。若两种主要动作几乎没有互补，先研究原因与数据代表性，不直接投入复杂 RL。

M2 输出：完整配置表、实例 manifest、split、原始记录、互补性报告、3–5 个代表性实例的轨迹解释及反例。不能仅挑选负分支获胜实例，也不能把双方 timeout 当成等速。

### M3：先做一次选择，确认在线观测是否有价值

先实现三个小模型：静态特征选择器；固定原生 prefix 后使用在线特征的一次选择器；只有时间/冲突计数的选择器。首选浅树（建议深度 ≤3）或 logistic regression，部署为轻量 C++ 规则/系数，不在决策循环中调用 Python 或网络。

整场运行的原生/负分支标签，只能训练从头静态选择；prefix 后动作选择需要从**同一个搜索状态**继续两种动作。采用确定性 prefix 重放并验证状态摘要，不要求先实现完整状态序列化。prefix 成本包括在每个部署 run 总时间限额内；离线生成标签的多次运行记作训练成本。prefix 已解出的实例计入整体结果，但不伪造“必须切换”的样本。

如果在线特征不能超过静态/时间基线，保留该负结果；若一次选择已获得全部收益，应将结论表述为早期选择，不宣称需要持续 adaptation。

### M4：只有证据支持时才做重复切换

在 restart 或明确的 safe search boundary 处理动作；不为每个 epoch 人为增加重启。冲突窗口预算和最短驻留期由开发集选择，初始只考虑 `10^3, 10^4, 10^5` conflicts 三种量级中的少数候选。记录请求与实际应用时刻的差；没有到达安全点时不得谎称动作已生效。

优先可解释 hysteresis（超过阈值才进入负分支，恢复需另一阈值）和冷却期；保持独立 controller RNG，不能消费 solver RNG 改变无操作轨迹。比较相同切换预算的固定/随机调度和 M3 一次选择。若需 bandit，再比较简单 discounted/sliding-window 方案与文献对照，明确动作会改变后续 learned-clause state，常规独立同分布 bandit regret 理论不直接适用。

切换时保留还是清理 saved/target phases、是否触发额外 backtrack、重回 native 时如何处理逾期 rephase，均是显式设计因素；先默认保留历史并避免新增重启，再对关键交互做消融。若原生 restart 会复用旧 trail，记录新策略影响可能延迟，不默默关闭该功能。

### M5：冻结策略、保留测试和科研结论

在测试前冻结数据划分、主要指标、模型、阈值、epoch、切换协议和分析脚本 commit。使用 family-disjoint 测试为主，追加去重后的未来年份或不同来源测试；时间留出集若仍包含训练家族，不能声称家族泛化。测试集只用于最终报告，debug 遇到错误须记录重新冻结过程。

交付可复现的表和图、总体与家族结果、置信区间、严重回退案例、控制器开销、训练/测试 compute 账本。原始运行缺失、OOM、crash、timeout 必须区分，不能悄悄丢弃。最终是 positive、mixed 或 negative result 都可以，但证据链必须完整。

## 5. 主要验收与研究止损

硬性门槛：无错误答案；结果可复现；无测试泄漏；使用完整时间预算；基线等价性有证据；不得伪造实验。错误答案应立即隔离对应二进制与结果并修复，不能当作 timeout 掩盖。

预设的 practical positive target：在冻结 held-out 集上，相对**验证集选定的最佳静态主要基线**，总体 PAR2 降低至少 5%，paired family-cluster bootstrap 95% CI 排除零收益，且 solved 数无实质下降。另报告相对 stock default；若要声称超过所有静态基线，应逐一比较。5% 是本项目目标，不是文献定理或必须做出来的数字。样本/家族不足时给区间并降低结论强度。

若 oracle gap 很小、特征只能记住家族、重复切换不优于一次选择或观测开销吞掉收益，应收缩方案并写清原因。停止无限参数搜索；在完整负结果、简单策略与复杂策略之间按证据选择。不要为通过验收而反复改 held-out 设计。

## 6. 建议产物与执行顺序

```text
docs/                   调研、审计、计划和固定协议
third_party/            锁定的 solver 依赖或其说明
patches/                相对固定上游的可审阅修改（若采用补丁方案）
src/                    轻量 controller（若不放在上游树）
scripts/                获取、build、运行、校验、分析入口
configs/                baseline/policy/experiment 的显式配置
benchmarks/             manifest、family/split、校验信息；不含大CNF
tests/                  符号语义、正确性、同prefix和日志schema检查
results/                小型汇总与原始记录索引；大文件位于明确外部路径
reports/                各里程碑结果与最终报告
```

无需机械采用目录，但必须有等价职责和一条可以从干净 checkout 复现小型实验的命令。先 M0–M2，再 M3，最后按结果决定 M4。推荐先用不超过约 100 CPU 小时的 smoke/pilot；后续按 [实验协议](EXPERIMENT_PROTOCOL.md) 明确核算，而不是一开始下载全部年份并运行完整矩阵。

每个里程碑提交：本次变更、执行命令、实际数据范围、结果、未通过项、下一步及所需 compute。长任务支持 resume 和幂等结果去重；中断后从账本恢复，不能重跑已完成实验来替换不利结果。
