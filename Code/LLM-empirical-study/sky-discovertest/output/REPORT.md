# sky-discovertest 执行报告

按 `README.md` 的要求执行：把 8 篇论文的 LLM 生成 solution（idea + implementation）实现成各自测试任务
`initial_program.py` 的接口形式，放在 `generation_program/`，用 ADRS 测试目录自带的 README 中写明的
测试方法评测，结果放在 `output/`。**未修改任何 ADRS 测试代码**。

---

## 1. 论文 → 任务的映射

8 篇论文来自 `data/pdf_mapping.jsonl`（都对应 ADRS 基准的用例），与 `ADRS/` 下任务目录的对应关系如下：

| # | 论文 (pdf_id) | 论文文件 | 对应任务目录 | 原始被测试代码 | 生成程序 | 状态 |
|---|---|---|---|---|---|---|
| 1 | `52875bf8ef4b3f8c` | Telemetry（*The Case for Validating Inputs in Software-Defined WANs*） | **目录缺失** | — | — | ⛔ 跳过（无测试文件） |
| 2 | `5dd2d839c66d339a` | MAS（MetaGPT） | `multiagent_system/` | `multi_agent_evolution*/initial_program.py` | — | ⛔ 跳过（测试环境不完整，见 §3） |
| 3 | `7d3b6e61ea96cc4f` | NS3（PowerTCP） | **目录缺失** | — | — | ⛔ 跳过（无测试文件） |
| 4 | `b93fea400aedf898` | Can't-Be-Late | `cant-be-late/` | `initial_greedy.py` | `cant_be_late.py` | ✅ 已测 |
| 5 | `c252b8a901feea74` | TXN（Towards Optimal Transaction Scheduling） | `txn_scheduling/` | `initial_program.py` | `txn_scheduling.py` | ✅ 已测 |
| 6 | `d18c13d036b3708f` | LLM-SQL | `llm_sql/` | `initial_program.py` | `llm_sql.py` | ✅ 已测 |
| 7 | `e3d82bafe7cb11e7` | Cloudcast | `cloudcast/` | `initial_program.py` | `cloudcast.py` | ✅ 已测 |
| 8 | `f948850caef3d25f` | Prism | `prism/` | `initial_program.py` | `prism.py` | ✅ 已测 |

映射依据：任务目录名与论文名基本一一对应（`cant-be-late` = Can't-Be-Late，`cloudcast` = Cloudcast，
`prism` = Prism，`llm_sql` = LLM-SQL，`txn_scheduling` = TXN，`multiagent_system` = MAS）；ADRS 基准
自身的用例集合（Telemetry / Cloudcast / EPLB / Prism / LLM-SQL / TXN / CBL / CBL-Multi / MAS / NS3）
正好等于这 8 篇论文 + EPLB + CBL-Multi。

### 1.1 关于两个"跳过"的任务

* **Telemetry（`52875bf8ef4b3f8c`）**：ADRS 目录里**没有**任何对应任务——既没有 SDN WAN 输入校验/修复
  相关目录，也没有 `telemetry*`、`repair*` 之类的文件（`find -iname "*telemetry*"`、按 `Pingmesh`/
  `VeriFlow`/`traffic matrix`/`validation engine` 等关键词全库 grep 均无命中）。ADRS 基准里的用例
  "Telemetry Repair" 未包含在提供的 `ADRS/` 检出中，因此**没有 `initial_program.py` 可实现**。
* **NS3（`7d3b6e61ea96cc4f`）**：同理，`ADRS/` 中没有拥塞控制/ns-3 相关任务（按 `PowerTCP`、
  `congestion control`、`ns-3` grep 无命中；`hp_quantization`、`sparse_attention` 两个目录经查是 LLM
  权重量化与稀疏注意力掩码任务，与 PowerTCP 无关）。
* 这两项按 README "如果两者有冲突无法实现，放弃该任务并报告原因 / 如果有错误，请报告并且跳过" 处理。

### 1.2 目录里其余任务为何未使用

`ADRS/` 里还有 4 个目录不属于这 8 篇论文：

* `eplb/`（MoE 专家并行负载均衡）与 `cant-be-late-multi/`（Can't-Be-Late 的多区域变体）是 ADRS 基准
  中 EPLB / CBL-Multi 两个用例，不在这 8 篇论文内；
