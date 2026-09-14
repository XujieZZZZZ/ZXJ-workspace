# sky-discovertest — 人类（论文）solution 执行报告

按 `README.md` 未注释的那一半执行：把 8 篇论文的**人类生成** solution（`data/human_data/<pdf_id>.json`
的 `solution.{idea,implementation}`）实现成各自 ADRS 测试任务 `initial_program.py`
（cant-be-late 为 `initial_greedy.py`）的接口形式，放在 `genration_program_human/`，用任务目录自带
README 写明的测试方法评测，结果放在 `output_human/`。**未修改任何 ADRS 测试代码。**

> 目录约定：`genration_program_human/`（拼写沿用 README）+ `output_human/`（与既有 LLM 结果的
> `output/` 并列，避免覆盖）。LLM 侧的同名报告见 `../output/REPORT.md`。

---

## 1. 论文 → 任务的映射

与 LLM 侧一致：8 篇论文里只有 5 篇在 ADRS 中有可运行的评测器。

| # | 论文 (pdf_id) | 对应任务目录 | 原始被测试代码 | 人类程序 | 状态 |
|---|---|---|---|---|---|
| 1 | `52875bf8ef4b3f8c` Telemetry | **目录缺失** | — | — | ⛔ 跳过（无测试文件） |
| 2 | `5dd2d839c66d339a` MAS（MetaGPT） | `multiagent_system/` | `multi_agent_evolution*/initial_program.py` | — | ⛔ 跳过（测试环境不完整） |
| 3 | `7d3b6e61ea96cc4f` NS3（PowerTCP） | **目录缺失** | — | — | ⛔ 跳过（无测试文件） |
| 4 | `b93fea400aedf898` Can't-Be-Late | `cant-be-late/` | `initial_greedy.py` | `cant_be_late.py` | ✅ 已测 |
| 5 | `c252b8a901feea74` TXN | `txn_scheduling/` | `initial_program.py` | `txn_scheduling.py` | ✅ 已测 |
| 6 | `d18c13d036b3708f` LLM-SQL | `llm_sql/` | `initial_program.py` | `llm_sql.py` | ✅ 已测 |
| 7 | `e3d82bafe7cb11e7` Cloudcast | `cloudcast/` | `initial_program.py` | `cloudcast.py` | ✅ 已测 |
| 8 | `f948850caef3d25f` Prism | `prism/` | `initial_program.py` | `prism.py` | ✅ 已测 |

跳过 3 篇的原因与 LLM 侧完全相同（Telemetry/NS3 在 ADRS 检出中无对应目录；MAS 的 `evaluator.py`
import 即因缺 `taxonomy_definitions_examples/` 报错、且需外部 API key），见 `../output/REPORT.md` §1.1。

**一个必须先说清的事实：这 5 个任务的 `initial_program.py` 本身就是论文作者交给 ADRS 的代码，
而人类 solution 是从论文里抽出来的方法描述——有 3 个任务两者是同一套算法，另 2 个不是。**

| 任务 | ADRS seed 是什么 | 人类 solution 是什么 | 关系 |
|---|---|---|---|
| llm_sql | 论文自己的 GGR 实现（类文档字符串写着 "GGR algorithm"） | OPHR 的贪心近似 GGR（含 FD 项） | **同一算法**，seed 少了 FD 项 |
| cant-be-late | 一个"安全线贪心"（非 UP） | Uniform Progress（UP） | 不同；ADRS 另附 `referenced_up.py` = 论文自己的 UP 代码 |
| cloudcast | 逐目标最短路（非论文 planner） | 覆盖网 + 条带 MILP planner | 不同 |
| prism | 贪心 KVPR 放置（论文 Algorithm 1 的骨架） | 同一骨架 + `token_size` 加权的排序键/累加量 | 近似同算法，差在排序键 |
| txn_scheduling | 直接调用真值代价 `get_opt_seq_cost` 的代价采样贪心 | SMF：热键代理代价模型 + 采样 s=5 的增量贪心 | 决策规则近似，代价模型不同 |

因此这轮实验测的是"**把论文方法描述翻译成代码后，在同一 evaluator 上能拿多少分**"，
对 llm_sql / prism 而言它必然与 seed 高度接近——这不是实现走了捷径，而是**seed 就是论文代码**。

---

## 2. 结果总表

