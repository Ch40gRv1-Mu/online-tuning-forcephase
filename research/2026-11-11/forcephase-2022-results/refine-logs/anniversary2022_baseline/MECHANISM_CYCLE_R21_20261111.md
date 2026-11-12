# R21 变量连接支持谱与极性：分辨饱和二核内部

依据完整R20：1767/1890题有>=99%变量位于普通二核；mixed179题覆盖全人口oracle仅0.422个百分点，按旧0.5停止，无模型reward。新问题不是降低其门槛，而是普通二核太粗时，更高连接支持是否提供选择信息。当前chat owner，无delegation，用户要求纯静态预测，goal未完成。

## 输入与分解

仍只用2022 retained4719及原seed0 T600三动作矩阵，D3385解，PAR2均值392.542654，1172三删失，2279可靠clear父标签，全免费oracle10.8528%。教授附件/family/known答案/终局统计不作输入。新资源资格由CNF观察最大变量<=100000、literal occurrences<=200000确定，纯输入计数；2325父题均有既有SHA验证原字节，不按缓存成员或赢家选题。这部分540三删失、全人口oracle4.8249个百分点；其余2394仍由基本42统计+新资源bit预测，全部4719评价，不增加SAT或下载任务。

规范化重复literal/tautology，保留原clause多重集；不执行赋值、UP、SAT假设或试解。定义变量剩余所连clause数阈值k，clause剩余变量数至少2。按变量最小度heap移除，clause少于2变量后删除，其余变量degree更新；level为迄今弹出的最大min-degree，对每变量/关闭clause记录level，得到完整(k,2)支持谱。二元例上路径全1、环全2、K4全3、单位子句不构成图边。源内正式检查这些定义，不声称新发明的算法，也不声称等价于CaDiCaL预处理或搜索行为。R20/I025普通二核、R06度尾是相关先前机制；本轮新增高阈值连接支持及其与极性位置的耦合。

20维拓扑：最大/平均支持level、异质性、level0/1/2比例、core/初始degree、clause关闭level统计、最高level质量、边加权level，以及两侧四分位角色质量。角色按每个公式level的25/50/75百分位划分，相同level不按ID拆开。48维极性聚合沿用R20明确字段。topology63为base43+20；primary signed111附真角色48量；random111在变量**精确occurrence-degree**及clause精确width档内固定seed20261121置换角色，保留每档角色数和全部变量/子句极性边际，模型同容量。绝对变量编号不是输入，null也不改原公式运行标签。

## 停止、评分和晋级

在读取新角色结果前固定信息屏障：max变量支持level>=3才称超出普通二核分辨率的informative。若这样的父题<50或它们合计全人口oracle<0.5个百分点，则停止，不训练/改定义/扩sample。若通过，仍在**所有4719**上训练/评分，不只取informative父题，也不将oracle或屏障成员身份作为特征；这些只是一次设计可行性判断。

评分完全复用R20预定程序：coarse4/fine5+原inner，iso隔离，256树深12叶4、seed20261111+fold，相对PAR2预测、inner原quantile family选margin，无特征/推理费的乐观情景。27外层，保存连续validation/held分数。primary须在原两个留出改善>=2%、对D区间下界>0，且对纯拓扑与同容量随机角色增量及区间方向支持，才导出预定3全开发模型并进入实测费用/部署。未通过停止该代理，不扫level分界/模型/seed。反复开发、名义区间不构成独立确认，不能宣称goal达成。

源/协议先commit再运行，4特征线程/4模型批量线程，collect15分钟、score15分钟硬界，预算2CPU核时，首完整评分含准备目标30分钟内；8GiB本机稀疏图O(L)、heap更新O(L log n)，无同时solver计时。collector core_spectrum_features.py，score_core_spectrum.py（R20同评分派生，字段名对应实际维数），输出mechanism_R21_features_20261111/mechanism_R21_20261111。所有失败、准备未知和新物理费用保留；不做逐题热query计时/部署的前置工程，不另开audit/dryrun。
