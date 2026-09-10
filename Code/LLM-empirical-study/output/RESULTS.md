# 任务二：LLM 生成 solution 的方法测试结果

> 把 `data/LLM_data/merged_llm_re_withsearch/` 中 8 篇论文的 LLM 生成 solution
> 转成可执行代码，放到 ADRS benchmark 上做一次完整评测。
>
> 日期：2026-09-10

---

## 0. 一句话结论

**8 篇里有 5 篇在 ADRS 中存在对应评测器，已全部完成"生成代码 → 完整评测"。**
这 5 篇里，LLM 方案在 **llm_sql（更快）、cant-be-late（方差更小）** 上有亮点，
在 **txn_scheduling 的一个 workload 上明显更好的同时另一个 workload 明显更差**，
在 **prism 和 cloudcast 上不如原始种子**。另外 3 篇（Telemetry / MAS(MetaGPT) /
NS3(PowerTCP)）在 ADRS 仓库中**根本不存在评测器**，无法测试，已按要求记录原因。

---

## 1. 关键前提：JSON 里是自然语言，不是代码

`merged_llm_re_withsearch/*.json` 的 `solution` 字段是
`idea`（方案思路）和 `implementation`（系统实现描述）两段**自然语言文本**，
其中没有任何可执行代码。因此 `data/initial-code/` 下的 5 个 `.py` 是
**我按 LLM 的 idea/implementation 逐条翻译成代码**的结果，不是 LLM 直接输出的代码。

这决定了本次评测的读法：

* 分数反映的是 **"LLM 所提出的方法（经翻译后）在该 benchmark 上的表现"**；
* 凡是 LLM 没写清楚、而接口又必须填的地方，都由我做了选择 —— 这些选择在
  §5 的保真度台账里逐条列出，并在 §6 给出敏感性分析；
* 按你的要求采用 **忠实优先**：保留 LLM 的核心思想与机制，只做接口适配；
  机制在接口下无法表达的部分**如实标注、不伪造**，方案本身不行就得低分。

---

## 2. 论文 ↔ ADRS 任务映射（这是本次任务最大的发现）

我核对了 `dataset/ADRS-and-let/README.md`、ADRS 目录实际内容、
**以及 ADRS 仓库的完整 git 历史（`git log --all --diff-filter=A`）**，
确认 ADRS 里**从来没有出现过** Telemetry / PowerTCP / MetaGPT 相关的任务目录。

| 论文（JSON） | pdf_id | ADRS 任务 | 评测器 | 本次结果 |
|---|---|---|---|---|
| Prism.md | `f948850caef3d25f` | `prism` | ✅ | ✅ 已测 |
| Cloudcast.md | `e3d82bafe7cb11e7` | `cloudcast` | ✅ | ✅ 已测 |
| Can't-Be-Late.md | `b93fea400aedf898` | `cant-be-late` | ✅ | ✅ 已测 |
| LLM-SQL.md | `d18c13d036b3708f` | `llm_sql` | ✅ | ✅ 已测 |
| TXN.md | `c252b8a901feea74` | `txn_scheduling` | ✅ | ✅ 已测 |
| Telemetry.md | `52875bf8ef4b3f8c` | — | ❌ | 跳过 |
| MAS.md（MetaGPT, ICLR'24） | `5dd2d839c66d339a` | — | ❌ | 跳过 |
| NS3.md（PowerTCP, SIGCOMM'22） | `7d3b6e61ea96cc4f` | — | ❌ | 跳过 |

### 为什么这 3 篇跳过

| 论文 | 原因 |
|---|---|
| **Telemetry.md** | ADRS 根 `README.md` 明确写着 *"Telemetry Repair — **Coming soon**. ... under active development and will be released in a future update."* 目录不存在。 |
| **MAS.md / MetaGPT** | ADRS 中没有任何多智能体/代码生成类任务；要评测 MetaGPT 需要 HumanEval/SWE-bench 一类基准，本仓库不含。 |
| **NS3.md / PowerTCP** | 需要 NS-3 网络仿真器作为评测底座，本仓库不含，也不具备离线安装条件（见 §3 网络限制）。 |

### 反向也成立：ADRS 里 3 个任务没有对应论文

