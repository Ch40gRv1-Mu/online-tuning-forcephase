# TA100 动态候选：来源、定义与可采集边界

状态：首10项已正式评分，后20项已冻结真实observer并进入一次共享192题的短前缀采集。最终可执行定义在 `configs/ta100/dynamic_registry_v2.json`；下文的设计期建议保留为来源历史，不能替代其版本化公式。本阶段仅使用既有180 fit、60 feedback；已消费的gate与最终测试均禁止读取。原六个动态聚合量、H04平均速度、H05多相位响应、H06条件传播均不计作本阶段新假设。

## 文献事实与我们的假设分开

- [Audemard与Simon，IJCAI 2009](https://www.ijcai.org/Proceedings/09/Papers/074.pdf)提出按学习子句涉及的决策层评价子句质量。它支持研究“冲突切割的层结构”，没有证明某个Glue统计能预测TA两相位优劣。TD18的层占用熵、TD29的层数与宽度联合分布，是我们的新假设。
- [Pipatsrisawat与Darwiche，SAT 2007](https://www.cs.toronto.edu/~fbacchus/csc2512/Readings/Pipatsrisawat-Darwiche2007_Chapter_ALightweightComponentCachingSc.pdf)讨论回溯抹去无关赋值造成的重复工作，并提出轻量缓存思想。这启发保留状态与相位记忆的观测；不把论文中的求解器收益移植到本数据。
- [Shaw与Meel，SAT 2020](https://www.cs.toronto.edu/~meel/Papers/sat20-sm.pdf)检验chronological backtracking与phase saving的相互作用，并研究DPS/LSIDS。它说明相位策略需要结合回退机制理解；TD13/26/27观测的是单个原生D前缀中的状态寿命或符号转移，尚无本数据上的有效性证据。[作者出版页](https://www.cs.utoronto.ca/~meel/publications/b2hd-SM20.html)提供论文及代码入口。
- [Fleury与Biere，SAT 2021](https://fmv.jku.at/papers/FleuryBiere-SAT2021.pdf)研究all-UIP shrinking与minimization的整合。TD14证明压缩、TD16理由重汇合和TD30引理依赖深度借鉴其中的证明/理由结构，公式与预测用途由我们提出。

上游[CaDiCaL analyze.cpp](https://github.com/arminbiere/cadical/blob/master/src/analyze.cpp)、[propagate.cpp](https://github.com/arminbiere/cadical/blob/master/src/propagate.cpp)、[decide.cpp](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)、[restart.cpp](https://github.com/arminbiere/cadical/blob/master/src/restart.cpp)、[averages.hpp](https://github.com/arminbiere/cadical/blob/master/src/averages.hpp)是机制及挂钩位置的第一手来源。`decide`区分saved/target等相位来源；`restart`的trail reuse会保留预计再次选择的决策前缀；`averages`区分潜在nonchronological jump level、实际backtrack level、trail和学习长度EMA。

这些链接的master会变化，不能代替执行身份。现有192份记录的定义以本地`fpcontrol.cpp`及observer source SHA `d92d0ef0638397fb6eddaad64a5b2d8619e8cf5d805d9f56dd469005bef16015`为准；新observer必须绑定其固定基底、变换、二进制、flags、seed、CPU限制及输入SHA。上游master与该可执行文件不自动等同。

## 首10项：无需新求解，只复用既有动作前记录

|ID|新机制|现有字段|
|---|---|---|
|TD01|回退方式混合|`c_chrono_frac`|
|TD02|自然重启是否保留前缀|`c_reuse_frac`，不是重启频率|
|TD03|决策相位来源的三桶熵|`c_target_src_frac`、`c_saved_src_frac`、剩余来源合并桶|
|TD04|target记忆定义域覆盖|`x_target_set_frac`|
|TD05|best/target进度记忆分离|`x_best_frac`、`x_target_frac`的归一化差|
|TD06|赋值前沿的快慢动量|`x_trail_ratio-1`，不是Glue快慢比|
|TD07|动态学习数据库积累|`x_red_per_irr`，不是输入clause/variable密度|
|TD08|saved/target边际极性差|`x_target_neg_frac-x_saved_neg_frac`；分母域不同，不称joint agreement|
|TD09|学习宽度局部/累计分离|`ln(x_size_avg/c_size_mean)`；mode切换会影响EMA解释|
|TD10|实际与潜在回退几何分离|`x_level_avg`与`x_jump_avg`的归一化差|

只取首次自然重启跨过1000冲突的checkpoint，要求NATIVE、`r_switches=0`、至少20学习事件、进程CPU≤2秒。现有首条的`c_`与`w_`统计相同；`saved_flip`没有上一条可比状态，不能伪造时间趋势。TD06/09使用求解器内部已维护的EMA，明确不把之后checkpoint或终局统计拿回动作前。

所有非有限值、缺字段、零分母及不足事件均为missing；比例不因接近零而随意加epsilon。三桶来源熵只容忍JSON六有效位引起的微小舍入误差，再按总和归一化；显著负桶则缺失。提取器保守复用原COMPLETE记录；不借新字段救回原MISSING任务。全240父题与原成本保留，缺特征按固定对照回退。既有探针物理CPU只作复用成本记录，不能再次计为新消耗；新增本地提取CPU单独记录。

## 其余20项：最小instrumentation建议

|记录位置|最小字段/固定摘要|支持候选|成本边界|
|---|---|---|---|
|学习子句落地前|全正/全负计数、saved下违反标志、size×Glue固定81格|TD11/19/29|复用一次学习文字扫描；常数计数器|
|已有分析reason遍历|reason数、UIP位置、level频数、引理依赖深度|TD14/17/18/30|不增加第二次完整图遍历；每live clause深度字段需计内存|
|固定256变量赋值/撤销/再决策|birth冲突、sign、chrono匹配标志|TD13/27|固定样本与固定seed；删失寿命不补零|
|自然重启前后|同一256变量的assigned/sign配对|TD26|每重启O(256)，不能改变决策或phase数组|
|固定抽样理由DAG|唯一决策祖先、最长路径、已访问祖先边|TD12/15/16|最多10000访问；预算不足即missing|
|学习/冲突窗口|2×128学习子句8-minhash、2×256分析变量bottom-k|TD20/23|固定内存、固定窗口、固定seed；ID只用于内部匹配，不输入模型|
|bump/学习时|256样本bump计数、固定时点activity秩摘要|TD21/22|秩排序可能较贵，必须测量，不能冒称零开销|
|watch循环|examined、satisfied-blocker-skip两个计数|TD25|热路径开销必须实测；不能改watch顺序|
|分析冲突边界|decision gap的Welford计数/均值/M2|TD28|至少32间隔；研究burstiness，均值速率不算新特征|
|学习子句生命周期|抽样256子句birth及first-reason-use|TD24|未使用者右删失；固定sample admission，不按效果挑子句|

新采集仍是一条有界原生D前缀，不增加F+/F−求解矩阵。源码、协议与完整192清单均已在采集前提交。TD19的设计期saved违反量会理论退化，已在任何新数据前改为target phase联合违反与边际独立差；TD24首次assertion复用的零龄问题同样前瞻改为post-assertion later reuse age。旧定义均保留为拒绝记录，不额外计轮。TD30只是CDCL理由依赖深度，不称LRAT证明高度。

每10项完成时，结合实际可用覆盖、吞吐、缺失与增量结果优化下一块工作流；不能因读过反馈改写已完成项定义，也不重新打开gate。
