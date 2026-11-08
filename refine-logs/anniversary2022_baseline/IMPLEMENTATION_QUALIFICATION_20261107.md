# 实现及小样例节点验证

状态：准备实际执行；本记录不代表已经通过。

用户询问dry run／代码能否跑通后提供当前SSH凭据。本轮按此接入原8CPU节点，实施脚本并做必要的小样例功能验证，不据此启动16065项全量T600，也不重开旧研究／邮件／其他owner队列。

范围固定为四个可检查的合成CNF（一个SAT、矛盾unit UNSAT、PHP(4,3) UNSAT、PHP(24,23)预期超时），D/F+/F−、seed0、每项2 CPU秒；最多12次实际solver运行，整验证进程上限0.05 CPU核时。qualification配置不允许超过8输入、10秒cutoff、0.25 CPU核时。结果单独保存为QUALIFICATION，不能补入正式600秒成本矩阵。

验证同一实际命令路径：localhost HTTP输入获取及SHA、CaDiCaL实际求解、SAT model／二进制LRAT检查、SIGTERM超时后的conflicts统计、单owner拒绝、完成后resume不新增physical run、完整三元组／删失汇总、导出逐文件SHA。旧二进制SHA匹配已接受记录，复用solver/checker，不编译或审计整套solver。

节点只使用标准Python库、现有`prlimit`／`taskset`和已绑定的solver/checker。Matplotlib未安装于节点，图在本地内置Python运行；结果snapshot不依赖本地访问远程CNF。验证完成后分别保存实际结果、进程CPU、图和剩余限制。

节点最新观察：8CPU、约14.5GiB可用RAM，磁盘约27GiB空闲。不能直接安排8份各8GiB证明；正式并发必须按实际证明上限和磁盘重新冻结。新runner支持磁盘admission和仅清理本run root下已完成且有效的输入缓存，不动其他项目。

实施顺序：源码和本文先commit → 上传必要源码／公开名单 → 实际节点CLI验证 → 本地绘图 → 记录PASS/FAIL及尚未证明的范围。没有独立audit阶段，也没有全量数据筛选。
