# 实验协议：何时强制负相位，哪些在线观察量值得使用

状态：研究前的预注册草案；本文的数值是默认预算与验收目标，不是已有实验结论。实施 agent 应先记录实际硬件和可用时数，选择下面能负担的一档；改变协议必须先写入 `EXPERIMENT_LOG.md`，注明是在接触哪些结果之前作出的决定。

固定上游：CaDiCaL `c60730422e758ef1cebe7aeddf2dda31c996bf04`，`VERSION=3.0.1`。参数与控制流程以 [SOURCE_AUDIT.md](SOURCE_AUDIT.md) 为准；文献定位见 [RELATED_WORK.md](RELATED_WORK.md)。

## 1. 要回答的问题和可证伪假设

1. **互补性**：原生默认与强制负相位在实例、家族、SAT/UNSAT 和搜索进程上分别有什么收益与损害？负分支是否只是少数家族或编码的优势？
2. **实例内一次选择**：相同开销下，短前缀的在线统计能否比只看 CNF 静态特征更准确地选择后续模式？
3. **反复切换的必要性**：重复观察和切换，是否优于一次选择、固定调度和相同切换预算的随机调度？
4. **解释与迁移**：哪些观察量在未见家族、后续年份和极性编码变化下仍然有预测价值？

在线统计能够预测“这个实例很难”，并不意味着它能够预测“此刻应换哪种相位”。最低要求是证明其对两动作的**相对收益**有增量信息，且这种信息转化为计入全部成本后的完整运行收益。不能事先假定动态策略必胜。

## 2. 先把比较对象定义清楚

`--forcephase` 不等于“启用负分支”：它强制使用 `--phase` 指定的初始相位，并同时绕开其他相位来源、阻止 rephasing。故不能把 default/forced-negative 的所有差异都归因为“是否保存相位”。原生默认含 target/best/saved 等机制，也不是教科书式的纯 phase-saving。

下列命令参数只展示与本研究相关的差异；共同参数、seed、时间/内存限制和证明设置必须写在 manifest 中。

| 编号 | 变体 | 明确设置 | 用途 |
| --- | --- | --- | --- |
| D | 原生默认 | `--phase=1 --forcephase=0` | 主要实际基线；保留该 pin 的其余默认 |
| I− | 仅初始化为负 | `--phase=0 --forcephase=0` | 区分“起点为负”与“持续强制为负” |
| F− | 强制负相位 | `--phase=0 --forcephase=1` | 主要候选动作 |
| F+ | 强制正相位 | `--phase=1 --forcephase=1` | 检查收益是否来自任意强制或特殊负极性 |
| D/no-R | 默认相位优先级、禁 rephase | `--phase=1 --forcephase=0 --rephase=0` | 机制消融 |
| I−/no-R | 负初始化、禁 rephase | `--phase=0 --forcephase=0 --rephase=0` | 与 F− 匹配 rephase 的主要机制消融 |
| S | 严格 saved-only | 最小源码诊断：决策相位只读 saved；未赋值时有固定、可审计的 fallback；禁 target/best 覆盖与 rephase | 仅作机制解释，不能冒称原生默认 |

先在小集合跑 D/I−/F−/F+，再在训练/验证子集完成 D/no-R、I−/no-R、S。若算力允许，最终候选也在 held-out 做这些消融。S优先用经审计和运行验证的最小CLI配置实现：显式初始方向、`--target=0 --rephase=0 --stubbornIOfocused=0`，同时验证普通自由decision确实使用saved及其fallback。若CLI不能满足定义，再做独立诊断patch；需给出实际配置/diff、更新saved的位置及决策计数。若暂未实现，报告“未实现”，不得用D冒充。

主实验动作集合保持二元：`A={D,F−}`。这是**原生语义的策略包选择**，包含 rephase 是否可运行的差异。另做 `A={I−/no-R,F−}` 的受控实验，才有资格讨论排除 rephase 后的持续强制效果。F+ 以及其他相位策略不是无限扩张动作空间的理由。

在线配置轨道C必须使用明确有效值对：D/NATIVE=`(forcephase=0,phase=1)`，F−/NEGATIVE=`(1,0)`；从输入前固定动作与prefix后改变动作是不同历史。若phase固定0而仅切forcephase，非强制组改名NATIVE_INIT_NEG。机制轨道P只在自由decision覆盖方向，保持原生rephase/likely_phase，其标签与C不能混用。细节见源码审计第8节。