* `hp_quantization/`（自适应权重量化）与 `sparse_attention/`（稀疏注意力掩码设计）不是这 8 篇论文的
  任务（且两者都跑不通：前者缺 `ptq.py`/模型权重，后者的 `sparse-attention-hub` 子模块为空、
  缺 `flash_attn` 等依赖）。

---

## 2. 已完成的 5 个任务：实现与测试结果

所有测试都在任务目录下、用各自 README 里给出的命令执行，未改动任何测试代码；结果文件在 `output/`。

| 任务 | 生成程序 | 指标（越大越好，除注明） | 生成程序 | 原始 seed | 结论 |
|---|---|---|---|---|---|
| cloudcast | `cloudcast.py` | `combined_score` = 1/(1+cost) | **0.00124095**（$804.83） | 0.00095524（$1045.86） | ✅ 优于 seed（成本 −23%） |
| llm_sql | `llm_sql.py` | `combined_score` | **0.687825**（hit 平均 0.690，用时 21.4 s） | 0.671741（hit 平均 0.707，用时 351.6 s） | ✅ 优于 seed |
| prism | `prism.py` | `combined_score` = 1/mean(maxKVPR)+成功率 | 20.6274 | 21.8916 | ❌ 略劣于 seed |
| txn_scheduling | `txn_scheduling.py` | `combined_score` = 1e6/(1+makespan) | 1718.21（makespan 581） | 2793.30（makespan 357） | ❌ 劣于 seed |
| cant-be-late | `cant_be_late.py` | `combined_score` = −(avg_cost+0.25·std) | −153.53（avg \$140.82） | −106.75（avg \$96.52） | ❌ 劣于 seed |

（"原始 seed"是本机同环境重跑的结果，与各任务 README 中的参考数字一致：cloudcast $1045.86、
prism 21.892、txn makespan 357、cant-be-late 单条 trace \$46.87 等。）

### 2.1 cloudcast（Cloudcast）—— 成本 −23%

* **solution 实现**：把一次性批量复制写成"每条边带每 GB 出网费 E(u,v) + 带宽 B(u,v)"的有向覆盖网上的
  **带截止期、最小成本多播**问题：目标 `min Σ E(u,v)·r_uv`，约束为速率上界 `r_uv ≤ B(u,v)`、每 VM 出
  网上限、以及**多播割约束** `Σ_{S→S̄} r_uv ≥ R`（R = F/T），用割生成 LP 求解；本次接口没有截止期
  参数，因此按 solution 的"二分搜索最小可行截止期"取可行速率，并把每个 partition 当作一路多播流：
  用贪心 Steiner 生成树（即割覆盖支撑集）让**一条边的 occurrences 被所有下游目标共享**（网络编码
  中继语义），再用"速率上界"的拉格朗日罚项 `E·(1+λ·load_e/B_e)` 决定各 partition 从源域哪条出边
  分流（对应 solution 的"多个 seed VM 分摊源瓶颈"）。
* **测试**：README "One command"（`evaluator.evaluate`，5 个 config）。
  * 生成程序：`total_cost = $804.83`，`avg_cost = $160.97`，`max_transfer_time = 4206.64`，
    `combined_score = 0.00124095`，`runs_successfully = 1.0`。
  * seed：`total_cost = $1045.86`，`combined_score = 0.00095524`。
* **结论**：✅ 生效。原因是 simulator 的出网成本按"每条边被多少个 partition 经过"计费（`len(partitions)
  × partition_vol × cost`），逐目标最短路会让同一条边为每个目标重复计费，而 solution 的多播树让目标
  之间共享边，因此更便宜。

### 2.2 llm_sql（LLM-SQL）—— 综合分更高（命中率略低但快 17 倍）

* **solution 实现**：`Evolved.reorder()` 实现 solution 的六部分物理规划器：
  1) 模块化（`col_merge` 组视为不可拆的复合模块，其余每列一个模块）；
  2) 统计每个模块的取值频次与渲染长度（与命中率指标一致的 `fillna("")+str` 渲染）；
  3) **贪心前缀排序**：反复选择 one-level reuse gain 最大且为正的模块
     `gain(m)=Σ_G Σ_v max(0,count_G(m,v)−1)·len(m,v)`，选完即按该模块切分活跃组并丢弃单例；
  4) **行序 = 前缀组的深度优先遍历**（按 (m_1,…,m_k) 排序，共享前缀的行连续发出）；
  5) 不动后端 KV-cache；6) 不增删任何行/列，仅改变字段顺序与请求顺序。
