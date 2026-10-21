# 预注册记录（LPN 机制实验）

以下条目按时间顺序原样摘自作者本地分支的 `reports/EXPERIMENT_LOG.md`，每条都在对应结果出现之前写下。正式网格 `lpn_sparse_main` 的预注册最早于 2026-10-21 20:20（UTC+8）提交在本地分支；本文件随本分支提交时，正式网格还没有任何结果。文中路径指原仓库布局（`scripts/`、`tests/`、`benchmarks/`），在本目录下对应的文件同名（`tests/test_lpn_reduction.py` 对应 `test_reduction.py`，`analyze_lpn_sparse.py` 对应 `analyze.py`）。

## 2026-10-21 · LPN 机制实验：dry run（只做流水线检查与规模校准，不下结论）

- 动机（用户提出）：在 LPN 的 syndrome-decoding 编码里，解 e 是稀疏的（wt(e) ≤ t 很小），预期强制负分支 F− 应优于 D。实验目的是检验“F− 的效果取决于解在该编码下是否稀疏”。
- 实现：`scripts/lpn_gen.py`。实例 (A, y)：planted 为 y = As + e，wt(e) = w；random 为 y 均匀随机。SAT 问题是“存在 wt(e) ≤ t 且 y+e ∈ colspace(A)”。三种编码：`syndrome`（He = Hy，H 为系统型 parity-check）、`secret`（显式 s，eᵢ = yᵢ ⊕ ⟨aᵢ, s⟩）、`flipe`（syndrome 编码中所有 e literal 取反，逻辑问题不变，但 planted 解变成稠密）。XOR 按 ≤4 变量切块并引入 Tseitin 辅助变量；wt(e) ≤ t 用 Sinz sequential counter。
- 归约正确性：`tests/test_lpn_reduction.py` 在 n ≤ 7、m ≤ 14 的 64 个 (A, y) × 3 种编码 × {D, F−} 上，与穷举结果全部一致：384 次求解，270 个 SAT model 通过独立的 LPN 语义检查（wt(e) ≤ t 且 y+e ∈ colspace(A)），114 个 UNSAT 通过 lrat-check。
- dry-run 网格：(n, m, t) ∈ {(16,32,3), (24,48,4), (32,64,5), (40,80,6)}，w = t，3 种编码 × {planted, random} × seed 0–2，共 72 个实例；配置 D、I−、F−、F+、I−/no-R；T = 20 s；8 worker，`--quiet-load 13`。对 random y，log2 E[#解] 分别为 −3.6 / −6.3 / −9.0 / −11.8，因此预期为 UNSAT。
- 用途：只用于确认流水线跑通、确定正式网格的规模，使 D 的耗时大致落在 1–300 s。**不以 dry run 的胜负挑选正式实验的规模或编码**；正式实验的网格与预测（P1–P5）在看到 dry run 的按配置比较之前另行登记，dry run 只用其各配置合并后的耗时分布来定规模。
- 数据泄漏处理：GBD test 划分中有 17 个 `minimum-disagreement-parity`（与 LPN 同类）。自造 LPN 实例只作为机制实验，不参与 M3 以后的方法选择；M5 报告中把该 family 标注为 seen family。

## 2026-10-21 · LPN dry run 结果（只看合并统计）与正式网格提案（在查看按配置比较之前登记）

- dry run：360 个运行，无 contended；150 个 SAT 全部通过 LPN 语义检查和 model 校验，150 个 UNSAT 全部通过 LRAT；planted 上无 UNSAT。
- 按配置合并后的规模校准：syndrome 和 flipe 在 n=40 时中位数 2–5 s，n=32 时约 0.1–0.3 s；secret 在 n=24 时约 7–12 s，n ≥ 32 在 20 s 内全部未解出。random 约为 planted 的 2 倍。（为定规模，合并视图按编码拆开，但始终合并全部配置。）
- **正式网格（提案，待用户确认后运行）**：
  - syndrome 与 flipe：(n, m, t) ∈ {(40,80,6), (44,88,7), (48,96,7), (52,104,8)}；secret：{(20,40,4), (24,48,4), (28,56,5)}。w = t。对 random y，log2 E[#解] ∈ [−14.4, −3.4]；(20,40,4) 为 −3.4，可能有少量 random 实例是 SAT，由语义检查处理并单独报告。
  - kind：planted / random；seed 0–9（新的 seed 范围 10–19，避免与 dry run 重叠）；配置 D、I−、F−、F+、I−/no-R；T = 120 s；最坏 1100 × 120 s = 36.7 核时。
  - 分组：同一 (n, m, t, kind, seed) 的三种编码共享同一 (A, y)，视为同一逻辑实例（同一 bootstrap 组）。
- **预注册预测**（主指标：逐实例 log2(cost_X / cost_D)，以及 PAR2；按实例组做 bootstrap）：
  - P1：syndrome + planted 上 F− 快于 D（中位 log-ratio < 0，CI 不含 0）。
  - P2：flipe + planted 上镜像：F+ 快于 D，F− 慢于 D。
  - P3：secret + planted 上 F− 相对 D 的优势小于 syndrome，或不存在。
  - P4：random（UNSAT）上 F− 的效应量小于对应的 planted，且无一致优势。
  - P5（探索性，无方向）：I− 与 F− 的比较，用于区分“初始符号”和“持续强制”。
  - 对称性检查：syndrome 上的 F− 与 flipe 上的 F+ 应近似相等（同一逻辑问题、同一相对极性；CaDiCaL 其余启发式并非完全极性对称，因此只要求近似）。

## 2026-10-21 · LPN 正式网格启动与分析细节（在任何正式结果出来之前）

- 用户确认按登记的网格运行：`lpn_main`，220 个实例 × 5 个配置 × 120 s，8 worker，`--quiet-load 13`。启动前清理了一个残留的诊断用 logging 进程。
- 分析实现（`scripts/analyze_lpn_predictions.py`）：逐实例 r_X = log2((c_X + 0.1)/(c_D + 0.1))，未解出（或未通过验证/语义检查）记 c = 2T，双方都未解出时 r = 0。效应量取实例中位数，95% CI 用 10,000 次实例 bootstrap（seed 20261021）。判定："supported" 表示 CI 不含 0 且方向与预测一致；"contradicted" 表示 CI 不含 0 但方向相反；其余为 "not supported"。+0.1 s 的 offset 沿用 M2 探索分析，用于抑制毫秒级实例的比值噪声。
- dry run 中的诊断（探索性，logging 版，n=32/40 的 syndrome planted 实例各 1 个）：decision 有 57–70% 落在 e 上；D 在 e 上约 79% 取 0，说明 phase saving 加上 counter 的 propagation 已经让 D 学到 e 多为 0。

## 2026-10-21 · 暂停 `lpn_main`，转向稀疏 secret（隐式稀疏）dry run

- 用户要求先做稀疏 secret 的 dry run。为避免两组实验争用 CPU，暂停 `lpn_main`（已记录 153/1100 个运行，其中 1 个 contended；在途运行未写入账本，续跑时会原样补齐）。
- 事故与修复：给生成器加 k 参数时，CNF 头部注释多写了 `k=None`，重新生成后覆盖了 dry 和 main 的 CNF（逻辑内容不变，字节改变）。已把 k=None 时的注释格式恢复为原样并重新生成，292 个文件的 SHA-256 与已提交的记录全部一致。manifest 多了一列空的 `k`。
- 同时清理了三个残留的等待循环 shell：它们的命令行包含自己 `pgrep -f` 的模式，导致永远自匹配、永不退出。之后改用 `[r]un_matrix` 写法。
- runner 新增 `--max-wall-hours` 整体 wall-clock 上限；每个 solver 运行仍带 `-t T`，并在 T+30 s 硬杀。

## 2026-10-21 · 稀疏 secret 机制实验：设计与预注册预测（在任何稀疏 secret 运行之前）

- 动机：syndrome 实验显示，wt(e) ≤ t 写在约束里时，D 能通过 propagation 加 phase saving 自己学到“e 多为 0”。为检验“F− 的价值取决于稀疏性是否已写进约束”，让稀疏性只出现在解里：planted secret 的重量恰为 k，相当于 HNF 变换后 secret 服从噪声分布的 LPN。
- 编码（变量顺序：先 e，后 s，再辅助变量）：`implicit`（secret 编码，只约束 wt(e) ≤ t，s 不加约束）、`explicit`（implicit 加 wt(s) ≤ k）、`implicitflip`（implicit 中所有 s literal 取反，planted 解在 s′ 上稠密）。按用户意见**不做 noiseless**，噪声率为常数 τ = 1/8：m = 3n，w = t = round(m/8)，k = round(n/8)。对 random y，log2 E[#解]：implicit 在 −8.2 到 −17.7 之间，explicit 在 −17.1 到 −38.2 之间。
- 归约正确性：`tests/test_lpn_reduction.py` 增加 4 个规模 × {planted, random} × 8 个 seed × 3 种编码 × {D, F−}，全部与穷举一致（全测试合计 768 次求解；512 个 SAT 语义检查通过，256 个 UNSAT LRAT 通过）。
- dry run（`lpn_sparse_dry`）：n ∈ {16, 24, 32, 40}，3 种编码 × {planted, random} × seed 0–2，共 72 个实例；配置 D、I−、F−、F+、I−/no-R；T = 20 s；`--max-wall-hours 1`。只用于流水线检查和规模校准；规模先按合并全部配置的视图确定。
- **预注册预测**（用于之后的正式稀疏网格；指标与判定同 `analyze_lpn_predictions.py`）：
  - Q1：implicit + planted 上 F− 快于 D。
  - Q2：explicit + planted 上 F− 相对 D 的优势小于 implicit（差值 CI 不含 0）。这是检验“信息已写进约束”的关键格。
  - Q3：implicitflip + planted 上镜像：F+ 快于 D，F− 慢于 D。这是关键反证格。
  - Q4：random（多为 UNSAT）上 F− 的效应量小于对应的 planted，且无一致优势。
  - Q5（探索性）：I− 与 F− 的比较，区分“初始符号”和“持续强制”。

## 2026-10-21 · 稀疏 secret 设计调整（用户意见，在看到任何稀疏 secret 结果之前）

- 用户意见：e 不应太稀疏，这样 LPN 本身足够难；s 要足够稀疏，这样 F− 的先验有用。因此把 e 的噪声率与 s 的重量分开设定。
- 新 dry-run 网格 `sparse_dry2`：τ_e = 1/5（m = 4n）和 τ_e = 1/4（m = 6n），w = t = round(τ_e·m)；secret 重量固定 k = 3；n ∈ {24, 32, 40, 48}；3 种编码 × {planted, random} × seed 0–1，共 96 个实例；配置与限时同前（T = 20 s，`--max-wall-hours 1`）。m 的选取保证 implicit 的 log2 E[#伪解] ≤ −5.9（explicit ≤ −18.8）。
- 正在运行的 `lpn_sparse_dry`（τ = 1/8，k = n/8）照常跑完，作为“e 很稀疏”的对照点。
- 预测 Q1–Q5 不变，适用于基于 `sparse_dry2` 校准后的正式网格。
- 用户要求先快速测试核心想法：`lpn_quick_implicit` 只取 `sparse_dry2` 中的 implicit + planted（16 个实例：τ_e ∈ {1/5, 1/4}，n ∈ {24, 32, 40, 48}，k = 3，seed 0–1），配置 D、F−、I−，T = 20 s，`--max-wall-hours 0.25`。用户预测：F− 能解且很快，D 基本超时。属于探索性快速检验，结论待正式网格确认。
- `lpn_quick_implicit` 结果（探索性）：20 s 内解出数 D 2/16、F− 10/16、I− 2/16；所有解出的 e 都等于 planted 解，14 个 SAT 答案全部通过语义检查和 model 校验。F− 超时集中在最大的几格（τ_e = 1/4 且 n ≥ 32，以及 τ_e = 1/5 且 n = 48）。I− 与 D 一样差，说明收益来自持续强制而不是初始符号；“持续强制”与“关闭 rephase”两者尚未分离，需要 I−/no-R 对照。
- `lpn_sparse_dry`（τ = 1/8）已跑完 360 个运行，语义检查和校验均已完成，尚未做分析。

## 2026-10-21 · 稀疏 secret 正式网格 `lpn_sparse_main`（预注册，运行前）

- 网格（`lpn_gen.py --grid sparse_main`）：编码 implicit / explicit / implicitflip；τ_e = 1/5（m = 4n）和 τ_e = 1/4（m = 6n）；n ∈ {24, 32, 40, 48}；w = t = round(τ_e·m)；k = 3；kind 为 planted 和 random；seed 10–19（与 dry run 的 0–2 和 quick test 的 0–1 不重叠）。共 480 个实例。
- 配置：D、I−、F−、F+、I−/no-R；T = 120 s；8 worker；`--quiet-load 13`；contended 规则同前。
- 顺序与上限：第一轮 planted（1200 个运行，最坏 40 核时，`--max-wall-hours 5`），随后重跑其中的 contended 运行；第二轮 random（同样规模，`--max-wall-hours 5`），随后重跑 contended。若某轮被上限截断，缺失的运行如实报告为 missing、不做插补；分析只使用 5 个配置都齐全的实例。
- 配对：sample() 与编码无关，所以同一 (τ_e, n, kind, seed) 的三种编码共享同一个 (A, y)，作为同一逻辑实例（bootstrap 的同一组）。
- 指标：r_X = log2((c_X + 0.1)/(c_D + 0.1))；c = CPU 秒数，未解出或未通过验证/语义检查记 2T；双方都未解出时 r = 0。取实例中位数，95% CI 用 10,000 次 bootstrap。主分析合并全部 τ_e 和 n，次要分析按 τ_e、按 n 分别报告。
- 预测（与 Q1–Q5 一致，具体化如下）：
  - Q1：implicit + planted 上 median r_F− < 0，且 CI 不含 0。
  - Q2：逐实例配对差 d = r_F−(explicit) − r_F−(implicit)（planted），median d > 0，且 CI 不含 0。
  - Q3：implicitflip + planted 上 r_F+ < 0 且 r_F− > 0，两者 CI 都不含 0。**事先说明的局限**：如果 D 在 flip 编码上也大多超时，删失会使 r_F− = 0，判定只能是 not supported；此时同时报告 solved 数。
  - Q4：random 上每种编码的 |median r_F−| 小于对应 planted，且 F− 无一致优势（CI 上界 ≥ 0）。**事先说明**：如果 random 上所有配置都超时，Q4 只是空洞成立，会标注 vacuous。
  - Q5（探索性）：r(F− vs I−) 与 r(F− vs I−/no-R)。后者用于分离“持续强制”与“关闭 rephase”。
