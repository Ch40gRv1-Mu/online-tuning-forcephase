# Online Tuning of Forcephase

**2026-11-07 更新：** [2022 Anniversary 基线脚本](ANNIVERSARY_BASELINE.md)已实现并通过节点小样例验证。按用户最新选择，5355题主名单中排除官方所有赛道均未解出的636题，保留4719题；正式运行尚未启动，资源／恢复配置仍待完成。

**2026-11-05 更新：** 本周已完成的现代 CaDiCaL 实验、TA100 特征探索、全部候选汇总、费用和下一阶段 goal 草案见 [本周研究快照](research/2026-11-05/README.md)。尚未建立稳定优于强固定对照的选择策略；以下“已确认的起点”保留2026-10-18初始规划的历史语境。

Research question: **When should a CDCL SAT solver use its native phase policy, and when should it force negative decision literals? Which observations available during solving predict that choice?**

本仓库用于科研项目 **Online Tuning Forcephase H:1**。目标是得到可复现、有解释力的实证结论，以及在证据支持时得到低开销在线策略。性能提升是待检验假说，不是预设结论。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [研究计划](docs/RESEARCH_PLAN.md) | 科学问题、假说、研究范围、里程碑与验收 |
| [相关工作调查](docs/RELATED_WORK.md) | 第一手论文与官方资料、已有结论的适用范围、创新性边界 |
| [CaDiCaL 源码审计](docs/SOURCE_AUDIT.md) | 固定版本、参数语义、调用路径、在线修改的实现约束 |
| [实验协议](docs/EXPERIMENT_PROTOCOL.md) | 基线、数据划分、观测量、标签、统计、算力预算 |
| [Agent Goal](docs/AGENT_GOAL.md) | 可直接交给执行 agent 的完整任务与交付标准 |

## 已确认的起点

- 调研日期：2026-10-18。初始仓库为空；本次提交只建立研究文档，**尚未实现策略或运行性能实验**。
- 源码基线：上游 [arminbiere/cadical](https://github.com/arminbiere/cadical)，固定提交 [`c60730422e758ef1cebe7aeddf2dda31c996bf04`](https://github.com/arminbiere/cadical/tree/c60730422e758ef1cebe7aeddf2dda31c996bf04)，该快照 `VERSION` 为 `3.0.1`。不把浮动 `master` 当实验标识。
- `--forcephase=1` 强制**初始极性**；负分支基线必须显式设置 `--forcephase=1 --phase=0`。默认 `phase=1`，所以仅写 `--forcephase` 会得到正分支。
- CaDiCaL 默认策略包含 saved / target phases 和 rephasing，不能直接称为“纯 phase saving”。强制负决策也不会禁止单位传播产生正赋值。
- 在线 phase/rephasing 选择已有研究。本项目优先贡献是解释、观测量验证、严格的在线评估和低成本实现。

## 执行方式

将 [docs/AGENT_GOAL.md](docs/AGENT_GOAL.md) 的全文设为 agent goal，并要求同时阅读其链接的全部研究文档。先通过 M0–M2 的语义、正确性、静态基线检查，再推进在线策略；阶段性提交代码、配置和结果索引。默认单进程单线程 CPU 求解，不要求 GPU、付费资源或大型神经模型。

研究期间应区分三类表述：**源码或文献已证实**、**本项目实验已观察**、**尚待检验的假说**。可靠的负结果同样是有效科研产出。
