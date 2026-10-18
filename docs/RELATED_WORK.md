# Phase selection 与 online forcephase：相关工作与证据边界

调查日期：2026-10-18。本文为研究设计依据，不是本仓库已完成实验的结论。论文论断、作者解释和本项目假说分开陈述；具体 CaDiCaL 行为以锁定版本的源码审计为准，见 [SOURCE_AUDIT.md](SOURCE_AUDIT.md)。

## 1. 项目起点需要修正的表述

- “所有 CDCL solver 都用 phase saving”过强。较准确的说法是：**phase saving 是现代 CDCL 的常见组成部分，但实际 decision polarity 还可能由 target、rephasing、API 指定 phase 等机制影响。**[R1, R2, R3]
- Phase saving 通常保存变量最近一次赋值，可能来自 decision 或 propagation；不宜统一定义成“最近一次 unit propagation 的值”。不同实现会在赋值或回退时保存，须核实。[R1, R2, R3]
- **固定负分支、初始化为 false、周期性重置为 false 是三种不同 intervention。**固定负分支在每次 decision 时优先选 false；初始化只影响尚无历史的情况；rephasing 改写 phase 后仍允许后续保存。不能把它们混为一个 baseline。[R1, R2]
- `--forcephase` 的含义是强制初始 phase，并不天然等于负分支。实验中必须显式给出 `--phase=0` 或 `--phase=1`，同时记录其他覆盖关系和副作用；不能只在命令标签中写“forcephase”。[S1]

建议研究问题：**在固定的 CaDiCaL 版本中，哪些可在线获取的信号，能预测继续使用原生方向策略或暂时强制负分支的收益？这种预测能否在计入观测、探索和切换成本后，形成跨实例族有效的策略？**

## 2. 已核实的一手文献

### R1. Phase saving 的原始动机

**Knot Pipatsrisawat, Adnan Darwiche. _A Lightweight Component Caching Scheme for Satisfiability Solvers_. SAT 2007, pp. 294–299.**

