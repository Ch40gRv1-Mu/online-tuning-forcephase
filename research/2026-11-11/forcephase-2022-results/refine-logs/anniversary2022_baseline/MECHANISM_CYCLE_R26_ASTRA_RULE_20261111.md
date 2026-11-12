# R26 Astra小clause/低inverseHorn的F+规则模板

用户明确要求Astra理解完整42维模型并提炼人类规则，/root/astra_linear42_rules已在约5分29秒内完整交付，未SAT。7条规则不能忠实压缩teacher；最纯F规则inner零覆盖、depth5追加规则inner0/5。唯一优先模板Tplus_small_inverseHorn来自R5：clause数较少、inverseHorn比例低、legacy balancecls_entropy上界；train45/64、inner13/22同teacher F+，仅描述性。报告完整负例保留，不能把teacher一致等同求解收益。

本轮检验这个模板可否成为实际经验规则。先锁Astra完整summary/rules SHA、协议和执行源码，再按原训练折**重拟合阈值**，不把全开发阈值1119/.253/.855带入新fold。所有2022均多轮开发，本轮是有界开发评价、不是独立最终测试。原联合完成状态分类提案从未冻结/执行，仍UNSCORED_DEFERRED，不伪造reward；R26标记本次实际Astra规则测试。

## 固定规则与拟合

两候选：主三条件[log1p(m),inverseHorn fraction,legacy balancecls entropy]各<=阈值时F+，否则D；匹配简化对照只前两项。方向与动作固定，不尝试F−或扫描其它字段。legacy熵实现quirk沿用，不伪称真实Shannon多样性；n,m/符号比例仅结构输入，不使用family/身份/known答案/终局输入。

阈值候选仅每个outer train的0/.05/.1/.2/.3/.4/.5/.6/.7/.8/.9/.95/1分位，重复去掉。训练支持>=32，目标最大Σ(PAR2_D−PAR2_F+)且正；平局依次少有效条件、较大支持、较小阈值索引。用稀疏分箱前缀和精确枚举这个有限网格。inner只作开/关：触发>=8且累计净收益>0才启用，否则整foldD，不重新选阈值。报告无inner开关原始选择作为预设诊断，不择其更好者宣称主成功。

原retained4719全人口、原T600 seed0三配置矩阵，D3385解、2279可靠clear、1172三删失、免费VBS空间10.8528%，D/F+oracle6.2239%，不按赢家/难题删人口。原随机混合iso5、coarse4、fine5与inner/等价隔离均不变，共28个rule fit，所有4719均有held预测。参考R12同scope teacher原折外动作仅报fidelity，不用于训练/门槛或选择；实际PAR2是主指标。解释teacher统计与真实gain分开。

主/简化各自保留全部scope、覆盖、救回/丢解、名义区间。原跨结构研发screen仍两个coarse/fine均>=2%且下界>0才推进部署，随机混合的正点可报告条件性证据，不能用它替代跨结构或独立确认。未过则停止本模板，不调quantiles/支持/字段或手挑fold。特征/query暂免费是乐观预测screen，费用未付不冒称可部署。

当前chat单一owner，Astra解释完成无其他worker，本轮不委派。源score_astra_small_fplus.py，输出mechanism_R26_astra_rule_20261111。5min硬限、0.25CPU核时，已有特征/标签复用不重算物理成本，无新CNF/solver/短搜索。目标含准备15min内首正式结果。失败/CPU记录，原材料不覆盖，goalactive。
