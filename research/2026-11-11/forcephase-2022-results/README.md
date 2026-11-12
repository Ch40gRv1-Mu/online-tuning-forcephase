# Forcephase：2022公式结构选择实验结果（2026-11-11）

**目前最好的完整计费同分布候选：42项CNF统计 + 三个成本分类器的平均分数。**
在4719题的等价组隔离五折开发预测中，计入已测特征和模型查询费用后，
相对固定D的PAR2降低 **2.349987%**，解出3423题（D为3385），净多38题。
这批2022数据已多次用于开发；结果不等于独立测试或同机端到端部署确认。

## 先读哪些文件

- [结果与限制摘要](SUMMARY_ZH.md)：正向结果、失败原因、当前状态与费用。
- [成本分类器完整结果](reports/anniversary2022_baseline/PAID_CLASSIFIER_R54_20261111.md)。
- [历次假说与失败解释](reports/anniversary2022_baseline/POLICY_FAILURE_MECHANISMS_20261111.md)。
- [完整研究过程](reports/anniversary2022_baseline/D_MECHANISM_PROGRESS_20261111.md)。
- [全部轮次索引](ROUNDS.csv)、[全部已保存评分索引](ALL_SCORES.csv)。不同成本/划分/诊断范围不可直接混排。
- [原始基线CPU图](outputs/anniversary2022_baseline/raw_data_20261110/cumulative_cpu_s.png)、
  [CPU散点图](outputs/anniversary2022_baseline/raw_data_20261110/scatter_cpu_s.png)、
  [conflict图](outputs/anniversary2022_baseline/raw_data_20261110/cumulative_conflicts.png)。
- [完整14157条基线](outputs/anniversary2022_baseline/raw_data_20261110/runs.csv)、
  [4719题三动作矩阵](outputs/anniversary2022_baseline/raw_data_20261110/matrix.csv)。
- [R54逐题预测与费用](outputs/anniversary2022_baseline/mechanism_R54_paid_classifier_20261111/predictions.csv)。

## 当前范围

只使用SAT Competition2022 Anniversary官方过滤后保留的4719题。
求解基线由Zhaofeng发布在Roushelfy/online-tuning-forcephase的
anni2022-cluster-run分支，提交0d82f6ed932e3f5ad0bde8d96d847dadc9ee8aa0。
CaDiCaL3.0.1固定c60730422e758ef1cebe7aeddf2dda31c996bf04，seed0，T600：

|动作|参数|解出|平均PAR2秒|
|---|---|---:|---:|
|D|--phase=1 --forcephase=0|3385|392.542654|
|F+|--phase=1 --forcephase=1|3076|468.236516|
|F−|--phase=0 --forcephase=1|3055|471.976052|
|VBS，每题事后选最快|不可部署oracle|3547|349.940732|

原5355主名单保留，依据官方三赛道结果排除636题；未按本项目相位结果再筛选。
没有family、文件身份、已知SAT/UNSAT答案或终局统计作为模型输入。
用户最新目标是相似结构混合分布内预测，整组未见结构结果仅作诊断。
研究目标目前暂停；打包和推送没有恢复研究或启动新实验。

## 内容与可复查性

`src/`为当前公开实验源代码，`refine-logs/`为冻结协议，`reports/`为结论，
`outputs/`保存已完成的汇总、费用、负结果和逐题预测；原生特征大缓存、CNF、
证明文件、教授原附件、SSH凭据、私钥和认证文件未包含。
`model.joblib`为已导出的R55候选，见其[policy.json](outputs/anniversary2022_baseline/mechanism_R55_classifier_serving_20261111/policy.json)。
模型为scikit-learn1.9.1/numpy2.5.4格式，仅应加载可信来源的joblib文件。
模型已导出及通过932个内层输入的序列化一致性检查；实际CNF入口资格检查尚未执行。

运行 `python3 tools/verify_published_results.py`，仅用已保存CSV复算主结果并核对发布清单，
不会训练或启动求解器。完整训练还需原GBD结构缓存、归档CNF和原协议环境；
本目录不是所有历史训练环境的自包含副本。CNF入口为
`python -m src.anniversary2022_baseline.classifier_mean_candidate --policy <policy.json> --cnf <input.cnf.gz>`。
原native二进制属于本机环境，发布版将绝对路径隐去；使用入口前需按原源码构建，
在新配置中明确设置本机二进制路径及其新SHA，不可假定跨平台二进制身份相同。

发布清单同时保留原始文件SHA和发布副本SHA。报告/结果中的本机用户名与绝对路径
经过替换，数值结果不变；这些发布副本的SHA因此可能不同于原冻结收据引用的SHA。
公开源代码和模型字节未做路径替换。历史报告按当时目标书写，以本摘要和最新范围更新为准。
