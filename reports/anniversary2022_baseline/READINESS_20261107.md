# 全量基线脚本：实际小样例已跑通

日期：2026-11-07（America/New_York）。状态：**IMPLEMENTED_FUNCTIONALLY_QUALIFIED；全量T600未启动**。

**后续用户选择：**现在按官方三赛道全部未解规则排除636题，保留4719题、14157项计划运行；完整5355主名单保留。筛选仅使用公开比赛成绩；缺失／不确定情况保留。见[筛选结果](../../outputs/anniversary2022_baseline/external_filter_summary.json)与[筛选协议](../../refine-logs/anniversary2022_baseline/EXTERNAL_DIFFICULTY_FILTER_20261107.md)。下面的5355全量描述是此前目标，不再是当前实际入选人口。

此后源码只增加外部cohort准入检查，八项本地实现检查及4719名单的实际receipt准入通过；没有重新运行求解器。原Linux小样例证据继续绑定下述原runtime，不能冒称新版本在4719题上已运行。

七个脚本及共享模块位于`src/anniversary2022_baseline/`。5355条公开输入已生成完整新角色名单，对应16065个计划任务；没有筛除旧比赛未解题或大文件。全部2022候选现在用于baseline/development，新独立测试仍待另外选定。

## 已执行证据

原8CPU节点上的真实CLI先后执行两个版本，每版4个合成CNF×3动作×seed0，每项2 CPU秒，共12次实际CaDiCaL调用。第二版复核了累计ETA修复及CPU工作槽绑定；第一版收据不覆盖。

|检查|第二版结果|
|---|---|
|真实SAT与本次model检查|3/3通过|
|真实UNSAT与本次二进制LRAT检查|6/6通过|
|CPU限时、SIGTERM退出、冲突统计|3/3按预算超时；全部12条conflicts非缺失|
|HTTP输入获取、实际plain SHA|4个输入全部通过|
|并发第二owner|被拒绝，未重复提交|
|完成后resume|0个新增physical run，原12条结果SHA不变|
|汇总|4个完整父题三元组，3题解出并集、1题全超时|
|导出|独立核对归档内所有成员SHA通过|
|绘图|4幅PNG、4幅PDF、自包含HTML生成，并检查累计曲线延伸到截止点；散点倍率线使用真实值|

这是功能证据，**不是5355题的性能结果或600秒长轨迹证明**。合成样例的相位差异没有研究解释价值。

执行代码：`101da1d90b28fb55d684276ef87e50b26e59b9ab`中的runtime；measurement source fingerprint：`170a9d2c128822ba7b560fa6aab2de6fa6a0dc3efc8fb1eaf0e506fb10a9aee4`。随后只更新绘图／测试／文档，不改变这份实际求解runtime。plotter SHA及依赖版本另见绘图收据和lock文件。

- [第二版原始通过记录](../../outputs/anniversary2022_baseline/qualification_v2/QUALIFICATION.json)
- [第二版原始收据归档](../../outputs/anniversary2022_baseline/qualification_v2/qualification_receipts.tar.gz)，SHA `9e38d83c752745829524f259a08a237e0654c53e1bf7ec6e5202a55d60dd296a`
- [HTML小样例报告](../../outputs/anniversary2022_baseline/qualification_v2/analysis/baseline.html)
- [实际计量](../../outputs/anniversary2022_baseline/qualification_v2/qualification_v2.resources.txt)

第一版归档SHA为`bac8044469a79bc4f7d97ad96962c99b5ba971618efb8a28fa7cde9d0b6308a0`，同样保留在`outputs/anniversary2022_baseline/qualification_v1/`。两版GNU time整进程树分别7.04 CPU秒，合计14.08秒（约0.003911核时）；不能再叠加内部solver/checker账目。第二版执行墙钟3.39秒。编程、传输、本地依赖安装和绘图未完整计量，不记为零。

另外，本地六项实现检查通过：缺统计与零值区分、DRAFT启动拒绝、错误model拒绝、plain/gzip/xz提取及缓存SHA、错误源SHA拒绝、partial不能按complete导出。没有新增正式SAT测量来补这些检查。

## 运行方式与依赖

节点求解／调度／汇总／归档使用Python 3.10标准库和已有`prlimit`、`taskset`、CaDiCaL及lrat-trim。现有二进制SHA与已验证版本匹配。

同路径的功能检查命令如下；`--root`必须是尚不存在的新目录，不能覆盖旧结果：

```bash
python3 -m src.anniversary2022_baseline.qualification \
  --root NEW_QUALIFICATION_DIRECTORY \
  --solver EXISTING_CADICAL_PATH \
  --checker EXISTING_LRAT_TRIM_PATH
python3 -m unittest src.anniversary2022_baseline.test_contracts -v
```

节点未安装Matplotlib；绘图在本地独立venv完成，`configs/anniversary2022_baseline/plot_requirements.lock.txt`记录实装版本。这不是要求给求解节点安装整套Python科学计算环境。

```bash
PLOT_PYTHON -m src.anniversary2022_baseline.plot_results --snapshot IMPORTED_SNAPSHOT_DIRECTORY
```

正式运行入口为`run_baselines start --spec SPEC --manifest MANIFEST --root RUN_ROOT`；恢复使用`run_baselines resume --root RUN_ROOT`。当前嵌套设计草案尚不是已冻结的执行spec，入口将拒绝它，不会误启动全量。

## 尚未证明的范围与下一步

- 600秒长轨迹、5355题持续吞吐、大输入内存profile、长期磁盘压力尚未在这套新runner上实测。代码能运行不等于已经证明全规模运行的资源可行性。
- 已验证的是完成后去重恢复和单owner锁。运行中controller崩溃的自动重试尚未合格：活着的孤儿子进程会阻止重复提交；不完整attempt保留并进入BLOCKED，需独立恢复身份，不能悄悄覆盖旧输出。
- 当前散点图展示both-solved对子；单侧解出、全未解及错误均保存在矩阵／coverage中，尚未绘成单侧删失符号。不能将这幅图当作完整状态覆盖图。
- 最新节点约有27GiB空闲磁盘；不支持8份各8GiB证明同时预留。正式proof上限、并发／缓存、资源恢复方案和新阶段总预算需在执行spec里明确。旧100核时与本次源码验证不是全量2677.5 solver核时的预算承诺。
- 公开GBD入口连通性已单独检查：一个官方名单URL返回200、XZ头，首段读取约1.40秒；没有下载完整16.4MB文件，不能把它当作吞吐或完整输入校验。

下一步是定好全量执行资源与错误恢复spec，再按完整5355名单逐项领取。当前owner没有活动solver队列；无新邮件、无其他聊天消息、无委派、无无关文件清理。
