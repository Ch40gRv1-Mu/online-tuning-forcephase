# 实现设计：forcephase 研究控制器（FPC）

本文描述 `patches/cadical-fpc.patch` 与 `solver/fpcontrol.{hpp,cpp}` 的语义。源码事实以固定提交 `c60730422e758ef1cebe7aeddf2dda31c996bf04` 为准，审计见 [SOURCE_AUDIT.md](SOURCE_AUDIT.md)；M0 复核结论见 [reports/M0_M1_report.md](../reports/M0_M1_report.md)。

## 1. 对上游的改动（全部在补丁中，约 100 行）

| 位置 | 改动 | 控制器关闭时的效果 |
|---|---|---|
| `options.hpp` | 新增 13 个 `fpc*` 选项（默认 0 / 不改变行为） | 无 |
| `internal.hpp` | 成员 `fpc`（控制器指针）、`fpcc`（计数器）、`fpc_pair/fpc_force/fpc_phase`（有效值对）、`fpc_sign`（轨道 P）、`fpc_src`；`eff_phase()`、`eff_forcephase()`；`native_phase_suggestion()` | `eff_*()` 返回 `opts.phase/opts.forcephase` |
| `decide.cpp` `decide_phase` | `opts.phase/opts.forcephase` → `eff_*()`；记录相位来源 `fpc_src` | 同上游 |
| `decide.cpp` `decide` | 计数自由决策、负号、来源；轨道 P 覆盖符号（优先级同 forcephase：低于 force_saved 和 API phase）；`fpc!=0` 时计算原生建议方向 | 只多几次加法 |
| `rephase.cpp` | `rephasing()`、`rephase_original/inverted` 读 `eff_*()` | 同上游 |
| `internal.cpp` `enlarge` | 首次扩容前构造控制器（因此固定动作在变量创建前生效）；saved 初值读 `eff_phase()` | 同上游 |
| `internal.cpp` `add_original_lit` | 原始子句的廉价静态计数（长度、正文字、Horn/反 Horn） | 只多计数 |
| `internal.cpp` CDCL 主循环 | `restart()` 之后调用 `fpc->at_restart()` | 不调用 |
| `internal.cpp` `solve` | 结束时 `fpc->finish(res)` 写 final 记录 | 不调用 |
| `analyze.cpp` | glue 和、低 glue 计数、最小化后长度和、回跳距离和 | 只多计数 |

源码审计补充（M0 复核时发现，审计原文未列出）：`decide_phase` 除 `decide()` 与 `likely_phase()` 外，还被 `warmup.cpp`、`walk.cpp`、`walk_full_occs.cpp`、`condition.cpp` 调用。轨道 C 的有效值对因此也作用于这些路径（与命令行 forcephase 语义一致）；轨道 P 只改 `decide()` 中的自由决策，这些路径保持原生。

## 2. 两个轨道与动作

- **轨道 C（`--fpctrack=0`，主轨道）**：动作是有效值对 `(forcephase, phase)`：`NATIVE=(0,1)`、`NEGATIVE=(1,0)`、`NATIVE_INIT_NEG=(0,0)`、`POSITIVE=(1,1)`。所有上游读取 `opts.phase/opts.forcephase` 的地方一致使用有效值，因此包含“禁用 rephase”“likely_phase/GC 布局”“rephase original/inverted 方向”“新扩容 saved 初值”等副作用。
- **轨道 P（`--fpctrack=1`，机制轨道）**：NEGATIVE 只把 `decide()` 中自由决策的符号设为负；rephase、target、likely_phase、warmup/walk、saved 初值等全部保持原生（opts 值）。

两个轨道的标签与结果分开命名（配置名后缀 `_C` / `_P`）。

## 3. 控制器模式（`--fpc`）

| 值 | 模式 | 行为 |
|---|---|---|
| 0 | off | 不构造控制器 |
| 1 | telemetry | 只记录，不设置有效值（命令行配置原样生效） |
| 2 | fixed | 在首次 `enlarge` 前应用 `fpcinit` 指定的动作并保持 |
| 3 | schedule | 初始动作后在第一个 `conflicts ≥ fpcat` 的自然 restart 处切换；`fpcperiod>0` 时之后每隔该冲突数再切 |
| 4 | policy | 读 `FPC_POLICY` 文件：`oneshot`（在 prefix 检查点上一次决策）或 `repeat`（每个窗口按分数 + 迟滞决策） |
| 5 | random | 每个窗口以 `fpcprob/1000` 概率切换（独立 RNG，`fpcseed`） |

