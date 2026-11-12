# 旧policy在4719题T600数据上的迁移回放

日期：2026-11-10。范围：`official_all_tracks_unsolved_v1`筛选后的4719题，非完整5355题；全部为已曝光开发数据。本轮不拟合、不改阈值、不重跑求解器。

## 结果：可评分的旧内容规则都没有胜过D

| 原冻结规则 | 平均PAR2/秒 | 相比D成本变化 | 解出题数 |
|---|---:|---:|---:|
| 固定D | 392.543 | 0 | 3385 |
| 平均子句长≤3.67724选D，否则F− | 404.459 | +3.04% | 3336 |
| 二元比例≤0.362327选F+，否则D | 433.949 | +10.55% | 3211 |
| 长度≥5子句比例≤0.00977806038068选F+，否则D（原保留失败候选） | 444.189 | +13.16% | 3170 |
| 长度≥5子句比例≤0.024555309337选F+，否则D | 446.929 | +13.85% | 3158 |
| 固定F+（两项原提案退化为此） | 468.237 | +19.28% | 3076 |
| 固定F− | 471.976 | +20.24% | 3055 |
| 三配置VBS（事后上界） | 349.941 | −10.85% | 3547 |

每行均覆盖全部4719题。原8个提案中7个已评分，重复树保留原ID；共有4条不同的非恒定内容规则和固定F+。图规则1项尚未评分，见下。

以上将结构特征视为免费，只评估所选配置的已有T600成本，是乐观回放，不是测得零费用，也不是实际部署。正的提取开销不能挽救这些已比D差的免费回放。但仍不能把单seed开发转移结果称独立确认。

逐题结果显示，规则并非从无命中过好选择：长度规则有297题优于D、347题劣于D；二元规则600题获益、808题受损；原保留失败候选863题获益、1220题受损。它们识别了一些机会，同时误切代价更大。当前证据不支持原样使用这些规则。

## 特征来自公开缓存，未补造缺失量

GBD的[公开base数据库](https://benchmark-database.de/getdatabase/base)覆盖全部4719个exact GBD key。2026-11-10下载21,602,304字节，用时19.416秒，快照SHA256 `15a3d19fd23ba72dd7c77b1b86113873f160760fa1c9710e9e5ed6a23ba29d84`。

- `s_mean_length = vcg_cdegree_mean`，原始每子句文字数均值。
- `s_binary_fraction = cls2/clauses`。
- `s_long_fraction = (cls5+cls6+cls7+cls8+cls9+cls10p)/clauses`。

字段定义见[GBDC文档](https://udopia.github.io/gbdc/doc/extractors/CNFBaseFeatures.html)，与GBDC源码commit `9f3a418c47bc4ecef9f940a39db2752a456632b7`的原始子句解析、计数实现对照。旧138题可比的长度/二元比例共276个数值逐项一致。当前GBD快照未绑定该源码版本，交集一致也不是逐题重新核验原始公式的证明；因此定位为公开缓存支持的迁移回放。新集群输入SHA/原日志/证明未重验。

只读取原始子句计数和长度字段，不用family、文件名、路径、年份、答案或终局求解统计作预测输入。hash只用关联。

## 尚未执行及不适用项

`formal_round3_0`需要去重变量—子句关联边上的cycle excess；GBD给出的是原始文字计数，不能当作distinct incidences。该规则未评分，没有把缺测当作树的missing分支。按未知题可选D/F+动作算出的全量平均PAR2范围为368.111–492.668秒，仅为界，不能判断其真正收益。

TA旧MiniSAT true/false树没有验证过的本次CaDiCaL动作语义映射；前缀续跑/条件子题策略没有兼容的动作前特征和延续矩阵；family规则被禁止。它们均未混入本次评分。H01/H02等最终恒定D与固定控制重合。没有I−列，不能声称在这批数据上与I−比较。

费用：本次回放本地进程CPU0.528秒、执行wall0.565秒；下载wall19.416秒另计。编程、资料查看和全部准备CPU未完整量化，不计为零。新增SAT调用0，未重复消费旧runtime核时。

## 产物与下一步

- [HTML表](../../outputs/anniversary2022_baseline/frozen_policy_replay_20261110/report.html)
- [逐题动作与得失](../../outputs/anniversary2022_baseline/frozen_policy_replay_20261110/predictions.csv)
- [汇总与来源](../../outputs/anniversary2022_baseline/frozen_policy_replay_20261110/summary.json)
- [实际使用的结构特征](../../outputs/anniversary2022_baseline/frozen_policy_replay_20261110/features.csv)
- [按conflicts累计解题图](../../outputs/anniversary2022_baseline/raw_data_20261110/cumulative_conflicts.png)

本轮已完成可评分候选回放，原阈值与policy不改。若后续继续研究，应针对误切反例检验新的或更精细的结构解释；复用现有完整成本矩阵，先冻结有限比较。图规则需补精确distinct-incidence特征才有实际分数。当前没有新policy成功或部署收益声明。