| ADRS 任务 | 说明 |
|---|---|
| `eplb` | DeepSeek 官方 GitHub 项目（`deepseek-ai/eplb`），`dataset/ADRS-and-let/README.md` 已注明"EPLB 任务是 github 项目，并不存在原始论文"。 |
| `hp_quantization` | 自适应码率量化任务，不属于这 8 篇论文。 |
| `cant-be-late-multi` | 是 Can't-Be-Late 的多区域扩展，README 注明"与 Can't Be Late 为同一篇论文"。 |

即：**"8 篇论文"和"ADRS 的 8 个任务目录"并不是一一对应的两套东西**，
交集只有 5 个。这是做 RQ2 下游实验时必须记住的约束。

---

## 3. 交付物与复现

### 交付物

```
data/initial-code/                       ← 5 篇论文的可执行代码
  prism__f948850caef3d25f.py
  cloudcast__e3d82bafe7cb11e7.py
  txn_scheduling__c252b8a901feea74.py
  llm_sql__d18c13d036b3708f.py
  cant-be-late__b93fea400aedf898.py

ADR-evaluator/                           ← 可独立运行的评测脚手架（无 Docker）
  run_eval.py                            统一入口
  README.md                              结构说明 / 环境 / 与上游的差异
  requirements.txt
  .venv/                                 已装好依赖的解释器
  tasks/{prism,cloudcast,txn_scheduling,llm_sql,cant-be-late}/

output/                                  ← 测评结果（本目录）
  <task>__<pdf_id>.json                  每篇的评测结果
  <task>__<pdf_id>.log                   评测器完整 stdout/stderr
  summary.json                           汇总
  reference/                             同一脚手架下原始 ADRS 种子的成绩（对照）
  RESULTS.md                             本文件
```

### 复现命令

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADR-evaluator

# 5 篇 LLM 生成代码（本报告的主结果）
.venv/bin/python run_eval.py --program-dir ../data/initial-code --out ../output

# 原始 ADRS 种子（对照基线）
.venv/bin/python run_eval.py --all-reference --out ../output/reference

