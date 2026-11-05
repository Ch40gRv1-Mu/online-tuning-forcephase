# 外部线索：MiniSAT phase 对比与编码结构

记录日期：2026-11-04。状态：解释与下一轮候选构想；未提取新特征、未拟合模型、未运行 solver，不是实验协议或验证结果。

后续状态澄清：本笔记最初对照的是父目录已完成的旧六类研究。随后核对到 `work/phase_prediction_20261104/project` 的更新交接：教授CSV已经有单独保存的输入报告，当前无family新阶段仍active，开发/gate/2022最终候选已冻结。当前测试与快速筛选以 `test_sets_and_fast_screen_2026-11-04.md` 所列新协议为准；下文旧300题和family留出的设想不是对新项目的执行建议。

来源：用户提供的英文来信和散点图（Runtime per instance: phase=false vs phase=true）。图例为 SAT n=87、UNSAT n=100；尚无逐题数据、家族标签、MiniSAT 版本/修改、命令行及样本纳入规则。不能将外部187题当作已经取得的独立确认集，也不能判断与现有300题是否重叠。

## 图支持的观察与尚未支持的解释

- 横轴 false、纵轴 true；对角线下方表示 true 更快。图形与“该批 UNSAT 多数偏 true、SAT 更分散且两方向都有大损失”的描述相容。没有逐题数值，不量化胜率、平均加速或显著性。
- 图没有组合/硬件家族标记。“组合题偏 false、硬件题偏 true”来自来信中的未人工核实猜测，图本身不能验证。
- SAT/UNSAT 是求解后的分层变量，可用于机制诊断；不能作为部署输入。来源、编码与可满足性可能混杂，不能把相关性写成因果机制。
- 水平/垂直 timeout 边缘是删失测量；双超时不提供方向。应明确是否画出全部运行、双超时或失败是否被排除。不能用封顶时间当实际精确耗时比。
- 外图只比较两个 phase；没有本项目 D。F+ 胜过 F− 不代表它胜过 D。

## 与本项目的衔接

当前实现记录：`src/run_short_traces.py` 的 D 为 `--phase=1 --forcephase=0`；`src/run_phase_traces.py` 的 F+ / F− 为 `--forcephase=1` 配合 `--phase=1/0`。外部实验究竟改变初始 phase、强制每次决策方向，还是同时关闭 phase saving，需要由原命令与代码确定。

官方 MiniSAT 源码含 phase saving 和用户 polarity 路径；CaDiCaL 源码将 forcephase 与 saved/target phase 区分。因此“phase=true/false”这个名称不足以证明两项实验语义一致。查阅的公开源码只用于说明此区别，不作为本地固定二进制版本的认证。

- [MiniSAT Solver.cc：cancelUntil / pickBranchLit](https://github.com/niklasso/minisat/blob/master/minisat/core/Solver.cc)
- [CaDiCaL decide.cpp：decide_phase](https://github.com/arminbiere/cadical/blob/master/src/decide.cpp)
- [CaDiCaL options.hpp：forcephase](https://github.com/arminbiere/cadical/blob/master/src/options.hpp)

H02 已检验纯正/纯负子句比例与长度加权符号差，没有得到选择收益；H03 的根传播残差也未通过。新信息值得推动的是同一组变量上的子句组合、编码角色与符号方向，而不是继续扫描同一组全局计数。此前的负结果并未覆盖专门的门结构或互斥组识别程序。

## 可操作的新假设

候选解释：编码中的选择变量、辅助门变量与约束连接方式，可能造成强制方向的不同搜索代价。以下均是待检验假设，不能直接断言速度方向。

1. 互斥/选择结构：同一变量组中，正的 at-least-one 子句与负二元 at-most-one 子句共同出现。例：`(x1 ∨ … ∨ xk)` 加 `¬xi ∨ ¬xj`。这种局部组合比“负二元子句多”更接近组合选择的编码机制；仍不能推出所有组合题偏 F−。
2. 门定义结构：例如 `z ↔ (a ∧ b)` 的三个子句为 `(¬z ∨ a)`、`(¬z ∨ b)`、`(z ∨ ¬a ∨ ¬b)`。识别共享变量的二元/三元完整模板及其符号方向，比只看长度直方图更具体。CaDiCaL 本身具有 AND/ITE/XOR 门提取代码，说明此类结构可从 CNF 操作性识别，不证明其可预测 phase 收益。
3. 优先保留两个候选家族：带方向的门模板覆盖/不对称，以及互斥组与正选择子句的配对覆盖。避免立即扩展成高维特征库。实际定义、归一化、提取上限和模型集合需在新协议中冻结；本笔记不预定胜负阈值。

[CaDiCaL congruence.cpp：门识别实现](https://github.com/arminbiere/cadical/blob/master/src/congruence.cpp)

极性解释的约束：把每个变量都换成它的否定，保持 SAT/UNSAT、子句长度和无符号关联结构，却对调 all-true / all-false 对应的语义赋值。因此，题型或无符号结构本身不足以普遍决定绝对的 true/false 方向；候选应保留编码符号和变量角色。这不是声称实际 solver 在翻转前后运行时间严格对称，预处理与其他启发式可能破坏时间对称性。

## 后续研究顺序与决定

本轮六类检验保持 COMPLETED_SCOPED_NEGATIVE；不因这封信改写既有结论、解冻标准、重启 heartbeat 或启动服务器工作。

若后续开展新一轮，先取得外部逐题运行表、benchmark ID/家族、solver 版本与命令、超时/验证及纳入规则，并核对输入重叠。仅在有原始数据时，按 SAT/UNSAT 与编码类别交叉分层检查现象，保留所有运行与删失，不按已知赢家选择子集。

新协议应先提交，再复用现有已验证300题进行明确标注的探索；不重测健康基线。用上述有限结构候选、按 family 留出评价完整学习程序，部署输入仅取 CNF，计入提取失败和成本，并同时对照 D/F+/F−。训练目标为特征成本加所选配置的既定 PAR2 成本，重点控制错误切换的尾部损失。SAT/UNSAT、人工家族只作分组诊断。

只有候选跨家族、计费后优于 D，才考虑冻结一个规则并用未参与选择的新题确认；原300题和已用于构想选择的外部结果均不得重新标为 untouched confirmation。执行前另立新一轮范围和协议；本笔记没有授权或启动任何实验。
