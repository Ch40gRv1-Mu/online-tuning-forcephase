# CaDiCaL 源码审计：`forcephase` 到底改变什么

审查日期：2026-10-18。固定上游为 [`arminbiere/cadical@c60730422e758ef1cebe7aeddf2dda31c996bf04`](https://github.com/arminbiere/cadical/tree/c60730422e758ef1cebe7aeddf2dda31c996bf04)，[`VERSION`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/VERSION) 为 **3.0.1**。通过 GitHub 读取并扫描此提交 `src/` 的全部 **162 个文件**；`forcephase` 命中只在 `decide.cpp`、`rephase.cpp`、`options.hpp`。这是**静态审查，没有构建或跑性能实验**；后续 agent 的 M0 必须下载相同提交，以 `rg` 和实际运行复核。下文的“风险”“建议”是据源码推导的实验设计，不是已有测量结果。

## 1. 首先修正项目中容易混淆的术语

此版本 `phase` 默认值是 **1（正相位）**，`forcephase` 默认值是 0。因此：

| 配置 | 普通内部决策的含义 | 自动 rephase |
|---|---|---|
| 原版默认 | 正初始化；随后使用 target / saved 等原版逻辑 | 开启 |
| `--forcephase` | 强制**正**相位 | 禁止 |
| `--forcephase --phase=0` | 强制**负**相位 | 禁止 |
| `--forcephase=0 --phase=0` | 负初始化；随后使用原版 target / saved 等逻辑 | 开启 |
| `--phase=0 --target=0 --rephase=0 --stubbornIOfocused=0` | 负初始化的纯 saved 对照，保留显式 API phase 的优先级 | 禁止 |

以上均以没有显式 API phase、没有特殊 `force_saved_phase` 状态为前提。`--no-phase` 等价于 `--phase=0`。不能将“裸 `--forcephase`”标记为 negative branching，也不能将 stock 默认组标记成“纯 phase saving”。这些名称必须出现在运行清单和结果表里。[`options.hpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/options.hpp)

## 2. 相位选择的真实优先级

[`Internal::decide_phase`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/decide.cpp#L125-L175) 可概括为：

```text
initial = (opts.phase == 1 ? +1 : -1)
p = 0
if force_saved_phase: p = saved[x]
if p == 0: p = API_forced[x]
if p == 0 and opts.forcephase: p = initial
if p == 0 and use_target: p = target[x]
if p == 0:
    if stubbornIOfocused and rephase == 2:
        according to rephase count, use initial / -initial / saved[x]
    else: p = saved[x]
if p == 0: p = initial
return p * x
```

`decide()` 只在正常的内部决策处调用它；默认 `target=1` 时，stable 模式允许 target，focused 模式通常使用 saved。`target=2` 则两种模式都允许 target。假设、constraint 的特殊决策和外部 propagator 返回的决策并不沿这条普通路径；因此“强制负”不能解释成所有赋值都为负。传播仍必须满足公式，正 literal 仍会大量出现。[`decide.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/decide.cpp#L217-L345)

`Solver::phase(lit)` 写的是 `phases.forced`，与 `opts.phase` 不同，而且其优先级高于 `opts.forcephase`。不要通过给所有变量调用 `phase(-x)` 来假装原生 `--forcephase`；这样会改变优先级与接口语义。[`phases.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/phases.cpp#L31-L54)

## 3. Saved phase 不是“最近一次单位传播”那么窄

[`Internal::search_assign`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/propagate.cpp#L99-L169) 在普通 search 赋值时执行：

```text
set current value[x] = sign(lit)
if not searching_lucky_phases:
    saved[x] = sign(lit)
push lit onto trail
```

普通决策、传播、learned clause 驱动、根单位、外部传播等相应路径都使用它；**决策也会写 saved**。`forcephase` 并未关闭这个写入，所以在强制模式运行一段时间后再切回 saved，并不是恢复切换之前的那份 saved。它会继承强制模式期间的赋值历史。

另外，变量创建时 saved 用 `opts.phase` 初始化；warmup 也会写 saved；rephase 会整体重设 saved，walk 会将其找到的最好 assignment 写回。回溯前的 `update_target_and_best()` 根据无冲突 trail 高度更新 target / best，普通 `unassign` 不清除 saved。相关位置：[`internal.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/internal.cpp)、[`warmup.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/warmup.cpp)、[`walk.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/walk.cpp)、[`walk_full_occs.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/walk_full_occs.cpp)、[`backtrack.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/backtrack.cpp#L10-L85)。

主实验应保留原本 saved 的更新。若研究“冻结/恢复旧 saved”，应单独命名、单独消融，并统计其 O(n) 复制开销。

## 4. 原生 `forcephase` 的其他作用

### 4.1 它同时禁止 rephase

[`Internal::rephasing()`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/rephase.cpp#L21-L33) 在 `opts.forcephase` 为真时直接返回 false。因此命令行比较同时包含“相位选择”和“取消周期性 rephase”的效果。rephase 包含 original、inverted、flipping、random、best、walk 等路径，会回溯、修改 saved / target、更新调度与计数；在特定条件下还会调用 `shuffle_scores()` 或 `shuffle_queue()`。shuffle 默认关闭，但不能对非默认配置忽略这个副作用。[`rephase.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/rephase.cpp#L113-L400)、[`queue.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/queue.cpp#L60-L88)、[`score.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/score.cpp#L18-L49)

### 4.2 它会间接改变复制式 GC 的布局

`likely_phase(x)` 调用 `decide_phase(x, false)`；`collect.cpp` 在按变量/queue 顺序复制 clauses 时使用 `likely_phase` 安排访问顺序。因此直接动态改变 `opts.forcephase` 还可能改变 clause 的内存布局，影响真实运行时间。这个效应不能仅用 conflict 数度量。[`decide.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/decide.cpp#L177-L180)、[`collect.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/collect.cpp#L364-L400)

应区分两种机制：**native-toggle** 必须保留上述全部原生作用；**decision-only** 只在真正的决策处覆盖符号，保持原生 rephase / likely_phase 路径。两者是不同 treatment，不能混用名称。主研究先测 native-toggle；decision-only 用于解释收益来源。

### 4.3 负相位依赖输入的 literal 编码

在审查的 forcephase 路径中没有找到“自动把负相位归一化为更有语义意义的方向”的步骤。`phase=0` 针对当前内部变量的负 literal。compact 会重映射变量和 phase 数组；不能用内部 index 当作持久的原公式变量身份。[`compact.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/compact.cpp)

建议对部分实例增加固定种子的变量重编号和独立变量极性翻转实验，保留可逆映射与原始实例分组；它们是同一逻辑问题的不同编码，不能分到训练/测试两侧。不要把对某个编码的负相位优势解释为逻辑性质。

## 5. 在线切换的实现边界

### API 限制

`Solver::set(name, val)` 对 forcephase 之类的普通 option 要求 solver 仍处于 **CONFIGURING**。`set_long_option` 同样如此。因此不能在 `solve()` 中调用 `set("forcephase", ...)`，也不能通过反复 `solve()` 后的普通 `set` 实现切换。重复分段 solve 还有额外的入口/出口影响，不是本研究首选实现。[`cadical.hpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/cadical.hpp#L687-L712)、[`solver.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/solver.cpp#L549-L578)

应在固定源码中添加专用、单线程的内部 controller 和 runtime action 字段；native-toggle 的有效值必须在决定 phase、rephasing、likely_phase 三条路径一致生效。原有 CLI option 仍作为初始配置，不绕过公开 API 状态检查。

### 建议的首个 hook

优先在**自然 restart 完成后**结算上一窗口、更新 action。`restart()` 回溯并更新 restart limit 后返回，之后主循环会再次传播。不要在传播、冲突分析、watch 遍历或内存搬迁中途切换。[`internal.cpp::cdcl_loop_with_inprocessing`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/internal.cpp#L280-L338)、[`restart.cpp::restart`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/restart.cpp#L164-L177)

必须满足：

1. controller仅调整后续有效phase配置，不直接改已有赋值、理由、learned clauses或proof规则。轨道C保留已审计的rephase/likely_phase等副作用；只有轨道P限定为仅覆盖普通自由decision符号。
2. 收集特征只使用切换时已经发生的事件；窗口、action、stable 状态、冲突与 tick 起止值可追溯。
3. 没有新增强制 restart 时，原有 restart / mode schedule 保持原逻辑。不要把 `restarting()` 当成纯查询；它会调用 `stabilizing()`，可能改变 stable 状态。
4. **restart 不保证回到 level 0**。默认 `restartreusetrail=1` 会复用前缀，`reuse_trail()` 判断变量排序，没有检查新 action 下的相位。切换后旧前缀可能暂留，这是可接受但需记录的延迟生效语义。不能添加错误的 `assert(level==0)`。
5. 若实现“切换时一定清空旧决策”的版本，必须调用已有 backtrack 路径，正确保留 assumptions / constraint 语义；它是另一个实验因子。应同时给所有 baseline 施加同样的额外 restart 条件。
6. controller disabled / fixed action 时须复现相应原版配置；日志开启和关闭都检查正确性与运行开销。

## 6. Rephase 恢复和 stable / focused 的风险

force 模式会让 rephase 计数和 limit 停留，而 conflict 继续增长；切回非 force 后，若 limit 已过期，主循环可能很快执行 rephase，覆盖刚保存的相位。这是**原生门控推导出的行为**，不是“切回纯 saved”的保证。默认 `rephase=1` 以总 conflicts 为时间；`rephase=2` 仅在 stable 时以 `stats.stabconflicts` 判断。`rephase()` 设置下一 limit、复制 target 并通过 `rephased` 标记影响后续 backtrack；不要只清一个布尔值或只重置 limit。

主实验保留自然原生恢复语义，记录 `lim.rephase`、rephase 类型与距最近事件的间隔。若比较“暂停调度并延后恢复”或“恢复时重置”，预先定义新语义并单独消融，不能把它们藏在 controller 内。

stable / focused 不只有 phase 区别，还包括变量选择、restart 和各自的移动平均。`stabilizing()` 会切换模式并 swap averages。因此在线特征必须包含当前模式，分析分模式报告；不能把模式变化导致的指标变化全部归因于 forcephase。[`restart.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/restart.cpp#L18-L120)、[`backtrack.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/backtrack.cpp#L46-L75)

## 7. M0 必须交付的验证证据

- `git rev-parse HEAD`、VERSION、编译器/构建参数及 `rg -n 'forcephase|likely_phase|phases\.saved' src` 输出。
- 参数真值表的小公式/日志验证，明确检查裸 forcephase 为正，`phase=0 + forcephase` 为负；包含 API forced phase 优先级测试。
- 固定 action 回归：关闭 controller、固定 stock、固定负 force，分别与未修改二进制比对 SAT/UNSAT、决策路径摘要及资源计数。不要要求不同 treatment 走同一路径。
- 至少覆盖 rephase 到期时开关、stable/focused 切换、trail reuse、compaction、lucky 预求解；这些位置不应出现状态破坏。
- M0的独立correctness子集验证SAT model和UNSAT proof；最终测试的所有solved结果均须验证，不能仅凭M0子集给全部结果认证。正式性能主比较默认所有配置统一启用proof，生成成本计入solver时间，checker成本另报；资源受限替代方案与一致性要求见实验协议第8.1节。
- 性能清单同时报告 wall time、CPU time、conflicts、ticks、内存、日志量及 controller 时间；“conflicts 更少”不能直接当作“更快”。

## 8. 轨道 C 的完整配置动作：必须同时定义 `phase`

针对轨道 C，主动作可以明确采用：

| 动作 | 有效 `forcephase` | 有效 `phase` | 含义 |
|---|---:|---:|---|
| `NATIVE` | 0 | 1 | 使用原版默认的相位选取、rephase 及其正初始方向 |
| `NEGATIVE` | 1 | 0 | 使用原版强制负方向，并禁止 rephase |

运行时应在同一个安全 hook 一次更新完整 pair，确保 `decide_phase`、`likely_phase`、rephase 和数组初始化看到一致的有效配置。固定动作从 solver 初始化阶段、**读入 DIMACS/创建变量之前**就生效，才能与相应静态命令行基线对齐。在线策略可从 `NATIVE` 开始，之后在自然 restart 处切换；“此刻配置相同”不表示它会重现从头运行另一静态基线的历史。切换本身不应额外重写已有 saved / target / best 数组。

对已读取的全部 162 个 `src` 文件再次扫描，`opts.phase` 的直接读取只有四处：[`decide.cpp:126`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/decide.cpp#L125-L175)、[`rephase.cpp:41,53`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/rephase.cpp#L39-L58)、[`internal.cpp:147`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/internal.cpp#L123-L185)。其影响是：

- 决策中的 initial fallback、forcephase 方向，以及启用 `stubbornIOfocused` 时的 original / inverted 方向随 pair 改变；`likely_phase` 复用该逻辑，因此同样影响上述 GC 布局。
- `rephase_original` / `rephase_inverted` 使用当时有效的 `phase`。恢复 `NATIVE` 后若立即触发过期 rephase，它按正初始方向的原版语义执行，而固定 `phase=0` 的设计按负初始方向执行。
- `Internal::enlarge` 将 **新扩大的 saved 数组区间**初始化为当时 `opts.phase` 的符号；不会重置已有区间。`init_vars` 不逐个重设 saved，且数组采用扩容策略，因此稍后新启用的变量还可能使用以前已经初始化的空余槽位。若启用 factor/BVA、incremental 输入或外部 propagator 创建新变量，应记录 action 和扩容事件，并覆盖相关测试；不能假设“新变量必定按当前 action 初始化”。[`internal.cpp`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/internal.cpp#L123-L185)、[`util.hpp::enlarge_init`](https://github.com/arminbiere/cadical/blob/c60730422e758ef1cebe7aeddf2dda31c996bf04/src/util.hpp)

`lucky.cpp` 没有读取 `opts.phase`；其预设真/假试探方向不因完整 pair 直接改变，lucky 求解阶段也不经过普通相位选择来决定这些试探方向。固定动作的初始化要求仍然适用。上述完整 pair 会综合改变方向、调度、初始化等因素，属于**配置策略**；如要隔离“只改变普通决策符号”的作用，应保留 decision-only 消融。

另一种设计是固定 `phase=0`、只切换 `forcephase`。它的非 force 动作是 **init-negative native-like**：saved 的初始符号、original / inverted rephase 与 stock 默认不同。可作为次要对照，但不可称为 stock default / `NATIVE` 而不加限定。两种设计不得共用未区分的策略标签。