## 3. 数据集、去重和冻结划分

### 3.1 来源与 manifest

优先使用公开的 SAT Competition Main Track CNF 和 GBD 元数据 [R1–R3]。推荐候选池为 2023–2025；2026 若数据可公开获得，可以作为额外时间外推集，不以“必须取得最新年份”阻塞项目。

每个实例记录：原 URL、下载日期、原始压缩文件 SHA-256、解压后 SHA-256、GBD identifier（如可得）、sanitized/original 关系、年份集合、家族、生成器/应用描述、变量/子句数、已知 SAT/UNSAT/UNKNOWN、split、选择理由。不得仅凭文件名判定重复或家族；元数据缺失时保留 `unknown`，并人工检查其来源，不能把所有 unknown 当作同一家族或每个文件当独立家族。

GBD 的 hash、isohash 和来源关系有助于去重，但 isohash 是候选等价类识别工具，不能当成一般 CNF 同构的完整证明 [R2]。另保留字节 hash 和保守来源分组。

### 3.2 两个互补的泛化问题

* **主要划分：家族外推。** 按 family/生成器/同一应用原型分组，约 60/20/20 分配 train/validation/test；小数据可用固定的 grouped cross-validation 做开发，再保留至少一个从未用于选择阈值的测试组。实例、同一实例的所有 seed、轨迹、检查点、改名版、sanitized 版、符号翻转及置换版必须在同一组。
* **额外划分：年份外推。** 例如以 2023–2024 开发、2025 测试；必须剔除和开发集重复的实例，并分别报告“见过家族的新实例”和“新家族”。仅按年份分割不保证 family-disjoint。两种泛化问题分别建 manifest、分别报告，不能混成一个更漂亮的数字。

选择子集时按家族、规模、已知 SAT/UNSAT 分层，记录固定抽样 seed。难度筛选只能用训练/开发阶段规定的先验规则或共同短 pilot；记录全部被筛掉实例，保留易例的成本评估。不能根据最终候选能否赢选择测试集。测试 SAT/UNSAT 标签只用于分层报告，不能作为策略输入。

### 3.3 编码敏感性

强制负相位依赖 CNF 变量极性的编码。选择少量 held-out 原实例，另生成全体符号反转、随机逐变量符号翻转、变量编号置换/子句顺序置换；分别隔离变换因素，固定变换 seed。所有变换可逆、保持可满足性，并验证模型映射。将变换视为同一原实例的重复测量，不能扩大独立样本量或跨 split。该测试用于界定编码敏感性，不要求策略对所有变换完全不变，也不能把编码本身的有效先验一概称作泄露。

## 4. 分阶段执行和停止条件

### M0–M1：正确性、观测与无操作测量

* 固定编译器、优化级别、依赖、上游/patch commit、CPU/内核、单线程/affinity、内存限制、runner 版本及完整命令。默认每进程一个物理核，避免 SMT 兄弟核竞争；限定并发，测量内存带宽和温度干扰。训练和测试不在不同型号机器上混算原始秒数。
* 对 D/I−/F−/F+ 和每个控制分支跑小型 SAT/UNSAT、随机小 CNF、可验证的生成例；SAT 验证完整模型，UNSAT 用独立 checker 验证证明。所有最终测试 solved 结果均须验证；checker 超时单列为“结果未验证”，不能当已验证 solved。
* 无补丁上游 vs 补丁默认关闭 vs telemetry-only vs no-op controller 四组比较。除了时间，还比较答案、决策/冲突数及动作轨迹；在固定 seed 和无时间触发控制时，telemetry/no-op 应保持搜索轨迹一致。
* 工程目标：在基线 >1 秒的代表性运行上，telemetry/no-op 的配对 median slowdown ≤1%，p95 ≤3%。这是优化/披露目标，超限不得删除慢样本；先找热点，再决定降低日志频率或特征数量。短例另报告绝对毫秒开销。
* 在日志中标明真实 decision count 中每种相位来源、F− 实际覆盖决策比例和 switch 次数，防止“选了动作但没生效”。日志默认只保留窗口聚合，避免每次赋值输出文本。

未通过正确性或动作生效检查，不扩大 benchmark。

### M2：静态互补性普查

