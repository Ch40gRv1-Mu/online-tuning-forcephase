# LPN 稀疏 secret：forcephase 什么时候真正有用

一个自包含、可在 Linux/slurm 或 macOS 上一条命令跑完的机制实验。它和主研究（`reports/FINAL_REPORT.md`）使用同一个 CaDiCaL pin（`c607304`，3.0.1）和同样的配置语义，但所有代码都在本目录内，不改动仓库其余文件。

**English summary.** On SAT Competition instances, forced-negative branching (F− = `--phase=0 --forcephase=1`) is almost never better than CaDiCaL's native phase policy (D). We construct a cryptographic family where it should be: LPN instances whose secret s is very sparse (weight k = 3), while the noise e is dense enough (rate 1/5 or 1/4) to keep the problem hard. In the "implicit" encoding the sparsity of s appears only in the solution, never in the constraints, so D cannot learn it by propagation and phase saving, while F− assumes it at every decision. Two controls test the mechanism: "explicit" writes wt(s) ≤ k into the CNF (F−'s prior becomes redundant), and "implicitflip" negates every s literal (the same problem with a dense solution, so F+ should win and F− should lose). An exploratory 20 s test gave solved counts of D 2/16, F− 10/16, I− 2/16. The formal grid and its predictions Q1–Q5 are pre-registered below.

## 1. 研究问题

主研究的结论是：在竞赛实例上，强制负分支 F− 几乎处处不如原生默认 D（见 `reports/FINAL_REPORT.md`；分支 `research/forcephase-study` 上的独立 M2 复现结果也一致）。这个实验反过来问：

> **F− 在什么条件下会稳定地胜过 D？** 我们的假说：当解在当前编码下大多是 0，**而且这条信息不在约束里**时。

“不在约束里”是关键。如果稀疏性写在约束里，例如 wt(e) ≤ t，D 会通过 propagation 和 phase saving 自己学到：一旦计数到 t，其余变量就被推成 0，phase saving 再把 0 记下来。我们在 syndrome 编码的预实验中观察到了这一点（第 6 节）。这时 F− 的先验是多余的，还要额外承担关闭 rephase 和强制辅助变量的代价。

## 2. 问题定义

参数：secret 长度 n，样本数 m，噪声重量 w，噪声上界 t，secret 重量 k。

- A ∈ GF(2)^{m×n} 均匀随机。
- **planted**：s 是重量恰为 k 的随机向量，e 是重量恰为 w 的随机向量，y = A·s ⊕ e。按构造必为 SAT，且解基本唯一（见第 4 节）。
- **random**：y 均匀随机。大概率 UNSAT，作为对照。

SAT 问题是：

    存在 s ∈ GF(2)^n, e ∈ GF(2)^m，使得 A·s ⊕ e = y 且 wt(e) ≤ t
    （explicit 编码另加 wt(s) ≤ k）

这是 secret 服从噪声分布的 LPN：经过 Hermite normal form 变换后，标准 LPN 的 secret 就服从噪声分布。在 LWE 上，这一形式与标准形式同样难（Applebaum–Cash–Peikert–Sahai 2009）。这里的 secret 比噪声稀疏得多：k = 3，而噪声率是 1/5 或 1/4。

## 3. 三种 CNF 编码（`lpn_gen.py::encode`）

变量编号：e₁..e_m 是变量 1..m，s₁..s_n 是变量 m+1..m+n，之后是辅助变量。

| 编码 | 约束 | s 的稀疏性 | 用途 |
|---|---|---|---|
| `implicit` | 每行一个 XOR：eᵢ ⊕ (⊕_{j: A_ij = 1} s_j) = yᵢ；加 wt(e) ≤ t | **只体现在解里** | 主格：F− 的先验在这里是新信息 |
| `explicit` | implicit 再加 wt(s) ≤ k | 写进约束 | D 能通过 propagation 学到，F− 的优势应大幅缩小 |
| `implicitflip` | implicit 中所有 s literal 取反（s′ = ¬s） | 解在 s′ 上稠密 | 镜像反证：F+ 应该赢，F− 应该输 |

构造细节：

- **XOR**：按每块 ≤ 4 个变量切开，x₁⊕x₂⊕x₃⊕a = 0 中的 a 是新的 Tseitin 辅助变量；每块用 2^{k−1} 条 clause 禁止所有奇偶性错误的赋值。
- **基数约束**：用 Sinz sequential counter 编码，辅助变量 r_{i,j} 表示“前 i 个变量中至少 j 个为 1”（单向蕴含）。
- **flip**：只做 literal 取反，逻辑问题完全不变。

正确性由三层保证：

