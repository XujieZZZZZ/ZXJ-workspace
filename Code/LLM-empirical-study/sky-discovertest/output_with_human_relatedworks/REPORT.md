# sky-discovertest — LLM（**以人类相关工作为输入**）solution 执行报告

按 `../README.md` 未注释的那一半执行：把 8 篇论文的 **LLM 生成** solution
（`data/LLM_data/merged_human_re/<pdf_id>.json` 的 `solution.{idea,implementation}`，其
`related_works_source` 指向 `data/human_data/<pdf_id>.json`，即 LLM 当年拿到的是**人类写的相关工作**）
实现成各自 ADRS 测试任务 `initial_program.py`（cant-be-late 为 `initial_greedy.py`）的接口形式，
放在 `../generation_program_with_human_relatedworks/`，用任务目录自带 README 写明的测试方法评测，
结果放在本目录。**未修改任何 ADRS 测试代码。**

> 目录约定：README 第 3 条只给了程序目录名 `generation_program_with_human_relatedworks`，结果目录
> 按既有惯例并列命名为 `output_with_human_relatedworks`（`output/` 是 LLM 自生成相关工作的结果、
> `output_human/` 是论文人类 solution 的结果，均未被覆盖）。
>
> 三侧同口径报告：LLM 自生成相关工作 → `../output/REPORT.md`；论文人类 solution → `../output_human/REPORT.md`；
> 本侧（LLM + 人类相关工作）→ 本文件。

---

## 1. 论文 → 任务的映射

8 篇论文里只有 5 篇在 ADRS 中有可运行的评测器，与另外两侧完全一致。

| # | 论文 (pdf_id) | 对应任务目录 | 原始被测试代码 | 本侧程序 | 状态 |
|---|---|---|---|---|---|
| 1 | `52875bf8ef4b3f8c` Telemetry | **目录缺失** | — | — | ⛔ 跳过（无测试文件） |
| 2 | `5dd2d839c66d339a` MAS（MetaGPT） | `multiagent_system/` | `multi_agent_evolution*/initial_program.py` | — | ⛔ 跳过（测试环境不完整） |
| 3 | `7d3b6e61ea96cc4f` NS3（PowerTCP） | **目录缺失** | — | — | ⛔ 跳过（无测试文件） |
| 4 | `b93fea400aedf898` Can't-Be-Late | `cant-be-late/` | `initial_greedy.py` | `cant_be_late.py` | ✅ 已测 |
| 5 | `c252b8a901feea74` TXN | `txn_scheduling/` | `initial_program.py` | `txn_scheduling.py` | ✅ 已测 |
| 6 | `d18c13d036b3708f` LLM-SQL | `llm_sql/` | `initial_program.py` | `llm_sql.py` | ✅ 已测 |
| 7 | `e3d82bafe7cb11e7` Cloudcast | `cloudcast/` | `initial_program.py` | `cloudcast.py` | ✅ 已测 |
| 8 | `f948850caef3d25f` Prism | `prism/` | `initial_program.py` | `prism.py` | ✅ 已测 |

跳过原因（本次重新核对过，未沿用旧结论）：

* **Telemetry / NS3**：ADRS 检出（`ADRS/cant-be-late, cant-be-late-multi, cloudcast, eplb,
  hp_quantization, llm_sql, multiagent_system, prism, sparse_attention, txn_scheduling`）里没有对应的
  任务目录，也没有可映射到的评测器。
* **MAS**：`multi_agent_system/` 下有 4 个变体，顶层没有 README 说明哪个是被测任务；其中
  `multi_agent_evolution_v2` / `_v2_gpt5` / `_v3_gpt5` 的 `evaluator.py` **import 即失败**
  （缺 `ADRS/taxonomy_definitions_examples/definitions.txt`，该目录整个不存在），只有
  `multi_agent_evolution` 能 import——但它的 `ProgramDevDataset` 要找
  `LLM-empirical-study/example_mas/programdev`（不存在），且判分必须调用 `gpt-4o-mini`
  （`OPENAI_API_KEY` 未设置）。三条都不满足，故跳过。

---

## 2. 结果总表