指标越大越好；"相对 seed"按原始量的相对变化给出。

| 任务 | 指标 | **人类 solution** | 原始 seed | LLM solution | 人类 vs seed | 人类 vs LLM |
|---|---|---|---|---|---|---|
| cloudcast | `combined_score` = 1/(1+cost) | **0.00156953**（$636.13） | 0.00095524（$1045.86） | 0.00124095（$804.83） | ✅ **+64.3%**（成本 −39.2%） | ✅ 更好 |
| llm_sql | `combined_score` | **0.6726315**（命中 0.70803，383.3 s） | 0.671749（0.70711，357.9 s） | 0.687825（0.69008，21.4 s） | ≈ 持平（+0.13%） | ❌ 略差（差在时间项） |
| prism | `combined_score` = 1/mean(kvpr)+成功率 | **19.6662** | 21.8916 | 20.6274 | ❌ −10.2% | ❌ 略差 |
| txn_scheduling | `combined_score` = 1e6/(1+makespan) | **2336.45**（makespan 427） | 2793.30（357） | 1718.21（581） | ❌ −16.4% | ✅ 更好 |
| cant-be-late | `combined_score` = −(avg+0.25·std) | **−107.32**（avg \$97.16） | −106.75（\$96.52） | −153.53（\$140.82） | ❌ 略差（−0.5%，近乎持平） | ✅ **大幅更好** |

**汇总：人类 solution 相对 seed 1 胜（cloudcast）4 负（其中 2 个是"近乎持平/略劣"）；人类 vs LLM
3 胜 2 负。** 人类方案在 cloudcast 上显著超过 seed（成本 −39%），在 txn 与 cant-be-late 上明显好于
LLM；只在 llm_sql（时间项）和 prism 上输给 LLM。

复现命令见 §4；机器可读结果见 `summary.json`。

---

## 3. 逐任务：实现与结果

### 3.1 cloudcast（Cloudcast）—— 成本 −39.2%，本轮唯一显著超过 seed 的方案

* **solution 实现**：按论文的 planner 逐条落地——
  1) **覆盖网**：以 region 为点、跨区链路为边，边上带每 GB 出网费 `cost` 与带宽 `throughput`；
  2) **节点聚类**：按"入/出向价格 + 带宽"特征把 71 个 region 聚成 ~20 个代表点（源点和目标点强制保留）；
  3) **跳数约束**：候选边只保留位于"源 → 至多 2 个中继 → 目标"路径上的边；
  4) **条带迭代贪心 MILP**（`pulp` + CBC）：对每个 stripe 解
     `min Σ cost_e·P_e s.t. F 满足流守恒（源发出 |DEST| 单位、每个目标吸收 1 单位）、F ≤ |DEST|·P`，
     即 P 定义一棵"以源为根、覆盖全部目标"的配送树；**一条边被同一 stripe 的多个下游目标共用时
     只付一次钱**，这正是论文用 `<COST_path, P_s>` 计价的语义。
* **接口适配（必须说明）**：ADRS 只暴露 `search_algorithm(src, dsts, G, num_partitions)`，
  论文 MILP 里的 `TIME`、`TRANSFER-SIZE`、`COST_VM`、`EGRESS_VM/INGRESS_VM`、`LIMIT_VM` 都不可见：
  * 配置里**没有复制截止期**，所以论文的容量约束 `volume_e ≤ <N,BANDWIDTH_e>·TIME` 按"该方案自身
    达到的时长 T"取值——任何方案在自己引发的 T 下都可行，即**时长约束不会砍掉任何多 stripe 共享**；
    因此第 2..STRIPES 个 stripe 的容量仍然松弛，直接复用第一个 stripe 的树（结果与逐步重解相同，
    省掉 10× 的 MILP 时间）；
  * `COST_VM` 不可观测，`N_v` 取容量约束要求的最小整数（=1），这正是目标函数在"实例零成本"极限下
    的选择；`TRANSFER-SIZE/STRIPES` 是每个出网项的公因子，不影响 MILP 的 argmin，故未进目标。
* **测试**：README "One command"（`evaluator.evaluate`，5 个 config，~65 s）。
  * 人类程序：`total_cost = $636.13`，`avg_cost = $127.23`，`combined_score = 0.00156953`，
    `runs_successfully = 1.0`。
  * seed：`total_cost = $1045.86`，`combined_score = 0.00095524`。