* **测试**：README "One command"（5 个数据集）。
  * 生成程序：`combined_score = 0.687825`，各数据集命中率 0.7940 / 0.6965 / 0.7959 / 0.3222 / 0.8421，
    `total_runtime = 21.4 s`（seed 为 351.6 s）。
  * seed（同环境重跑，与 README 参考值 0.671749 一致）：`combined_score = 0.671741`，命中率 0.794 /
    0.707 / 0.795 / 0.397 / 0.842。
* **结论**：✅ 综合分更高。命中率平均略低（0.690 vs 0.707，beer 与 PDMX 上偏低），但运行时间从
  72 s/数据集降到 4.3 s/数据集，触发 `0.05·(12−runtime)/12` 的运行时间奖励，因此 `combined_score`
  反超。

### 2.3 prism（Prism）—— 略劣于 seed

* **solution 实现**：把 solution 的"流体常驻规划器"落到单次放置接口上：按 solution 的排序键
  `p_j·a_j/w_j = (req_rate/slo)/model_size` 递减贪心提升模型，为"make-before-break"过渡保留
  `RESERVE_FRACTION = 10%` 的显存余量（预留装不下时退回普通放置），每个模型放到放进去之后
  **KVPR 最小**的 GPU 上；装不下的模型保持排队（不塞满/不超配）。
* **测试**：README "One command"。
  * 生成程序：`max_kvpr = 19.6274`，`success_rate = 1.0`，`combined_score = 20.6274`（50 个用例）。
  * seed：`max_kvpr = 20.8916`，`combined_score = 21.8916`。
* **结论**：❌ 略劣（−1.26）。分析与消融（本地复算 50 用例）：差异几乎全部来自 solution 的排序键里
  除以 `model_size`——它优先提升小模型，对"最小化各 GPU 压力最大值"这种 min-max 装箱并不划算；
  用 seed 的排序键（`req_rate/slo`）+ 本文的"最小化放入后压力"选择规则可得到 22.34，用 seed 原有规则
  是 21.89。solution 未规定"放进哪块 GPU"，这一步由本实现按"压力最小"补齐，故上述对比只改排序键。

### 2.4 txn_scheduling（TXN）—— 明显劣于 seed

* **solution 实现**：实现为"任意时刻可停"的**带权图着色规划器**：
  4a) 带权 DSATUR 贪心（按 p_i 递减、冲突度破平；放入"边际增量最小"的兼容色类，否则开新类）；
  4b) 部分着色上的 beam search（下一个顶点取"已着色邻居最多"者，后继 = 每个兼容色类 + 开新类，
      保留最优 B 个，代价 ≥ 当前最优者剪枝）；
  4c) 局部搜索（单点搬移、成对交换、色类合并，直到无改进）；
  4d) 小窗口精确分支定界（阈值 12，本任务 100 笔交易不触发）。
  最后把色类序列线性化为执行序（色类依次执行、类内并发），并用 `workload.get_opt_seq_cost(seq)`
  如实计算 makespan 返回。
* **测试**：README 的单文件命令 `python evaluator.py <program>`。
  * 生成程序：`makespan = 581`，`validity = 1.0`，`combined_score = 1718.21`。
  * seed：`makespan = 357`，`combined_score = 2793.30`。
  * （修复过程中的一个插曲：beam search 返回的部分着色覆盖不全时会被接受，导致 `validity = 0`；已加
    "必须是完整排列"的校验，最终 `validity = 1.0`。）
* **结论**：❌ 明显劣。原因：solution 的代价模型是"各类最大时长之和"（加权着色 makespan），而本任务
  的真实代价函数是**基于锁冲突的顺序仿真**（冲突交易可部分重叠），两者几乎不相关——例如 W1 的冲突图
  是完全图（27→100 个色类），代理代价 1600 而真实代价 452；W3 代理 243 / 真实 91。代理模型失配导致
  着色方案在真实指标上变差；seed 直接在真值代价函数上做贪心采样，天然占优。另外 solution 的 beam
  search 只保留"当前代价最小"的部分解 + 以 incumbent 剪枝，在冲突图上很快整层被剪空（实测每层只剩
  1 个后继、26 层后死亡），因此本实现实际等价于 DSATUR + 局部搜索，beam 未起作用。