指标越大越好。三侧同口径（本侧 / LLM 自生成相关工作 / 论文人类 solution）：seed = ADRS 自带基线，
LLM(self-RE) = `../output/`，人类(论文) = `../output_human/`。

| 任务 | 指标 | **本侧：LLM + 人类相关工作** | seed | LLM(self-RE) | 人类(论文) | 本侧 vs seed | 本侧 vs LLM(self-RE) | 本侧 vs 人类(论文) |
|---|---|---|---|---|---|---|---|---|
| cloudcast | `combined_score` = 1/(1+cost) | **0.00153675**（\$649.72） | 0.00095524（\$1045.86） | 0.00124095（\$804.83） | 0.00156953（\$636.13） | ✅ **+60.8%**（成本 −37.9%） | ✅ 更好 | ❌ 略差（−2.1%） |
| llm_sql | `combined_score` | **0.66525**（命中 0.69325，52.0 s） | 0.67174（0.70711，351.6 s） | 0.68783（0.69008，21.4 s） | 0.67263（0.70803，383.3 s） | ❌ −1.0%（命中 −1.39pp） | ❌ 差（差在命中率） | ❌ 略差 |
| prism | `combined_score` = 1/mean(kvpr)+成功率 | **19.7366** | 21.8916 | 20.6274 | 19.6662 | ❌ −9.8% | ❌ 略差 | ✅ 略好（+0.4%） |
| txn_scheduling | `combined_score` = 1e6/(1+makespan) | **2808.99**（makespan 355†） | 2793.30（357） | 1718.21（581） | 2336.45（427） | ≈ **打平**（0…+0.8%） | ✅ **大幅更好（−39%）** | ✅ 更好 |
| cant-be-late | `combined_score` = −(avg+0.25·std) | **−142.84**（avg \$139.20）〔读法 B：−106.77〕 | −106.75（\$96.52） | −153.53（\$140.82） | −107.32（\$97.16） | ❌ −33.9%（见 §3.5） | ✅ 更好 | ❌ 差 |

† txn 的 makespan 依赖 wall-clock 时间预算（solution 规定的），空闲机器 5 次重跑为 **354 / 355 / 355 / 357 / 357**，
中位 355 → `combined_score` 2808.99；与另一进程争用 CPU 时退化为 365 → 2732.24。表里取中位数，区间见 §3.4。

**汇总：本侧真赢 1（cloudcast，成本 −37.9%）、打平 1（txn）、真输 3（llm_sql −1.0%、prism −9.8%、
cant-be-late −33.9%）。对 LLM 自生成相关工作的版本 3 胜 2 负；对论文人类 solution 2 胜（txn、prism）3 负。**

### 2.1 三侧横向对照（同一个任务，三种输入）

| 任务 | seed | LLM 自生成 RE | **LLM + 人类 RE** | 论文人类 solution | 官方 SOTA |
|---|---:|---:|---:|---:|---:|
| cloudcast `combined_score` | 0.00095524 | 0.00124095 | **0.00153675** | 0.00156953 | 0.00159429 |
| llm_sql `combined_score` | 0.67174 | **0.68783** | 0.66525 | 0.67263 | 0.729 |
| prism `combined_score` | **21.8916** | 20.6274 | 19.7366 | 19.6662 | 26.26 |
| txn `combined_score` | 2793.30 | 1718.21 | **2808.99** | 2336.45 | 4238.6 |
| cant-be-late `combined_score` | **−106.75** | −153.53 | −142.84 | −107.32 | −95.69 |

**把"输入换成人类写的相关工作"确实改变了产出**：5 个任务里 4 个的分数动了，且方向多数向上
（cloudcast \$804.83→\$649.72、txn 1718→2809、cant-be-late −153.5→−142.8），只有 prism 略降
（20.63→19.74）。但它并没有把 LLM 变成人类 solution 的水平：人类侧在 llm_sql 上与 seed 打平、
在 cant-be-late 上打平，而本侧这两项都明显落后。样本只有 5 个任务，这一条只能当作方向性观察。

---

## 3. 逐任务：实现与结果

每个任务的程序文件头部都逐条引用了 solution 原文，并标注了接口无法承载、因而未实现的部分。
测试命令一律取自任务目录自带的 README，**测试代码零改动**。

