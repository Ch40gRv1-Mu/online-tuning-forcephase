# 实验日志（预注册决定与变更记录）

本文件按时间记录协议的具体化与变更。每条注明**是在接触哪些结果之前**作出的决定。所有时间为 UTC。

## 2026-10-18 19:20 — 运行前的协议具体化（未接触任何 benchmark 求解结果）

此前只运行过：M0 正确性套件（随机/构造的小 CNF）、smoke（20 个 train 实例 × 4 配置 × 10 s，只用于验证 runner/证明/校验流水线）。没有查看任何 300 s 结果。

**求解器与构建**
- CaDiCaL 固定提交 `c60730422e758ef1cebe7aeddf2dda31c996bf04`（3.0.1），子模块 `third_party/cadical`。研究补丁 `patches/cadical-fpc.patch` + `solver/fpcontrol.{hpp,cpp}`。
- 正式实验的二进制在 gs-srun 容器（Ubuntu 22.04，g++ 13.4）内由 `scripts/build_solver.sh` 构建，`-O3 -DNDEBUG -static`。所有配置统一使用打补丁二进制（`build/fpc`）；M0/M1 证明 controller 关闭和 telemetry-only 时搜索统计与上游二进制完全相同。

**数据**
- 候选池：GBD `main_2023`–`main_2026`（meta.db/base.db 于 2026-10-18 19:02 下载，SHA-256 见 `benchmarks/SOURCES.md`）。纳入规则：GBD `bytes`（解压后 sanitized CNF）≤ 100 MB。
- 家族组：GBD family 经保守别名合并（`scripts/build_manifest.py` 中 `ALIASES`），再按 isohash 并查集合并；`unknown` 按 author 分组。
- 开发池（2023–2025）按家族组用种子 20261018 贪心随机分配 train/val/test ≈ 60/20/20：train 612 例 / 67 组，val 205 / 22，test 204 / 21。2026 年池中不与开发池重复（hash/isohash）的 304 例为年份外推集 `t2026`，标记 seen（107）/ devtest（49）/ new（148）。
- **test 与 t2026 在 M5 冻结前不运行任何求解器配置。**

**运行与计时**
- 主 cutoff：T = 300 s 单核 CPU 时间（user+sys，wait4）；开发与最终主表使用同一 T。内存上限 RLIMIT_AS 16 GB。
- runner 轮询 CPU 时间，到 T 发送 SIGTERM（CaDiCaL 优雅结束并写出统计）；答案只有在 CPU ≤ T 且通过验证时记为 solved。
- 证明政策（协议 8.1 默认方案）：所有配置统一 `--lrat=1`（二进制 LRAT），写入节点本地 tmpfs，生成成本计入求解时间；UNSAT 用 lrat-trim（固定提交 b30f400）检查，SAT 用独立 `tools/checkmodel` 对求解器实际读取的 CNF 检查；checker 时间单列。
- 并发：Slurm `cpu-low` 独占节点，每节点 48 个求解进程，绑定到间隔的物理核（SMT 兄弟核空闲）。
- seed：seed 0 为原始 CNF；seed s>0 为 `cnfscramble perm s`（变量重命名+子句/文字顺序打乱，保持符号，因此保持编码的极性偏置）。说明：CaDiCaL 的 `--seed` 在 F− 下几乎不改变轨迹（禁 rephase、walk 不运行），所以用 scrambling 作为重复测量。
- 遥测：所有运行开启 telemetry（`--fpc=1`，窗口 1e4 冲突，检查点 1e3…1e6）；开销在 M1 单独测量并披露。

**M2**
- 主静态配置：D=(forcephase 0, phase 1)、I−=(0,0)、F−=(1,0)、F+=(1,1)，在 train+val、seed 0 上运行。
- validation-SBS：在 **val** split 上按 PAR2 从 {D, I−, F−, F+} 中选；另报告 train+val 上的结果和 D/F− 二动作 SBS。
- 诊断配置 D/no-R、I−/no-R、S（纯 saved）和轨道 P 固定负决策在 train+val 上运行。

**M3（预先限定）**
- prefix 长度候选：1e3、1e4、1e5 冲突（在之后第一个自然 restart 处决定）；标签来自同一 prefix 的确定性重放（`sw{K}_C`，NATIVE→NEGATIVE），NATIVE 分支即 D 运行本身；以检查点 digest 验证 prefix 相同。
- 模型：深度 ≤ 3 的树或 L2 正则 logistic；在 train∪val 上按家族组交叉验证选择；比较 static（`cnffeatures`，成本计入）、time-only（r_ 组）、online（全部）三类特征。

## 2026-10-18 20:25 — M2 census 完成后的开发集决定（未接触 test / t2026）

- M2 census（train+val，D/I−/F−/F+，T=300 s）完成：3,268 次运行，1,337 次 solved（全部验证通过），1,931 次 timeout，无 crash/memout/wrong。
- 按预注册规则，validation-SBS = **I−**（val 上 PAR2：I− 401.1 < D 415.4 < F+ 419.0 < F− 432.2）。两动作 SBS（D/F−）= D。最终主比较对象因此是 I−，并另报 D。
- 在开发集上观察到 {D, F−} 的静态 oracle 只比 I− 低约 2.4% PAR2。因此在主轨道 C（NATIVE prefix → NEGATIVE）之外，**新增目标明确的次要变体** NATIVE_INIT_NEG（phase 固定 0，只切换 forcephase）：I− prefix 在 K∈{1e3,1e4,1e5} 后切换到 NEGATIVE（配置 `sw*_Cin`，实验 `m3in_replay_*`）。这是目标文件允许的、必须单独命名的设计；它与 D 基础的结果分开报告，并与 stock default 对比。该决定只基于开发集数据。
- M3 的其余预注册内容不变（K 候选、模型族、分组 CV）。
