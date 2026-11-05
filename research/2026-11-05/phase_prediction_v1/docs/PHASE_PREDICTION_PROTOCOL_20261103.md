# Phase prediction v1：执行协议与冻结边界

日期：2026-11-03。上位目标：[当前 goal](PHASE_PREDICTION_GOAL_20261103.md)。

本协议先冻结 P0/P1；P2/P3 的精确名单和候选必须在对应求解或评分前另存带 SHA 的配置，不先试出结果再补写规则。

## 输入角色与禁止项

`results/phase_prediction_v1/inputs/provenance.json` 保存三个附件及 SHA。`input_audit.json` 和候选 CSV 是 exact-hash 审计结果；整个 2022 候选集合为受保护命名空间。

URI、hash 只用于下载、去重、固定拆分。family/文件名/作者/年份/应用类型/known SAT status 禁止作为训练特征、策略分支或选择分层。所有模型输入必须来自明确的数值白名单。终局搜索统计不可作为前缀观测。

开发候选严格来自教授 CSV 的 400 个标识减去全部 5355 个受保护测试标识，当前 300 个。按 SHA256(`phase-prediction-v1-20261103:` + hash) 排序，前 180 为 fit、中间 60 为 feedback、最后 60 为 gate。新规范化等价检查若合并标识，以等价组为原子重新排序，在任何新性能评分前冻结最终清单。

P1 固定从 fit 的排序中取前 48 个可获取且满足输入预算的实例。资格只看文件大小、变量上界和格式，不看相位赢家；替补按同一排序，逐条记排除理由。单 CNF 解压后上限 100 MB、header 变量上限 5,000,000；这些是 pilot 资源限制，不是对总体分布的定义。

## 初始配置与记录