* **结论**：✅ 成本 −39.2%，分数 +64.3%，**好于 LLM solution（$804.83）**。机理：seed 对每个目标各走
  一条最短费路，同一条边被多个目标重复计价；论文的配送树让一条边被下游目标共享，且能把流量绕经
  便宜的 waypoint region（论文 "avoiding expensive direct source-to-destination edges"）。
  剩余差距：官方 SOTA 为 0.00159429，本方案 0.00156953（差 1.6%）。

### 3.2 llm_sql（LLM-SQL）—— 与 seed 持平

* **solution 实现**：论文的 GGR。选择规则严格按 solution 正文："对每个字段 c 的每个取值 v 计算
  `HITCOUNT(v,c,T,FD) = (len(v)² + R_v 上被 FD 推断字段的平均长度) · (|R_v|−1)`，取最大者，把
  `[c] + 推断字段` 放在最前"；FD 由表本身读出（c 的每个取值唯一决定 c' 时 c→c'）；递归到
  `row_stop/col_stop` 深度即停，停止时用"每字段期望 HITCOUNT ≈ avg_len(c)²"的固定序
  （`Algorithm.calculate_col_stats` 的 score）。`reorder_columns_for_value` 按**位置**而不是列名
  重排（PDMX 的 `path`+`metadata` 合并后与原有 `path_metadata` 列重名，按列名会崩）。
* **接口适配**：ADRS 的 `initial_program.py` **就是论文自己的 GGR 代码**（类注释 "GGR algorithm"），
  与 solution 描述同构；两者的差别只有 solution 明写的 FD 推断项（seed 里 `dep_graph` 从未被赋值，
  注释写着 "NOTE: not used"）与 per-(v,c) 选择（seed 是按"全局取值"选）。本实现按 solution 补齐了
  这两点，其余（分块并行、`original_index` 回填、末行排序等）保持与 seed 一致。
* **测试**：README "One command"（5 个数据集，~6.5 min）。
  * 人类程序：`combined_score = 0.6726315`，命中率 0.79405 / 0.70733 / 0.79667 / 0.40016 / 0.84196，
    `total_runtime = 383.3 s`。
  * seed（本机重跑，与 README 参考值 0.671749 一致）：`combined_score = 0.671741`，命中率 0.79409 /
    0.70733 / 0.79485 / 0.39680 / 0.84240，`total_runtime = 351.6 s`。
* **结论**：≈ 持平（+0.13%）。逐数据集几乎相同（beer 完全一致；BIRD +0.18pp、PDMX +0.34pp 是我们的
  实现差异，不是算法差异）。**人类输给 LLM 的唯一原因是运行时间项**：seed 与本实现都是 70–77 s/数据集
  （远超 12 s 的奖励阈值，时间项恒为 0），LLM 的单遍贪心只要 4.3 s/数据集，白拿 `0.05·(12−rt)/12`
  的 0.0322。命中率上人类（0.70803）高于 LLM（0.69008）。

### 3.3 prism（Prism）—— 略劣于 seed

* **solution 实现**：论文 "For model placement, Prism sorts models in descending order of SLO-weighted
  token rate (token_rate * token_size / TPOT SLO), then greedily assigns each model to the GPU whose
  KV Pressure Ratio (KVPR) is minimized"。KVPR 的公式在 Markdown 里损坏，按 solution 自己给出的
  复原（Algorithm 1 及上下文）：**分子 `w_token_rate` 累加 `token_rate*size/SLO`**，分母是剩余共享
  KV 显存；排序键 = `req_rate * model_size / slo`。
* **接口适配**：`compute_model_placement(gpu_num, models)` 是一次性放置、无跨调用状态，所以 solution
  里的**迁移规则**（"KVPR 改善超过 τ 才迁移"）与**本地请求仲裁**（共享队列 + TTFT/chunked-prefill
  调度）没有对应物，未实现；空闲驱逐需要时间轴，也未实现。装不下时沿用 `initial_program.py` 的
  `ValueError`（保持接口行为一致）。
* **测试**：README "One command"（50 个用例，0.3 ms/用例）。
  * 人类程序：`max_kvpr = 18.6662`，`success_rate = 1.0`，`combined_score = 19.6662`。
  * seed：`max_kvpr = 20.8916`，`combined_score = 21.8916`；官方 `best_program.py` 25.718。