### 3.1 cloudcast（Cloudcast）—— 共享边多播树，成本 −37.9%

* **solution 实现**（tree-column LP）：
  1) **图构造**：region = 一个 VM，`src` 是源 VM，`dsts` 是目的地终端，其余 region 是候选中继；
  2) **候选树生成**：直接多播树（源到全部目的地的最小费路并集）、**每个中继的星型树**
     （root→relay→所有目的地）、**两跳中继 + fan-out 划分**（按"哪个中继更便宜"把目的地分给 r1/r2）、
     以及**随机扰动下的贪心 directed-Steiner 构造**（反复挑"从当前树出发最便宜"的未连通目的地、
     加上其路径；深度上限 3 跳，找不到才放宽）——候选池按 solution 的"最大池容量"取上限 250 棵（按边集去重）；
  3) **树列 LP**：`min Σ_t f_t·Σ_{e∈t} price_e s.t. Σ_t f_t = S`，用 pulp/CBC 求解；
  4) **条带到树**：取 `f_t > 0` 的树，把 `num_partitions` 条条纹按体积比例分给它们；
  5) **执行**：每棵树展开成每个 (目的地, 条带) 的转发表项。
* **接口适配（必须说明）**：LP 的边容量行 `Σ_{t∋e} f_t ≤ bw_e·T` 与 VM 出/入向容量行需要
  `bw(u,v)`、per-VM caps 和运行截止期 `T`，这三者接口都不暴露，**写不出来**；只剩需求等式，
  所有容量行松弛，LP 因此把全部体积放在池里最便宜的那棵树上（= 所有条带共用一棵多播树）。
  "字节区间"在接口里不存在，条带即 partition。容量行的对偶价格也就不存在，solution 的列生成
  循环改为"重新扰动生成一批 Steiner 树，直到没有新树加入或池满"——这正是 solution 写的另一个
  终止条件（"until no beneficial tree is found or a maximum pool size is reached"）。
* **测试**：README "One command"（`evaluator.evaluate`，5 个 config，~38 s）。
  * 本侧：`total_cost = $649.72`，`avg_cost = $129.94`，`combined_score = 0.00153675`，
    `runs_successfully = 1.0`，`max_transfer_time = 4317.86`。
  * seed：`$1045.86` / `0.00095524`；LLM(self-RE)：`$804.83` / `0.00124095`；人类：`$636.13` / `0.00156953`。
* **结论**：✅ 成本 **−37.9%**，分数 **+60.8%**，是本次唯一的真赢。机理与人类侧同源：模拟器按
  "每条边被多少个 partition 经过 × 流量 × 单价"计费（`simulator.py::__total_cost`），seed 的逐目标
  最短路让同一条边**为每个目的地重复付一次钱**；多播树让下游目的地共用同一条边，只付一次。
  与人类侧（\$636.13）的 2.1% 差距不在机制而在**树的求解方式**：人类侧是"区域聚类 + ≤2 跳约束 +
  精确多播 MILP"，本侧是"候选池枚举 + 取最便宜"，池里最好的树比精确解贵 2.1%。

### 3.2 llm_sql（LLM-SQL）—— 前缀规划器有效，但尾部字段被固定成 schema 序

* **solution 实现**（四模块中的 2/3/4 可落地）：
  * **Module 2 profiler**：对关系做有界随机采样（上限 20000 行，固定种子），逐字段统计取值频次，
    用字符长度作 token 成本代理（无 tokenizer 可用），并做 CORDS 式相关性检测；
  * **Module 3 前缀规划器**：初始 1 个 live group（= 全部采样行），每步对每个未选字段算
    `score(f) = Σ_G Σ_v max(0, n(G,v)−1)·len(G,v)`，选分数最大者进入前缀；随后按该字段取值**分裂
    live group**，丢弃样本数 < `tau_min` 的组；live group 超 `G_max` 或没有字段得分为正则结束；
    **剩余字段按原 schema 序**接在前缀之后；
  * **Module 4 物化**：行序 = 前缀 trie 的 DFS——按 `(cnt_1 降, v_1 升, cnt_2 降, v_2 升, …, cnt_k 降, v_k 升)`
    字典序排序，cnt_j 是"前 j 个字段分组"的行数。