所有模式共享：最短驻留 `fpcmindwell`（窗口数）、最大切换次数 `fpcmaxsw`。

## 4. 安全点与切换时的状态处理（显式定义）

- **唯一应用点**：CDCL 主循环中自然 `restart()` 返回之后（`restart()` 已执行 `backtrack(reuse_trail())` 并更新 restart 限制）。不新增 restart，不在传播/分析/GC/inprocessing 中途切换。请求与实际应用的冲突数分别记录（`requested`、`conflicts`）。
- **trail reuse**：默认 `restartreusetrail=1` 时 restart 后可能保留部分旧决策前缀；切换不强制回到 0 层，新动作对已保留前缀延迟生效。这是记录在案的语义，不添加额外回溯。
- **saved / target / best**：切换不复制、不清空、不恢复。强制期间 saved 仍被决策和传播更新，切回 NATIVE 时继承这些值。
- **rephase 计时**：NEGATIVE 期间 `rephasing()` 返回 false，`lim.rephase` 停住而冲突继续增长；切回 NATIVE 后若已过期，主循环会立即执行一次 rephase（M0 G 检查已观察到）。这是主实验的“自然恢复”语义。消融 `--fpcrlim=1`：切回时若过期则推迟到 `now + rephaseint·(rephased+1)`，并在 switch 记录中写 `rephase_postponed_from`。
- **RNG**：控制器使用独立 splitmix64，不消耗求解器随机数。telemetry 只读状态。
- **证明**：控制器不接触 clause、reason 或 proof。M0 中所有切换应力测试的 UNSAT 结果都用 LRAT 证明验证。

## 5. 遥测 JSONL（schema 1）

由环境变量 `FPC_LOG` 指定路径；每条记录一行，写后 `fflush`。

- `header`：schema、版本、全部 fpc 选项、相关原生选项、检查点列表、特征名列表。
- `init`/`switch`：原因（init/schedule/oneshot/repeat/random）、动作、请求冲突数、实际冲突数、时间、模式、层、切换次数、`rephase_lim`、`rephase_postponed_from`；前 32 次切换带状态 digest。
- `checkpoint`：在第一个 `conflicts ≥ K` 的 restart 处（K ∈ {1e3,2e3,5e3,1e4,2e4,5e4,1e5,2e5,5e5,1e6}），含状态 digest 和完整特征向量 `f`（`w_` 特征相对上一检查点）。**所有模式都写**，因此 D 运行的检查点特征就是一次选择策略在同一 prefix 上看到的特征。
- `decision`：oneshot 策略的分数、选择、prefix。
- `window`：每 `fpcwin` 冲突后第一个 restart，含特征（`w_` 相对上一窗口）、动作、驻留、repeat 分数。
- `final`：结果、总计、切换数、各动作占用的冲突/决策/CPU 时间、控制器热点耗时 `hook_time`、决策计数（自由决策、负号、原生建议为正、P 覆盖/翻转、来源分布）、最终 digest。

特征组（缺失值写 `null`，分母为 0 时缺失）：
- `s_`（C 组，静态）：log 变量数、log 子句数、子句/变量比、平均长度、单元/二元/三元比例、正文字比例、Horn、反 Horn 比例。
- `r_`（R 组，进度/原生机制）：log 冲突、CPU 时间、当前 stable、距下次 rephase、当前有效动作、切换数。
- `c_`/`w_`（累计/窗口比率）：决策/冲突、传播/决策、ticks/冲突、冲突/秒、glue 均值、低 glue 比例、1st-UIP 长度、最小化后长度、回跳距离、chrono 比例、每千冲突 restart、trail 复用率、负决策比例、原生建议为正比例、target/saved 来源比例、每千冲突学到单元/二元、stable 冲突比例、rephase 次数。
- `x_`（当前状态）：glue fast/slow 及比值、trail EMA 与活动变量比、jump/level/size EMA、best/target 赋值比例、活动变量比例、不可约子句/变量、冗余/不可约、256 个固定抽样变量的 saved 负比例与翻转比例（**v1 的翻转比例失效**，见 §5a）、target 设定比例与负比例。

