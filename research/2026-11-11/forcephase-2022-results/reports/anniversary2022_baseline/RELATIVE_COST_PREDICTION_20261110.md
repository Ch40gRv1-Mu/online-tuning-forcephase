# 求解前预测 D、F+、F− 谁更快

按照用户暂不使用短搜索的方向，已完成全部静态预测比较。原输入特征只来自 CNF 结构，目标为原有 CaDiCaL seed0、T600 的已观测求解成本及超时惩罚。没有新求解和求解前缀。完整人口为官方过滤后的4,719道2022 Anniversary开发题。

## 主要结果

本轮相对回归树在六项已有 SCC/极性特征上，粗结构四折的PAR2降幅为 **0.0425%**，净多解 **1**，精确结构块区间 **[−0.0093%, +0.1650%]**。细形态五折降 **0.1212%**，净多解 **2**，区间跨零。最终开发内标定对这一表示选择直接D，已保存这一失败候选的模型和标定结果。

22维CNN池化结构上的相对回归，在细形态留出降0.3328%、多解6，但粗结构仅降0.0014%、解题数相同。完整人口28维GBD通用特征即便按免费采集计费，粗结构相对回归也与D几乎相同。因此本轮尚未取得稳定优于D的静态预测器。

## 全部冻结比较

下表成本增幅为正表示比D更慢或超时惩罚更高。GBD行假设特征采集免费，计入实测热推理；池化行复用实测原CNF编码费用；rule6行复用两份实测提取收据之和，其合并入口尚未逐题重测。三类费用边界保留，不能合并称端到端实测。

| 分组、表示、模型 | 平均PAR2秒 | 解出 | PAR2相对D增幅 | 增幅95%结构区间 |
|---|---:|---:|---:|---|
| D | 392.543 | 3385 | 0 | — |
| coarse_gbd_full_free_ridge_relative | 413.285 | 3299 | +5.2842% | [+1.6392%, +9.4951%] |
| coarse_gbd_full_free_trees_absolute | 392.543 | 3385 | +0.0002% | [+0.0000%, +0.0003%] |
| coarse_gbd_full_free_trees_relative | 392.544 | 3385 | +0.0002% | [+0.0001%, +0.0003%] |
| coarse_pooled_costed_ridge_relative | 395.620 | 3372 | +0.7839% | [+0.0801%, +2.0123%] |
| coarse_pooled_costed_trees_absolute | 392.752 | 3384 | +0.0534% | [-0.0000%, +0.1282%] |
| coarse_pooled_costed_trees_relative | 392.537 | 3385 | -0.0014% | [-0.0055%, +0.0023%] |
| fine_gbd_full_free_ridge_relative | 392.645 | 3384 | +0.0262% | [-0.0542%, +0.1378%] |
| fine_gbd_full_free_trees_absolute | 392.050 | 3387 | -0.1254% | [-0.3393%, +0.0026%] |
| fine_gbd_full_free_trees_relative | 392.261 | 3385 | -0.0716% | [-0.3742%, +0.2810%] |
| fine_pooled_costed_ridge_relative | 395.482 | 3372 | +0.7487% | [-0.2474%, +2.8267%] |
| fine_pooled_costed_trees_absolute | 392.543 | 3385 | -0.0000% | [-0.0000%, -0.0000%] |
| fine_pooled_costed_trees_relative | 391.236 | 3391 | -0.3328% | [-0.7902%, -0.0295%] |
| coarse_rule6_costed_ridge_relative | 395.769 | 3370 | +0.8218% | [-0.2110%, +2.4147%] |
| coarse_rule6_costed_trees_absolute | 392.876 | 3384 | +0.0848% | [-0.0000%, +0.2038%] |
| coarse_rule6_costed_trees_relative | 392.376 | 3386 | -0.0425% | [-0.1650%, +0.0093%] |
| fine_rule6_costed_ridge_relative | 392.374 | 3386 | -0.0429% | [-0.3037%, +0.2267%] |
| fine_rule6_costed_trees_absolute | 392.310 | 3386 | -0.0591% | [-0.2053%, +0.0027%] |
| fine_rule6_costed_trees_relative | 392.067 | 3387 | -0.1212% | [-0.3398%, +0.0124%] |

相对树与绝对成本树使用同一输入、64棵树、深度上限6、叶子下限32。相对树预测 PAR2(D)−PAR2(F±)，绝对树预测三个PAR2再比较。Ridge使用同输入、固定alpha10作为线性对照。粗结构线性外推出现明显误选成本，保留全部负结果。三动作都超时的题在相对目标中为零差额，未伪造赢家。

四折粗簇和五折细形态划分沿用CNN冻结表，GBD等价组不跨折，内层20%形态组独立标定一个收益门槛。门槛及是否关闭特征仅由内层成本选择。选择有限门槛时，预测后决定D也收取已发生的编码和推理费用。关闭模型的折会直接D并省略特征，公开记录其选择。零门槛原始动作也单独保留，未按外层表现选为主结果。

rule6为SCC非二元需求、该量的资格标志、平均子句长度、纯正比例、纯负比例和二元比例。它明确复用既有正向机制。资源资格覆盖2,843题，其余1,876题回退D并计入全人口。原两阈值的固定已见开发回放以及粗组重拟合的不同划分，仍以此前报告为准，与本轮同模型目标对照分开解释。

## 费用和正常入口

两阶段共完成 **81次外层拟合**、两个独立的开发内训练/标定模型。测得训练分析CPU合计 **73.15秒**，墙钟分别 **51.86秒、19.09秒**。费用统计包含实际模型预测。原有特征CPU是反事实选择成本，未重复计为本轮物理提取。依赖安装和入口导入前启动开销不在阶段计时中。

两个已保存模型的CNF入口均实际执行。池化模型实际计算并输出两个F动作相对D的预测成本收益和flags。六特征模型最终门槛为null，按内层标定直接D，因此正常模型会跳过特征提取。另用同一已训练权重、仅为实现验证把门槛设零，执行了真实gzip原题的六特征活动路径，确认读取、两原生提取器、预测与flags衔接。该工程分支模型未进入任何策略评分。

当前结果是反复使用的2022开发证据，没有独立测试或新的SAT运行。所有18个比较的4,719行费用已从原始成本矩阵和实际动作重新计算一致。重跑受输出身份和单owner锁保护。

实现为 `src/anniversary2022_baseline/predict_relative_cost.py`。已验证的池化模型位于 `outputs/anniversary2022_baseline/relative_cost_prediction_20261110/pooled_relative_predictor.joblib`，六特征模型位于 `outputs/anniversary2022_baseline/relative_cost_rule6_20261110/relative_predictor.joblib`。在项目根目录可以执行以下命令，只预测配置，不调用SAT求解器。

```sh
work/anniversary2022_plot_env/bin/python -m src.anniversary2022_baseline.predict_relative_cost predict input.cnf.gz --model outputs/anniversary2022_baseline/relative_cost_prediction_20261110/pooled_relative_predictor.joblib
```

两阶段的 `predictions.csv` 和 `summary.json` 保存全部预测收益、动作、费用、模型设置及分组标定记录。第二阶段的 `verification_and_costs.json` 保留正常入口、工程分支和费用证据。