在训练/验证集合跑 D/I−/F−/F+，给出配对 runtime scatter、cactus、PAR2、SAT/UNSAT、家族明细及 seed 变化。计算由 validation 选出的 single-best static（SBS）和两动作逐实例最优的 virtual best static（VBS）。VBS 使用未来信息，仅诊断静态互补空间，不能部署，也不是动态切换的理论上界。

若 SBS 与 VBS 的差距极小（默认参考 <2% PAR2），或者 F− 的优势完全不稳、只由少量异常样本造成，先做敏感性和机制分析；优先完成可解释的负结果，不自动升级到 RL。2% 是预算门槛而非显著性结论，不能删除原始结果来创造互补性。

### M3：一次在线选择

所有实例先用一个预先确定的共同 prefix（默认 D；另做 I− prefix 的敏感性），在既有 restart 安全点观察状态，然后选择 D 或 F−，之后不再更改。

开发时最多比较三个预注册 prefix 长度，例如 `10^3/10^4/10^5` 个累计冲突；若 solver 在到达阈值前 solved，直接计入 solved 和总成本，不能从结果中剔除。实际动作在达到阈值后的第一个既有 restart 应用，记录真正的冲突数、时间和偏移。若整段运行没有安全点，则不强行插入 restart，保留原模式并记录原因。对大量无冲突/极易实例另用固定最大探测时间做预算保护，此时间也计入总成本。

模型先试深度 ≤3 的树/少量阈值规则，再试正则化 logistic 或浅层树模型；复杂模型作为离线诊断，不先引入在线 Python、神经网络或高成本图特征。阈值、feature scaling、缺失值处理、model size 和 prefix 长度只用 train/validation 选择。

### M4：有条件的重复切换

仅在 M3 证实存在可迁移在线信息，或同状态继续实验明确显示搜索过程中动作偏好变化时开展。窗口默认按冲突数定义，到既有 restart 才应用；最多验证三个窗口尺度。设最短驻留（默认至少一个完整窗口）、最大切换次数、置信度阈值和 hysteresis，记录无切换/只切一次的退化行为。不得把无限频繁切换当作探索。

先部署可解释规则或离线训练的小策略。MAB 是第二阶段可选分支：比较不衰减 UCB、sliding/discounted UCB 或一个低复杂度 recency rule；不同时搜索许多 RL 架构。CP2025 DynamicSAT 已使用 UCB 和 LBD 反馈调配置，CP2026 工作已指出可变长度 restart 的 credit bias [R6–R7]，因此“使用 MAB”本身不是新贡献。

MAB 只观察被执行动作的结果；动作改变 learned clauses、活动度、saved phases 及后续状态，reward 非平稳且有延迟。标准独立同分布 bandit 的 regret 界不能直接迁移为本求解器的运行时间保证。只声称已实际测得的效果。

### M5：冻结和最终评估

冻结唯一主要候选、基线、参数、模型、特征、seed、数据 manifest 和代码 SHA 后，运行一次 held-out 主比较；可分析失败但不能继续用这批数据选策略。后续改法需新 holdout 或明确称为探索性结果。保留所有超时、崩溃、OOM、验证失败和完整失败原因。

## 5. 必须打败的基线，以及每个比较回答什么

| 基线 | 具体要求 | 排除的解释 |
| --- | --- | --- |
| D、I−、F−、F+ | 使用相同 runner 和共同参数 | 起始符号/固定符号/原生语义差异 |
| validation-SBS | 由 validation 决定，test 前冻结 | 挑错静态对手造成的表面改进 |
| static-feature selector | 只看解析时获得的廉价 CNF 特征 | 在线观察是否有额外价值 |
| 一次在线选择 | 与重复切换同特征、模型容量和开发预算 | 反复动作是否必要 |
| 时间/冲突计数 selector | 只用进度、mode、预算，不看内容统计 | 只是一个隐藏的时间表 |
| 固定 schedule | D→F−、F−→D 和固定交替，少量validation预选切换时点 | 手工时间表是否已经足够 |
| matched-budget random | 与候选相同的决策机会、驻留约束、最大切换数，并匹配期望/实际占用比例 | 随机扰动或切换次数带来的收益 |
| shuffled-label control | 仅在train打乱标签后重训，同预算并冻结后评估；test标签不能参与构造策略 | 拟合噪声/容量优势 |
| no-op/telemetry-only | 相同采样与决策代码开销，动作始终 D | 测量代码成本与轨迹干扰 |
| VBS-static | 按最终真实runtime挑 D/F−，标注 oracle | 互补性诊断；不得拿作可部署方法 |

