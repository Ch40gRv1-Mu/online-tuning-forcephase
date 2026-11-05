# ta100-observer-v1：执行前源码契约

状态：源代码与非编译的hook性质测试就绪，**尚未编译、尚未运行新probe**。root提交协议/源码后才执行下面命令。字段定义采用`dynamic_candidates_next_v2.json`；原TD19/24的退化定义只保留diagnostic。

## 输入、隔离与身份

- 唯一基底：`/home/vipuser/forcephase_phase_prediction_20261104/build/ta-probe-v1-source`，其中`src/fpcontrol.cpp` SHA为`d92d0ef0638397fb6eddaad64a5b2d8619e8cf5d805d9f56dd469005bef16015`。
- `src/ta100/observer/BASE_SOURCES.json`绑定19个实际读取的基底源文件；`apply_observer.py`先严格核对，逐个唯一锚点插入，再复制到**不存在的新目录**。旧source/binary不覆盖，不使用其它owner目录。
- 新增`ta100_observer.cpp/.hpp`，插入12个原文件，共14个新增/修改文件。原搜索条件、动作参数、watch顺序、变量/子句排序和随机数操作不修改。唯一新增Clause字段为观察深度，搜索不读取；实际padding增量必须由编译后的sizeof记录，不能声称恰好只多2字节。
- `TA100_SOURCE_BINDINGS.json`包含基底SHA、修改文件SHA、**完整新src文件集合SHA**，其canonical SHA为`observer_source_sha256`。新manifest必须绑定该bundle SHA、编译binary SHA、CPU helper SHA、收集器SHA和profile，不能只绑定`fpcontrol.cpp`。

## 正确时点与缺失

仍为seed0、原生D、2CPU秒包含解析和观察、10wall、1.5GiB、自然restart跨1000conflicts。使用第一条NATIVE、switches=0记录；原checkpoint learned≥20，建议新收集器同时要求`ta100.support.learned≥20`。字段独立可为null，**不要求20项同时完整**。所有新计算完成后才写`process_cpu_s`，避免把rank/相似度计算漏在预算外。超预算或不完整JSON按缺失处理，不能延长时间救字段。

源日志在原checkpoint中增加`ta100={observer,features,support,caps,diagnostics}`；旧`f`数组及原phase/action机制保持不变。之后记录的`ta100`为null，不使用终局答案/计数。旧192条COMPLETE没有新字段，不兼容新method身份。

## 有界实现

- 活跃外部变量按固定hash取bottom256；外部标识用于匹配，适应compaction，不作为模型输入。样本初始已有赋值不伪造birth时间；只统计本观察器见到完整birth/unassign的寿命。
- 学习子句环形缓冲区最多256项，每项8-minhash及至多256个精确外部变量。大子句仍可完整算minhash；依赖精确文字列表的activity enrichment超cap即null。两个128学习子句窗口用于recurrence。
- 分析变量每128次analysis形成bottom-k256窗口；Jaccard是公共hash阈值下的估计，不冒充全集合精确值。无外部身份的辅助变量使该比较不可用，不混合重编号ID。
- 真正reason DFS至多256个查询、全前缀10000条祖先边、路径深度256。终端决策、最长路径、重访边都读实际reason。遇external reason、cycle、未赋值父节点或cap，相关字段整体null；不从平均层数构造祖先图。
- TD22在checkpoint使用当前实际branching priority：stable为score，focused为bumped stamp，外部ID仅打破相同priority。`nth_element`取top ceil(N/10)，O(N)时间和4N临时字节；不是历史pre-bump rank。
- TD24v2用Clause id的bottom256样本；moving GC不依赖旧地址。显式记录原始driving assertion前后，之后首次reason使用才计age，缺复用保留删失。
- TD30是**自observer激活以来的主CDCL操作依赖层**：激活时及非主CDCL生成的边界clauses为0；主analysis/shrink/minimize所实际察访reason的最大层+1赋给新主学习子句。包含谓词探索察访，属于操作依赖图，不声称是LRAT证明精确高度。16位饱和使字段null。
- 其余为实际符号桶、target联合违反、最终学习level占用熵、size×Glue81格联合秩相关、UIP trail定位、观察到的reason压缩、watch阻断命中、重启符号保留、chrono再决策转移及decision-gap Welford离散度。零分母为null，TD28至少32间隔。

共享固定状态约1MiB量级，另有rank的4N暂存和Clause padding；真实峰值/CPU需实测。没有永久hardcoded unsupported字段，但有真实结构/事件/预算不可观测；支持数、cap和字段覆盖必须公开。

## root提交后的精确build步骤

先把`src/ta100/apply_observer.py`、`observer/`及selftest main按原相对目录上传到新的phase，例如`ROOT/phases/ta100-observer-v1/src/ta100/`。`ROOT`为`/home/vipuser/forcephase_phase_prediction_20261104`。以下是待执行命令，不表示已执行：

```sh
python3 /home/vipuser/forcephase_phase_prediction_20261104/phases/ta100-observer-v1/src/ta100/apply_observer.py --source-root /home/vipuser/forcephase_phase_prediction_20261104/build/ta-probe-v1-source --output-root /home/vipuser/forcephase_phase_prediction_20261104/build/ta100-observer-v1-source
taskset -c 6 make -C /home/vipuser/forcephase_phase_prediction_20261104/build/ta100-observer-v1-source/build -j1 cadical
g++ -O2 -I/home/vipuser/forcephase_phase_prediction_20261104/build/ta100-observer-v1-source/src -I/home/vipuser/forcephase_phase_prediction_20261104/build/ta100-observer-v1-source/build /home/vipuser/forcephase_phase_prediction_20261104/phases/ta100-observer-v1/src/ta100/observer_selftest_main.cpp -L/home/vipuser/forcephase_phase_prediction_20261104/build/ta100-observer-v1-source/build -lcadical -o /home/vipuser/forcephase_phase_prediction_20261104/phases/ta100-observer-v1/observer-selftest
/home/vipuser/forcephase_phase_prediction_20261104/phases/ta100-observer-v1/observer-selftest
```

CPU6只是示例固定编译槽，root按实际资源分配；不抢其它worker。构建过程需用既有计费wrapper记录CPU/wall、编译器、命令、log SHA及退出码；生成binary留在新build目录或新phase/bin中，不覆盖旧bin。selftest只测数学不变量，不读CNF、不求解；没有另开独立audit/dryrun。

源变化后的C++尚未编译，不能声称编译成功或求解序列已实测一致。非编译的5项源码性质测试已通过：精确19文件SHA/唯一anchors、原搜索语句保留、phase apply与旧特征定义逐字一致、CPU时点顺序、20列与真实挂钩/cap约束。
