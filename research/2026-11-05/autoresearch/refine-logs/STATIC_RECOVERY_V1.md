# 静态提取恢复协议 v1

Owner：root；2026-11-05 UTC。状态：产物已准备，须提交后执行；本协议不改变统计筛选标准。

## 失败与恢复范围

首次输入准备在源码提交 `59c5b38` 下因文件名描述后缀含长 hex seed 而解析失败，墙钟 0.301 秒，CPU 未测量；没有产生快照、评分或 SAT 调用。`28161c6` 修复 basename GBD 前缀解析。

原本地清单 32 项在资源检查阶段退出 2，报告可用内存约 1.29 GiB，没有开始单题。记录的 owner PID 45565 已不存在；原 results、inflight、temporary 均为空，无 build/completion，原 owner 记录保留。资源限制不降低。

原远程 96 项由 root 的正式 terminal session 7050 确认退出 2，completion 为 STOPPED_INCOMPLETE、3/96 已记录 FAILED、无活动任务；3 项均在原始 CNF SHA 校验后、特征提取前因尺寸元数据检查失败。其准备 CPU 合计 1.185257515 秒、提取 CPU 为 0。root 在恢复前保存旧 completion 和 3 个不可变失败 receipt；原队列不重启。

这 3 项失败和另 125 项未开始任务合为唯一恢复清单，共 128 项。原 64 个可复用成功缓存和 48 个排除父题不重跑。

## 尺寸语义修复与身份

GBD 目录特征 `bytes` 与下载后原始 CNF 的文件长度不同，不能用作逐字节尺寸断言。既存公共 `benchmarks/checksums.csv` 对当前 128 项均记录相同 CNF SHA、压缩 SHA 和精确 `bytes_cnf`；128 个精确尺寸均小于原 100000000 字节上限。

新清单仅把 `metadata.bytes` 改为该 SHA 绑定的 `bytes_cnf`；原 GBD 数值及来源在恢复 sidecar 逐项保留。保持所有 task_key、input_sha256、compressed_sha256、extractor_source_sha256 和 profile 不变；worker 的原始 SHA、精确尺寸、header 计数和实际资源上限检查不放宽。输入准备器后续只把公共 checksum 的原始尺寸写入精确断言；没有原始尺寸时不把 GBD 特征冒充它。

- 任务：[static_recovery_manifest_v1.json](../configs/ta_feature_discovery/static_recovery_manifest_v1.json)
- 恢复证据、原清单 SHA 和尺寸对照：[static_recovery_v1.json](../configs/ta_feature_discovery/static_recovery_v1.json)
- 首次导入与本地资源失败：`outputs/ta_feature_discovery/execution_failures/`，CPU 未测量保留 null。

## 执行与费用

root 提交本协议、准备器修复、清单和 sidecar 后，使用 node_id `remote-8cpu-recovery`、shard `all-128-missing-recovery-v1`。选择新的独立 output 名 `static_remote_recovery_v1`，不得复用原输出 binding；远程绝对位置由 root 在正式 dispatch 记录。

继续使用已冻结 worker 和 extractor，不改 profile。请求最多 3 workers，worker 按实际 CPU、可用内存和磁盘自动降低并发；没有合格槽位时保存失败并停止。优先传入只读 `--input-cache /home/vipuser/forcephase_phase_prediction_20261104/data`，每次复用仍验证原始 CNF SHA 和实际尺寸上限。

每题原子发布并立即 checkpoint，失败和 TIMEOUT 均保留；不静默重试。新完成 receipt 的 node 身份与旧失败区分，根 owner 统一合并。此前失败 CPU 继续进入研究费用账本，未测量 CPU 不写成 0；恢复准备/提取 CPU 另行实测。

所有 240 个父题的可用、排除或正式不可用状态齐备后，生成新不可变 development 快照并开始完整候选评价。不能根据部分 feedback 调规则或提前评分；gate/test 继续封存。计时标签仍直接复用 TA，恢复不调用 SAT solver。
