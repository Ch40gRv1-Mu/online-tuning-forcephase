# 最终研究报告：CaDiCaL 何时该用原生相位策略、何时该强制负分支？

<!-- M4/M5 sections are filled from reports/M4_report.md and reports/M5_report.md -->

## English abstract

(filled after M5)

## 0. 表述约定

**[源码]** 固定源码已证实；**[实验]** 本项目实验已观察（给出数据范围）；**[假说]** 尚待检验。所有表和图都由仓库脚本从运行记录生成；运行记录可通过 `run_id` 追溯到 `$FP_DATA/runs/` 下的原始日志。

## 1. 研究问题与回答（摘要）

(filled after M5)

## 2. 方法

### 2.1 求解器与动作语义

- 固定 CaDiCaL `c60730422e758ef1cebe7aeddf2dda31c996bf04`（3.0.1）。补丁约 100 行（`patches/cadical-fpc.patch`）+ 控制器源文件（`solver/fpcontrol.*`），设计见 [docs/DESIGN.md](../docs/DESIGN.md)。
- **配置轨道 C**：动作为有效值对 `(forcephase, phase)`：NATIVE=(0,1)、NEGATIVE=(1,0)、NATIVE_INIT_NEG=(0,0)、POSITIVE=(1,1)；所有上游读取这两个选项的位置（决策相位、likely_phase/GC 布局、rephase 门控、rephase original/inverted、变量创建时的 saved 初值，以及 walk/warmup/condition 的初始相位）一致使用有效值。固定动作在变量创建前生效，与命令行配置逐项等价（M0 证明）。
- **极性轨道 P**：只把自由 CDCL 决策的符号设为负（优先级与 forcephase 相同，低于 API phase），其余原生路径不变。
- 切换只发生在自然 restart 之后；不新增 restart，不清空/复制 saved/target/best；强制期间 rephase 计时停住，返回 NATIVE 时过期的 rephase 会立即发生（主语义），`fpcrlim` 为推迟它的消融。
- 默认 `phase=1`：裸 `--forcephase` 强制**正**方向（M0 用 API 与决策计数验证）。

### 2.2 正确性与可复现性

- 所有 solved 结果都经验证：SAT 用独立的 `tools/checkmodel` 对求解器实际读入的 CNF 校验模型；UNSAT 用二进制 LRAT 证明（所有配置统一开启，生成成本计入求解时间）由 lrat-trim 检查，checker 时间单列。验证失败记为 wrong，checker 超资源记为 unverified（本项目两者都为 0）。
- 运行由 `scripts/fprun.py` 以内容寻址 run id 管理（含二进制和策略文件哈希），结果不可覆盖，可断点续跑；所有尝试（包括被中断的）写入 attempts 日志，汇总为 [COMPUTE_LEDGER.md](COMPUTE_LEDGER.md)。
- 运行环境：gs-srun 容器（Ubuntu 22.04，g++ 13.4，静态链接），Slurm `cpu-low` 独占节点（AMD EPYC 9454），每节点 48 个求解进程绑定到间隔物理核；CPU 时间（user+sys）计时，T = 300 s，内存上限 16 GB。

### 2.3 数据与划分

- SAT Competition 2023–2026 主赛道（GBD 元数据与文件），纳入解压后 ≤100 MB 的实例。
- 家族组：GBD 家族名经保守别名合并（如 graph-coloring/coloring、多个 multiplier 家族、hardware 系列），再按 isohash 合并同构副本。
- 开发池（2023–2025）按家族组分为 train 612 例 / 67 组、val 205 / 22、test 204 / 21（种子 20261018，运行任何求解器之前固定）。2026 年中与开发池不重复的 304 例为年份外推集 t2026（seen 107 / devtest 49 / new 148）。
- 编码变体（全局翻转、随机翻转、变量置换+子句打乱）与原实例同组；seed 1、2 定义为变量置换+子句/文字打乱（保持符号）。

### 2.4 统计

PAR2（solved 且已验证记 CPU 秒，否则 2T）；每个实例先对 seed 平均；相对差的 95% 区间用以家族组为单位的 cluster bootstrap（10,000 次，种子 12345）；timeout 是右删失，不当作精确运行时间；oracle/VBS 只作诊断。

## 3. M0–M1：语义、正确性与开销

详见 [M0_M1_report.md](M0_M1_report.md)。要点：
- 7,604 次 M0 运行（带断言构建）0 失败；154 组上游/补丁搜索统计逐项相同；32 个同 prefix 重放 digest 一致；选项真值表与 API 优先级全部符合源码。
- M1（292 个实例 × 3 配置 × 3 次重复）：上游 / 控制器关闭 / telemetry 的搜索统计在 289 个全解实例上 0 差异；telemetry 相对控制器关闭的中位 slowdown 0.08%（目标 ≤1%，达到），p95 4.16%（目标 ≤3%，未证明；同配置重复之间 p95 噪声 5.77%，hook 实测时间 p95 0.07%）。

## 4. M2：静态互补性与机制（dev）

详见 [M2_report.md](M2_report.md)。

| 配置 | solved（SAT/UNSAT） | PAR2 | 相对 D |
|---|---|---|---|
| D（stock） | 363（197/166） | 361.5 | — |
| I−（仅初始负；validation-SBS） | 377（208/169） | 351.9 | +2.7% [+0.3, +5.6] |
| F−（强制负） | 305（143/162） | 400.7 | −10.8% [−20.9, −4.3] |
| F+（强制正） | 292（125/167） | 409.3 | −13.2% |
| D/no-R | 313（136/177） | 397.6 | −10.0% |
| I−/no-R | 329（153/176） | 386.2 | −6.8% |
| S（纯 saved） | 319（135/184） | 394.2 | −9.0% |
| P−（轨道 P） | 302（145/157） | 403.4 | −11.6% |

- 互补：D/F− 静态 oracle 比 D 低 5.0% [2.5, 8.0]，比 I− 只低 2.4%。
- 机制：关闭 rephase 是 SAT 损失的主因，在 UNSAT 上略有收益；同样关闭 rephase 时，强制方向比用 saved 更差；只强制决策而保留 rephase（P−）同样差。
- 编码：F− 获胜的家族（brent-equations、polynomial-multiplication 等）在全局符号翻转后变为大幅劣势，随机翻转后优势消失；随机翻转也让 stock D 的 PAR2 从 97.9 升到 167.0（388 例子集）。

## 5. M3：一次选择（dev）

详见 [M3_report.md](M3_report.md)。在 4,233 个同状态重放（digest 一致 4,230）上，静态、time-only 与在线一次选择器（K = 1e3/1e4/1e5；D 或 I− prefix）在家族分组嵌套 CV 中都没有超过“从不切换”；在线特征模型比不切换差 1–3.5%，与 shuffled-label 对照相当；单变量信号几乎全部是家族间差异。RQ3：21% 的实例在不同 K 的同状态偏好不同；反向固定调度 F−→D@1e4 在 dev 上优于 D 与 I−。

## 6. M4：无观测固定调度（dev）

(filled from M4_report.md)

## 7. M5：冻结后的 held-out 评估

(filled from M5_report.md)

## 8. 成本

(filled at the end from COMPUTE_LEDGER.md)

## 9. 反例与局限

(filled at the end)

## 10. 与相关工作的差异

(filled at the end)

## 11. 已知、未知与下一步

(filled at the end)