matched random 若要精确匹配候选的实际 switch 次数和占用时长，会用到候选完整轨迹，故只能是**诊断性回放基线**，不是可在线实现的算法；可部署 random 使用 test 前冻结的 validation 分布。两种必须分开标记。报告 D 与 F− 的总驻留冲突数、CPU 时间、切换数分布，而不只报告“选了几次”。

在小预算下，最终 held-out 至少比较D、F−、validation-SBS、一次在线选择、固定schedule、random和唯一主要候选；相同配置去重，通常最多7组。SBS从D/I−/F−/F+中按validation预选，另报告D/F−的二动作SBS。机制/特征消融优先放在开发集，不能将一个小预算项目膨胀为全量笛卡尔积。

## 6. 在线观察量：先便宜，再有理由地扩展

每个观察量必须定义采样时点、分母、累计/窗口范围、EMA 时间尺度、缺失值与获取成本。只读取动作执行前已发生的信息，不读取后续 solved 状态、真实 SAT/UNSAT、文件名/年份/家族标签或其他 solver 的未来轨迹。

| 组 | 初始观察量 | 需要检验的假设 |
| --- | --- | --- |
| P：极性与不同意见 | 最近决策/propagation 的负值比例；saved 为负比例的固定大小抽样；saved 与 F− 的决策分歧率；saved 极性翻转率 | 两模式确实给出不同决策，负极性有状态依赖 |
| Q：冲突/学习质量 | 窗口 LBD mean/median 或廉价分桶、低 glue 子句比例、learned clause 长度；recent/long EMA 比率 | F− 的收益能否从学习形态预判 |
| T：搜索形态 | decisions/conflict、propagations/decision、trail 长度/活动变量数、最大trail增长、backjump 距离、chrono/nonchrono比例 | 停滞、深探与多样性的区别 |
| R：进程/原生机制 | 累计冲突、已用预算比例、focused/stable mode、最近 restart/rephase 的距离、rephase 来源 | 是否仅在替代原生模式/时间表 |
| C：廉价静态控制 | log变量/子句数、clause/variable比、二元/三元子句比例、正负literal比例、Horn比例 | 相对廉价静态选择的增量 |

P 组全变量扫描不能每个窗口运行；固定抽样或维护已有计数，并单独计量开销。需要大量新分支的每赋值计数先在小样本测 overhead。分母为零记 missing 并加 mask，不能产生 NaN/inf 或用未来数据填充。SATZilla 的 probing 特征说明短搜索行为可用于算法选择，但不证明上述任何一个观察量对此项目有用 [R4–R5]。

### 6.1 “有用”的判定方法

1. **增量比较**：C → C+R → C+R+P/Q/T；随后对唯一候选做 feature-group leave-one-out。所有版本相同 prefix、动作空间、模型容量上限和开发预算；统计开销也计入。
2. **预测与决策分开**：报告 held-out cost-weighted regret/两动作成本差估计和校准，而不只报告分类 accuracy/AUC。两个动作耗时近似相同时可预测错误但无实质损失；双超时不能武断标 winner。
3. **跨组稳健性**：按 family 和 SAT/UNSAT 报告效应方向、覆盖率、样本数、CI；同一规则若只在 seen-family 有效，结论必须收窄。
4. **解释可信度**：树规则/partial dependence/SHAP 等只作描述；不能用模型解释图直接宣称因果机制。用干预、受控 rephase 消融和同状态继续实验支持机制。
5. **防止存活偏差**：晚窗口只见到尚未 solved 的实例。画每时刻的 at-risk 数量，分别报告条件于存活的诊断与全体实例的完整部署分数；不能将晚期幸存者与全部早期例直接相比。

## 7. 同状态继续实验和状态带入

从头分别执行 D 与 F−，在相同冲突编号截取的两个状态已经不同；它们后续表现不能当作“同一时刻换动作”的反事实。