[DOI](https://doi.org/10.1007/978-3-540-72788-0_28) · [论文 PDF](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)

论文将保存被回退撤销的赋值称为 progress saving。动机是远距离回退可能丢掉无关组件的已有解，造成重复工作。保存这些值后，变量再次成为 decision 时优先复用。论文报告工业实例上的总体改善，也存在变慢实例；它没有证明任何输入上都优于固定负分支。

**对本项目：**强制负分支可能损失“恢复已有进展”的能力。应观察回退规模、重复决策、重启后赋值重合等候选信号，但这些信号是否能预测最终收益仍待实验。

### R2. Target phasing、best phasing 与 rephasing

**Armin Biere, Mathias Fleury. _Chasing Target Phases_. POS 2020.**

[作者论文 PDF](https://fmv.jku.at/papers/BiereFleury-POS20.pdf) · [源码和实验日志](https://fmv.jku.at/chasing-target-phases/)

该工作区分 saved、best、target assignments：best/target 缓存较长的无冲突部分赋值；target 优先引导后续 decision，缺失时回退到 saved。Rephasing 则按计划改写 saved，采用 original、inverted、flipped、random、local-search、best 等方式。作者在 CaDiCaL、Kissat 等实现上比较组合，尤其关注 SAT 性能。结果与 restart、focused/stable 模式及其他启发式耦合；论文中的默认值属于当年版本。

**对本项目：**原生 CaDiCaL baseline 不能简单命名为“纯 phase saving”。候选信号需包括模式、target 覆盖率、最近 rephase 类型/间隔及有效决策来源。应区分强制负分支的直接作用和它绕开其他策略的作用。

### R3. Chronological backtracking 改变 phase heuristic 的作用

**Arijit Shaw, Kuldeep S. Meel. _Designing New Phase Selection Heuristics_. SAT 2020, pp. 72–88.**

[arXiv](https://arxiv.org/abs/2005.04850) · [作者论文 PDF](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf) · [作者源码](https://github.com/meelgroup/duriansat)

作者在 Maple_LCM_Dist_ChronoBTv3 中，只改变 chronological-backtracking state 的 phase policy。该设置下 random、always false 与 phase saving 的聚合表现接近；将 random 用于全部状态则明显较差。DPS 累计近期极性趋势，未带来显著总体改善；后续 LSIDS 使用 literal activity 得到改善。该证据不能推出“phase saving 普遍无用”，也不能直接迁移成 CaDiCaL 的结论。

**对本项目：**记录 chronological/non-chronological backtracking 状态；把状态与 policy 的交互作为消融。DPS/极性稳定性可以作为候选解释，但不能因机制直觉就视为已验证预测器。

### R4. 负分支可能利用编码偏置，但并非处处有效

**Emre Yolcu, Scott Aaronson, Marijn J. H. Heule. _An Automated Approach to the Collatz Conjecture_. CADE 2021；扩展版 Journal of Automated Reasoning 67, article 15, 2023.**

[arXiv 全文](https://arxiv.org/pdf/2105.14697) · [期刊 DOI](https://doi.org/10.1007/s10817-022-09658-8) · [作者实验仓库](https://github.com/emreyolcu/rewriting-collatz)

扩展版 “SAT Solving Considerations” 和 Table 2 比较了负分支与 phase saving。其 order encoding 中较小整数需要更多 false，矩阵解释又倾向稀疏、小系数；作者将此作为负分支可能有效的解释，并提出跨 restart 多样性解释。实验中负分支有显著获益，也有明显损害；作者明确限制泛化。表中采用 25 次重复、120 秒 cutoff。

**对本项目：**这是研究动机和实例族来源，不是“负分支经常更优”的全域证据。应把模型/编码偏置与探索多样性作为两条待验证机制，使用符号翻转对照区分它们。

### R5. Phase heuristic 的组合、动态权重已有先例

**Jingchao Chen. _Phase Selection Heuristics for Satisfiability Solvers_. 2011.**

[arXiv 与 PDF](https://arxiv.org/abs/1106.1372)

该论文将 ACE、Jeroslow–Wang、RSAT 等 phase heuristic 组合到 MPhaseSAT，并用实例条件和搜索阶段控制策略。它说明“根据条件选择 phase heuristic”并非新问题；其基线、实现和数据年代较早，不能用报告结果替代现代 CaDiCaL 对照。

**Jingchao Chen. _A Dynamic Phase Selection Strategy for Satisfiability Solvers_. 2012.**

[arXiv](https://arxiv.org/abs/1208.1613)

已核实摘要：它利用搜索过程中动态计算的 implied literals 权重构造 phase strategy，并在 Glucose 2.0、Lingeling 上报告实验。本次未对实现作独立复现。其动态 literal scoring 与本项目二选一的 forcephase 控制不完全相同，但排除了泛称“首个在线 phase selection”的新颖性表述。

### R6. 在线 bandit 选择 rephasing 已有直接近邻

**Xinyan Chen, Wenxuan Guo, Wanqian Luo, Hui-Ling Zhen, Xijun Li, Mingxuan Yuan, Junchi Yan. _Kissat-MAB-rephasing and Kissat_relaxed_. SAT Competition 2022 proceedings, pp. 35–36.**

[官方竞赛 proceedings](https://satcompetition.github.io/2022/downloads/sc2022-proceedings-DRAFT.pdf) · [论文全文镜像](https://home.mis.u-picardie.fr/~cli/sc2022_proceedings.pdf)

该 solver description 用 UCB 在 best phases、inverted、original、local search 之间在线选择 rephasing，反馈依赖决策及被决策变量的统计。它属于竞赛系统说明，不能等同于对所有模块做充分消融的独立论文。动作是 rephasing，并非每次 decision 的固定负分支控制。

**对本项目：**若推进M4并主张持续自适应优于已有在线方法，应加入无上下文bandit或合理简化复现作为方法基线；M0–M3不以先实现复杂bandit为前提。不能宣称“首次用bandit在线选phase”。反馈是否预测最终runtime，应在本项目中单独验证。

### R7. DynamicSAT：在线配置调整的近邻

**Zhengyuan Shi, Wentao Jiang, Xindi Zhang, Jin Luo, Yun Liang, Zhufei Chu, Qiang Xu. _DynamicSAT: Dynamic Configuration Tuning for SAT Solving_. CP 2025, 34:1–34:23.**

[正式论文](https://doi.org/10.4230/LIPIcs.CP.2025.34) · [全文 PDF](https://drops.dagstuhl.de/storage/00lipics/lipics-vol340-cp2025/LIPIcs.CP.2025.34/LIPIcs.CP.2025.34.pdf) · [作者代码](https://github.com/cure-lab/DynamicSAT)

已核实正文方法与附录参数表：DynamicSAT 基于 Kissat 4.0.0，以公式变化触发在线配置调整，使用 UCB 和 `U − 最近平均 LBD` 反馈，并在 SAT Competition 2024 数据上评估。其 rephase 参数组含 `rephase`、`rephaseinit`、`rephaseint`。这是配置控制的重要近邻，但不等同于每次 decision 强制负分支。具体参数和实现的详细对照见实验协议；其 LBD 反馈在本动作空间的有效性仍需验证。

### R8. 不等长 restart 的信用分配已有专门研究

**Jinghu Liang, Sami Cherif, Chu-Min Li. _Not All Restarts Are Equal: MAB-Learning at the Right Time Scale for SAT_. CP 2026, 39:1–39:18.**

[正式论文](https://doi.org/10.4230/LIPIcs.CP.2026.39) · [全文 PDF](https://drops.dagstuhl.de/storage/00lipics/lipics-vol379-cp2026/LIPIcs.CP.2026.39/LIPIcs.CP.2026.39.pdf) · [作者代码](https://github.com/JinghuLiang/Duration_Aware_kissat_MAB)

已核实正文第 4、5 节：作者在 Kissat 4.0.2 的 stable mode 中选择 VSIDS/CHB，指出不等长 Luby restart 导致反馈及 pull-count 偏置，并设计按持续时间归一化/加权的反馈与选择机制。这研究的是变量选择而非 polarity。本项目若在 restart 边界更新控制器，必须明确采样间隔和成本单位；不应将“按持续时间归一化反馈”单独当作新贡献。

### R9. 图着色中的直接负分支证据

**Marijn J. H. Heule, Anthony Karahalios, Willem-Jan van Hoeve. _From Cliques to Colorings and Back Again_. CP 2022, 26:1–26:10.**

[正式论文](https://doi.org/10.4230/LIPIcs.CP.2022.26) · [作者 PDF](https://www.andrew.cmu.edu/user/vanhoeve/papers/cliques_coloring_CP2022.pdf)

第4节明确说明在其图着色实例上，negative branching优于phase saving，并使用CaDiCaL的 `--forcephase=1 --phase=0`。这是与本项目动作直接对应的应用证据，但其编码与实例分布有限。可作为目标家族，不能把该论文的观察直接外推为整个SAT Competition上的一般结论。

### R10. 静态/探测特征与算法选择

**Hadar Shavit, Holger H. Hoos. _Revisiting SATZilla Features in 2024_. SAT 2024, 27:1–27:20.**

[正式论文](https://doi.org/10.4230/LIPIcs.SAT.2024.27) · [作者特征工具](https://github.com/hadarshavit/satzilla)

该工作更新SATzilla特征提取与评估，涉及运行时间预测、可满足性预测与算法选择。它支持把已有公式/探测特征用作强对照；不证明某个特征能预测forcephase收益。本项目不必从零重建全量昂贵图特征，先比较静态cheap features与内部在线计数；若调用探测工具，探测成本必须进入部署总预算，工具解出的实例也必须计入结果。

### R11. 学习phase不等于在线二选一控制

**Wenxi Wang, Yang Hu, Mohit Tiwari, Sarfraz Khurshid, Ken McMillan, Risto Miikkulainen. _NeuroBack: Improving CDCL SAT Solving Using Graph Neural Networks_. ICLR 2024.**

[正式论文与摘要](https://proceedings.iclr.cc/paper_files/paper/2024/hash/2f27964513a28d034530bfdd117ea31d-Abstract-Conference.html)

其方法离线学习有利于找model的变量phase，并在求解前查询一次神经模型，强调减少在线推断成本。这里只核实官方摘要，不推断具体训练标签实现。它说明phase学习已有独立研究路线，但逐变量预测与本项目选择NATIVE/NEGATIVE并非同一动作空间；作为扩展背景，不要求第一阶段重做GNN系统。

### S1. 运行语义必须来自锁定源码

[CaDiCaL 官方源码](https://github.com/arminbiere/cadical) · [decision phase 代码](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/decide.cpp) · [rephase 代码](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/rephase.cpp) · [选项定义](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/options.hpp)

复现必须记录commit SHA；以上源码链接已固定到本项目审查版本。`--forcephase`、`phase(lit)` API、target、rephase及模式间的优先级和可运行时修改性由源码审计确认。

## 3. 新颖性应放在哪里

| 不宜声称的贡献 | 可以研究、但仍需证据的贡献 |
| --- | --- |
| 首次研究 phase selection 或 phase saving 的局限 | 现代锁定版本下，固定负分支与原生 phase stack 的系统化差异及其适用条件 |
| 首次在线切换 phase / 首次用 MAB 选 phase | 面向 forcephase 的低成本在线信号，能否超越固定策略、定时切换和无上下文 bandit |
| 负分支通常更有效 | 哪些实例族、搜索状态、编码方向与时间阶段存在可复现收益或损害 |
| 相关特征说明了因果机制 | 预注册干预、状态匹配与符号翻转实验，能否排除编码偏置、模式耦合和观测开销 |
| 单一 LBD、conflict rate 或 trail 指标代表求解进展 | 哪些代理反馈在训练外实例族中，确实预测最终 runtime / solved count |
| 测试集上的 oracle 策略就是可部署策略 | 用只依赖过去观测的控制器，在完整成本计入后弥补多少 oracle gap |

“更有效”首先指同一时间与硬件预算下的最终求解表现，不是更高 conflict/s、更多传播或更低平均 LBD。后者是候选观测或辅助解释。

## 4. 必须保留的推理与反证设计

### 4.1 符号方向不是问题的语义不变量

以下为数学推理，而非引用某论文的实测结论。设对每个变量选择符号 `s_i ∈ {−1,+1}`，同时替换其全部出现位置；反向映射赋值即可保留 SAT/UNSAT。若所有变量都翻转，“全部 decision 优先 false”在原变量含义下变为优先 true。因此固定负分支的收益可能依赖编码方向，不能仅归因于原问题语义。

至少做全局翻转和若干随机变量符号翻转；同时保留变量重命名、clause/literal order 对照。它们是不同扰动，不应混名。原实例及所有派生版本必须位于同一数据划分，防止泄漏。该推理不保证现代 solver 在变换后逐步轨迹一致，因为预处理与 tie-breaking 也可能改变。

### 4.2 保持收益的解释与观察成本分开

“负分支绕开了坏的 saved phase”“更接近稀疏模型”“提供更强 restart 多样性”“在某种 backtracking state 更合适”都是合理候选假说，不是当前结论。对应实验应分别控制符号方向、切换时刻、restart/mode、saved/target 状态保留方式，再报告最终 runtime 与变换后的效果。

观测可能改变执行时间；切换会改变后续学到的 clauses；所有动作共享搜索历史。因此不能用静态独立 arm 的直觉直接主张标准 bandit regret 保证，也不能把不同历史中的短窗代理值当作同状态反事实。

### 4.3 允许以明确的否定结果完成项目

若在严格划分、完整开销与多次重复后，在线信号不能稳定预测收益，或复杂控制器不优于简单调度，应明确报告：已测动作、数据分布、预算、置信区间、失败机制和适用范围。可复现实证和有边界的机制结论本身是交付物；不得为了得到正结果选择性删掉不利实例族。

## 5. 执行 agent 的补查要求

1. 开始大规模实验前，完成 R7、R8 全文与代码的逐项比对，覆盖动作、观测、反馈、评估；本次已读关键方法和参数/实验设置，尚未独立复现其代码，继续更新本文件的阅读范围。
2. 本调查是一轮针对性检索，不是系统综述；论文写作前沿上述文献的引用链补查近期 phase/rephasing、online algorithm configuration 工作。
3. 若发现更接近的“CaDiCaL forcephase 动态控制”工作，先缩小创新性主张，再实施有区分力的实验；不要把未检索到当作不存在。
4. 引用文献中的结果时保留 solver、年份、实例分布、CB/NCB 状态等条件；自行复现实验与原文报告必须分别标注。
