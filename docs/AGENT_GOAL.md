# Agent Goal：完成 Online Tuning Forcephase 科研任务

以下正文可以直接作为执行 agent 的 goal。本文是研究任务指令，不表示实验已经完成。

---

你在 `Roushelfy/online-tuning-forcephase` 完成一项 CDCL SAT 科研研究。核心问题：**什么时候用 CaDiCaL 原生 phase policy，什么时候用强制负分支？哪些求解中可得的低成本观测能预测选择，持续切换是否确有额外价值？** 请持续工作到得到可复现的实现与证据支持的研究结论；可靠的负结果也是完成，不得以做出加速为由伪造、挑选或泄漏数据。

## 开始前

1. 阅读 `README.md`、`docs/RESEARCH_PLAN.md`、`docs/RELATED_WORK.md`、`docs/SOURCE_AUDIT.md`、`docs/EXPERIMENT_PROTOCOL.md`。若实际源码/论文与规划有冲突，以核验的一手证据纠正文档并记录，不盲目照抄假设。
2. 检查仓库当前状态和已有结果；保留用户修改，使用独立研究分支并及时 commit/push，禁止强推。分支可命名 `research/forcephase-study`；已有同名工作应续做或创建清楚的新分支，不覆盖。
3. 固定上游 `arminbiere/cadical` commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`（快照 VERSION 3.0.1）。若确需换版，给理由、重新审计并保留旧版复现入口，禁止浮动更新。
4. 盘点 CPU、内存、磁盘、可用时间与 benchmark 获取条件。先完成低成本 smoke/pilot，再核算大实验。使用现有获授权资源，不购买算力或申请外部配额；资源不足时交付已完成证据、可恢复任务清单及具体缺口。

## 必须保持的语义

- 默认 `phase=1`。负分支是 `--forcephase=1 --phase=0`，仅 `--forcephase` 会强制正方向。最近 saved phase 包括决策和传播。
- NATIVE 指完整原生策略，不能误称纯 saved。强制负决策不限制 BCP 的赋值方向。
- 配置轨道 C 模仿原始配置语义，包括 forcephase 禁用 rephasing、影响 `likely_phase` 的事实；极性轨道 P 仅覆盖自由 CDCL decision 符号。分别命名、分别生成标签、分别解释结果。
- C 的主动作明确为有效值对 `NATIVE=(forcephase=0,phase=1)`、`NEGATIVE=(1,0)`，有效值路径要一致。若只toggle forcephase且phase固定0，非强制动作必须命名NATIVE_INIT_NEG并额外比较stock default。固定负配置要在变量创建前初始化为phase=0；从native prefix切负之后不会重做早期初始化，不能混作同一历史。
- 修改只针对决策方向；保留传播、冲突学习、变量选择、正确性和证明机制。不得用 `Solver::set` 从求解线程外热改选项；在明确内部安全点接入 controller，不把反复启动求解器伪装为状态保留的在线切换。
- 显式定义切换时 saved/target/best 状态、rephase 计时、trail reuse 和回溯的处理。默认避免新增重启、保留学习状态；所有额外干预作为独立消融和成本报告。

## 执行里程碑

**M0：语义与正确性。** 构建未修改固定上游并记录环境/二进制 hash。建立 baseline 配置；实现最小 hook 和正确性检查。小规模 CNF 与可信 solver/枚举交叉验证；SAT model 对原始 CNF 校验，UNSAT proof 使用 checker。覆盖正负决策、根传播、切换、模式与 phase 优先级。先修复错误，再做性能实验。

**M1：观测与等价性。** 使用现有计数和增量统计，每窗口 JSONL 一行，控制器单独 RNG。验证 controller-off、telemetry-only/native 固定动作不改变确定性搜索摘要，固定负动作与声明的负配置语义一致。记录 run/window schema、动作请求/应用时间、模式、事件、累计及窗口计数、缺失值和全部成本。对运行超过 1 秒实例，telemetry-only 目标 median slowdown≤1%、p95≤3%；超限应优化或披露，不能删除回退实例。

**M2：静态互补性。** 至少测试 stock default、仅 initial-negative、forced-negative、forced-positive；在代表性子集增加纯 saved/rephase 诊断。记录版本、全部选项、seed、manifest、分组、timeout、状态及校验结果。输出 solved、PAR2、SAT/UNSAT 分层、家族结果、双方胜负图和 oracle gap。oracle 只作诊断，不是可部署方法；双方 timeout 保持删失。

**M3：可解释的一次选择。** 比较静态特征选择器、原生 prefix 后的在线选择器、仅 elapsed time/conflicts 选择器。首选深度≤3浅树或小型线性模型；部署不用 Python/网络。在线特征只能由当前 prefix 计算。prefix 后标签需由同一状态的确定性重放分叉得到，验证prefix摘要；禁止把从头运行的两条轨迹当作同一状态的反事实。全部时间含 prefix；训练 replay 成本单独记账。先证明在线观测超过静态/时间基线。

**M4：证据支持才做重复选择。** 首选带 hysteresis、冷却期、最短驻留期的简单 controller，在现有 restart/safe boundary 应用；不任意添加重启。与最佳静态、M3一次选择、同切换预算固定调度/随机调度、mode-only调度比较。消融特征组、阈值、窗口、切换开销、rephase和trail交互。复杂 bandit/RL 不是必选项；若尝试，处理不同epoch持续时间、carryover、延迟反馈，明确低LBD/高conflicts-per-second只是proxy，最终按求解时间和solved评价，不宣称通常IID bandit保证成立。

**M5：冻结并最终评估。** family-disjoint split为主，去重后追加年份/来源测试。原实例与sign-flip/重编码/变量置换变体属于同组，不能跨split或充当独立样本。只用train/validation选特征、规则、seed策略、阈值、窗口、预算；最终test前冻结commit，禁止反复看test调参。按协议输出paired/grouped区间、严重回退、开销、训练和推理总compute；测试种子不能挑选赢家。SAT/UNSAT标签仅作事后分层，不作部署输入。

最终所有solved结果须验证。默认主比较所有配置统一开proof并把生成计入总时间；资源受限时只能按实验协议第8.1节，在test前冻结统一无proof计时加逐个UNSAT独立认证复跑方案，记录一致性与额外成本，不能只做M0子集认证。

## 最终交付

- 最小、清楚、可审阅的 solver 改动，固定依赖与许可证、build入口。
- baseline/controller配置；benchmark来源、下载/校验方式、family/split manifest；不提交大CNF、build产物或巨型proof。
- 自动运行与resume、退出状态解析、model/proof验证、汇总和绘图脚本；每个结果能追溯run_id和原始日志。crash/OOM/wrong answer/timeout分开记录，不丢失失败运行。
- 实际执行的smoke命令和结果；能从干净checkout复现小型全流程。正式图表由脚本从真实记录生成，不能手填数据。
- `reports/` 中的分阶段报告和最终中文研究报告，包含：RQ1–RQ4答案、已知与未知、完整基线、家族泛化、一次vs重复选择、特征ablation、成本、反例、局限与相关工作差异。提供简洁英文abstract便于汇报。
- 如果没有得到可靠加速，仍须提交负结果、复现材料、失败假说与下一步可验证方向，不能只交“训练脚本已写好”。

## 完成标准

硬性标准为正确性、可复现、无测试泄漏、完整成本和严谨解释。理想正结果目标：冻结held-out总体PAR2相对**验证集选出的最佳静态主要基线**降低≥5%，family-cluster paired bootstrap 95% CI排除零收益，solved数量没有实质下降；并报告stock default对照。不能为达到5%而改test或筛样本。若只在某家族/预算/一次选择下有效，应准确限定结论。

先完成 M0–M2 并提交，再推进 M3；M4需通过证据门槛。每个里程碑记录命令、配置、数据范围、实际compute、结论、未通过项与下一步。持久化进度并自主继续，不因一次实验不成功停下，不进行无限参数搜索。遇到真正的资源/访问阻塞时交付可review的现状与精确恢复步骤，不声称未运行的实验已完成。