可负担的诊断方法是**确定性 prefix replay**：保存 prefix 的动作历史和触发计数，重新运行至同一安全点，核对状态摘要，然后分别用 D/F− 继续。摘要至少包含冲突/决策数、活动变量数、learned clause 数、trail 摘要、RNG 状态/调用计数（能安全获得时）；摘要一致只是复现检查，不能声称证明全部内存一致。无需实现公共 state serialization；若 Linux process-fork 可安全适用，可作为离线优化，先验证父子执行等价性。

* 从 D prefix、F− prefix 及少量随机/当前候选 prefix 分层取样，避免只在默认策略访问的状态上训练后却部署到完全不同状态。
* 一个 replay 分支必须重放完整前缀，且最终评价使用相同从进程启动起的总 `T`，包含 prefix、特征、决策及动作成本。不能让两个 continuation 各自额外获得完整 `T`。
* 完整 continuation 的结果是该状态“现在选某动作、以后保持该动作”的条件成本，不是任意后续动态策略的最优 Q 值。
* 两分支都在剩余预算内未 solved 时，终端标签仍被删失，不能因为更低 LBD 或更高 conflict rate 就定 winner。短 horizon 的 LBD、trail-growth 等结果只能是 proxy；单列其对最终成本差的相关性、反例和验证集合。
* policy 执行时保留 learned clauses、变量活动度、saved/target/best 历史和 RNG；不要为切换额外清空它们或加入新 restart。分别记录每次动作切换前后的原生状态。
* `forcephase` 开启期间 saved 的更新以及 rephase 计时器是否继续演进，以 pinned source 为准。重新关闭时可能恢复旧 target 或触发积压 rephase，必须测试并记录。若另做“切换即重置saved/target”的方案，它是不同动作，要独立命名、消融和计费。

短窗 reward 候选只限少量预注册形式（如 mean-LBD、低glue学习率、trail增长），先验证与最终 runtime 的关系；“冲突越多越好/越少越好”均无普遍保证。固定冲突窗内的 CPU 时间、固定时间窗内的冲突数也不能单独代表求解进展。可变长度 restart 的 reward 必须归一化/分层并做 duration-aware 对照 [R7]；任何归一化都须避免零分母和极端小样本。

## 8. 时间、超时、统计与展示

### 8.1 完整成本与异常

主要指标为端到端 CPU runtime（单核）及相同总 cutoff `T` 下的 mean PAR2：

\[
 c_i = \begin{cases}t_i,&\text{在 }T\text{ 内给出结果且经独立验证正确},\\2T,&\text{超时或未解决},\end{cases}\qquad
 \mathrm{PAR2}=\frac1N\sum_i c_i.
\]

解析、pre/inprocessing、公共 prefix、feature 提取、model inference、switch、运行时日志全部在 solver 预算内。下载和离线训练不算部署 runtime，但报告 core-hours/峰值内存/日志大小；checker 成本单列，所有 solver 用相同验证政策。runner 启动等不可忽略成本另报端到端 wall time。证明生成配置应统一，不得 baseline 开证明、候选关证明。

正式主比较默认**所有配置统一开启proof**：proof生成计入solver时间与cutoff，SAT检查原始CNF模型，UNSAT检查每个proof，checker成本另列。若资源明确不足，可在接触test前冻结替代方案：主计时全部关闭proof，对每个最终UNSAT用同二进制、同CNF/seed/动作协议独立开启proof复跑并校验，记录复跑成本、答案及确定性计数/摘要一致性；此类结果标注“独立认证复跑”，不能声称直接认证了无proof运行轨迹。两模式不一致或证明未通过的结果保持未验证并调查；正式主表不能把未验证结果当verified solved。无论采用哪一种政策，不能只校验有利配置或一个小子集。

Timeout 是右删失：真实 runtime 只知 `≥T`，`2T` 是评分罚值，不是观测到的运行时间。做 runtime prediction 时用删失感知方法或明确只拟合 solved 子集并披露偏差；不能把超时当精确 `T`/`2T` 回归标签。崩溃、OOM、错误答案、证明失败分别计数；错误答案一票否决候选的正确性验收，不能用 PAR2 掩盖。

### 8.2 主要与辅助报告