1. `test_reduction.py` 在小规模上穷举所有 wt(e) ≤ t（explicit 还穷举所有 wt(s) ≤ k）作为 ground truth，与 D、F− 的求解结果对照。目前 768 次求解全部一致：SAT model 通过 LPN 语义检查，UNSAT 通过 lrat-check。其中也覆盖了第 6 节用到的 syndrome 编码族。
2. 每个 SAT 答案都会被 `lpn_check.py` 独立解码，直接检查 A·s ⊕ e = y 和重量约束。
3. 每个 UNSAT 答案都会被 `verify_runs.py` 用同一二进制加 `--lrat` 复跑，并由 lrat-check 验证。

## 4. 实例与参数（预注册网格 `sparse_main`）

| τ_e | n | m | t = w | k | log2 E[#伪解]（implicit / explicit） |
|---|---:|---:|---:|---:|---|
| 1/5 | 24 / 32 / 40 / 48 | 4n | round(m/5) = 19 / 26 / 32 / 38 | 3 | −6.0 / −5.9 / −7.8 / −9.6；explicit ≤ −18.8 |
| 1/4 | 24 / 32 / 40 / 48 | 6n | round(m/4) = 36 / 48 / 60 / 72 | 3 | −6.3 / −7.6 / −8.8 / −10.0；explicit ≤ −19.1 |

- “伪解”指 planted 解之外的解（稠密 s 加上重量 ≤ t 的 e）。m 的取值保证其期望个数 ≪ 1，否则 D 可能直接找到伪解。
- 每格 seed 10–19，kind 为 planted 和 random，三种编码共 480 个实例。同一 (τ_e, n, kind, seed) 的三种编码共享同一个 (A, y)，按配对实例分析。
- 实例由 Python `random.Random(<参数字符串>)` 确定性生成。`run_all.sh` 会把生成的 CNF 与 `benchmarks/expected/lpn_sparse_main.sha256.jsonl` 对比，任何不一致都直接停止。已在 Python 3.11 和 3.12 上确认 480/480 一致。

## 5. 配置与预注册预测

配置（命令行见 `fplib.py::CONFIGS`）：

| 名称 | 参数 | 作用 |
|---|---|---|
| D | `--phase=1 --forcephase=0` | 原生默认 |
| I− | `--phase=0 --forcephase=0` | 只改初始符号，保留 phase saving 和 rephase |
| F− | `--phase=0 --forcephase=1` | 持续强制负，并关闭 rephase |
| F+ | `--phase=1 --forcephase=1` | 持续强制正 |
| I−/no-R | `--phase=0 --forcephase=0 --rephase=0` | 关闭 rephase，但不强制；用于分离“强制”与“关 rephase” |

共同参数是 `--stats --seed=0 -t T`，T = 120 s。主指标是子进程 CPU 时间：只有在 T 内答出、CPU ≤ T 且通过验证的运行才算 solved，未解出的 cost 记为 2T。

**指标**：逐实例 r_X = log2((c_X + 0.1)/(c_D + 0.1))，取实例中位数，95% CI 用 10,000 次 bootstrap。判定规则：

- **supported**：方向与预测一致，且 CI 不含 0；
- **contradicted**：方向相反，且 CI 不含 0；
- 其余为 **not supported**。

**预测**（2026-10-21 在任何正式结果之前登记，见 `PREREGISTRATION.md`）：

| # | 预测 |
|---|---|
| Q1 | implicit + planted：F− 快于 D |
| Q2 | 逐实例配对差 d = r_F−(explicit) − r_F−(implicit) > 0，即把稀疏性写进约束后 F− 的优势缩小 |
| Q3 | implicitflip + planted：F+ 快于 D，**且** F− 慢于 D（关键反证格） |
| Q4 | random：F− 的效应小于对应的 planted，且没有一致优势 |
| Q5（探索性） | F− vs I−（初始符号）；F− vs I−/no-R（持续强制 vs 关 rephase） |

**已事先说明的局限**：

- 如果 D 在 implicitflip 上也大多超时，删失会让 r_F− = 0，Q3 的 F− 部分只能判为 not supported。因此报告同时给出 solved 数。
- 如果 random 上所有配置都超时，Q4 只是空洞成立，会标注 vacuous。

## 6. 已有证据（本机 Apple M4 Pro，均为探索性）

| 实验 | 设置 | 结果 |
|---|---|---|
| syndrome 编码 dry run | 稀疏性**写在约束里**（He = Hy，wt(e) ≤ t），n = 16–40，T = 20 s | F− 无优势：syndrome + planted 的 PAR2 为 D 0.47、F− 0.56。诊断显示 D 在 e 上的 decision 有约 79% 取 0，即 D 自己学到了稀疏性 |
| 稀疏 secret dry run，τ = 1/8 | e 很稀疏（m = 3n，t = m/8），k = n/8，T = 20 s | Q1 方向一致但 CI 含 0（中位比值 ×0.62）；Q2 supported（d = +1.37，CI [+0.20, +3.85]） |
| **quick test** | implicit + planted，τ_e ∈ {1/5, 1/4}，k = 3，n = 24–48，2 个 seed，T = 20 s | **solved：D 2/16，F− 10/16，I− 2/16**；所有解出的 e 都等于 planted 解 |

quick test 的逐实例结果见 `results/PRIOR_RESULTS.md`。I− 和 D 一样差，说明收益来自持续强制而不是初始符号；正式网格中的 I−/no-R 用来进一步分离“强制”和“关 rephase”。

## 7. 运行方法

需要：Python ≥ 3.10（只用标准库；画图需要 matplotlib，没有则跳过）、C 编译器、git。

```bash
# 端到端检查，约 2–5 分钟：构建、归约测试、24 个小实例、校验、分析
GRID=smoke T=10 experiments/lpn_sparse_secret/run_all.sh

# 正式网格：480 个实例 × 5 个配置 × 120 s，最坏 80 核时
WORKERS=46 experiments/lpn_sparse_secret/run_all.sh
```

- **solver**：优先用 `build/upstream/cadical`（即 `scripts/build_solver.sh upstream` 的产物，同一 pin）；没有则从 `third_party/cadical` 子模块或 GitHub 拉取 pinned 源码自行构建（不加 `-static`，可在 macOS 上编译）。lrat-check 来自 `third_party/drat-trim`（pin `2e3b2dc`）。构建信息写在 `$LPN_WORK/bin/BUILDINFO`。
- **工作目录**：`LPN_WORK`，默认 `$FP_DATA/lpn_sparse_secret`（没有 `FP_DATA` 时为 `~/lpn-sparse-secret-work`），用于存放二进制、CNF、原始日志和临时 proof。仓库内只写 `results/<EXP>/` 下的小型账本和汇总。
- **顺序与上限**：先 planted（Q1–Q3），再 random（Q4）。每轮受 `MAX_WALL_HOURS`（默认 5）限制，每轮之后自动续跑一次（上限 1 小时），用于重跑受争用的运行并补齐被截断的部分。重复执行 `run_all.sh` 是幂等的：已完成的运行会被跳过。
- **计时有效性**：wall/CPU > 1.10 的运行判为受争用（contended），作废并重跑，最多 3 次。在独占节点上可以把 `QUIET_LOAD` 设得很大来关闭等待。本 runner 不做 CPU 绑定。
- **slurm 示例**（仿照 `scripts/slurm_submit.sh`，未在集群上测试过）：

```bash
sbatch --partition=cpu-low --nodes=1 --ntasks=1 --exclusive --mem=0 --time=12:00:00 \
  --wrap "source /mnt/data/shared/config/env.sh; gs-srun --ntasks=1 --cpus-per-task=\$SLURM_CPUS_ON_NODE \
          bash -c 'cd $PWD && WORKERS=46 QUIET_LOAD=1000 experiments/lpn_sparse_secret/run_all.sh'"
```

**输出**：

| 文件 | 内容 |
|---|---|
| `results/<EXP>/runs.jsonl` | 每次运行一条记录，只追加 |
| `results/<EXP>/lpn_semantic.jsonl` | SAT 答案的 LPN 语义检查 |
| `results/<EXP>/verify.jsonl` | model 校验和 LRAT 认证复跑 |
| `results/<EXP>/predictions.md` / `.json` | Q1–Q5 判定与各格表 |
| `results/<EXP>/effects.png` | 各配置相对 D 的效应图 |

## 8. 文件

| 文件 | 作用 |
|---|---|
| `run_all.sh` | 一条命令跑完全流程 |
| `build.sh` | 准备 cadical 和 lrat-check |
| `lpn_gen.py` | 采样、三种（以及预实验用的 syndrome/flipe/secret）编码、网格定义、语义检查 |
| `test_reduction.py` | 与穷举对照的归约正确性测试 |
| `run_matrix.py` | 可续跑的 runner（含 contended 检测、wall-clock 与核时上限） |
| `lpn_check.py` | SAT 答案的 LPN 语义检查 |
| `verify_runs.py` | model 校验与 LRAT 认证复跑 |
| `analyze.py` | Q1–Q5 分析 |
| `fplib.py` | 配置、DIMACS、solver 调用、checker |
| `PREREGISTRATION.md` | 预注册记录（按时间顺序，摘自实验日志） |
| `results/PRIOR_RESULTS.md` | 第 6 节的探索性结果明细 |