* **接口适配**：Module 1（算子捕获与安全性分类）无对应物——evaluator 直接给出关系与合并列组，
  且它的序列化就是"逐值直接拼接"，正属于 solution 说的 safe 结构化序列化；`col_merge` 按 harness
  传入的列组先合并（与 seed 同一套 `merging_columns`），保证 profiler 看到的是同一张关系表；
  `tau_min` / `G_max` 是 solution 点名但未量化的参数，本实现取 `TAIL_MIN_ROWS=8`、`MAX_LIVE_GROUPS=512`；
  Delta Lake 持久化与 cracking 式增量重排无对应物。
* **测试**：README "One command"（5 个数据集，~52 s）。
  * 本侧：`combined_score = 0.66525`，命中率 0.79416 / 0.70142 / 0.80848 / **0.31972** / 0.84248
    （均值 0.69325），`total_runtime = 52.0 s`。
  * seed：0.67174（均值 0.70711，357.9 s）；LLM(self-RE)：0.68783（0.69008，21.4 s）；
    人类：0.67263（0.70803，383.3 s）。
* **结论**：❌ −1.0%（命中率 −1.39pp）。逐数据集：movies 79.42/79.39 持平、beer 70.14/70.73 略差、
  BIRD **80.85/79.63 更好**、PDMX **31.97/39.59 明显退步**、products 84.25/84.20 持平。
  **分差几乎全部来自 PDMX 一个数据集**（−7.6pp）。
* **机制（已做消融，PDMX）**：

  | 变体 | 命中率 |
  |---|---:|
  | 本实现（前缀列序 + 前缀 trie 行序） | 31.95 |
  | 本实现列序 + **按整行排序** | 31.97 |
  | 本实现列序 + **原始行序** | 31.98 |
  | 全局贪心列序（不做 group 分裂）+ 前缀行序 | 29.47 |
  | seed 的 GGR 列序（参考值） | 39.59 |

  行序三行几乎不动 → **分差 100% 在列序，不在行序**；全局贪心（29.47）比本实现（31.95）还差，
  说明前缀贪心 + group 分裂本身是有效的。真正的损失点是 solution 明写的最后一句——
  "**All remaining fields are appended after the chosen prefix fields in their original schema order**"：
  规划器在 PDMX 上选到 32 个前缀字段后 live group 全部消亡、循环结束，剩下 19 列按 schema 序固定；
  而 seed 的 GGR 在每层递归中都会重排剩余列，等于把整行的列序都纳入优化。**这是"按 solution 正文
  实现"与"打好分"之间的一次真实取舍，本实现按正文，未做改动。**

### 3.3 prism（Prism）—— 排序键里的除法方向

* **solution 实现**（居住规划器）：`U_m = (Q_m + α·predicted_demand_m)·priority_m / (W_m + expected_KV_m)`；
  按 `U_m` 决定"驻留/副本数"，然后对 GPU 做多资源 best-fit-decreasing，每块 GPU 预留一个小的
  staging buffer；"**活跃模型尽量分散到不同 GPU，低流量模型共置**"。
* **接口适配**：接口只暴露 `model_size`(W) 与 `req_rate`，故取 `Q_m = predicted_demand_m = req_rate`
  （一次性调用没有短/中期到达率历史，`α=1` 因此不影响排序）、`priority_m = 1/slo`、
  `expected_KV_m = 0`（未暴露；评测器的分母本来也只含 model_size）、staging buffer = 5%。
  **"cold 模型给 0 个副本"落不了地**——接口里 `models` 里的每个模型都必须被放置，否则整个用例判失败；
  因此活跃/低流量的划分改用 solution 自己的活动性定义（"队列是否为空"，这里 `req_rate ∈ [1,10)`
  全部为正）→ 规划器**退化为"分散"子句**（放在 KVPR 最小的 GPU 上），低流量的 BFD 共置分支在这批
  测试用例上不会被触发。驱逐/预取引擎、请求级 GPU 调度没有对应物。
