# TA100 observer v1：提交前实现方案

Owner为root；parallel_learning独占新增observer补丁、计数字段与合成性质测试。现有求解器、源树、其它owner进程及192份旧receipt不覆盖、不重标。新命名空间`ta100-observer-v1`，旧记录没有这些字段，不能冒称兼容。

一次共享原生D前缀采集TD11–30，仍为seed0、2CPU秒包含解析、10秒wall、1.5GiB，首次自然restart跨1000conflicts且至少20学习事件。只记动作前字段，不新增restart或改变相位、学习、watch顺序、随机数与任何启发式。源码/协议提交前不编译或跑probe。

|候选|实际挂钩及最小状态|可行性与边界|
|---|---|---|
|TD11/19/29|最终学习子句、变量saved相位；3个符号桶、违反计数、81格size×Glue|可复用已有学习文字遍历；非空且saved完整才计违反率|
|TD14/17/18|分析reason计数、UIP trail位置、最终学习子句level频数|主分析路径计数；不把预处理冲突当普通冲突|
|TD13/27|固定256变量样本的赋值birth、撤销sign、chrono匹配标记|完整寿命/同变量再决策才能计；compaction导致映射失效时标缺失或重建epoch，不混合ID|
|TD20/23|两个窗口的变量bottom-k256；两个128学习子句窗口、8个minhash|固定seed与容量；明确为估计集合相似度；空窗口不写0|
|TD21|同一256样本的bump计数、sum与sumsq|样本条件HHI，不冒称全变量精确HHI|
|TD22|动作前当前branching priority的秩、最近256学习子句变量|需核实stable score和focused queue语义；不可靠时明确unsupported/null，不能借历史均值代替|
|TD24|固定256学习子句的birth/first-use|Clause对象回收或指针复用必须invalidate；不能把未复用写年龄0|
|TD25|propagate watch loop中的examined与satisfied blocker skip|两个纯计数，热路径开销实测后记费|
|TD26|自然restart前后同一256活跃样本的assigned/sign|保持配对时点；分别记录正负分母，任一无支持则缺失|
|TD28|分析冲突间decision-gap的Welford n/mean/M2|至少32间隔；不重新以均值速率计新机制|
|TD30|已有分析reason引用上的学习引理依赖深度|需明确Clause生命周期与根unit无reason对象的边界；饱和/不完整即缺失|
|TD12/15/16|固定抽样reason DAG的祖先、深度和重访边|最多256样本/10000祖先访问；必须真实遍历reason；遇缺失reason、cycle或cap不补造数值|

共享状态目标小于1MiB（不含TD22可能需要的active-rank临时向量或TD30每live-clause字段）；所有增长容器都有硬上限。理由查询与rank工作放在checkpoint或已有分析遍历，避免每次传播做昂贵图遍历。额外状态无定义、预算不足或尚未正确实现的字段写`null`及原因；不能以旧均值、输入静态量或其它候选的别名填充。

完成补丁后向root交付：受SHA约束的基底文件清单、唯一替换/插入锚点、补丁文件/新源码SHA、支持字段及null原因清单、固定build CLI、合成hook不变量测试。root提交后才在独立源树编译，并记录新二进制/编译费用；192任务仍需新manifest绑定，不复用旧COMPLETE为新字段。

## 执行前源码推导的两项替换（root已批准）

TD19原saved-phase violation在常规主CDCL学习时会退化：新子句被当前trail否定，而search_assign已把saved更新为该赋值。TD19v2改为学习子句对既有TARGET phase向量的联合违反比例；每个事件须全部文字的target已定义，未知不当作0，无可评价事件则字段null。保留可评价事件数与全部学习事件数。

TD24原birth-to-first-reason-use被定义它的driving assertion支配，通常为0。TD24v2明确跳过该birth assertion后再记录首次reason使用年龄；未再次使用者右删失，不能补0。hook包围原始search_assign_driving参数，确保根层reason被canonicalize为null仍可准确识别birth，并避免nested search_assign重复计数。原saved/first-use只留diagnostic，不输入模型、不计额外轮。

原v1注册表不改。草案`work/ta100/dynamic_candidates_next_v2.json`仅替换这两项，附原定义和源码拒绝理由；未以新结果选择定义。
