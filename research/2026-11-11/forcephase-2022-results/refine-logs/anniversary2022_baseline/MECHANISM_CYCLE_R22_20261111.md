# R22 完整literal–clause/complement图的带符号邻域模式

R21完整反馈：core×极性免费主候选coarse+0.1152%、fine−1.4842%，未胜匹配随机；停止core/role微调。R11–R21主要删失问题不是数量不足，而是聚合量和原结构迁移失准。新问题是此前pooling丢失的高阶有符号连接模式是否增加选择信息。当前chat owner、不delegation，用户只要求解前静态预测，无SAT短搜索。

完整4719 retained2022重复开发，seed0 T600原矩阵全部复用；D3385解、2279可靠clear父标签、1172三删失，全oracle10.8528%。与R21相同纯输入资格nmax<=100000、L<=200000，2325 SHA绑定缓存原题、540三删失、oracle4.8249个百分点。其余2394仍用基本统计预测，全部4719评分，不按赢家/缓存可用性增删题，无下载或solver任务。输入禁family/元数据身份/known答案/终局统计；结构signature的64bit散列只由公式邻域生成，不是instanceID/hash。

## 表示与对照

规范化duplit/taut后，对每变量保留positive/negative两个literal节点，clause节点连接所含literal，正负literal之间单独complement关系。四轮固定同步颜色更新：初始literal按符号及对数occurrence-degree桶、clause按截断width/正literal数编码；后续用旧自身、两个邻居混合和及literal的complement旧色更新。各轮对所有节点固定128bin散列计数，平方根归一化，四轮512维。不学习消息权重、不离散赋值、不传播逻辑、不调用SAT，不把迭代次数当搜索前缀。它是明确复用颜色邻域/图核类思想的近似表示，不是新发明的WL算法，不保证无碰撞或完整图同构区分。旧GCN仅采样邻域、R09只枚举符号重叠；本轮使用完整资格公式、包含complement语义及更高阶模式，非重复重命名那个实验。

三个同维555视角（附base42+相同资源bit）：primary signed555；unsigned555合并literal正负初始颜色并不使用clause正literal数，保留无方向连接模式；rewired555仅在精确(clause width, clause正literal数,literal符号)档内固定seed20261122重连literal端点，精确保每literal在各clause类型的出现次数、每clause正负数及变量Horn/度边际，破坏高阶关联。null可为多重图，重复边保留，不能把它当真实重连CNF或复用新formula运行标签；没有任何标签增广。三view模型容量相同，原GBD42都取真实原题。

预设信息门槛：signed与rewired512向量L2差>1e−6的父题至少50，且这些父题全人口oracle>=0.5个百分点，否则停止不训练或换bins/轮数。差异mask仅做设计可行性，不入模或挑训练分母。

## 评分与成本

完全沿R20免费screen：原coarse4/fine5及inner/iso隔离，27个256树深12叶4相对成本模型，seed20261111+fold，inner原quantile margin候选；原所有4719评分。仅批量CPU推理，费用免费是乐观预测情景，采集物理CPU仍入账。连续validation/held结果保留。primary在两原留出均改善>=2%、区间下界>0，且相对unsigned/null两对照配对增量及区间方向支持，才导出预定3全开发模型并进入实际费用/部署。否则停止该表示，不调bin数/round/种子；不能挑最好view冒称原主假说成功。名义区间未作所有开发选择校正，整个2022非独立测试，goal仍须真实验证。

先提交实现/协议再执行，4特征线程、4模型/批量推理线程，本机8GiB、555维矩阵约60MiB，规范化边<=200k。collect15分钟、score20分钟硬限，2CPU核时，首完整评分含准备目标30分钟内。正式提取内检查变量重编号/clause重排不变性、unsigned补极性不变及signed方向保留；原字节SHA及null守恒属于执行检查，不开独立audit/dryrun。collector literal_color_features.py、scorer score_literal_colors.py，输出mechanism_R22_features_20261111/mechanism_R22_20261111；失败费用保留，健康运行不重提。