* 主表：相同测试集的 PAR2、#solved、SAT/UNSAT/UNKNOWN 分项、相对 validation-SBS 的差值及 CI。
* 辅表：相对 D、各静态模式和调度基线；新 solved/丢失 solved 的交集；win/tie/loss；timeout/OOM/error；特征/决策开销、切换次数和驻留比例。
* 图：完整测试集 cactus、配对 runtime scatter（超时边界明确）、按family效果森林图、动作/观察量随冲突与CPU时间的轨迹；同时给样本数。
* common-solved 的几何平均 speedup 可作辅助，不能替代完整集 PAR2。不得只报告被两者都解出的简单子集或最好的 seed。
* 可报告 `(SBS−policy)/(SBS−VBS-static)`，但分母接近零时不报告比例；动态 policy 可能超过 VBS-static 或劣于 SBS，这不是计算错误，也不能据此称 VBS-static 是动态 oracle 上界。

### 8.3 Seed、复跑和置信区间

开发至少 1 个固定 seed；晋级候选至少 3 个配对 seed，小集合做 5 个更稳健。若多个 seed 的轨迹完全相同，明确说明这些并非独立随机证据，补做 CPU 时间复跑或有理由的 scrambling。不同配置用相同实例/seed配对，但不能声称配对 seed 消除了随机性。

每个实例先按 seed 平均成本，再按测试集实例计算主分数。bootstrap 以 family/生成器组为最高抽样单位，保留组内全部实例、seed 与变换版本；可做两层 family→instance 重采样。报告 95% paired grouped-bootstrap CI、bootstrap seed 和重采样次数（默认 10,000），同时给 instance-bootstrap 的敏感性。family 很少时 CI 不稳定，明确限制，辅以 leave-one-family-out，不能把成千窗口当成成千独立样本。

测试主假设只对冻结的唯一候选检验。许多规则/特征的探索在 train/validation 完成；若发布多个最终假设，标 exploratory 或对多重比较作校正。效果量和最坏家族回归比单个 p 值更重要。

## 9. 算力预算：先选档，再跑；不得自动购买

CPU 核时上界使用：

\[
 H_{\max}=\frac{N\cdot K\cdot S\cdot T}{3600},\qquad
 W_{\mathrm{ideal}}=H_{\max}/P.
\]

`N` 是实例数、`K` 是配置/策略数、`S` 是 seed 数、`T` 是每次完整运行秒数、`P` 是可用物理核数。实际 wall time还受内存、checker、下载、任务排队和失败复跑影响。预算按**所有尝试**累计；不能把只展示的获胜配置当成总成本。manifest 跑前输出 worst-case 核时并设置总任务数/核时上限，达到上限暂停新增运行并写 checkpoint。

| 档位 | 具体可执行规模 | 最坏CPU核时（不含checker） | 可支持的结论 |
| --- | --- | --- | --- |
| smoke | 20例×4静态配置×1seed×10s | 0.23 h | 构建、参数、正确性与runner；不支持性能结论 |
| pilot | 60例×6配置×1seed×60s | 6 h | 方向、测量开销、互补性初筛 |
| course/minimum | 开发120例×8配置×1seed×300s；冻结测试80例×最多7配置×3seed×300s | 80+140=220 h | 有限制但完整的研究；300s cutoff结论不能推广为5000s |
| expanded | 开发240例×10配置×3seed×600s；测试160例×7配置×3seed×1000s | 1,200+933.3≈2,133 h | 更多家族与更长预算，候选/消融须筛选后晋级 |
| competition-scale（可选） | 只对冻结测试400例×6配置×3seed×5000s | 10,000 h | 接近竞赛cutoff；不作为完成项目的必要条件 |

以上 `K` 是总配置预算，已包含静态/选择/调度/候选，不能对每种模型再套一次整个矩阵。最低档若资源少于220核时，应缩小开发搜索并保留held-out，而不是取消测试或重复seed。允许以完成的较小档交付诚实的结果。

同状态 replay 额外预算：`N_state × 2 actions × S × T /3600` 核时，因为每个分支重放完整prefix；例如40状态×2×1×300s=6.67h。默认只在开发集分层抽40个状态；需要多个时间点时先减少实例/控制总状态数。早停/分级只在开发集用于筛选，最终测试统一cutoff，不能按候选表现给更多时间。不同cutoff不得直接混算一张主表。

若运行环境无可用编译器、数据下载或足够时数，先完成可运行pipeline、小例验证和未执行矩阵清单；注明阻塞与恢复命令，不伪造性能结果，也不自行购买算力。

## 10. 验收：性能正结果和研究完成是两回事