* **测试**：README "One command"（50 个用例，<1 s）。
  * 本侧：`max_kvpr`(倒数值) = 18.7366，`success_rate = 1.0`，`combined_score = 19.7366`。
  * seed：21.8916；LLM(self-RE)：20.6274；人类：19.6662；官方 `best_program.py` 25.718。
* **结论**：❌ −9.8%。**消融把分差完整归因到一个因子**：把"按 `U_m` 排序"换成 seed 的排序键
  （`req_rate/slo` 降序）、放置规则不变，**逐位复现 seed**（两边都是 `21.891622105209393`）；
  去掉 staging buffer 则几乎无影响（19.7433）。也就是说
  `U_m` 里**多除的那个 `W_m`**（"每字节驻留成本"意义下的需求密度）是全部差价的来源：
  它是"**该不该把模型留在显存里**"的正确键，却不是"**怎么装箱让最大 KVPR 最小**"的正确键。
  这一点与人类侧恰好互为镜像——人类侧 prism solution 的排序键**乘**了 `model_size`，同样偏离 min-max。
  两个方向相反、结果都是负分，说明这个任务的评测指标对"加权/除权"极不宽容。

### 3.4 txn_scheduling（TXN）—— 与 seed 打平，好于另两侧

* **solution 实现**：
  * **Step 1 访问集**：事务 = 操作序列（读/写 + 键），每个操作预测时长 `p_{i,k} = 1`；
  * **Step 2 冲突图**：同一键且至少一个是写 → 连边（读-读不成边），记录冲突操作对，
    再分解成**冲突连通分量**；
  * **Step 3 代理 makespan**：按全序 π 建 DAG（事务内弧 `op_{i,k}→op_{i,k+1}`、事务间冲突弧按 π 定向），
    取**最长路**作为 `M(π)`（接口不暴露 worker 数，故用 solution 的无界 worker 分支；受限 worker 的
    list scheduler 无对应物）；
  * **Step 4 NEH 构造**：按 `l_i = Σ p_{i,k}` 降序（并列按冲突度）逐个插入到使 `M` 最小的位置；
  * **Step 5 iterated greedy**：`d = max(2, ⌊n/5⌋)` 个位置随机破坏 + 打乱后按 NEH 规则重插，
    `M(π_new) ≤ M(π_best)` 接受，否则以 `exp(−Δ/T)` 接受；每轮接受后做一遍相邻交换局部搜索；
    每 workload 15 s 时间预算、`T_0 = 0.1·M_init`、冷却 0.9、停滞 300 轮终止；
  * **Step 6 派发**：各分量的最优 π 合并（拼接）成最终顺序。
* **接口适配**：MVTSO / early-write-visibility 版本管理器与"运行期访问集不符则回退到下一个窗口"是执行期
  机制，接口只要一个执行序，故未实现；**返回的 makespan 用环境真值 `Workload.get_opt_seq_cost(schedule)`**
  （与 seed 同一做法），代理 DAG 只用于**选序**、从不用于报数（该 evaluator 不校验报数，报假数可刷到 1e6，
  本实现不做）。
* **测试**：README 单文件命令 `python evaluator.py <program>`（~45 s）。
  * 本侧：**makespan 354 / 355 / 355 / 357 / 357**（空闲机器 5 次），中位 **355** →
    `combined_score = 2808.99`，`validity = 1.0`；逐 workload（354 那次）= **234 + 51 + 69**。
    与另一进程争用 CPU 的一次是 365 → 2732.24。**这个抖动来自 solution 规定的时间预算（按 wall-clock
    计），不是随机性**——evaluator 用 `EVAL_SEED = 2026` 固定了 RNG，本程序的随机源因此可复现，
    唯一的非确定性是搜索被时间截断的位置。
  * seed：357 / 2793.30；人类：427 / 2336.45；LLM(self-RE)：581 / 1718.21。
* **结论**：≈ **与 seed 打平**（空闲 5 次的区间是 0…+0.8%；CPU 争用时 −2.2%），但对另两侧是压倒性的：
  比人类侧好 **17%**（makespan 355 vs 427），比 LLM(self-RE) 好 **39%**。逐 workload 看：W1 **234 vs 252（更好）**、
  W2 **51 vs 57（更好）**、W3 **69 vs 48（更差）**。
