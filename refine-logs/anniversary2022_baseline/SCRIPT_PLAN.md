# 2022 Anniversary 全量 CaDiCaL 基线：脚本设计

日期：2026-11-05；实现更新2026-11-07。状态：IMPLEMENTED_FUNCTIONALLY_QUALIFIED_NOT_FULL_LAUNCHED。

**最新范围修订：**用户2026-11-07随后选择排除官方所有赛道均未解出的636题，保留4719题，计划14157次求解；覆盖不足／不确定项保留。完整5355主名单原样保留。本修订覆盖下文旧的“5355全部执行、不按历史未解筛选”要求。见`EXTERNAL_DIFFICULTY_FILTER_20261107.md`与新的`manifest.official-solvable.v1.csv`，不得再把4719题结果称为5355全集实测。

七个脚本已实现，实际节点小样例、续跑去重、汇总／导出和本地绘图已通过。具体证据和未验证范围见`reports/anniversary2022_baseline/READINESS_20261107.md`。下文保留原设计；正式全量spec仍为DRAFT，不能将小样例当作T600／5355题证据。

## 目标与本次确定的范围

将官方2022 Anniversary完整5355条输入在同一版本 CaDiCaL 下分别运行 D、F+、F−，每次600秒预算、seed0，建立 **5355×3=16065** 条完整基线。先交付原始数据、累计解题曲线、配对散点和三配置 VBS，再开展特征研究。不将小面板、阈值筛选、特征工程或独立audit/dryrun作为全量任务的前置研究。

用户本次明确：**“整套都用于基线和开发，之后另找独立测试集”**；随后强调：**“教授的意思就是要把全部数据跑出来”**。这覆盖旧5355候选池的封存角色，但不改写旧协议／结果。原96题确认名单同样不再是新研究的独立测试；新独立测试尚未选定。不得继续声称整套5355仍为未曝光最终测试。

讨论记录仅作需求来源，自动转写可能有误，后半段非研究闲谈不纳入需求。相关段落：4:22–5:37三配置与VBS；6:15–8:35初始600秒及完整基线；11:55–13:44保存时间、conflicts和输出。记录中按旧比赛结果排除未解题是可选建议；本次用户要求全部跑，因此**不启用任何历史未解筛选**。

## 固定实验定义

