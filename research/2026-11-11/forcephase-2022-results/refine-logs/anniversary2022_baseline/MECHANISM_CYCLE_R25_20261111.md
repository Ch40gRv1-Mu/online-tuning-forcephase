# R25 方向条件化的临界clause依赖及需求位置

完整R24免费主候选粗−1.0504%、细−1.5164%，长程Gram未过screen，不再调谱尺度。新的遗漏是方向性：Gram不能直接表达“改变哪个变量会让clause失去唯一满足literal”。当前chat owner，不delegation，纯静态预测，无SAT短搜索，goal未完成。

去重：旧signed_boundary.hpp只计均匀参考方向下的opposed/one-satisfied质量和repair concentration；旧root signed_walk在根UP后全clause做三步无回退流；R16/BP是对称因子更新的总体pool。R25复用这些相关概念，但新的是按参考方向构造有向critical网络，条件于该方向纯符号clause的需求位置，并测全局SCC/可达与稳态反馈。不是新发明PageRank，不把这些分流路径当实际逻辑传播或已确定的D行为。

固定retained4719 2022重复开发及原seed0 T600矩阵，D3385解、PAR2均值392.542654、clear2279、三删失1172，全oracle10.8528%。沿用nmax<=100k/L<=200k的2325纯计数资格，540三删失、覆盖oracle4.8249个百分点，所有原字节既有SHA；其余2394以base42+同资源bit预测，全部4719评价。不用family/身份/已知答案/终局统计，不新求解或按赢家补样。

## 静态定义与控制

规范化duplit/taut后，分别以全真/全假为**计数参考**，不实际试跑赋值。参考方向下0个满足literal的clause贡献1/width需求到各变量；有唯一满足literal且width>=2时，由这个literal变量指向其余变量，每target权1/(width−1)。这表达失去唯一满足literal后有多个可能repair，并不强制全部target。每source按critical clause数归一化成P（有出边row sum1，无出边row0），单位critical clause仅作blocked结构标记，不作SAT/UNSAT答案。

分数质量q固定满足q=0.05*r+0.95*P^Tq；从r开始迭代，L1步差<=1e−9、最大512，显式残差<=2e−9，不收敛/超限是工程失败，不能当普通solver timeout训练。每formula10CPU/30wall秒。迭代数、残差、计时仅receipt，不入模型。计算SCC、凝聚sink/source及从需求位置的图可达，不是logical closure或分支搜索。

每方向8局部量为opposed/critical/blocked比例、需求支持比例、需求加权fanout、需求熵、平均fanout、直接blocked需求。16全局量为q总量/集中/熵、q-r对齐、需求支持/blocked/无出边/多clause/fanout质量、cycle/SCC-size质量、需求可达比例/blocked比例/最大SCC、sink/source质量。两方向24+24+差24=72维，附base43为primary actual115。local67只取两方向及差的8局部量，新增全局增量需胜它；uniform115保同原图和局部量、仅全局流/可达从均匀source开始；rewired115按R22精确(width,npos,sign)档重连，保全部literal/类型计数、局部8量及需求r（正式执行检查），破坏其与有向网络连接。null可为多重图，不是新CNF运行或数据增广，三个115同容量。

信息门槛固定为actual72与rewired72差L2>1e−6的父题>=50且其全人口oracle>=0.5个百分点，不满足停止、不换定义或扩大选题。mask只作设计可行性，全部4719仍训练/评分。正式小图检查有向链、fractional质量、补极性交换方向及重编号；不另开audit/dryrun。

## 评分与预算

原coarse4/fine5、inner与iso隔离，四view36个256树深12叶4相对PAR2模型，seed20261111+fold，inner旧quantile margin family；免费feature/query为乐观预测情景，实际提取CPU仍记账。连续val/held保存。primary两原留出均>=2%、对D名义区间下界>0，且对local/uniform/rewired三控制配对增量和区间方向支持才导出预定四全开发模型并进入真实费用/部署；否则停止此代理，不扫damping/round/source或挑bestview宣称成功。所有2022已开发，区间未校正全部迭代，正点仍非独立确认或目标完成。

协议/源先commit再正式执行，4特征线程（BLAS1）/4模型批量线程，8GiB稀疏结构不展开clique。collect15min、score15min硬限、2CPU核时，首评分含准备目标30min内。critical_repair_features.py / score_critical_repair.py，输出mechanism_R25_features_20261111/mechanism_R25_20261111。失败/费用保留、健康任务不重复，原matrix/feature仅逻辑复用，准备未知不填0，无server队列或邮件。

执行修复v2（新公式结果读取前）：64ef3e6版在内置链/补极性语义检查中发现无root方向的np.bincount空权重返回int，原地归一化抛dtype错误，0正式父题提取，原failure.json/费用保留，不填预测reward。只加显式float转换，数学定义/名单/阈值/控制/模型不变。源码修复提交后以新输出mechanism_R25_features_v2_20261111执行；不覆盖旧身份。成功后scorer绑定新features路径，原score输出尚未运行可继续沿用。无健康worker重启。

完整评分后开发诊断（不改结果/候选/阈值）：按救回、丢解、双方解出、双方删失分解实际成本差额，并保存每原留出最多12大损失/12大收益的原静态结构量。身份仅关联counterexample，不入模型或新增路由；不从其他fold预测训练meta。诊断代码也先提交再执行，CPU单列，帮助下一假说定位损失来源，不能把反例分析算作新的预测reward。