# 单篇
.venv/bin/python run_eval.py --task prism --program ../data/initial-code/prism__f948850caef3d25f.py
```

`run_eval.py` 只依赖 `--program-dir` 里 `<task>__*.py` 的**文件名前缀**推断任务，
所以以后只要有中间输出文件夹，把文件按 `<task>__<任意>.py` 命名就能直接批量测。

### 环境上的两个硬约束

1. **本机没有 Docker，也没有 sudo**（`docker` 不存在、`sudo` 需要密码）。
   ADRS 的评测器本来是容器化的（`evaluate.sh` → `python /benchmark/evaluator.py`），
   但评测器本身就是普通 Python，且本机此前的成功运行
   （`skydiscover/outputs/adaevolve/llm_sql_0825_1331/`）已经是按宿主 Python 跑的。
   `ADR-evaluator/` 把这条路径显式化、可复现化。**没有改动
   `skydiscover/benchmarks/ADRS/` 下的任何文件**，全部是拷贝。
2. **HuggingFace 不可达**（`curl` 返回 000），PyPI 可达。
   `cloudcast` 的 `profiles/*.csv` 和 `examples/config/*.json` 由
   `download_dataset.sh` 从 HuggingFace 拉取，本机拿不到 —— 已从本机另一份
   完整 checkout（`wyq/ai4system/skydiscover/benchmarks/ADRS/cloudcast/evaluator/`）
   拷贝过来。`cant-be-late` 的 153 MB 真实 trace 上游已解包，直接拷贝。

### 一处必须记录的依赖修复

`zxj` conda 环境的 pandas 已升到 **3.0.5**，会让 `llm_sql` 直接崩：

```
TypeError: Invalid value '[...]' for dtype 'int64'
```

（`df[col] = <含字符串的 list>` 在 pandas 2 会 upcast 到 object，pandas 3 直接报错。）
因此 `ADR-evaluator/.venv` 是基于 `zxj` 的 `--system-site-packages` 虚拟环境，
只把 `pandas` 钉到 `>=2.0,<3`、`numpy<2`、`networkx>=3.2,<3.4`（cloudcast 要求）。
**没有改动你现有的 conda 环境。**

---

## 4. 结果

### 4.1 总表

`combined_score` 是各评测器自己定义的官方指标（越高越好），量纲各不相同，**不能跨任务比较**。

| 任务 | LLM 生成方案 | 原始 ADRS 种子 | 谁更好 |
|---|---|---|---|
| `prism` | **20.826** | 21.892 | 种子略好（+5.1%） |
| `cloudcast` | **0.000582** | 0.000965 | 种子好得多（成本低 40%） |
| `txn_scheduling` | **1733.1** | 2840.9 † | 种子更好，但见 4.3 的结构性差异 |
| `llm_sql` | **0.6928** | 0.6775 | **LLM 略好** |
| `cant-be-late` | **−113.05** | −106.75 | 种子略好（均值成本低 8.9%），但 **LLM 方差小 22%** |

† `txn_scheduling` 的种子带随机性（随机起点贪心），单次运行 makespan 在 351–379 波动，
对应 combined_score 约 **2602–2841**。LLM 方案是确定性的，makespan 恒为 576。

### 4.2 原始指标明细

| 任务 | LLM 方案 | 原始种子 |
|---|---|---|
| `prism` | avg KVPR `1/19.826 = 0.05044`，success 50/50 | avg KVPR `1/20.892 = 0.04787`，success 50/50 |
| `cloudcast` | 5/5 配置成功，总成本 **1717.85** | 5/5 配置成功，总成本 **1035.14** |
| `txn_scheduling` | makespan **576**（wl1 452 / wl2 38 / wl3 86），3 个 schedule 全部合法 | makespan 351–379（本次 351） |
| `llm_sql` | 平均前缀命中率 **0.6870**，总耗时 **11.8 s** | 平均命中率 **0.7132**，总耗时 **385.2 s** |
| `cant-be-late` | 平均成本 **105.08**，标准差 **31.90**，1080 次仿真 | 平均成本 **96.52**，标准差 **40.92**，1080 次仿真 |

`cant-be-late` 的每次评测都是**完整**的：4 个 trace 环境 × 30 条 trace × 3 个
deadline 配置 × 3 个切换开销 = **1080 次仿真**，全部成功、无超时。
`prism` 是 50 个固定种子的测试用例，`cloudcast` 是全部 5 个配置，
`llm_sql` 是全部 5 个数据集，`txn_scheduling` 是全部 3 个 workload —— 均无抽样、无提前退出。

### 4.3 逐篇解读

#### `llm_sql` —— LLM 唯一"更好"的任务，但赢在速度而非命中率

LLM 方案（把 prompt 当作共享前缀树，贪心选择"一级复用增益最大"的列模块，
再按前缀分组做深度优先的请求排序）实现了 **0.6870** 的平均命中率，
略低于种子的 **0.7132**（低 3.7%）；但它的总耗时只有 **11.8 s**，
而种子是 **385.2 s**（**快 32 倍**）。

评分公式 `0.95×命中率 + 0.05×(12−min(12, 平均耗时))/12` 对耗时封顶在 12 s：
种子平均每次 77.0 s，速度项直接归零；LLM 平均每次 2.37 s，速度项拿满。
于是 combined_score 反超（0.6928 vs 0.6775）。

**诚实提示**：这 0.015 的差距几乎全部来自速度项，而速度项受机器负载影响。
LLM 方案的命中率是确定性的（两次独立运行 5 个数据集的命中率逐位相同），
combined_score 则会随耗时在 ±0.004 内浮动（实测两次 0.6886 / 0.6928）。
按命中率看，**种子仍然更好**（0.7132 vs 0.6870）。
顺带一提，种子本身带轻微随机性（两次运行第 4 个数据集命中率 0.39631 / 0.39597）。

逐数据集命中率（LLM）：movies 0.7803 / beer 0.6732 / BIRD 0.8168 / PDMX 0.3222 / products 0.8426。
PDMX 偏低是因为该数据集给了两个 `col_merge` 组合，而我的实现按 LLM 的
"复合模块原子且不拆分"只把它们**保持相邻**、没有真正融合成一列（见 §5）。

#### `txn_scheduling` —— 方法在两个 workload 上反向

LLM 方案把事务调度建模成冲突图上的**加权图着色**（颜色类＝可并发执行的事务集合，
目标 `Σ_c max_{i∈C_c} p_i`），用加权 DSATUR + 束搜索 + 局部搜索（单点移动/成对交换/
类合并）求解。逐 workload 看：

| workload | 冲突图 | LLM | 种子（5 次实测范围） |
|---|---|---|---|
| wl1 | **完全图**（4950 条边，100 个颜色类） | **452** | 255–263 |
| wl2 | 952 条边，18 类 | **38** | 53–55 |
| wl3 | 1423 条边，21 类 | **86** | 50–65 |

结论很干净：**冲突图稀疏时（wl2/wl3）LLM 的着色方案确实更好；完全冲突时（wl1）明显更差。**
原因不是 bug，而是 LLM 目标函数的性质 ——

* wl1 是完全图，任何调度都必须全串行，LLM 的目标 `Σ_c max p_i` 在所有调度上恒等于 1600，
  **对顺序完全不敏感**，于是规划器退化成一个任意顺序（按事务序号），代价 452；
  而种子的贪心是按**真实代价**逐步选下一个事务，能挑出更好的串行顺序。
* wl2/wl3 的冲突结构让着色真正起作用，LLM 把可并发事务归到同一颜色类，
  比种子的贪心串行更接近最优。

这是"**代理目标与真实目标不一致**"的典型案例：benchmark 的 makespan 是锁竞争模拟出的
带时序量，LLM 的 `Σ_c max p_i` 只是它的近似。

#### `cant-be-late` —— 均值略差，方差明显更小

LLM 方案用"**进度不变量**"取代 spot/on-demand 的二分：维护可回退线
`F(t) = W − R(D − t − δ)`（从这条线开始再启动 on-demand 锚点仍能赶上 deadline），
on-demand 锚点只在 spot 已经把它推到线之上时释放，spot 掉线就立刻重新拉起锚点。

跨全部 1080 次仿真的结果：

| | 平均成本 | 标准差 | combined = −均值 − 0.25×标准差 |
|---|---|---|---|
| LLM | 105.08 | **31.90** | −113.05 |
| 种子 | 96.52 | 40.92 | −106.75 |

**均值贵 8.9%，但标准差小 22%。** 这与 LLM 方案的设计意图一致：它明确牺牲一部分成本
去换"deadline 可保证"（锚点期要花钱），换来的是跨 trace 的稳定性。
`_apply_strong_guarantee` 的**强保证覆盖次数为 0**，说明它自己的不变量从未失效到
需要 harness 兜底 —— 安全性设计是有效的。

#### `prism` —— 略差，且差因可解释

LLM 方案是一个**两时间尺度的常驻控制器**（慢尺度上按 `p_m·a_m/w_m` 贪心决定哪些模型
常驻显存，保留 10% 显存给 make-before-break 的换入）。评测接口是**一次性静态放置**，
所以能映射的只有"慢尺度的准入规则"。结果 avg KVPR 高 5.1%。

差距有明确来源：LLM 方案**保留了 10% 显存做切换余量**，可用容量从 80 GB 降到 72 GB，
放置更保守 → KVPR 更高。这是设计本身的取舍（为了动态切换），在静态一次性评测里
就变成了纯粹的损失。

#### `cloudcast` —— 差距最大，且根因清晰

LLM 方案把一次性大传输建模成**deadline 约束下的最小成本编码多播 LP**：
决策变量是每条边上的速率 `r_{u,v}`，目标 `min Σ E(u,v)·r_{u,v}`，约束是速率上界 +
每个终端"收到速率 R"的割约束。结果总成本 **1717.85**，比种子的 **1035.14** 高 **66%**。

两个原因，都可以量化：

1. **评测图是完全有向图**（71 个区域、4970 条边＝所有点对都有直连），
   任何目的地都有直连边。多跳中继只会**增加**计费边，所以最小成本解本就是"每条直连"，
   而种子的 Dijkstra 恰好就是这个解。LLM 的 LP 在数学上没做错，是这张图上"优化"没有空间。
   > 我做过敏感性验证：把目标速率降到 20%，成本降到 **1093.20**，仍略高于种子的 1035.14。
   > 换句话说，**即使把 deadline 这个自由参数调到最优，LLM 的方案也打不过直连。**
2. **deadline 是接口没有的自由参数**。LLM 的模型要求"给定 deadline 求最小成本"，
   而 `search_algorithm(src, dsts, G, num_partitions)` 根本不传 deadline。
   我按 LLM 自己写的兜底规则"二分搜索最小的可行 deadline"取了**最紧的可行 deadline**
   （即最大可行速率），这会让 LP 尽可能并行铺开、用上大量中继边 → 成本最高。

敏感性（5 个配置的总成本）：

| 目标速率（相对最大可行速率） | 总成本 |
|---|---|
| 100%（本次采用） | **1717.85** |
| 50% | 1343.78 |
| **20%** | **1093.20** ← 最优 |
| 5% | 1105.69 |
| 1% | 1110.15 |

曲线是 U 形：速率太高就多铺中继边（出流量成本高），太低则传输时间变长（实例小时成本高）。
**deadline 的选择让这个方案多花了 57% 的钱** —— 这是 §6 里最值得注意的一处接口强制选择。

---

## 5. 保真度台账（改写尺度：忠实优先）

下表逐文件列出"保留了 LLM 的什么"与"接口强制改变了什么"。
每个 `.py` 的模块 docstring 里也有同样的说明。

### 通用

* ✅ 保留：LLM 的核心机制、目标函数、算法阶段与参数含义。
* ⚠️ 接口强制：函数签名、返回类型、依赖、数据入口。
* ❌ 不伪造：接口无法表达的机制（分布式调度、字节级流水、EMA 反馈等）**不假装实现**。

### 逐文件

| 文件 | 保留的 LLM 机制 | 接口强制的改动 |
|---|---|---|
| `prism__f948850caef3d25f.py` | 常驻集合准入规则：按 `p_m·a_m/w_m` 降序贪心、10% 显存预留、"把 GPU 显存当工作集"的负载均衡目标 | 两时间尺度控制、EWMA 预测、`T_idle` 迟滞、make-before-break 换入换出、有界队列 → 一次性静态放置接口里**没有对应物**，未伪造。预留是"软预算"，放不下时退回硬上限（因为接口没有队列可停放）。 |
| `cloudcast__e3d82bafe7cb11e7.py` | 速率 LP（变量/目标/速率上界/割约束）、"不可行就对 T 二分找最小可行 deadline"、把速率解落地成存储转发路径 | ①割约束 LP 用**等价的紧凑多商品流形式**求解（Lun 等的编码多播结论：两者最优值相同）——换的是求解方式不是模型，LLM 的割生成过程未复现；②速率向量按每个终端的流量分解成显式路径，分区按流量比例分配（最大余数法）；③bootstrap/token-bucket/随机线性编码是流水细节，接口只表达"谁发给谁"；④**deadline 接口不提供**，按 LLM 兜底规则取最紧可行值；⑤per-VM 聚合上限在 `G` 里不可观测，只强制了每边上界。 |
| `txn_scheduling__c252b8a901feea74.py` | 冲突图构造（含读写/写写判据）、加权 DSATUR（4a）、部分着色束搜索（4b）、单点移动/成对交换/类合并局部搜索（4c）、小窗口精确分支定界 + 团下界（4d）、anytime 可中断 | ①`p_i` 取事务操作数（模拟器只暴露这个；LLM 的 EMA 估计在一次性运行里观测不到）；②窗口机制 `W`/`T` 无对应物，整批视为单窗口；③**类间执行顺序** LLM 没有指定 —— 按其 part 5"执行器按规划器产出的有序颜色类列表走"，采用规划器**自己的建类顺序**（不做任何重排）；④返回的 makespan 用模拟器实测值（对应 LLM"执行器记录实际类时长"）。 |
| `llm_sql__d18c13d036b3708f.py` | 模块抽象（单列 / 复合模块原子不拆分）、一级复用增益公式 `Σ_G Σ_v max(0,count_G(m,v)−1)·len(m,v)`、贪心排序、按前缀分组做深度优先请求排序、单例踢出活跃分区、唯一高基数字段沉到尾部 | ①benchmark 的 prompt 序列化是**裸拼接**（无列名标签、无分隔符），LLM 的 `label: value` 渲染无法表达 —— 加标签会改掉被评测的字符本身，故 `len` 取值的自身长度；②`col_merge` 复合模块按 LLM"绝不拆分"只**保持相邻**、不融成一列（保数据不变）；③RadixAttention 交互、模块注册、淘汰处理、LOTUS/DB-GPT 集成在 `reorder` 接口里无对应物，未伪造。 |
| `cant-be-late__b93fea400aedf898.py` | 进度不变量 `F(t)=W−R(D−t−δ)`、三条规则（锚点释放 / 濒临回退线立刻拉起 / spot 掉线立刻拉起）、无预测无竞价、spot 不可用则以锚点为保证 | ①窗口边界检查点、分区两阶段提交、lineage 重算、分区队列、状态存储 → 逐 tick 决策接口里无对应物，未伪造（模拟器的 `task_done_time` 单调递增，天然就是 LLM 的"已提交持久进度"）；②**迟滞余量按 δ→(δ+τ) 统一替换**：LLM 假设 "τ 远小于 δ"，但本 benchmark τ 固定 600 s，而 overhead=0.02 h 时 δ=72 s，字面照搬会**每个 tick 抖动一次**（实测 204 次切换 / 313 tick，成本 125.57）。替换后抖动消失、强保证覆盖 0 次。 |

---

## 6. 敏感性：三个"接口强制选择"的影响

这三处不是 bug，是我在 LLM 没写清楚处做的选择，**直接影响分数**，单独列出来。

1. **cloudcast 的 deadline（影响最大）**：接口不传 deadline，我按 LLM 兜底规则取最紧可行值
   → 总成本 1717.85；若取最优速率（20%）则为 1093.20。**差 57%**。
   两种取法都在 LLM 文本里有依据（"给定 deadline 求最小成本" vs "不可行则二分找最小可行 deadline"），
   我选了**字面更直接**的那条。种子 1035.14 在两种取法下都不被超越。
2. **cant-be-late 的迟滞余量 τ vs δ**：字面照搬 LLM 的 `2Rδ` / `Rδ+Rτ` 会在本 benchmark
   的 tick 粒度下抖动（实测成本 125.57 / 204 次切换）；统一替换为 `(δ+τ)` 后为 63.03 / 0 次抖动。
   这是**参数适配**（LLM 自己的假设在接口上不成立），机制未改。
3. **txn_scheduling 的颜色类执行顺序**：LLM 的目标函数对类顺序**不敏感**，而 benchmark 的
   makespan 对其高度敏感（实测同一划分换个类顺序，wl3 从 86 变 100）。
   我按 LLM part 5 的字面表述采用规划器建类顺序，未做任何重排（重排就是我自己加设计了）。

---

## 7. 判读提醒与局限

* **本结果是"LLM 方法 + 我的翻译"的联合产物**，不是 LLM 直接写代码的产物。
  翻译时所有非平凡选择都已记录在 §5/§6 和每个文件的 docstring 里。
* **各任务的 `combined_score` 量纲不同，不能横向比较**；同一文件里的
  "LLM vs 种子"才是有意义的对比，且已固定在同一 harness、同一数据、同一机器上。
* `txn_scheduling` 的种子单次运行有随机性（2602–2841），表中取本次 `output/reference/` 的实测值；
  LLM 方案确定性。
* `llm_sql` 的 combined_score 含受机器负载影响的速度项（±0.004）；**命中率是确定性的**，
  按命中率看种子仍更好。
* **3 篇（Telemetry / MetaGPT / PowerTCP）无法评测**，因此本报告不能对这 8 篇做任何
  聚合统计（如"平均提升 X%"）。
* `prism` / `cloudcast` / `txn_scheduling` 的评测是**单次完整评测**（按你的要求"只测一次、
  测试必须完整"），种子对照同样单次；需要置信区间的话应重复采样（`txn_scheduling`、`cloudcast`
  的种子都带随机性）。