|项目|设计|
|---|---|
|输入|官方 `track_anni_2022.uri` 全部5355条；每条保留，即使下载／资源失败|
|主求解器|CaDiCaL 3.0.1，commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`，原生静态CLI，无新特征observer|
|D|`--phase=1 --forcephase=0`|
|F+|`--phase=1 --forcephase=1`|
|F−|`--phase=0 --forcephase=1`|
|seed|全部0；首轮不追加重复seed|
|主预算建议|每次600 CPU秒；同时记录wall；1800秒wall仅为独立看门狗，不能冒称600 CPU秒超时|
|验证模式建议|三配置统一计时二进制LRAT；SAT检查本次model，UNSAT独立检查本次证明；checker CPU另计，不重跑完整solver来认证|
|数据角色|全部baseline_development；身份／来源只用于关联、下载、去重和任务分配，不能作后续预测输入|
|I−|本次主矩阵只含教授要求的三配置。I−作为后续策略的强静态对照保留；若追加，单独版本化5355项，不阻挡三配置数据交付，也不把三配置结果冒称已胜过I−|

正式启动前冻结二进制SHA、输入名单SHA、脚本SHA、资源profile、时钟／证明政策和预算。本文件及spec为设计草案；没有新服务器队列，也没有新的预算支出。

## 七个脚本

|脚本（拟建于 `src/anniversary2022_baseline/`）|职责|主要输出|
|---|---|---|
|`prepare_manifest.py`|读取官方URI及本地5355条存档；核对完整标识集合，生成新角色名单与确定性顺序；不读旧相位赢家，不删除历史未解／大文件|`manifest.csv`、`manifest_receipt.json`|
|`stage_inputs.py`|按需下载、断点重试、校验压缩及plain SHA、原子标记READY；复用完整缓存；有界预取，不先下载完5355题才开算|输入缓存、`input_receipts/`、下载失败记录|
|`run_baselines.py`|唯一owner调度器；创建16065个逻辑任务，统一管理下载／solver／checker资源、恢复和状态；SSH退出不影响任务|`queue.sqlite`、`progress.json`、物理费用账本|
|`run_one.py`|执行一个input/action/seed；绑核、限CPU/内存、捕获全部输出、保存最后1000行、解析终局统计、触发独立验证|不可变`runs/<run_id>/measurement.json`、日志、model／proof摘要、验证sidecar|
|`collect_results.py`|把每次实际执行与验证证据关联成5355×3成本矩阵；保留缺失／错误，不猜赢家；生成统一可视化快照|`runs.csv`、`instances.csv`、`matrix.csv`、`summary.json`、`coverage.json`|
|`plot_results.py`|读取固定snapshot，生成累计解题曲线、配对散点和VBS，不启动solver|HTML、PDF/PNG、绘图用CSV|
|`export_results.py`|导出源码身份、名单、原始收据、日志和图；核对SHA与预期任务集合；不装入密码或巨大临时证明|结果包、`MANIFEST.sha256`、完成收据|

共享解析与身份定义在`common.py`；`qualification.py`只做有界功能验证。`run_baselines.py status`输出状态与ETA，`resume`接回原owner账本，不新建另一份队列。源码已实现；准确CLI及实际运行证据见readiness报告。

## 单项结果必须保存什么

`run_id`由实际CNF SHA、solver SHA／commit、选项、seed、600秒预算及计时方式、证明与验证政策、runner／parser SHA、主机和资源profile生成。逻辑配置与实际命令同时保存。

最低字段：

```text
instance_key, input_sha256, action, seed, run_id, attempt_id
solver_commit, solver_sha256, runner_sha256, command, host_id, cpu_affinity
status, exit_code, stop_reason, timeout_clock, cutoff_s
cpu_user_s, cpu_system_s, cpu_s, wall_s, maxrss_kib
conflicts, decisions, propagations, restarts, conflicts_observation
answer_reported, verification_status, verification_cpu_s
log_sha256, tail_log_sha256, proof_bytes, proof_sha256
resource_profile, physical_execution_id, source_reuse_id
```

`conflicts_observation`区分完整终局计数、超时退出时计数、最后一次进度下界和缺失。缺失为null，不能填0。计时运行中的最终conflicts可作结果／预测标签，不能直接作将来动作前特征。

## 调度、恢复与资源

- 一个持久化SQLite账本，原子claim，记录owner／PID开始时间／主机boot身份。失联或lease过期先核查原进程；连接失败不等于可重新提交。每个实际执行有唯一physical ID，复用不重复收费。
- 主任务是完整16065项；8题×3只是第一个完整进度块，随后继续全集，不设oracle／明确标签数的继续门槛。它也是正式数据，不另开dryrun。首份完整小块曲线目标30–60分钟；未达到则报告实际准备、下载、验证瓶颈，不换题制造进度。
- 以无标签确定性顺序逐题推进，三个动作顺序做固定平衡；不按已测速度／赢家补题。各动作在同一输入上用相同资源profile；输入准备好即可入队。
- 最多8个CPU token，solver、解压、model检查、LRAT checker共享，避免8个solver外再叠加8个checker。下载可有少量I/O并发；解压／检查也计CPU。使用实际可用RAM、磁盘及其他owner占用决定并发，不盲开8个大进程。
- 输入按滑动窗口缓存；至少留磁盘安全底线，按活跃证明容量做admission。只回收本研究可重新获取、已有SHA且没有被在途任务引用的临时CNF／已验证证明，不动其他项目。失败证明保留到修复证据完成；空间不足暂停新领取，不能静默删失败。
- 不沿用旧pilot的100MB／5M变量排除条件。大题进大内存profile，必要时减少并发。OOM、下载失败、proof容量和checker错误分开记录；有界版本化恢复，保留费用。超过节点资源的题进入阻塞清单，不删题或伪装普通timeout。
- 正常CPU截止先发一次SIGTERM，给原生CaDiCaL输出统计的宽限，再强制结束；硬看门狗另记原因。固定源码已确认SIGTERM走正常终止处理；实现时验证实际输出路径。旧SIGPROF直接终止helper不能照搬成“超时conflicts必完整”的保证。
- SAT／UNSAT只有本次答案通过相应检查且CPU≤600才计solved。检查未完成保留`PENDING_VERIFICATION`，不当作solver timeout；仅检查证据重试，不默认重跑求解。

## 图表与指标：第一阶段的正式产物

1. **时间累计解题图**：x=CPU秒0–600，y=通过验证的解出数，D/F+/F−/VBS四条线。另列wall版本，不混用轴；可附cactus图作为同一数据的另一视图。
2. **conflicts累计解题图**：四条线，明确限定“600 CPU秒观察窗内解出”。VBS-conflicts与VBS-time各自取最优，可能选不同配置，不混称一条oracle。
3. **三组配对散点**：D–F+、D–F−、F+–F−，时间和conflicts各一版；1×、2×、10×参考线，未解／只解出一侧／缺失分开标识。零conflict保持真实0，需要对数展示时明确使用1+conflicts，不偷偷改原数据。
4. **汇总与逐题矩阵**：5355题覆盖、三配置解出并集／交集、每配置solved、PAR2（600秒下未解为1200）、最优固定配置、三配置VBS、差距、全超时数、错误与待验证数。PAR2罚分不当物理CPU费。

时间VBS定义：对每题取三个配置中通过验证且在预算内解出的最小CPU时间；三者均未解为∞（解题曲线）或1200（PAR2）。**超时的已用conflicts不是解完所需conflicts**，不能把较小计数判成更容易或赢家。conflicts更接近搜索工作量，但每次冲突处理成本会随配置／轨迹变化，不能据此声称运行时间完全硬件无关。

进度图只使用同一snapshot中已完成并核对的父题三元组，显著标出`PARTIAL: n/5355`。全体任务状态另列，不能只画解出子集或把部分结果称全量。固定块和吞吐仅用于交付／ETA，不修改研究人口或停止全集。

最终`COMPLETE_VALID_MATRIX`要求5355个输入槽位、16065个任务都有可解释且有效的终态；普通预算超时是有效终态。若任何题仍下载失败、资源错误、未验证或缺测，状态只能是`PARTIAL`／`COMPLETE_WITH_UNRESOLVED_ERRORS`，必须列出；不能因为“全部尝试过”就声称完整有效基线。

## 现有代码怎样复用

原现代项目路径：`work/phase_prediction_20261104/project/experiments/phase_prediction/`。

可版本化复用：`run_pilot.py`的SHA／原子写、model检查与统计解析；`fetch_public_cohort.py`的原子READY和压缩／plain校验思路；`matrix_reuse.py`的精确物理身份复用原则；`export_receipts.py`的逐文件清单。复用源码要绑定新快照SHA，不改旧文件。

**不能直接把旧`run_matrix.py`改一个N就启动**：它只允许特定开发角色，最多144题，静态动作固定四列，T600并发上限4，而且先准备整批输入并强制提取结构特征。旧`analyze_matrix.py`同样强绑定角色、四配置和特征文件。本次另写轻量runner／collector，旧证据保持不变。旧T60、MiniSAT false/true、共同前缀延续不能填入新T600静态矩阵；旧600秒记录只有实际输入、二进制、时钟／验证及资源身份均兼容才可引用。

## 规模、费用和ETA

全5355题、三配置、不含重试／检查的solver上限：

`5355 × 3 × 600 / 3600 = 2677.5 CPU核时`。

|每项平均solver CPU|全量solver CPU核时|8核理想计算墙钟|
|---|---:|---:|
|10秒|44.625|5.58小时|
|60秒|267.75|33.47小时|
|120秒|535.5|66.94小时|
|600秒上限|2677.5|334.69小时，约13.95天|

这些是场景计算，不是已观测ETA。输入准备、解压、排队、checker、失败恢复和分析另计；真实RAM／磁盘可能降低并发。前8题完整后给第一版，前64题完整后按端到端吞吐更新。补I−会增加5355项，最坏再加892.5 solver核时。

旧研究100核时是旧阶段的预算，不能宣称已覆盖这一全量计划。新阶段必须在正式spec里明确预算与剩余资源政策；上表不是已经授权的支出，也不因预算不足悄悄把全集改成子集。预算触及边界时checkpoint并报告剩余量，任务目标仍是全集。

## 预期运行接口（尚未实现）

```bash
python -m src.anniversary2022_baseline.prepare_manifest --spec configs/anniversary2022_baseline/spec.json
python -m src.anniversary2022_baseline.run_baselines start --spec configs/anniversary2022_baseline/spec.json --root RUN_ROOT
python -m src.anniversary2022_baseline.run_baselines status --root RUN_ROOT
python -m src.anniversary2022_baseline.run_baselines resume --root RUN_ROOT
python -m src.anniversary2022_baseline.collect_results --root RUN_ROOT --snapshot SNAPSHOT_DIR
python -m src.anniversary2022_baseline.plot_results --snapshot SNAPSHOT_DIR
python -m src.anniversary2022_baseline.export_results --root RUN_ROOT --require-complete
```

`start`必须拒绝DRAFT spec、未冻结SHA／预算和已存在健康owner；`resume`只接回相同run root。命令中的路径为占位符，不含SSH凭据。

## 当前状态与唯一下一步

Owner：本聊天；无委派、无服务器作业、无新邮件。允许的数据角色已由用户明确更新。

下一可执行动作：在已实现并小样例验证的源码上明确全量资源／错误恢复和预算，冻结正式spec后才启动5355题。必要实现检查已做，见readiness；不将它们冒称正式全量执行。

## 来源

- 用户讨论记录：`/Users/expexp/.codex/attachments/878d3c7b-ea51-4260-a6b8-57c76650ebb1/Note_20261105_1441_otter.ai.txt`。只据前约15分钟研究段落整理，不把转写文本视为运行授权。
- [SAT Competition 2022 下载页](https://satcompetition.github.io/2022/downloads.html)：Anniversary URI及详细结果入口；URI目标为`https://benchmark-database.de/getinstances?track=anni_2022`。本次未下载新CNF或运行solver。
- [官方赛道说明](https://satcompetition.github.io/2022/tracks.html)：比赛通常5000秒；本方案600秒是讨论中的初始预算，不冒称比赛原预算。Anniversary覆盖历年Application／Crafted／Main输入；官方Anniversary不强制UNSAT证明，本计划统一LRAT是本研究额外的验证选择，会计入求解成本。
