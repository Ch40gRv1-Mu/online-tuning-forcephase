# 2022 Anniversary T600 基线结果（4719 题 × D / F+ / F−）

日期：2026-11-09。状态：**COMPLETE_VALID_MATRIX**。
- **覆盖**：4719 题 × 3 配置 = 14157 次运行全部有有效终态，没有错误、缺失或待验证项；同一题的已验证答案没有冲突。
- **代码**：合作者分支 d306829 加上集群适配，见 [CLUSTER_RUN_V1.md](CLUSTER_RUN_V1.md)。
- **执行**：冻结 spec [spec.cluster-v1.json](../../configs/anniversary2022_baseline/spec.cluster-v1.json)；运行时间 2026-11-08 23:26 至 2026-11-09 06:08 UTC，24 个 shard，4 个 cpu-mid 节点。
- **范围限定**：结果只覆盖排除官方全赛道未解题后的 4719 题，不是完整 5355 题的实测。

## 设置

| 项目 | 值 |
|---|---|
| 求解器 | CaDiCaL 3.0.1（`c607304`，静态编译，SHA `250220f9…`），原生 CLI |
| 配置 | D `--phase=1 --forcephase=0`；F+ `--phase=1 --forcephase=1`；F− `--phase=0 --forcephase=1`；seed 0 |
| 预算 | 每次 600 s solver 进程 CPU，到时 SIGTERM；1800 s wall 只作看门狗 |
| 验证 | 运行时生成二进制 LRAT。SAT 用本次 model 逐子句检查；UNSAT 用 lrat-trim（`b30f400`）检查本次证明 |
| 解出 | 答案通过验证，且 CPU ≤ 600 s |
| PAR2 | 按合作者设计，未解记 1200 s |
| 资源 | 每个 solver 绑定一个独占物理核（同核另一线程空闲）；地址空间 32 GiB |

## 主要结果

| 配置 | 解出 | SAT | UNSAT | 超时 | ≤ 10 s | ≤ 60 s | ≤ 300 s | 独有解出 | 平均 PAR2 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D | **3385** | 1714 | 1671 | 1334 | 1696 | 2378 | 3086 | 281 | **392.5** |
| F+ | 3076 | 1432 | 1644 | 1643 | 1601 | 2148 | 2796 | 50 | 468.2 |
| F− | 3055 | 1421 | 1634 | 1664 | 1589 | 2172 | 2764 | 70 | 472.0 |
| 时间 VBS | 3547 | 1789 | 1758 | 1172 | 1827 | 2565 | 3269 | | 349.9 |

- **最强单一配置是 D**：比 F+ 多解 309 题，比 F− 多解 330 题。
  - **差距主要来自 SAT 题**：SAT 上 D 多 282 / 293 题，UNSAT 上只多 27 / 37 题。
- **三配置 VBS**：比 D 多解 162 题（+4.8%），平均 PAR2 低 10.9%（349.9 s 对 392.5 s）。
  - 这是逐题事后取最优的上界，不是可部署的策略。
- **两两配对**（另一方未解 / 两者都解出时快 2 倍以上）：

  | 配对 | 只有前者解出 | 只有后者解出 | 前者快 ≥ 2× | 后者快 ≥ 2× |
  |---|---:|---:|---:|---:|
  | D 对 F+ | 401 | 92 | 474 | 195 |
  | D 对 F− | 442 | 112 | 471 | 172 |
  | F+ 对 F− | 211 | 190 | 306 | 328 |

  快 2 倍的统计只计较慢一方 ≥ 1 s 的题。
- **逐题最快配置**（至少一个配置解出的 3547 题）：
  - D 1141、F+ 698、F− 692；
  - 1016 题打平（相差 1% 或 0.1 s 以内）。
- **三配置都解出 2823 题。三配置都超时 1172 题（24.8%）**：这些题在 2022 官方比赛中至少有一个赛道的求解器解出（比赛时限通常 5000 s），但本基线 600 s 内都没有解出。

## 图

