# RQ2 语料适用性分析:实验设计注意事项汇总

> **来源**:对 `ADRS-and-let/md/` 下 8 篇论文(Let the Barbarians In 基准的 ground-truth 论文)通读后的适用性分析。
> **日期**:2026-09-02
> **目的**:为 RQ2-1 / RQ2-2 / RQ2-3 实验构建输入与参考答案时提供注意事项清单。
>
> 8 篇论文对应:Telemetry.md(输入验证,HotNets'24)、Cloudcast.md(NSDI'24)、Can't-Be-Late.md(NSDI'24)、LLM-SQL.md(LLM 查询优化)、MAS.md(MetaGPT,ICLR'24)、NS3.md(PowerTCP,SIGCOMM'22)、Prism.md(多 LLM 共享服务)、TXN.md(R-SMF 事务调度,PVLDB'24)。

---

## 1. 结论速览(判断基线)

- 8 篇**全部可切分为 Observation / Related Work(含 claim+引用) / Method 三部分**,可作为 RQ2 语料。
- 逻辑链条按严密程度分三档:
  - **高**(方法可被观察与 RW 差距近乎逐条回溯):Cloudcast、Prism、PowerTCP(NS3)、TXN(R-SMF)
  - **中高**(内部推理严密,但方法与 RW 关联弱,方案由自身理论导出):Can't-Be-Late、Telemetry
  - **中**(Motivation 偏定性/类比,方法含大量设计自由空间):LLM-SQL、MetaGPT
- **主样本集建议**:Cloudcast、Prism、PowerTCP、TXN、Can't-Be-Late(5 篇结构最规范)
- **对照组**:Telemetry(低 RW 密度样本)
- **压力/慎用样本**:LLM-SQL、MetaGPT(观察实证性弱,RW→Method 依赖跨域类比,建议改造后使用或仅作消融)

---

## 2. RQ2 实验设计重要提醒(核心)

### 2.1 Observation 输入的截取 —— 防"答案泄漏"

论文的引言/§2 往往**同时**包含观察与"对既有系统的分析",后者本属于 Related Work 的答案。

- **泄漏最严重**:PowerTCP(NS3.md)的 §1–2 Motivation 本身就是对现有 CC 算法(DCTCP/TIMELY/SWIFT/HPCC 等)建模解剖并得出"电压/电流单维度不足"——若整段作 Observation 输入,LLM 只需重述即可凑出 RW 结论,RQ2-1 失效。
- **轻量泄漏**:LLM-SQL 的 §2 Background 已含列存压缩(RLE/C-Store/Parquet)、缓存等本应属 RW 的类比内容。
- **较干净**(可整节照搬):Prism(§3 trace 分析)、Telemetry(§1–2 事故根因)、Can't-Be-Late(§2 trace 刻画)。
- **操作建议**:给 LLM 的 Observation 只保留"现象 / 测量 / 问题目标",剔除一切对具体已有系统/方法的评述。截取后做一次自查:Observation 文本中出现任何"系统名+评价性动词(无法/未能/只考虑…)"即视为泄漏,需删除或改写。

### 2.2 RW→Solution 可导性不均 —— 评估须分层

即便把人类 RW 全部输入,LLM 能稳定推出的也只是**设计层面的方案思想**;论文 GT 中的公式、协议、系统模块等细节大多**不是 RW 可导出的**(多来自论文自身理论或工程实现)。

- 典型:Can't-Be-Late 的 Uniform Progress 依赖自建竞争比/随机模型;PowerTCP 的 power 定义有数学推导;Telemetry 的 Hodor 只是方案草图。
- **操作建议**:RQ2-2/2-3 的解法评估采用分层打分(思想命中 / 机制命中 / 细节命中)或 LLM-as-judge 设计分,而非要求细节一致;否则人类拿到 RW 也答不满,测试会系统性低估所有模型。

### 2.3 观察实证性差异 —— 影响 RQ2-1 前提

RQ2-1 隐含假设"给定 observation 能圈定 related work 范围"。该前提在 8 篇中强弱不一:

- 实证驱动(观察可支撑 RW 圈定):Cloudcast、Prism、Telemetry、Can't-Be-Late、TXN(部分)、PowerTCP(分析式观察,可用但注意 2.1)
- 定性/类比驱动(人类也无法从 observation 唯一圈定 RW):**MetaGPT(无任何测量数据)**、LLM-SQL(机会识别型)
- **操作建议**:将后两类从 RQ2-1 主结果中降权或剔除,保留为难度梯度/压力测试。

### 2.4 md 转换质量 —— 制作输入前必须处理

- 公式大量乱码(如 `$ \Gamma _ { n o r m }$` 类碎片);图片全部丢失(`images/` 目录不存在,仅剩占位路径);部分表格退化为 HTML。
- **影响**:Observation 若依赖图(Cloudcast 图 2/3 价格与带宽分布、Can't-Be-Late trace 图、TXN makespan 示例图等),需回 PDF 将关键数据**补写为文本/表格**再作输入;公式为主的方法节(md 版)不能直接充当给 LLM 的参考答案原文。

### 2.5 参考答案(RW GT)抽取

- 部分论文 RW 不只在一个章节:Telemetry(§5 + §3.1 设计空间中对无监督方法 [13,9] 的讨论)、LLM-SQL(§7 + §2 Background)、Prism(§8 + 引言/§3.3 的对比段落)——抽 GT 需**跨节合并**。
- RW 段落中混有非学术引用(云厂商文档、博客、github),制作 GT 时应过滤或单独标注。
- GT 匹配建议以 **claim 语义级**为准(判断"LLM 是否说出同一 gap/评价"),而非引用身份逐条相同;论文间的 RW 密度差异大,建议标准化每篇 GT 的 claim 条数上下限。

---

## 3. 其他需要注意的点

### 3.1 论文类型差异对 GT 形态的影响

| 论文类型 | 代表 | Method GT 形态 | 影响 |
|---|---|---|---|
| 位置论文/方案草图 | Telemetry | 高层方案设想 + 初步回测,无完整系统 | GT 粗粒度,对比可行但评价空间小 |
| 完整系统论文 | Cloudcast、Prism、TXN | 算法/协议/实现细节齐全 | GT 细节不可复现层多,须分层评分 |
| 理论+策略论文 | PowerTCP、Can't-Be-Late | 定理 + 控制律/策略 + 模拟/原型 | 关键洞察非 RW 可导,见 2.2 |
| 框架/方法论文 | MetaGPT、LLM-SQL | 框架组件/算法 | 主观设计空间大,GT 模糊 |

### 3.2 逐篇"观察截取边界"备忘表

| 论文 | Observation 可取范围 | RW 主要所在 | 特判风险 |
|---|---|---|---|
| Cloudcast | §1–2(含算例与计价数据) | §6 + Table 5 | 图 2/3 数据需补写;RW 密度最高,GT 最丰富 |
| Prism | §3 整节(现象+Implication) | §8(+引言) | 图 1 活跃/空闲矩阵需文字化 |
| PowerTCP | 需人工改写为"原始目标",不可直接取 §1–2 | §6(+§2 内嵌) | 观察与 RW 纠缠最重,泄漏风险第一 |
| TXN | §2(+§3.2 hot-key 观察) | §6(+§5.4 对照) | 观察含 makespan 模型,须连模型假设一起给 |
| Can't-Be-Late | §2 trace 刻画 | §8 | RW→Method 松;GT 理论成分高 |
| Telemetry | §1–2 事故分析 | §5(+§3.1) | RW 薄(约 4–5 个 claim 团),区分度低 |
| LLM-SQL | 动机段(剔除 §2 背景) | §7(+§2) | 观察非实证;RW 分散 |
| MetaGPT | 需人工补实证场景 | §2 | 无实证观察;跨域类比跳变 |

### 3.3 跨 RQ 的共性风险

- **RQ2-1**:需为每篇定义"核心 claim"(即该论文与 prior work 的 gap claim),可全部从引言/摘要中提取,这本身可以作为人类标注的一致锚点。
- **RQ2-2**:人类 RW 输入与 LLM 生成解法间"信息差"不均(见 2.2),横向比较 8 篇的绝对分数意义有限,**只能篇内解读**。
- **RQ2-3**:两组输入仅 RW 来源不同(人类 vs LLM),需控制格式/长度/条数一致;LLM-RW 组存在"幻觉引用、虚构论文"风险,需在评估时区分"错误引用影响"与"结构/思路影响";差异可能很小,建议对每个实例多次采样取分布而非单次输出;若样本量(≤8)不足,可用自助抽样/配对检验在实例内做推断。
- **域间难度不均衡**:系统类论文(Cloudcast/TXN/Prism)的 RW 高度结构化、可导性强;策略类(MetaGPT 等)反之——分难度报告结果,不要混在一起给单一结论。

### 3.4 环境与数据完整性提醒

- 语料来源:`Let the Barbarians In`(arXiv 2512.14806)共 10 任务,其中 EPLB 为 github 项目、Can't Be Late Multi-Region Extension 与原论文同源,故只有 8 篇对应论文;实验设计时注意任务↔论文映射存在"一个任务用同一篇论文"的情况。
- 后续制作正式评测数据时,建议为每篇产出三件套:裁剪后 Observation 文本、结构化 RW 三元组(claim / 论文 / 支撑句)、分层 Solution 概要(思想级/机制级),并保留人类标注说明。

---

*本文件为分析备忘;详细逐篇评估见对话记录(总览表 + 逐篇分析)。*