* **机制**：代理 makespan 在分量之间取 **max**（各分量之间没有弧，最长路 = 各分量最长路的最大值），
  而环境真值 `get_opt_seq_cost` 是**加和**式锁冲突仿真——分量间的先后对代理完全不可见，代理只优化
  "最大的那个分量"。这解释了 W1/W2 赢、W3 输的形态：代理把置信度放在了错的分量上，但由于它在
  **每个分量内部**仍然保留了真实的冲突结构（只是把"整行读写集"换成了"操作级 DAG"），净效果是打平，
  而不是像"各类最大时长之和"那样的代理彻底失配（LLM(self-RE) 的 581）。

### 3.5 cant-be-late（Can't-Be-Late）—— 一个"何时启动 on-demand tail"的读法，价值 +44%

* **solution 实现**：把任务看作**两模式自动机**（spot 模式 / 保证性 on-demand tail），核心不变量是
  **failover horizon** `T = D − L − (W − C)/R`，三条控制律：
  ① 检测到 spot 抢占且任务当时依赖 spot → **立即启动 on-demand tail**（因为抢占发生在 `T` 之前，tail 必然按时完成）；
  ② 仍在 spot 模式但 `now` 已进入 `T` 前**一个轮询周期**内 → 主动启动 tail；
  ③ 指示 spot worker 检查点（`min(now + delta_checkpoint, T − K)`），检查点未确认而到达 `T` 则转入 tail。
  另有 spot offer 排序（按有效单位成本）与准入判定 `W ≤ R·(D − admission − L)`。
* **接口适配**：`W = task_duration`、`D = deadline`、`C = Σ task_done_time`、`R = 1` 工作单位/秒
  （一个 on-demand tick 恰好完成 `gap_seconds` 的工作）、`L = restart_overhead`（模拟器对每次
  cluster type 切换收取的恢复开销）、轮询周期 = `env.gap_seconds`。模拟器**没有 checkpoint 机制**
  （进度按 tick 落盘即耐久），故 `K = 0`、`delta_checkpoint` 退化为一个 tick；spot offer 的价格/
  可用性预测器在这条 trace 上无可排序对象（只有 `has_spot` 布尔值），但随之而来的
  "**下一个检查点够不到 `T` 就不派新 spot 工作**"保留为 `now + gap ≤ T`；准入判定不能"拒绝"任务
  （接口必须返回一个 ClusterType），不可准入时全程走保证性资源。
* **测试**：README 路线 2（`PYTHONPATH=shims simulator/.venv/bin/python evaluator.py <program>`，
  4 env × 3 deadline × 3 overhead × 30 trace = 1080 次仿真，~2.5 min）。
  * 本侧：`runs_successfully = 1.0`，`avg_cost = $139.20`，`cost_std = $14.56`，
    `combined_score = −142.84`（min \$80.61 / max \$148.73）。
  * seed：\$96.52 / −106.75（本次同命令重跑，逐位一致）；人类(论文 UP)：\$97.16 / −107.32；
    LLM(self-RE)：\$140.82 / −153.53。
* **结论**：按上述读法 ❌ −33.9%。但这条结论对**一个句子怎么读**极其敏感，必须摊开说：

  | 读法 | 采用的原文 | 行为 | avg_cost | combined_score |
  |---|---|---|---:|---:|
  | **(A) 本报告主结果** | IMPLEMENTATION："*if a preempted job was relying on spot, the controller **immediately starts an on-demand tail***" | 任一次 spot 抢占 → 转入 on-demand 并运行到结束（latch） | **\$139.20** | **−142.84** |
  | (B) 对照 | IDEA："*an on-demand instance as a guaranteed tail that is **scheduled as late as possible***" | 不 latch：抢占后仍用 spot，只有到达 `T` 才真的走 on-demand | **\$96.54** | **−106.77** |
  | — 参考 | ADRS 自带 seed | 安全线贪心 | \$96.52 | −106.75 |

  两种读法相差 **+44% 成本**，而 (B) 的结果与 seed **几乎逐位相同**（\$96.54 vs \$96.52）。
  本报告以 (A) 为主结果：README 要求"严格按照 solution 提出的算法进行实现"，而 IMPLEMENTATION
  一节是算法规格，IDEA 一节是动机；两者在这一点上给出的行为相反，(B) 作为对照同时列出。
