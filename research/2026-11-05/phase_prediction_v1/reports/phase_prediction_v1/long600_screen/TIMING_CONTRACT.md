# 计时解释补充

原固定binary的帮助确认-t是墙钟时限。既有T600矩阵为native wall600、CPU后备602、外部wall610，结果按实际CPU计PAR2并要求verified CPU<=600，同时排除争用。12/16全删失是该实际双时限/证明模式下的事实，不意味着每条都实际消耗整600 CPU秒，也不能给纯CPU截止算法作普遍oracle上界。原始记录、已算PAR2/区间与冻结成功标准不变。

正式policy部署另使用已实际资格的CPU-budget-exec，native wall仍600，小数剩余CPU=600-h由进程timer执行；所有实耗含tick过量记账，成功仍要求h+t<=600。该修复不构成任何新模型收益。