**工程完成必须满足：** 固定版本与干净build；动作语义经过小例验证；SAT/UNSAT正确性检查；可恢复runner与schema；冻结划分；全部raw results、proof/checker状态、分析脚本和一条命令重建表图；记录实际预算；未执行项写清楚。

**预设实际收益目标：** 在冻结 held-out 上，相对 validation 选出的 best static，主要候选的 mean PAR2 降低至少5%，paired family-grouped bootstrap 的95% CI排除0，且 solved 数没有实质下降。默认“无实质下降”按配对seed平均 solved 不低于SBS解释，同时列出每seed变动和新增/丢失 solved；不能用一个大幅加速的家族掩盖广泛丢失solved。目标不满足时如实称作“未达到预设性能目标”；不得事后换指标或调test凑数。

**“在线观察有用”另需满足：** 相同资源下优于 C/C+R控制及随机/固定schedule；至少一个特征组的增量在held-out或预注册grouped-validation中稳定；给出可读规则、反例和适用范围。若一次选择已经最好，应选它，不要求重复切换以显得更复杂。

**负结果也可完整完成项目：** 复现并量化 D/F− 的互补性或缺乏互补性；解释初始化/rephase/编码因素；说明尝试过的prefix、观察量、简单模型和有限动态策略及预算；给出不确定性、失败例、可复现实验与下一步。区分“没有足够证据”“给定预算内无稳定收益”和“证明不可能”；本项目通常只能支持前两种。

## 11. 主要参考来源

以下仅概括与协议直接相关的事实；方法与数值预算是本项目的设计选择，不冒充文献结论。

* **[R1] SAT Competition 2026, Tracks**：官方主要顺序赛采用5000s、32GB、PAR2及SAT/UNSAT证书；本项目可采用较小cutoff，但需明确限制。<https://satcompetition.github.io/2026/tracks.html>
* **[R2] Iser and Jabs, Global Benchmark Database, SAT 2024**：公开元数据、标识、来源映射和isohash工具；isohash以候选等价类帮助去重。<https://doi.org/10.4230/LIPIcs.SAT.2024.18>；全文 <https://arxiv.org/pdf/2405.10045>
* **[R3] SAT Competition 2026, Benchmarks**：公开格式、清理过程、家族描述与选择脚本；清理会移除重言式子句和重复literal。<https://satcompetition.github.io/2026/benchmarks.html>
* **[R4] Xu, Hutter, Hoos and Leyton-Brown, SATzilla, JAIR 2008；SATzilla2012 description**：基于实例特征的算法组合/代价敏感选择，是一次选择和成本计入的近邻。<https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/>；<https://www.cs.ubc.ca/~kevinlb/papers/2012-SATzilla2012-Solver-Description.pdf>
* **[R5] Shavit and Hoos, Revisiting SATZilla Features in 2024, SAT 2024**：更新预处理器、探测solver与特征提取预算，研究预测和选择任务。<https://doi.org/10.4230/LIPIcs.SAT.2024.27>；早期特征定义含unit-propagation与search-depth探测：<https://www.cs.ubc.ca/labs/beta/Projects/SATzilla/Report_SAT_features.pdf>
* **[R6] Shi et al., DynamicSAT: Dynamic Configuration Tuning for SAT Solving, CP 2025**：在Kissat上使用公式变化触发、UCB与recent-LBD reward；包括rephase选项的在线调整，并非直接研究CaDiCaL forcephase。<https://doi.org/10.4230/LIPIcs.CP.2025.34>；代码 <https://github.com/cure-lab/DynamicSAT>
* **[R7] Liang, Cherif and Li, Not All Restarts Are Equal: MAB-Learning at the Right Time Scale for SAT, CP 2026**：讨论不同restart长度造成的reward和计次偏差，提出duration-aware反馈与选择；不能把每个restart简单视为等长独立样本。官方发布2026-07-13。<https://doi.org/10.4230/LIPIcs.CP.2026.39>；代码 <https://github.com/JinghuLiang/Duration_Aware_kissat_MAB>
* **[R8] Shaw and Meel, Designing New Phase Selection Heuristics, SAT 2020**：在特定Maple/chronological-backtracking场景对phase-saving、always-false、random等做消融，提醒不能把局部经验推广为所有CDCL普遍事实。<https://arxiv.org/abs/2005.04850>