* **机制**：读法 (A) 把"某一个 tick 的 spot 不可用"直接升级为"这笔任务此后全程按需"，
  而 Can't-Be-Late 的场景是 48 h 任务 / 52 h 截止（只有 4 h 余量）、spot 频繁被抢占——
  于是任务几乎总是很早锁定在 on-demand 上。**`cost_std = 14.56`（seed 是 40.92）就是这种"恒定高价"的指纹**：
  它不再随 trace 好坏起伏，因为大多数 trace 都被同一条路径吞掉了。这也解释了为什么它比
  LLM(self-RE) 的 −153.53 好：后者是**反复横跳**（均值更贵 140.82、方差还大 50.87），
  本侧则是**一次锁定后不动**（均值略低 139.20、方差小得多）。

---

## 4. 复现命令

```bash
GEN=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/sky-discovertest/generation_program_with_human_relatedworks
ADR=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS
OUT=/home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/sky-discovertest/output_with_human_relatedworks

# cloudcast（~38 s，pulp/CBC；详细日志写 gzip）
cd $ADR/cloudcast && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import contextlib, io, json, sys
import evaluator
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    result = evaluator.evaluate(sys.argv[1])
open("/tmp/cloudcast_humanre_verbose.log","w").write(buf.getvalue())
print(json.dumps(result, indent=2))' "$GEN/cloudcast.py"

# prism（~0.5 s）
cd $ADR/prism && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator; print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))' "$GEN/prism.py"

# txn_scheduling（~45 s；时间预算按 wall-clock，机器需空闲才可与 seed 同口径比较）
cd $ADR/txn_scheduling && /home/zhangxujie/miniconda3/envs/ai4system/bin/python evaluator.py "$GEN/txn_scheduling.py"

# llm_sql（~1 min 本次实现；seed 需 ~10 min）
cd $ADR/llm_sql && /home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator; print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))' "$GEN/llm_sql.py"

# cant-be-late（~2.5 min，README 路线 2）
cd $ADR/cant-be-late && PYTHONPATH=shims simulator/.venv/bin/python evaluator.py "$GEN/cant_be_late.py"
```

## 5. 产出清单

```
sky-discovertest/
├── generation_program_with_human_relatedworks/     # 5 个 LLM(人类相关工作) 方案实现
│   ├── cloudcast.py                    #   树列 LP：候选树池（直接/星型/两跳/随机化 Steiner）+ 最便宜树共用
│   ├── llm_sql.py                      #   前缀布局规划器：共享 token 质量的贪心字段序 + 前缀 trie 行序
│   ├── prism.py                        #   居住效用 U_m + 活跃模型分散放置（低流量 BFD 共置）
│   ├── txn_scheduling.py               #   冲突图 → 逐分量 DAG 最长路 + NEH + iterated greedy
│   └── cant_be_late.py                 #   failover horizon 两模式自动机（spot / 保证性 on-demand tail）
└── output_with_human_relatedworks/
    ├── REPORT.md                       # 本报告
    ├── summary.json                    # 机器可读映射表 + 指标（四侧对照）
    ├── <task>.result.{json,txt}        # 各任务 evaluator 的原始输出
    ├── cloudcast.verbose.log.gz        # cloudcast 模拟器详细日志
    ├── cant_be_late.stdout.txt         # 路线 2 的完整 metrics JSON（1080 次仿真）
    ├── cant_be_late_baseline.{stdout.txt,result.json}  # seed 同命令同批次重跑（§3.5 对照）
    └── cant_be_late_tail_late.{stdout.txt,result.json} # 读法 (B) 控制变体（§3.5 对照）
```

> 说明：`cant_be_late_tail_late.stdout.txt` 对应的程序只是**读法对照**，不是本侧交付的程序
> （它的源文件放在 `/tmp/cant_be_late_tail_late.py`，未进入交付目录）；seed 重跑用于确认
> baseline 数值在本批次仍然逐位一致。
