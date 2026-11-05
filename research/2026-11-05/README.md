# Force-phase 本周更新（2026-11-02 至 2026-11-05）

**尚未建立能稳定优于强固定对照的相位选择规则。** 下面区分两条已完成研究，不能把 TA 的 false/true 标签当作现代 CaDiCaL 的 D/F+/F− 标签。

| 研究 | 本周交付 | 结果与边界 |
|---|---|---|
| 现代 CaDiCaL | 原16题 T600、40题 T60 四配置双 seed 完整矩阵；实际反馈迭代；三类新结构；8次部署 | T60 共320项有效；新规则未可靠超过 D/I−。8/8部署动作和计费一致，仅证明实现一致性 |
| TA100 | 100项探索、10次工作流修订、13种实际不同规则及全部负结果 | 12项新增字段被采用，仅1项开发点估计正向：+0.1601%，95%区间跨零；没有可信新增收益 |

## 阅读入口

- [现代研究完整报告](phase_prediction_v1/reports/phase_prediction_v1/FINAL_REPORT.md)、[逐项证据](phase_prediction_v1/reports/phase_prediction_v1/FINAL_EVIDENCE.json)。
- [TA100报告](autoresearch/reports/ta100/REPORT.md)、[100项特征目录](autoresearch/reports/ta100/FEATURE_CATALOGUE.md)、[全排名](autoresearch/reports/ta100/LEADERBOARD.csv)。
- [全部100项规则与结果](autoresearch/reports/ta100/email_delivery/ALL_100_RULES_AND_RESULTS.json)、[13种不同可执行策略](autoresearch/reports/ta100/email_delivery/all_13_policies.py)、[HTML](autoresearch/reports/ta100/email_delivery/TA100_COMPLETE_REPORT.html)。
- [现代物理费用](phase_prediction_v1/results/phase_prediction_v1/cost_ledger_provisional.json)、[TA100费用](autoresearch/reports/ta100/RESOURCE_COSTS.md)。这些账本有继承费用，不能把各报告总数直接相加。
- [下一阶段 goal 草案](NEXT_GOAL_DRAFT.md)。这是待讨论的研究设计，本次发布没有启动新实验。

## 两个关键瓶颈

1. **可判别样本少、选择空间小。** 现代 T60 开发40题中，25题四配置全部删失；16题反馈上，免费逐题挑选 D/F+/F− 也未胜过 I−。TA100 的60题反馈只有24个明确标签，现有浅树到免费 oracle 的剩余空间仅0.8823%。这些都是相应面板的诊断，不是一般不可能性证明。
2. **已有信号不稳定。** 蕴含图、奇偶模板、chronological backtracking 等有正向点估计，但覆盖、误选成本或不确定区间不支持可靠推广。

## 复现与发布范围

两个子目录保留各自源码、冻结协议、失败候选、数值特征、汇总结果和费用。现代求解器固定 CaDiCaL 3.0.1 commit `c60730422e758ef1cebe7aeddf2dda31c996bf04`；D/F+/F− 是动作，I− 只作静态对照。

这是独立分支上的源码／结果快照，原研究工作区和 Git 历史不改动。来源 commit、交付包 SHA 与逐文件 SHA 见 [PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json)。现代快照保留原交付包的时点状态，随后 goal/automation 关闭收据另附；它们不代表活动任务。

未发布原始教授附件、逐题 TA 计时表／逐题开发或 gate 预测、密码、SSH known_hosts、大 CNF/LRAT 或最终测试输出。部分原报告链接指向保留在本地的原始证据，发布导出不会伪造缺失文件或修改旧 SHA。源码复算 TA 指标仍需获授权的原始表；这里的聚合结果可直接阅读，数值特征缓存不含 TA 计时标签。

共享 gate 已消费，2022 Anniversary 全部5355候选继续保护，不能把它们用作新开发数据。I− 不被悄悄加入可学习动作。下一阶段需要新协议和明确的数据角色。
