# R12 linear42/min3正信号的候选固化与已测费用

当前chat owner，不delegation。用户连续追问后明确保留2.097677%的正证据：全部4719公式、随机混合五折、等价组隔离、每题一个OOF预测，D3385→3419解；原coarse/fine +0.3709%/−0.2608%同时保留。原R12导出的模型是legacy52，不能代替这个42维候选。当前本阶段补可执行候选和费用范围，不改原评价门槛、不称整体goal完成或独立最终确认。原计划联合完成分类尚未冻结或执行，作为UNSCORED_DEFERRED保留，不编reward。

固定沿用R12 linear42变换、三训练seed20261111/12/13、每模型256树max_depth12/min_leaf4/max_features0.8、每方向min3、训练内原quantile margin family及相同inner_validation。只新拟合3个开发模型：以全部非inner公式训练，inner只标margin；**不在全4719上重新评分这个全开发模型**，不能把训练内预测冒称新2.1%验证。模型规模记录实际树/节点/叶数；可比较的预测标量定义为internal thresholds+2*leaf outputs，另列feature整数选择，不能冒称等同神经权重数。计费包含重训/序列化/分析，不重算旧14157solver物理CPU。

CNF接口使用已冻结并在2843原题核过42维float32兼容的native extractor，绑定二进制和变换SHA。native自身8CPU秒/12wall秒、max变量5M，外层timeout14秒，提取失败选择D且成本仍须付；不运行任何SAT。对按key固定排序的前8个既已验证公开2022文件作本阶段实际输入路径测量，核native向量与冻结GBD同输入及序列化模型动作一致，选择不看胜负。只是必要的输入/费用实现检查，非独立audit/dryrun、非性能确认；模型加载/冷启动另列，不假装免费。Mac二进制也不声称已部署Linux server。

费用重算**只复用原R12 OOF动作和原query/aggregation费**；加入R14-v3测得2843的feature_CPU_s，另外1876未知暂为0的乐观界，不能说完整费用已测。若某折原margin=None则逻辑全D短路，不收该折feature费。三个原划分完整4719均重算，按相同T600的h+t<=T，否则1200，保留原与新PAR2/名义区间。既有Mac特征CPU与cluster solverCPU相加只是探索性定价，非同机端到端测量。对未知费用固定0/.1/.5/1/2/5/8CPU秒作敏感性表，是假设成功提取成本，不代表实际观察，也不模拟未测资源失败。不得重调门槛/改动作以挑最好回放。

先提交本协议与两个源再执行，materialize_linear42_candidate.py、linear42_candidate.py，输出linear42_candidate_20261111。单一owner/输出身份、3fit，无新outer fit/新solver/新标签/短搜索。4训练线程、输入测量串行BLAS1以隔离资源，本机8GiB。预算15分钟/1CPU核时，目标含准备30分钟内交付完整模型+policy.json+费用表+actual node数+输入receipt。失败保留独立身份。正结果适用范围与原结构迁移失败分开报告，后续仍需真实费用覆盖和独立确认，goalactive。
