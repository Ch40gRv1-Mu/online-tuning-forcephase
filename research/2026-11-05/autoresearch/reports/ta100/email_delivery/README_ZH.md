# TA100完整规则与结果

先打开 reports/ta100/email_delivery/TA100_COMPLETE_REPORT.html：包含13种不同实际策略的全精度规则、100轮特征定义/来源/覆盖/结果，以及10次workflow修订。

100轮不等于100种不同最终策略：88轮没有采用新增字段，重复得到旧静态规则；共13种不同决策树。排名前10只是13种中的前10，负增量也保留。

all_13_policies.py提供choose_phase(rank,features,eligible=True)，rank为1..13，features须来自原定义的提取器。不会自动采集特征或运行SAT。缺失/非有限的当前分支字段、资源资格不满足时选true。

ALL_100_RULES_AND_RESULTS.json是逐轮定义/结果/模型的汇总，LEADERBOARD.csv是已有100轮排名。outputs/ta100/B01..B10保留全部原始逐轮结果、逐题预测、五折结果、proposal及完成标记；configs/src/refine-logs保留冻结定义、源码、协议和workflow。MANIFEST.json列文件SHA。

指标是TA原false/true计时的PAR2约定（超时10000），不是新增测得wall。数据角色为180fit/60feedback、192合格采集项；所有结果都是探索性，未使用gate或最终测试，未证明部署净加速。服务器CPU和TA wall分列。每轮原始模型不变，本次仅包装既有记录发送邮件。