### 2.5 cant-be-late（Can't-Be-Late）—— 明显劣于 seed（约 +46% 成本）

* **solution 实现**：实现 solution 的"受保护进度 / 回退线"控制不变量：
  `P(t)=sum(task_done_time)`、`W=task_duration`、`D=deadline`、`R=W/D`、`δ=restart_overhead`、
  `τ=env.gap_seconds`，回退线 `F(t)=W−R(D−t−δ)`，松弛量 `slack=P−F(t)`：
  ① 锚点（ON_DEMAND）在跑且 `slack ≥ 2Rδ` → 撤销锚点（有 spot 就用 SPOT，否则 NONE）；
  ② 无锚点且 `slack ≤ Rδ+Rτ` → 立刻启用 ON_DEMAND 锚点；
  ③ 观察到 spot 被撤销（上一 tick 是 SPOT 且本 tick 无 spot）→ 立刻启动锚点；
  ④ 其余情况：有 spot 用 SPOT，否则等待（NONE）。接口完全对齐 `initial_greedy.py`
  （`Strategy` 子类 + `NAME` + `_from_args` + `_step`，只定义一个策略类）。
* **测试**：README 路线 2（`PYTHONPATH=shims simulator/.venv/bin/python evaluator.py <program>`，
  4 envs × 3 deadline × 3 overhead × 30 traces = 1080 次仿真）。
  * 生成程序：`runs_successfully = 1.0`，`avg_cost = $140.82`，`cost_std = $50.87`，
    `combined_score = −153.53`（min \$47.91 / max \$232.74）。
  * seed：`avg_cost = $96.52`，`cost_std = $40.92`，`combined_score = −106.75`。
* **结论**：❌ 明显劣，且不是"差一点"。逐 tick 追踪（trace 0，d48/dl52/o0.02）显示生成策略有
  **219/313 个 tick 在跑 ON_DEMAND（70%）**，而 seed 只有临近 deadline 才用按需实例。直接原因：
  solution 的两条阈值在 `τ > δ` 时会**交叉**——撤销阈值 `2Rδ` 低于启用阈值 `Rδ+Rτ`，状态
  "无锚点且 slack∈(2Rδ, Rδ+Rτ)" 不稳定，控制器每 1–2 个 tick 就在 ON_DEMAND↔SPOT 之间来回切换
  （实测 tick 6→7→8→9→10 为 SPOT, ON_DEMAND, ON_DEMAND, SPOT, ON_DEMAND …）。
  solution 自己写明参数应满足 `τ` 小到使 `R·τ ≪ δ`（"τ is the control loop interval, chosen small
  enough that Rτ is negligible relative to δ"）；本任务里 `δ = restart_overhead = 72 s`，而仿真步长
  （控制周期）`τ = 600 s`，是 δ 的 8 倍，假设不成立。按 README 要求严格实现、未改阈值，因此如实报告
  该结果与原因。
* **参数敏感性（重要）**：由于 solution 同时给了"阈值里带 `Rτ`"和"τ 要小到 `Rτ ≪ Rδ`"两条说明，本报告
  额外实现了把 `Rτ` 项去掉的变体 `generation_program/cant_be_late_tau_negligible.py`（仅此一处不同）：

  | 版本 | avg_cost | cost_std | combined_score |
  |---|---|---|---|
  | 原文阈值（τ = 仿真步长 600 s，主交付） | \$140.82 | \$50.87 | **−153.53** |
  | τ 可忽略（按 solution 的参数说明，变体） | \$106.54 | \$41.79 | **−116.99** |
  | seed `initial_greedy.py` | \$96.52 | \$40.92 | −106.75 |

  即：若按 solution 自己的参数要求（控制周期远小于 δ）实现，控制器就有正常滞回、不再抖动，成本从
  −46% 收敛到 −10%；但本任务的决策粒度固定为 600 s，无法满足该要求。两个数字都如实给出，主交付保持
  对规则的逐字实现。

---

## 3. 跳过的任务：multiagent_system（MAS）

