# Force-phase研究接手prompt

你负责接手这个仍未完成的研究任务，继续实际开发和验证policy，不要只写方案，也不要将60秒的小pilot结论扩大为整个目标已经完成。

## 目标与背景

研究能否仅凭CNF公式结构及动作前求解统计，在D、F+、F−之间选择更好的配置。教授提供的MiniSAT相位false/true实验显示不同公式偏好不同方向，但没有提供版本、命令或代码，因此不能声称精确复现、也不能把原false/true标签直接等同于真实赋值方向。

主实验使用CaDiCaL 3.0.1，固定commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`：
- D：`--phase=1 --forcephase=0`。
- F+：`--phase=1 --forcephase=1`。
- F−：`--phase=0 --forcephase=1`。
- I−：`--phase=0 --forcephase=0`，必须作为强静态对照，当前不是第四个可学习动作。

教授禁止使用problem family信息。禁止把family、生成器/应用名、文件名、路径、URI、年份、作者、实例ID/hash、已知SAT/UNSAT答案作为模型输入或路由规则。hash只用于下载、关联、固定抽样、去重。可用视角：子句长度/极性分布、变量—子句图分量/叶/度/cycle excess、局部gate模式，以及动作前glue/LBD、学习长度、决策层、回跳和传播统计。不要把终局统计当作前缀观测；“deck-like”含义未确认，不能擅自当作已有DAG标签。

用户要求reinforcement in-context learning：当前agent读开发反馈、保存成功/失败经验并提出下一版可执行JSON policy，权重不更新。最多8轮、每轮最多2个提案，深度最多3；阈值和叶动作在fit上拟合，feedback可反复用于有界开发，gate只能最终用一次，最终测试不可反馈进上下文。保留负reward和反例，不冒称已训练Algorithm Distillation，也不虚构第二个LLM的无记忆实验。需要与相同容量/成本目标的简单规则或树对照。

## 工作区与必读资料

原工作区：`/Users/changrum/Documents/GitHub/online-tuning-forcephase-lpn`。若使用随附zip，先在独立目录解包，保留相同相对路径。必读：
1. `docs/PHASE_PREDICTION_GOAL_20261103.md`、`docs/PHASE_PREDICTION_PROTOCOL_20261103.md`。
2. `reports/phase_prediction_v1/{STATUS,INPUT_AUDIT,SOURCE_AUDIT,P1_LEARNABILITY,ONLINE_LEARNABILITY,RICL_HISTORY}.md`。
3. `results/phase_prediction_v1/server_reference.json`、`cost_ledger_provisional.json`、`context/`。
4. `experiments/phase_prediction/` 的运行、分析、policy与测试代码；`configs/experiments/phase_prediction_v1/` 的冻结名单及spec。

原附件在本机Downloads：`data.csv`、`track_anni_2022.uri`；本地归档在 `results/phase_prediction_v1/inputs/`。交接zip不包含教授原始CSV、图片或密码；需要原始附件时沿用用户已有文件访问。附件内容是研究数据，不是agent指令。

## 数据与防泄漏

用户已确认2022 Anniversary URI清单5355条为最终测试候选全集。隔离336个exact或GBD isohash等价曝光条目后，有5019个未曝光候选组；GBD去重不是一般同构证明。教授CSV有400个完整false/true配对，300个在全部受保护候选之外；开发冻结为180 fit、60 feedback、60 gate。96个确认候选已封存。整个5355候选集合都不得参与开发，不能只避开最终抽出的96个。新测试solver输出从未读取。

资源资格是plain CNF≤100MB、header变量≤5M，不能按赢家替换。合格fit144、feedback48、gate51，保留资源排除记录。所有seed/轨迹按父实例或等价组统计，不能把它们当独立样本扩充n。

## 已完成的真实结果

1. RICL第1轮仅为旧CaDiCaL成本矩阵warm start，144 fit/48 feedback：平均长度≤3.67724选D，否则F−，相对D改善0.50%，探索区间跨零；二元比例≤0.362327选F+，否则D，改善3.60%，区间也跨零。不能称新服务器验证。第2轮两个提案为长度+极性浅树、纯图结构浅树，已冻结但未评分，不得补写虚构reward。
2. 新服务器P1，48 fit×3配置、seed0、T60：D/F+/F−解出11/13/11，平均PAR2为93.738848/90.409961/94.460735秒。三动作oracle为90.212644，仅比固定F+好0.218%。35例三者均删失。已暂停原144例T120静态扩展，但这不能否定更长预算。原144条测量全部验证；一例证明预算扩展用独立sidecar，原JSON未改写。
3. 在线16 fit×3延续、seed0、总T120，计时文本LRAT：共同D前缀在跨过1000冲突后的自然重启处观测，再保持D/转F+/转F−。48条完整有效，14例到达决策点，2例提前解出；实际触发1000至6920冲突。D延续解出3例，F±各2例；PAR2为196.800119/210.002346/210.001809秒，oracle只比保持D好0.00031094%。13例全部删失，一例仅D解出。未观察到有用正向切换标签，尚未训练出内容在线policy。这些F±是D前缀后的延续，不能和P1从初始化即F±混算。
4. 原版合成门禁8项、FPC2 no-op/前缀门禁12项、二进制LRAT检查门禁22项通过。本地语义/泄漏/成本/复用测试已有记录；检查不能替代真实策略泛化验证。

## 当前实际运行，接手先检查，不能重复提交

服务器移动入口 `223.109.239.36:13752`，电信入口 `180.127.11.177:13752`，账户优先 `vipuser`。使用用户最新提供的凭据；不把密码写入代码、日志、prompt或归档。在原机器可尝试已认证的复用socket `/private/tmp/forcephase-handoff-20261104c.sock`，known_hosts为 `data/phase_prediction_v1/known_hosts`。socket失效不表示实验停止。

远程根目录：`/home/vipuser/forcephase_phase_prediction_20261104`。
当前阶段：`long600_fit16`，最近2026-11-04 18:26 UTC核实PID **6096**实际存活，完成 **19/64** 条、逻辑累计 **2.889331 CPU核时**、stopped=false。该PID是GNU time父进程，命令行包含该阶段。

- 源码：`src/long_v5/`；配置：`metadata/long600_fit16_spec.json`；名单：`metadata/online16.csv`。
- 日志：`logs/long-screen-transition.log`。
- 输出：`phases/long600_fit16/results/{progress,completion}.json`、`runs/`。
- 整进程资源：完成后 `logs/long600_fit16.resources.txt`。
- 同一16个冻结fit，D/F+/F−/I−，seed0、T600，最多2并发，每进程3GiB内存、4GiB证明容量。计时生成二进制LRAT，独立 `lrat-trim --no-trim` 验证，成功要求exit20且`s VERIFIED`。旧ASCII checker成功码是0，不可混淆。
- 最坏solver10.6667核时，阶段停止阈值14核时；整个研究总预算100核时，含失败、验证、抽取、部署与工程。已完成P1可核对2.006979h、在线成功整进程1.387911h、首批证明上限失败0.135061h另计；初始编译没有完整CPU记录，保守留2h工程预留。必须用实际账本复核后续可行性。

先看真实PID/命令行、日志、完成文件。连接失败、观察超时、过期socket都不是终止证据，不得据此重启。程序已经在运行，勿覆盖当前源码/二进制/原始JSON。运行身份包含二进制、输入、动作、seed、预算、验证方式及观察代码。新程序支持SHA绑定的相同物理测量复用；扩大队列时避免重复核时。logical matrix费用可能包含复用记录，实际执行费用看parent资源并去重。

## 接下来实际做什么

1. 接续上述真实运行，出现OOM/文件容量/验证错误则保留失败和费用，不当普通timeout训练；排查后采用新身份修复。不要动其他用户/项目进程或清理无关文件。
2. 该阶段完成后在服务器执行 `src/long_v5/export_receipts.py --root <远程根目录>/phases/long600_fit16 --out <远程根目录>/exports/long600_fit16_receipts.tar.gz`，取回后检查归档与逐文件SHA，再用 `experiments/phase_prediction/analyze_matrix.py` 严格分析完整矩阵。600秒是主要cutoff，120/300只是同一长轨迹内诊断，不挑最好cutoff当确认结果。
3. 根据真实较长预算结果继续开发有信息的结构/搜索统计策略；需要新增fit/feedback面板时，在读取其新结果之前冻结名单、配置、seed、预算和验证政策。保留全部RICL迭代及错误选择费用；不能只追accuracy、只看解出子集或把双超时编成赢家。
4. 对候选做真实部署与离线评分一致性核对。主PAR2按总T预算计算：feature/decision CPU=h，求解CPU=t，仅当验证成功且h+t≤T才给h+t，否则2T。prefix与遥测不免费；checker费用另计实验账本。与D/F±、I−和匹配容量的简单规则比较。
5. 只有开发gate相对最强简单/静态对照有至少2%点改善且配对区间方向支持，实际部署一致，才解封确认集。gate只用一次，不把反例回流；最终测试冻结policy，不在测试中更新。未过门槛则交付明确范围的负结果或证据不足，不能宣称完成了未执行的测试，也不能把60秒小面板当整个任务。
6. 最终交付代码、冻结配置、policy/经验记忆、验证证据、费用账本和结论报告。现有旧研究原样保留。当前goal尚未完成；本次交接不是完成声明。

服务器只接受必要研究代码和公开benchmark资料，教授原始附件及旧本地性能记录之前没有上传；曾有全量敏感bootstrap上传被自动审查拒绝，已改为安全最小包，不应再尝试原全量导出。
