# 600秒矩阵资源恢复：执行前冻结

2026-11-04 23:01 UTC 已恢复认证。只读核查：原PID6096不存在，无solver/runner存活，GNU time exit1，progress stopped=true，57/64条，缺completion。错误为D/seed0的一条测量exit=-25（SIGXFSZ），544.713593 CPU秒、证明恰好4GiB。其余56条无错误/争用，成功回答已验证。本次先读取错误、有效性、身份和费用，不对不完整矩阵作性能或policy评分。

原long_v5源码、二进制、原始JSON、失败证明、日志不改写。恢复阶段另命名long600_fit16_recovery_v1，源码long_v6。保持原16 fit、四配置、seed0、T600、二进制LRAT及独立exit20+s VERIFIED政策、2 worker和3GiB进程内存；新执行项统一8GiB证明上限。每条证明未达到原4GiB上限的56条记录按原字节及SHA复用，保留原identity与run_id，禁止伪装成新身份测量。原1错误保留为失败和费用，不作为普通超时训练；另执行此项及7缺项，共8条。精确复用SHA、新执行keys、源identity和失败SHA在recovery_v1_plan.json冻结。

这是明确记录的资源修复，不是选择有利结果的重跑。求解器、输入、seed、动作、T、内存、证明/验证语义不变。分析只允许冻结56条旧identity，且逐条验证SHA、身份差异仅runner与proof cap、未触达旧cap、无错误/争用；拒绝其他身份混用。新8条仍有错误则暂停，不把资源失败计为timeout。原包不满足完成条件，不运行原completed exporter伪造导出；只读取回57条和源身份用于恢复。恢复完成后用原export_receipts导出新阶段，经archive与成员SHA、spec/cohort检查后再严格分析完整64条。

磁盘要求12GiB底线+2×8GiB=28GiB，观察剩余约29.4GiB，执行前再次检查；不删除其他项目文件。新solver最坏1.333333核时，加checker保守0.266667，额外0.5核时工程/框架预留。旧long实际27518.13 CPU秒=7.643925核时，含失败，不另加其记录CPU；此前已核对3.530065399，合计已知11.173990399核时。加2核时旧工程预留、本次2.1核时预留仍低于100核时。恢复后从GNU time资源账本记实际物理费用，复用logical矩阵不能再次记费；合并long600源+恢复物理费用按14核时守卫检查。

主要分析仍T600，120/300仅诊断；完整矩阵前不冻结新模型阈值、不评分round2、不读gate或最终测试。Round2仍需符合既定fit/feedback、2seeds和minleaf12协议，本16fit/seed0筛查不能充当其正式反馈。

用户当前询问为何没收到邮件，已明确请求本次状态邮件；2026-11-04补发至此前确认地址，Gmail返回message id 1a1a8cbb054b1ba0，已读回To及SENT/INBOX。此为本次通知授权，未改为无限期邮件授权。SSH密码仅进入认证TTY，未写入文件。

## 23:15 UTC的正式资源接续v2（执行前冻结）

v1在2/8新项后因RuntimeError: disk reserve reached退出，time18825与runner18826均不存在，progress stopped=true，GNU time exit1。两条新测量均UNKNOWN且无争用，不是新solver错误；保留为有效删失结果。物理CPU1218.74秒=.338538889核时，全研究已知11.512529288核时。源日志和timefile的逐字节SHA已保存。

根因是每个后续job要求free>=12GiB+2×8GiB时，将另一活动proof已消耗的预留再次当作新需求。v2读取活动proof物理分配块并加回预留额度，仅对同一批已保留的cap记一次；12GiB安全底线和完整2×8GiB容量不降低，无关磁盘压力仍拒绝。6项恢复边界测试通过，含旧4GiB来源、新8GiB来源、内容篡改/语义变化拒绝和容量重复计数反例。long_v6不改写，v2源码另放long_v7。

v2精确名单为原56条+v1新2条共58条SHA复用，仅执行剩余6条。两个来源的原identity分别保留，新身份额外绑定恢复helper SHA。metadata/recovery_plan.json冻结来源、记录SHA、6个key、原始失败SHA及v1日志/timefile SHA；v1必须确已因该空间admission终止才能继承，不因连接失败接续。原16fit、四动作、seed0、T600和验证政策不变。源失败、源+v1物理费用随新结果包保留；logical复用费用不二次累计。

剩余solver上界1核时、checker保守.2核时、框架/工程.3核时；与源long+v1实际7.982463889合计低于14核时，全研究连同工程预留远低于100核时。v2完成后仍按原exporter导出新阶段，再SHA导入与完整64矩阵分析，不伪造原两阶段完成。

## 23:27 UTC的资源接续v3（执行前冻结）

v2仍在2/6后因disk reserve reached终止，time21983/runner21984均已不存在；保留新Iminus/D两条有效UNKNOWN。v2父进程1218.09CPU秒=.338358333核时，累计已知研究11.850887621核时。没有把排队失败写成solver timeout，也没有丢弃其中已完成结果。v2未保存当时空间快照，不能把二次退出的具体文件系统原因当作已证实。v1/v2原源码与结果保持不变。

v3精确复用60条（原56、v1两条、v2两条），仅执行4缺项；元数据冻结三个来源的identity、每条SHA、两次调度失败的日志/费用及失败JSON。新源码long_v8与新identity绑定helper。admission容量不足时，释放共享锁，等待在途任务完成/空间释放后重查；没有在途任务时最多等待10秒后才报资源失败，保留详细free/active allocation诊断。底线12GiB、2×8GiB cap、2workers、3GiB内存、原16fit/seed0/T600/四配置和验证政策均不变。新增并发测试验证等待者释放锁，另一worker可完成并通知，不会死锁；共7项恢复边界测试通过。

原long/v1/v2实际物理8.320822222核时，v3 solver最坏.666666667、checker.133333333、框架/工程.3；合计低于14核时，全研究含已知11.850887621及2核时旧工程预留低于100核时。先冻结再执行。完成后才用原exporter和严格64矩阵分析；策略reward、gate和最终测试仍未触及。