digest 为 FNV-1a，覆盖冲突/决策/传播/restart/rephase 计数、子句计数、stable、层、`lim.rephase`、trail 全部文字和全部变量的 saved/target 相位。digest 相同是重放一致性的检查，不是全部内存相同的证明。

## 5a. 控制器版本：v1（第一轮）与 v2（audit v2 修复）

| | v1（`solver/v1/`，构建变体 `fpc`，schema 1） | v2（`solver/`，构建变体 `fpc2`，schema 2） |
|---|---|---|
| 使用范围 | 第一轮全部 36,077 次运行（M1–M5）与 audit v2 开销复测 | audit v2 之后的代码；尚无用于科学结论的实验数据 |
| `x_saved_flip_frac` | **失效**：checkpoint 与 window 共用一份样本相位历史，因此 flip 常常是“与上一条不同类记录”的比较；compaction 重新编号内部变量后，样本索引指向别的变量也被当作翻转 | 两个记录流各自维护历史；只比较前后两次都活跃、都有 saved 值的样本；无可比历史时为 `null`；检测 `stats.compacts` 变化后重建固定大小样本并清空两个流的历史（每条记录带 `compacts` 与 `sample_epoch`） |
| 同一 restart 两类记录 | 先写 checkpoint 并可能执行 oneshot 动作，再计算 window 特征（window 中 `r_action`、`dwell` 是动作之后的值） | 先从同一份动作前状态计算并写出两类记录（`action` 均为动作前），再按模式至多执行一次动作 |
| RNG | 样本抽取与 random 模式共用一个 splitmix64 | 样本 RNG 与动作 RNG 分离（都不使用求解器 RNG） |
| 策略解析 | 成员函数 | 自由函数 `parse_policy`（测试可直接调用同一份代码） |

两版的补丁（`patches/cadical-fpc.patch`）相同，所以控制器关闭时完全一致；audit v2 的集成测试（`tests/audit_v2/test_controller_v2.py`）在 20 个实例上核对了 off、telemetry、fixed NEGATIVE、冻结调度 F−→D@1e4 与 oneshot 策略下 v1、v2（及上游）的搜索统计、最终 digest 和切换点逐项相同；M0 套件在 `fpc2`/`fpc2-check` 上 0 失败。random 模式在 v2 中因 RNG 分离而与 v1 轨迹不同（第一轮正式实验未使用 random 模式）。v1 的 flip 特征在 audit v2 的 M3 复核中被统一排除（[CORRECTION_PROTOCOL.md](CORRECTION_PROTOCOL.md) §5）；不得混用 v1 与 v2 遥测。

## 6. 策略文件（`FPC_POLICY`）

```
fpc-policy 1
type oneshot              # 或 repeat
prefix 10000              # oneshot：必须是一个检查点值
threshold 0.5             # oneshot：score > threshold 则选 a1（默认 NEGATIVE）
enter 0.6                 # repeat：a0→a1 当 score > enter
exit 0.4                  # repeat：a1→a0 当 score < exit
model tree ( c_glue_mean 7.25 R 0.2 ( r_stable 0.5 L 0.9 0.1 ) )
# 或 model linear <bias> <n> { <feature> <mean> <scale> <impute> <weight> }×n   （输出 sigmoid）
```

树节点 `( 特征 阈值 缺失方向 左子树 右子树 )`，`x ≤ 阈值` 走左；叶子为分数。部署时不调用 Python 或网络。

## 7. 运行与验证流水线

`scripts/fprun.py`（仅标准库）：内容寻址 run id（含二进制 SHA-256、策略文件 SHA-256、参数、实例、seed、T、内存、证明政策），结果不可覆盖；`scripts/slurm_submit.sh` 以 Slurm 数组在 gs-srun 容器中运行分片。SAT 用 `tools/checkmodel` 对求解器实际读取的 CNF 检查；UNSAT 用 lrat-trim 检查二进制 LRAT。状态分为 solved / timeout / memout / crash / error / wrong / unverified，均保留。
