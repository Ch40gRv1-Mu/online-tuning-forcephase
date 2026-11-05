# 本轮交付包

先读`reports/phase_prediction_v1/FINAL_REPORT.md`，再按需要查看`FINAL_EVIDENCE.json`中的逐项证据与SHA。结论是明确范围内未建立稳定选择器；不包含独立最终测试结果。

- `experiments/phase_prediction/`、`solver/`、`patches/`：运行、特征、policy、验证与必要实现测试代码。
- `docs/`、`configs/`：冻结协议、输入名单／资源资格、策略与执行配置。
- `results/phase_prediction_v1/context/`：真实正式经验、reward与反例。
- 其余选定结果：完整矩阵／新特征／部署分析、原始收据归档、失败和物理费用。
- `long600_dev40_partial_receipts.tar.gz`明确只是用户替换的partial：159有效记录和1项取消。不能当作完整T600矩阵。

包内`MANIFEST.sha256`覆盖每个文件。原始CNF、大型LRAT、原始教授图片／xlsx／完整表、凭据和Git内部文件不重复打包。CNF身份及公共来源保留；固定CaDiCaL源码commit与工具SHA见最终报告和SOURCE_AUDIT。大证明按原政策在实际验证或UNKNOWN后移除，保留日志、大小／SHA。

为原表诊断复算另附`professor_pairs_development_only.csv`：只含冻结fit／feedback的240个配对，不含gate或受保护候选标签。`professor_pairs_development_projection.json`绑定原始表和投影SHA。原诊断源码在已有工作区读取`professor_pairs.csv`；若仅使用交付包，应在新的隔离副本中将这份投影放到该预期路径，不能覆盖已有原表。指标使用相同允许行可复算，但输入文件SHA将相应变为投影SHA，不能冒称原始完整表身份。

所有结果人口、预算及验证模式保持分开。复查已有证据无需重跑SAT。若主动重新运行分析，使用新的输出目录，保持冻结证据不变；新服务器运行不由这个包自动授权或启动。

共享8轮策略配额已经使用；额外新特征仅作预先限定的fit内刻画，没有新增正式reward或policy。共享gate只消费一次，不能将它或5355最终候选当作新开发数据。
