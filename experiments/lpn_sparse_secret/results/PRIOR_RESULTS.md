# 已有的探索性结果（本机 Apple M4 Pro，macOS，8 worker）

这些都是 dry run 或快速检验，不是正式结论；正式结论以 `sparse_main` 网格为准。所有数字由原分支的分析脚本从原始账本生成；所有 SAT 答案都通过了 LPN 语义检查，所有 UNSAT 答案都通过了 LRAT 校验。

## 1. Quick test：implicit + planted，k = 3，T = 20 s（`lpn_quick_implicit`，seed 0–1）

| τ_e | n | m | t | seed | D | F− | I− |
|---|---:|---:|---:|---:|---|---|---|
| 1/5 | 24 | 96 | 19 | 0 | timeout | 13.53 s | timeout |
| 1/5 | 24 | 96 | 19 | 1 | timeout | 0.04 s | timeout |
| 1/5 | 32 | 128 | 26 | 0 | timeout | 1.54 s | timeout |
| 1/5 | 32 | 128 | 26 | 1 | timeout | 1.30 s | timeout |
| 1/5 | 40 | 160 | 32 | 0 | timeout | 4.58 s | timeout |
| 1/5 | 40 | 160 | 32 | 1 | timeout | timeout | timeout |
| 1/5 | 48 | 192 | 38 | 0 | timeout | timeout | timeout |
| 1/5 | 48 | 192 | 38 | 1 | timeout | 19.34 s | timeout |
| 1/4 | 24 | 144 | 36 | 0 | 13.55 s | 0.15 s | 14.05 s |
| 1/4 | 24 | 144 | 36 | 1 | timeout | 0.07 s | timeout |
| 1/4 | 32 | 192 | 48 | 0 | timeout | timeout | timeout |
| 1/4 | 32 | 192 | 48 | 1 | 2.12 s | 3.22 s | 10.55 s |
| 1/4 | 40 | 240 | 60 | 0 | timeout | timeout | timeout |
| 1/4 | 40 | 240 | 60 | 1 | timeout | 4.54 s | timeout |
| 1/4 | 48 | 288 | 72 | 0 | timeout | timeout | timeout |
| 1/4 | 48 | 288 | 72 | 1 | timeout | timeout | timeout |

20 s 内解出：D 2/16，F− 10/16，I− 2/16。

## 2. 稀疏 secret dry run，τ = 1/8（`lpn_sparse_dry`：m = 3n，t = round(m/8)，k = round(n/8)，n = 16–40，seed 0–2，T = 20 s）

这一组的 e 很稀疏，与正式网格不同。

| prediction | effect [95% CI] | verdict |
|---|---|---|
| Q1 implicit+planted: F− vs D | -0.69 [-3.34, +0.00] (×0.62) | not supported (CI includes 0) |
| Q1 (τ_e = 1/8) | -0.69 [-3.34, +0.00] (×0.62) | |
| Q2 paired d = r(explicit) − r(implicit), n=12 | +1.37 [+0.20, +3.85] (×2.59) | supported |
| Q2 explicit+planted: F− vs D | +0.00 [-0.50, +0.03] (×1.00) | |
| Q3 implicitflip+planted: F+ vs D | -0.04 [-1.41, +0.00] (×0.97) | not supported (CI includes 0) |
| Q3 implicitflip+planted: F− vs D (predicted slower) | +0.00 [+0.00, +0.56] (×1.00) | not supported (CI includes 0) |
| Q4 implicit random: F− vs D (planted -0.69) | +0.00 [+0.00, +0.00] (×1.00) | supported |
| Q4 explicit random: F− vs D (planted +0.00) | -0.01 [-0.04, +0.00] (×1.00) | not supported |
| Q4 implicitflip random: F− vs D (planted +0.00) | +0.00 [+0.00, +0.00] (×1.00) | not supported |

## 3. Syndrome 编码 dry run（稀疏性写在约束里；`lpn_dry`，m = 2n，n = 16–40，seed 0–2，T = 20 s）

PAR2（秒），全部规模合并：

| enc | kind | D | I− | F− | F+ | I−/no-R |
|---|---|---:|---:|---:|---:|---:|
| flipe | planted | 0.68 | 0.49 | 0.51 | 0.28 | 0.57 |
| flipe | random | 1.39 | 1.29 | 0.80 | 1.30 | 1.32 |
| secret | planted | 22.83 | 21.96 | 21.89 | 21.58 | 21.19 |
| secret | random | 23.20 | 23.00 | 22.87 | 22.64 | 22.62 |
| syndrome | planted | 0.47 | 0.42 | 0.56 | 0.57 | 0.58 |
| syndrome | random | 1.26 | 1.27 | 1.31 | 0.78 | 1.31 |

诊断（logging 版 CaDiCaL，syndrome + planted 各 1 个实例；n=40 只看前 20k 个 conflict）：decision 有 57–70% 落在 e 上；D 在 e 上的 decision 约 79% 取 0，说明 D 通过 counter 的 propagation 和 phase saving 自己学到了 e 多为 0。

