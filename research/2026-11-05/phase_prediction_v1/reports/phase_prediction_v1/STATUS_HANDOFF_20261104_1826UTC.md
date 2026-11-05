# Phase prediction v1 当前状态

更新时间：2026-11-04 18:26 UTC。Goal仍active；用户现在要求交接prompt给另一个agent。

- P0输入/相位语义/泄漏边界审计完成，原MiniSAT代码不可得。5355个最终候选中336个exact或GBD等价曝光被隔离；5019个未曝光候选组。非测试开发300个，180 fit / 60 feedback / 60 gate；未读取新测试solver输出。
- RICL仅第1轮旧成本warm start完成：长度、二元比例两个policy，区间均跨零。第2轮长度+极性及图结构提案已冻结但未评分。没有虚构新reward。
- P1：48例、144次T60新计时已全部验证，D/F+/F−解出11/13/11，PAR2为93.738848/90.409961/94.460735秒。oracle相对固定F+只改善0.218%。35个全删失例保留；不启动原144例T120静态扩展。
- 在线16例：48次T120完整有效，14例到达共同D前缀，D/F+/F−延续解出3/2/2；oracle相对保持D仅改善0.00031094%。本地重查121个文件SHA及原始前缀遥测通过，报告 `ONLINE_LEARNABILITY.md`。
- 主动核时：P1可核对小计2.006979h；在线成功阶段整进程1.387911h；首批证明上限失败0.135061h另计；初始编译缺整进程CPU，保守工程预留2h，不能伪造精确总成本。
- 二进制LRAT独立检查器22项合成门禁通过。当前运行 `long600_fit16`：同一16个fit，D/F+/F−/I−，seed0，T600，共64次。最多2并发、3GiB内存/进程、4GiB证明容量/进程，阶段CPU停止阈值14h，项目总预算100h。2026-11-04 18:26 UTC核实PID6096存活，19/64次完成、逻辑核时2.889331、stopped=false；这不是完整性能结果。
- 当前服务器根目录 `/home/vipuser/forcephase_phase_prediction_20261104`；代码 `src/long_v5`；日志 `logs/long-screen-transition.log`；输出 `phases/long600_fit16/`。SSH移动入口223.109.239.36:13752，vipuser；新复用socket `/private/tmp/forcephase-handoff-20261104c.sock`。密码不落盘。

下一步先读取交接prompt `docs/PHASE_PREDICTION_AGENT_HANDOFF_20261104.md`，核查同一真实进程与日志；完成后导出、验SHA、严格分析，再继续新fit/feedback policy更新、实际部署及条件式gate/确认。不得因连接/观察失败就重复启动任务。当前没有独立确认的新policy；goal未完成。
