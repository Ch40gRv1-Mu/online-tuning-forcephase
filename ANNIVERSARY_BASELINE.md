# 2022 Anniversary 基线：当前实现与运行边界

**当前状态：小样例功能验证通过；全量5355题尚不能直接一键启动。**

最新范围按用户2026-11-07选择调整：保留完整5355题主名单，**仅排除官方顺序／并行／云三个赛道中所有求解器都未解出的636题，保留4719题**（包括4个覆盖／状态不确定项）。D/F+/F−、seed0、每项600 CPU秒，共14157项。筛选不使用我们的相位赢家，不额外删掉“比较难”或大文件。全部2022数据已改作基线／开发，之后另选独立测试集。

筛选产物：[4719题运行名单](configs/anniversary2022_baseline/manifest.official-solvable.v1.csv)、[636题逐项排除原因](configs/anniversary2022_baseline/manifest.official-solvable.v1.excluded.csv)、[来源／匹配覆盖及完整receipt](configs/anniversary2022_baseline/manifest.official-solvable.v1.receipt.json)、[摘要](outputs/anniversary2022_baseline/external_filter_summary.json)。官方ZIP来源SHA、每赛道28／6／2个求解器列与少量cutoff超限但官方接受的非罚分成绩均保留；不能只凭一个赛道没解出就删除，也不能将缺失hash当未解。

## 已交付

- [七个脚本、共享模块和实现测试](src/anniversary2022_baseline/)。
- [完整5355题输入名单](configs/anniversary2022_baseline/manifest.v1.csv)及[SHA收据](configs/anniversary2022_baseline/manifest.v1.receipt.json)，无须访问原机器才能获得该名单。
- [节点实际验证报告](reports/anniversary2022_baseline/READINESS_20261107.md)：最终版12次真实求解，3 SAT／6 UNSAT验证通过，3 CPU超时；统计、单owner、完成后续跑去重、汇总与导出通过。
- [验证原始记录](outputs/anniversary2022_baseline/qualification_v2/QUALIFICATION.json)、[原始归档](outputs/anniversary2022_baseline/qualification_v2/qualification_receipts.tar.gz)、[绘图HTML源码](outputs/anniversary2022_baseline/qualification_v2/analysis/baseline.html)。HTML下载后在浏览器打开；这些是四个合成输入的功能结果。
- [脚本计划](refine-logs/anniversary2022_baseline/SCRIPT_PLAN.md)和[完整来源／逐文件SHA](reports/anniversary2022_baseline/PUBLICATION_SOURCE.json)。代码来自独立本地研究工作区的精确快照，保留原执行commit和runtime文件SHA，不把snapshot提交冒充原测量commit。

## 可以验证的路径

Linux节点使用Python 3.10+标准库、`prlimit`、`taskset`、指定CaDiCaL与lrat-trim。先在仓库根目录运行实现测试：

```bash
python3 -m unittest src.anniversary2022_baseline.test_contracts -v
```

有界真实功能验证使用新目录，最多4个输入×三配置、每项2 CPU秒，不提交5355题队列：

```bash
python3 -m src.anniversary2022_baseline.qualification \
  --root NEW_QUALIFICATION_DIRECTORY \
  --solver EXISTING_CADICAL_PATH \
  --checker EXISTING_LRAT_TRIM_PATH
```

绘图依赖与求解节点分开；可在本地venv安装[已实际使用的依赖](configs/anniversary2022_baseline/plot_requirements.lock.txt)，再运行：

```bash
python3 -m src.anniversary2022_baseline.plot_results --snapshot SNAPSHOT_DIRECTORY
```

## 全量启动还差什么

1. 正式执行spec：当前`spec.draft.json`是设计草案，不是直接可执行的已冻结配置，启动器会拒绝DRAFT。
2. 全量资源与新预算：当前节点磁盘约27GiB，证明容量与并发、缓存及大输入资源配置尚需确定。当前4719题全部超时的solver上限为2359.5核时，checker另计；不把这个上限说成已实耗或已完成。
3. 中断／资源错误恢复：已完成记录不会重跑；活着的孤儿进程会阻止重复提交。中途崩溃的不完整attempt目前保留为BLOCKED，不能冒称已实现自动无损接续。

下一步应完善以上执行配置及恢复能力，再在固定4719题名单上持续领取任务。该人口的结果必须标明经外部难度筛选，不能称完整5355题实测。当前验证不代表600秒长轨迹、大公式或长期磁盘压力已经通过。

本分支没有密码、原始教授附件或私有逐题TA计时表；没有启动全量任务，也没有修改旧研究结果。