任务目录 `ADRS/multiagent_system/` 下有 4 个变体（`multi_agent_evolution`、`_v2`、`_v2_gpt5`、
`_v3_gpt5`），顶层 `README.md` 为空（无人写测试方法），4 个变体的 README 内容相同，没有说明用哪一个。
更关键的是**测试环境不完整，评测无法启动**（已实测）：

1. `evaluator.py` 在 **import 时**就打开 `ADRS/taxonomy_definitions_examples/definitions.txt` 与
   `examples.txt`（MAST 分类法定义），而该目录在提供的 `ADRS/` 中不存在：

   ```
   FileNotFoundError: [Errno 2] No such file or directory:
   '.../ADRS/taxonomy_definitions_examples/definitions.txt'
   ```

   即 `import evaluator` 直接失败，任何候选都无法评分（`test_setup.py` 也一样起不来）。
2. 评测还依赖外部 LLM：judge 用 OpenAI `gpt-5-mini`/`o1`（`OPENAI_API_KEY`），多智能体本身也要
   调 LLM 后端；本机未设置该 key，也不应替用户联网调用。

按 README"如果有错误，请报告并且跳过"，该项跳过（未生成程序，因为无法测试的产物对评测无意义）。
若后续补齐 `taxonomy_definitions_examples/` 并提供 API key，可再补做；届时还需要确定用 4 个变体中的
哪一个作为"该任务的 initial_program.py"。

---

## 4. 复现命令（每个任务都用各目录 README 里给出的命令）

```bash
GEN=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/sky-discovertest/generation_program
ADR=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS
OUT=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/sky-discovertest/output

# cloudcast（~4 s）
cd $ADR/cloudcast && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import contextlib, io, json, sys
import evaluator
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    result = evaluator.evaluate(sys.argv[1])
open("'"$OUT"'/cloudcast.verbose.log", "w").write(buf.getvalue())
print(json.dumps(result, indent=2))' "$GEN/cloudcast.py"          # → cloudcast.result.json

# prism（~0.5 s）
cd $ADR/prism && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator; print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))' "$GEN/prism.py"

# txn_scheduling（~2 s，README 里 evaluator.py 自带 CLI）
cd $ADR/txn_scheduling && /home/zhangxujie/miniconda3/envs/ai4system/bin/python evaluator.py "$GEN/txn_scheduling.py"

# llm_sql（~0.5 min）
cd $ADR/llm_sql && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator; print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))' "$GEN/llm_sql.py"

# cant-be-late（~2–3 min，README 路线 2 = evolution loop 使用的那条）
cd $ADR/cant-be-late && PYTHONPATH=shims simulator/.venv/bin/python evaluator.py "$GEN/cant_be_late.py"
```

## 5. 产出清单

```
sky-discovertest/
├── README.md                      # 原始要求（未改动）
├── generation_program/            # 5 个生成程序
│   ├── cloudcast.py               #   Cloudcast 解（多播树 + 割约束/容量罚项）
│   ├── llm_sql.py                 #   LLM-SQL 解（前缀感知物理规划器）
│   ├── prism.py                   #   Prism 解（常驻规划器 + 10% 过渡预留）
│   ├── txn_scheduling.py          #   TXN 解（带权着色 anytime 规划器）
│   ├── cant_be_late.py            #   Can't-Be-Late 解（受保护进度/回退线控制器）
│   └── cant_be_late_tau_negligible.py  # 上述的 τ→0 敏感性变体（见 §2.5）
└── output/
    ├── REPORT.md                  # 本报告
    ├── summary.json               # 机器可读的映射表 + 指标（生成程序 vs seed）
    ├── <task>.result.*            # 生成程序的评测输出（原始 stdout/JSON）
    ├── <task>_baseline.result.*   # seed（initial_program.py / initial_greedy.py）同环境重跑
    └── cloudcast.verbose.log.gz   # cloudcast 模拟器详细日志（解压后 ~13 MB）
```

> 说明：`cant_be_late.stdout.txt` / `cant_be_late_baseline.stdout.txt` 是 README 路线 2 的完整 metrics
> JSON（含 36 个 scenario 的均值/方差）；`txn_scheduling.result.txt` 含 evaluator 打印的子进程输出
> 与 metrics JSON。