* **结论**：❌ −10.2%，也劣于 LLM 的 20.627。机理与 LLM 那次的发现同源但方向相反：**评测的 KVPR 是
  `Σ(req_rate/slo) / 剩余显存`，而论文的排序键乘了 `model_size`、累加量也乘了 `model_size`**。
  乘 `model_size` 会把"又小又要得急"的模型排到前面、并把它们的权重放大，对"最小化各 GPU 压力最大值"
  这种 min-max 装箱不利。这是"论文的代理量 ≠ 评测的真值量"的又一例：solution 里的 `token_size`
  是它自己那套 SLO 记账的一部分，落到本任务的指标上就变成了偏置。

### 3.4 txn_scheduling（TXN）—— 劣于 seed，但明显好于 LLM

* **solution 实现**：论文的 SMF。规则按 solution 正文："先随机放一笔事务播种；每步**均匀随机采样
  s=5 笔**未调度事务，用**预测热点键操作**和 §2.1 的 makespan 模型（操作单位时间、冲突操作串行、
  事务内部保序）计算各自追加后的**增量 makespan**，取最小者追加，平手随机；无预测热点键的事务视为
  不影响 makespan、立即执行；每个热点键**只保留最近一次冲突操作**（更早的冲突在它被追加时已经计入）"。
* **接口适配**：本任务只给三个 workload，没有 application hints / traces / cluster 元数据，因此
  * R-SMF 的**分类器**（trace → metadata 向量 → 聚类 → 代表热点键操作集）无法训练；"预测热点键操作集"
    退化为该事务**自身在热点键上的操作**（完美预测），热点键沿用环境自带的定义
    （`Workload.hot_keys_thres`，key 号 ≤ 100）；
  * **MVSchedO** 是运行期并发控制协议（`SCHED_KEY` / `pred_ops` / 提交校验），在"只返回一个执行序"
    的接口里没有对应物，未实现；
  * 返回的 makespan 仍是**环境真值** `Workload.get_opt_seq_cost(schedule)`（与 seed 一致）——
    §2.1 的模型只用来**选序**，不用来报数。
* **测试**：README 单文件命令 `python evaluator.py <program>`。
  * 人类程序：`makespan = 427`（305 + 56 + 66），`validity = 1.0`，`combined_score = 2336.45`。
  * seed：`makespan = 357`（252 + 57 + 48），`combined_score = 2793.30`；LLM：581 / 1718.21。
* **结论**：❌ −16.4%，但**比 LLM 好 36%**。原因和 LLM 那次同源、程度更轻：SMF 用的是一个**代理
  makespan**（只看热点键、只看每个键最近一次冲突），而评测的 `get_opt_seq_cost` 是对**完整读写集**
  做加锁冲突仿真（还带 `find_earliest_read` 的连续读共享）。代理更粗 → 排序不如 seed 在真值上做
  贪心。差别在于：SMF 的代理**保留了真实冲突结构**（只是裁剪），所以只掉 16%；LLM 的"各类最大时长
  之和"与真值几乎不相关，掉了 38%。

### 3.5 cant-be-late（Can't-Be-Late）—— 与 seed 基本持平，远好于 LLM

* **solution 实现**：论文的 **Uniform Progress**，六条规则逐条落地：
  ① Thrifty（`cp=C0` 即停）；② Safety Net（`R(t) < C(t)+2d` → 转 on-demand 一直到完成）；
  ③ Exploitation（在 spot 上就待到被抢占）；④ Uniform Progress（空闲且 `cp(t) < ep(t)=t·C0/R0` →
    用 on-demand 追进度）；⑤ Taking Risks（有 spot 就用）；⑥ Hysteresis（在 on-demand 上要等到
    `cp(t) ≥ ep(t+2d)` 才允许换到 spot）。
* **接口适配**：Next Spot Lifetime Oracle `o(t)` 需要预测未来 spot 生存期，本模拟器不暴露，故走
  solution 明写的"无 oracle"分支（⑥/⑤）；多实例 gang-scheduling 的 Polarization Rule 属于
  `cant-be-late-multi` 那个独立任务，单实例接口无对应物。