CaDiCaL 固定 commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`。D=`--phase=1 --forcephase=0`，Fplus=`--phase=1 --forcephase=1`，Fminus=`--phase=0 --forcephase=1`。共同 seed=0，T=60 秒，最多4并发。新运行都以 CPU 计入 PAR2；同时记录 wall cutoff 与争用。

数据与 model/proof 一律针对实际读取的 CNF。SAT 必须独立 model 检查；UNSAT 必须有独立可验证证据。错误、OOM、争用、验证未完成均单列，不当作 timeout 训练。全超时不能赋予一个赢家。

每次运行的内容身份包含二进制、输入、配置、seed、预算、验证政策和观测代码 SHA。检查到已完成记录就复用；错误修复生成新身份，不覆盖旧测量。

## 特征

第一版 `cnf_structure.cpp` 仅输出公式统计及变量—子句图统计。图的 cycle excess 定义为 `incidences − active_variables − clauses + connected_components`；component 计算包含原始空子句节点。重复文字不重复计图边。二元/三元 gate 模式为带文字符号的局部编码匹配，不使用应用标签。

抽取器对 5 百万变量及局部模式存储设上限，达到模式存储上限时给 gate 数值 null 并标 exact=0，不把截断计数冒充精确值。特征抽取 CPU/内存/错误必须记录并计入部署成本。

在线特征需在后续配置中列出实际 schema、采样时间、共同 prefix、缺失策略及开销。原生 MiniSAT 不自带可直接借用的 LBD 日志时，须按学习子句中不同决策层数定义只读计数，并检验不改变搜索；不能伪造 glue 字段。

## Feedback in-context learning

当前 Codex 读取开发运行摘要，提出有限深度 JSON 决策树；`policy.py` 严格检查 feature allowlist、有限阈值、缺失分支和三种动作，不执行字符串代码。

每轮 episode 至少保存：policy/hash、开发 split_role、实际评价输入集合 hash、baseline 和候选 PAR2/solved/总成本、reward、反例摘要、策略修改理由和保留决定。reward 必须来自真实计分，不先给空 baseline 伪造一个正 reward。

定义开发 reward：`1 − mean_PAR2(policy, including deployment overhead)/mean_PAR2(frozen development static baseline)`。baseline 只能在 fit 上选定；feedback 可进入上下文，gate 和测试结果都不能进入 episode memory。最多8轮，每轮最多2提案，保留失败轮。

提案需和同一损失、同样数值输入、同样容量/预算的简单树或规则基线比较。无经验记忆对照只能称同预算提案对照，不能虚称没有实际执行的第二模型或跨模型审查。

最终冻结前，对门槛和置信区间使用固定的 instance/equivalence-group 配对重采样，不使用 problem family 信息。重复 seeds 和轨迹不能扩充独立 n；所有同实例信息属于同组。

## 统计与门槛

主度量是计入成本的完整 PAR2 与 solved；accuracy、散点相关、oracle 空间是诊断。先求同实例跨 seeds 的均值，再在配置间比较。两超时不推断真实相对速度。

静态 oracle 和同状态 continuation oracle 分开；不能把改变初始动作的收益全归于在线选择。最终候选必须在开发 gate 相对最强简单/静态基线有至少2% PAR2 点改善且方向经配对区间支持，实际部署与离线一致，才解封确认集。小样本区间过宽时报告证据不足。

未过门槛则保留完整 RICL 历史和成本分析，停止为正结果不断追加调参；不使用测试集再选规则。

## 原始证据与方法定位

- 教授附图采用 wall time，图例 SAT=87、UNSAT=100；CSV另有213个双超时配对，不能默默删除它们后称为全体收益。
- 原始 false/true 的解释须查源码。MiniSAT 源码中 literal sign 布尔值与赋值真值可以相反，且 phase saving 的版本差异必须区分：[官方 Solver.cc](https://github.com/niklasso/minisat/blob/master/minisat/core/Solver.cc)。
- 反馈与经验上下文的设计参考 [Reflexion](https://arxiv.org/abs/2303.11366) 的参数不更新式记忆反馈；不将它声称为已训练 [Algorithm Distillation](https://arxiv.org/abs/2210.14215) 的 transformer。

所有新运行、协议变更、已接触结果与预算写入本阶段状态和账本。服务器连接凭据不进入任何版本化产物。

## 2026-11-04 增补：旧成本矩阵 warm start

在读取任何新服务器性能或 development_gate 评分之前，允许一个明确标注的离线 warm-start 回合：仅使用冻结 fit/feedback 中可关联到旧项目完整 D/F+/F−、seed=0、orig、已验证结果的记录，以及旧静态特征。整个测试候选集和 gate 都排除。

本回合恰好提出两个预先指定的单层规则：子句平均长度 stump、二元子句比例 stump。阈值限 fit 中 1/8 到 7/8 分位点，左右叶动作各由 fit 成本最小值确定；每边至少8个 fit 样本。fit 选静态基线，feedback 只评价并写入上下文，不根据 feedback 重训这两个提案。

reward 使用旧成本矩阵和已记录的旧静态特征 CPU，明确标记 `offline_static_cost_matrix_legacy`。它不是新服务器运行、不是实际部署验证，也不能说明新图结构抽取器的开销。保存缺失/排除样本数与原始文件 SHA；将来仍须用新服务器确认。该回合占用8轮上限中的第1轮，保留其负 reward。

## P2 的有界在线观测与强静态对照

除了静态特征，用户要求的 glue/决策层统计至少做一个有界试验，不能因静态规则没有成功就宣称在线信息无效。默认在同一无标签hash顺序的前16个合格 fit 实例、seed=0、D共同前缀、K=1000冲突后的自然restart，记录只读的glue/学习长度、决策层/回跳和传播统计，再分别keep-D、转F+、转F−。每条完整运行总T=120秒，prefix不免费；三分支检查到的prefix摘要必须一致。最多48条完整运行，最坏1.6 solver核时；源码和遥测no-op门禁通过后才执行。早解/未到K/三者超时都保留。

策略动作集合仍为D/F+/F−。最终强静态对照必须另列 **I−**（`--phase=0 --forcephase=0`），因为旧研究中仅改变初始相位已有竞争力。不能把只优于D解读为超过最强已知简单方案。I−不是额外可学习动作，也不提供family信息；它在新硬件上重测。

若扩展开发到144例、2seeds、T=120秒，三个动作加I−对照的最坏solver预算为38.4核时。确认最多5个独特配置可取D/F+/F−/I−/唯一冻结policy，96例×2seeds×120秒为32核时；不能看到测试结果后换对照。所有阶段总CPU仍受100核时约束，验证和实际部署开销优先保留。

**证明成本约束（P2/P3启动前必须实现）：**正式扩展和确认采用计时运行同时生成LRAT、checker另记CPU的统一验证政策，不能在38.4/32核时预算之外再为每个UNSAT无条件重复一个完整求解。SAT仍检查本次model；证明生成成本包含在所比较配置的计时中，报告限定为该验证模式。P1保留其无证明计时+UNSAT证明复跑的工程pilot身份，不能直接与正式验证模式混算分数。P2、在线有界试验、P3的名义solver上限合计72核时，P1含最坏复跑4.8核时；剩余至多23.2核时用于抽取、检查器、部署/工程和失败。每阶段启动前按实际剩余额度核算完整矩阵与验证预留，不够则在看该阶段结果前缩小并冻结规模；不得省略校验来完成名义矩阵。

**精确开发角色及gate预算：**144例扩展面板由hash顺序前96个fit和前48个feedback构成，P1的48例是前者子集；其余开发候选不自动加入调参。60个development_gate仅在最多8轮提案结束后一次性使用，最多3个独特配置、seed=0、T=120秒，最坏另加6 solver核时，禁止再把gate反例写回上下文。将这6核时计入后，P2/在线/gate/确认的求解上限为78核时，加P1最坏复跑4.8后，余17.2核时用于工程、抽取、检查和故障。若阶段预算预计不足，在读取该阶段性能前按既定hash顺序缩小面板并记录，不能事后删除失败实例。

2026-11-04执行前澄清：上述“前96/48”均指满足同一100MB plain/5M header variables资源资格后的顺序。180 fit中144合格、60 feedback中48合格；扩展面板已冻结为96+48。60 gate中51满足同一资格，若进入gate只评价这51例并保留9例资源排除记录，不能声称覆盖全部60。资源排除清单为 `configs/experiments/phase_prediction_v1/resource_exclusions.json`，无相位结果参与筛选。在线16例名单和spec也已冻结。P2正式矩阵尚未启动，须先通过P1完整性和选择空间检查；名单冻结不代表已获得运行结果。

**P2起的端到端评分定义（读正式结果之前固定）：**静态policy的可用预算为T，若特征/选择CPU为h、所选分支本次验证有效的求解CPU为t，仅当h+t≤T时计为solved并给h+t，否则给2T。单纯always动作不收取未执行的图特征费用。先前warm-start的“PAR2再加特征费”保留为旧诊断定义，不与此主分数混算。在线分支的计时本身包含共同prefix、遥测和续跑；只有policy还执行的额外外部特征或决策成本另加。独立checker成本计入实验核时账本，主solver PAR2以产出随后被验证的答案为截止点；验证失败不产生成功标签。实际部署需执行同一全预算限制并核对离线预测，不能仅选成本矩阵中最好的一列就称部署完成。

## P1运行中的验证异常与一次扩展

2026-11-04，在P1未完成、尚未整体评分时的健康检查发现1例 `UNVERIFIED_CERTIFICATION`：原计时运行55.208589 CPU秒返回UNSAT，而同配置、同seed的带证明复跑在60秒预算返回UNKNOWN，尚未达到原先的最终冲突/decision计数。未检测到争用。此条不是普通超时标签，也不删出矩阵。

明确允许**仅验证用途**的一次120秒证明复跑，最多处理4个此类条目，仍用原二进制、输入、配置和seed；必须复现原计时运行的conflict/decision/propagation/restart/rephase最终计数，并通过同一独立LRAT检查。原始计时、首次证明超时和原JSON一律不改写。新增证据写 `results/certification_extensions/<run_id>.json`，绑定原记录SHA及二进制/输入/checker SHA；分析使用这一独立证据完成验证，并将首次失败及本次扩展CPU全部记账。扩展失败则阻止衔接，不再自动追加尝试。它不改变P1的60秒测量预算，也不改变后续正式实验的统一计时LRAT模式。

## 在线文本证明资源修正与600秒删失检查

在线16例首批因1GiB文本LRAT文件上限收到SIGXFSZ，保留3条运行及1条failure，整进程资源486.22 CPU秒。它未产生完整矩阵、未进入policy反馈。`online16_v2` 在独立目录统一采用2GiB文本证明上限，原16例、三个延续动作、seed0和T120不变；旧阶段未改写或混入。实际修正依据和成本均已保存。

**在看到P1后作出的开发阶段决定：**P1在T60下35/48父实例三者均未解出，三动作oracle仅比固定F+改善0.218%。暂停原144例T120静态扩展，但不能把这一短时上限推广成现代公式上的普遍结论。因而增加一次固定的600秒删失检查，名单仍为hash顺序前16个合格fit，不按赢家替换；D/F+/F−及I−、seed0、共64条，最坏求解10.6667核时。主要分析预算固定为600秒，120/300秒仅作同一长运行内的诊断删失分析，不从多个cutoff挑最优作为确认结果。

新检查计时生成二进制LRAT，由固定源码 `test/cnf/lrat-trim.c` 的独立检查实现以 `--no-trim` 单独进程验证，要求exit20及 `s VERIFIED`。它已在新服务器通过22项合成检查，包括ASCII/二进制相同搜索计数、两个检查器交叉验证ASCII、拒绝未完成二进制和在SAT公式上的伪空子句。当前在线试验仍使用原文本模式，不跨模式混算CPU分数。

600秒检查使用最多2个solver、每个3GiB内存、4GiB证明文件上限，并在12GiB可用磁盘底线外预留全部并发证明容量。阶段CPU停止阈值14核时，另考虑在途子进程预留；与已执行阶段和工程预留合计仍明显低于100核时。冻结文件为 `configs/experiments/phase_prediction_v1/long600_fit16_spec.json`，新源码目录 `src/long_v5`。守卫只在当前在线48条完整、前缀/model/proof严格分析通过后衔接；终止/缺失进程或失败分析不会触发重启。

新测量的内容身份包含solver/checker/观测源码、验证模式、内存与证明容量、输入SHA、动作、seed和T。队列名单及整体预算属于单独冻结的计划身份；以后扩大队列可通过原记录SHA复用物理测量，不为同一确定性运行重复消耗核时。复用拒绝不同输入、预算、检查器、修改过的原记录及失败/争用结果。新试验未完成前，以上均为执行安排，不是策略收益证据。