- 按 CPU 秒的累计解题曲线：[cumulative_cpu_s.png](../../outputs/anniversary2022_baseline/cluster_v3/analysis/cumulative_cpu_s.png)
- 按 conflicts 的累计解题曲线：[cumulative_conflicts.png](../../outputs/anniversary2022_baseline/cluster_v3/analysis/cumulative_conflicts.png)。conflicts VBS 与时间 VBS 分别取最优。
- 配对散点：[scatter_cpu_s.png](../../outputs/anniversary2022_baseline/cluster_v3/analysis/scatter_cpu_s.png)、[scatter_conflicts.png](../../outputs/anniversary2022_baseline/cluster_v3/analysis/scatter_conflicts.png)。只画两者都解出的题，单侧解出与未解保留在 `matrix.csv`。

图由合作者的 `plot_results.py` 生成。matplotlib 用的是 3.9.2（分析 venv），不是 lock 文件中的 3.11.2。

## 数据

- **仓库内**（`outputs/anniversary2022_baseline/cluster_v3/`）：
  - `analysis/summary.json`：汇总，含 14157 个结果文件的路径与 SHA；
  - `analysis/report.json`：上面各表；
  - `analysis/matrix.csv`：逐题三配置状态、CPU、conflicts、PAR2；
  - `analysis/runs.csv`：逐次运行；
  - `analysis/curve_data.json` 与图；
  - `shards.json`：各 shard 的作业号、主机、CPU、核时与完成状态。
- **集群上**（`/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase/anni2022_baseline/`）：
  - `cluster_v3/shard-XXX/`：每次运行的 `result.json`、完整日志（gz）、最后 1000 行与输入 receipt；
  - `cluster_v3_analysis/`：完整 snapshot，包括 57 MB 的 `instances.json`。
  - 输入 CNF 已按设计在三次运行有效完成后删除，可按 receipt 中的 URL 与 SHA 重新下载。
- **复现合并与图表**（在容器内）：
  ```bash
  tools/anni2022_cluster.sh collect NEW_SNAPSHOT_DIR
  PLOT_PYTHON -m src.anniversary2022_baseline.plot_results --snapshot NEW_SNAPSHOT_DIR
  python3 tools/anni2022_report.py --snapshot NEW_SNAPSHOT_DIR
  ```

## 计算量

- **正式运行**：owner 进程及其全部子进程实耗 990.8 CPU 小时，其中 solver 973.6 CPU 小时、验证 5.7 CPU 小时。最长的 shard 用了 6.7 小时 wall。
- **两次中止的启动**（不计入结果）：
  - 第一次已记录 728 次运行，solver 30.9 CPU 小时，另有在途运行；
  - 第二次 92 次运行。
- **Slurm 分配**：三次启动共 72 个作业，按 20 个逻辑 CPU × 时长计 2893 核时。分配数大于实耗，因为每个 shard 预留了整核，同核的第二个线程保持空闲。

## 计时与资源备注

- **wall / CPU**：超过 60 s 的运行中，中位数 1.06，90% 分位 1.23。比值偏高主要与证明写入节点本地盘的速率相关。计时以 CPU 为准，wall 只作看门狗。
- **内存**：单次运行最大 RSS 27.9 GB，在 32 GiB 地址空间限制以内；没有运行因内存或文件大小限制失败。
- **共享节点**：每个节点最多 7 个 shard（56 个 solver）同时运行，各自绑在不同物理核上。单 seed、单次运行，未做重复测量。
- **一处代码修正影响 conflicts 字段**：合作者原版 `parse_stats` 会把 CaDiCaL 3.0.1 的缩进子项 `c   conflicts: 0 … per warmup` 当作顶层值。本结果用修正后的解析器（见 CLUSTER_RUN_V1.md）。合作者 qualification_v2 的 conflicts 数字也受同一问题影响：
- pigeonhole(4,3) 的三次 UNSAT 都记为 0，修正后为 6–7；
- timeout 夹具 F± 记为 0，修正后为 10⁵ 量级。