* **测试**：README 路线 2（`PYTHONPATH=shims simulator/.venv/bin/python evaluator.py <program>`，
  4 envs × 3 deadline × 3 overhead × 30 traces = **1080 次仿真**，~2.5 min）。
  * 人类程序：`runs_successfully = 1.0`，`avg_cost = $97.157`，`cost_std = $40.666`，
    `combined_score = −107.323`（min \$46.87 / max \$188.17）。
  * seed：`avg_cost = $96.515`，`cost_std = $40.921`，`combined_score = −106.746`。
  * LLM：`avg_cost = $140.82`，`cost_std = $50.87`，`combined_score = −153.532`。
* **结论**：❌ 差 0.5%（avg 贵 0.66%，std 低 0.6%）——**实际上与 seed 打平**，两者都远好于 LLM
  （LLM 比 seed 贵 46%）。这条曲线上的三种策略：安全线贪心（seed）\$96.52、UP（论文）\$97.16、
  阈值交叉抖动的 LLM 控制器 \$140.82。
* **交叉验证（重要）**：ADRS 里另附了**论文作者自己的 UP 代码** `referenced_up.py`。用同一条命令跑它：
  `avg_cost = $94.677`，`cost_std = $41.060`，`combined_score = −104.942`。也就是说本实现（按 solution
  正文严格写的 2d 安全网 + 滞回优先于抢 spot）比论文代码（安全网用 1d、且 `if has_spot: return SPOT`
  会让滞回失效）贵 2.6%，两者都落在 seed 附近的 ±2% 带内。这个差异来自 solution 正文与论文代码的
  两处不一致，不是实现错误：**按正文实现 = −107.32，按论文代码 = −104.94，seed = −106.75**。

---

## 4. 复现命令

```bash
GEN=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/sky-discovertest/genration_program_human
ADR=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS
OUT=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/sky-discovertest/output_human

# cloudcast（~65 s，MILP 用 pulp/CBC，单次求解上限 20 s）
cd $ADR/cloudcast && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import contextlib, io, json, sys
import evaluator
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    result = evaluator.evaluate(sys.argv[1])
open("/tmp/cloudcast_human_verbose.log", "w").write(buf.getvalue())
print(json.dumps(result, indent=2))' "$GEN/cloudcast.py"

# prism（~0.5 s）
cd $ADR/prism && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator; print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))' "$GEN/prism.py"

# txn_scheduling（~2 s）
cd $ADR/txn_scheduling && /home/zhangxujie/miniconda3/envs/ai4system/bin/python evaluator.py "$GEN/txn_scheduling.py"

# llm_sql（~6.5 min）
cd $ADR/llm_sql && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator; print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))' "$GEN/llm_sql.py"

# cant-be-late（~2.5 min，README 路线 2）
cd $ADR/cant-be-late && PYTHONPATH=shims simulator/.venv/bin/python evaluator.py "$GEN/cant_be_late.py"
```

## 5. 产出清单

```
sky-discovertest/
├── genration_program_human/            # 5 个人类（论文）方案实现
│   ├── cloudcast.py                    #   覆盖网聚类 + 跳数约束 + 条带迭代 min-cost 多播 MILP
│   ├── llm_sql.py                      #   GGR：per-(v,c) HITCOUNT（含 FD 推断项）+ 递归分组
│   ├── prism.py                        #   论文排序键 token_rate·token_size/SLO + 最小 KVPR 放置
│   ├── txn_scheduling.py               #   SMF：热点键代理 makespan + 采样 s=5 增量贪心
│   └── cant_be_late.py                 #   Uniform Progress（六规则）
└── output_human/
    ├── REPORT.md                       # 本报告
    ├── summary.json                    # 机器可读映射表 + 指标（人类 vs seed vs LLM）
    ├── <task>.result.{json,txt}        # 各任务 evaluator 的原始输出 / 结构化指标
    ├── cloudcast.verbose.log.gz        # cloudcast 模拟器详细日志
    ├── cant_be_late.stdout.txt         # 路线 2 的完整 metrics JSON（1080 次仿真）
    └── cant_be_late_referenceUP.*      # 论文自带 UP 代码的同命令对照（§3.5）
```

> 说明：`cant_be_late_referenceUP.*` 不是本次交付的程序，而是 ADRS 自带的论文参考实现，用它做
> 同环境对照以界定"实现差异"与"方法差异"。
