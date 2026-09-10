# Deep Research（深度研究）领域综合报告

> **报告性质**：本文是一份面向研究者的 Deep Research（DR）领域综述性报告，基于用户提供的 11 篇最新论文（`md/` 目录）的全文精读，并结合对 arXiv 与各机构公开发布材料的检索，回答六个问题：DR 是什么、任务形态、意义与应用场景；DR 的基本流程与机制、主流实现、业界最佳实践及其原因；当前 DR 的缺陷、影响与证据；以及深入该领域应阅读的代表性论文清单。
>
> **撰写日期**：2026-09-02
> **本地证据**：`md/` 目录下 11 篇论文（10 篇正文 + 1 份提取日志）。文末附"本地语料索引"。
> **术语说明**：Deep Research 在文献中也称 Deep Research Agent (DRA)、Research Agent、Agentic Search；与之近邻的产品形态是 Generative Search Engine（生成式搜索引擎，GSE，如 Perplexity、Bing Copilot、You.com 的普通问答模式）。

---

## 目录

1. [Deep Research 是什么：定义、任务形态、意义与应用](#第一部分-deep-research-是什么)
2. [Deep Research 的基本流程、机制与最佳实践](#第二部分-deep-research-的基本流程机制与最佳实践)
3. [当前缺陷、影响与证据](#第三部分-当前缺陷影响与证据)
4. [深入该领域：代表性论文清单与阅读路线](#第四部分-代表性论文清单与阅读路线)
5. [结论与展望](#第五部分-结论与展望)
6. [本地语料索引与参考文献](#第六部分-本地语料索引与参考文献)

---

# 第一部分 Deep Research 是什么

## 1.1 概念起源与产业背景

Deep Research（深度研究）是 2024 年底至 2025 年兴起的一类 LLM Agent 应用范式：用户给出一个高层的、开放式的信息研究需求，系统自主执行"规划 → 多轮检索/浏览 → 证据交叉验证 → 综合 → 撰写带引用的长报告"的循环，输出接近人类分析师水准的研究报告。

**时间线**：Google 于 2024 年 12 月在 Gemini 中率先推出 Deep Research 产品；OpenAI 于 2025 年 2 月发布基于 o3 系列（专门针对网页浏览优化、经强化学习训练）的 Deep Research 模型，并随后并入 Microsoft Copilot；Perplexity、xAI Grok、Kimi、腾讯、阿里（通义 DeepResearch）等迅速跟进。学术界方面，开源实现如 HuggingFace Open DeepResearch、LangChain Open Deep Research、DeerFlow（字节）、WebThinker（人大）、DeepResearcher（GAIR）等相继出现；大量评测基准（DeepResearch Bench、BrowseComp、LiveDRBench、DeepResearchGym、ResearcherBench、LiveResearchBench、DRBench、MRDRE、DR-Arena、DREAM、ReportLogic 等，后文逐一介绍）在 2025 年井喷。

一份系统性综述（Shi et al., arXiv:2512.02038）把 DR 的演化归纳为**三个阶段/路线图**：
- **Phase I – Agentic Search（代理式搜索）**：以"找对资料"为目标的多跳问答与浏览（如 GAIA、BrowseComp、多跳 QA）；
- **Phase II – Integrated Research（整合式研究）**：迭代地规划子问题、从异构内容（网页、表格、图表、PDF）检索并综合成结构化长报告——即当前主流 DR 系统的能力带；
- **Phase III – Full-stack AI Scientist（全栈 AI 科学家）**：提出假设、设计并执行实验、评审与反驳、产生新见解（AI Scientist、AI Co-Scientist、Nova 等代表）。

因此，"Deep Research"既是**一类任务**（开放式的长链条信息综合），也是一类**系统**（把 LLM 推理与检索/浏览/计算工具耦合起来的 Agent），还是一种**产品形态**（生成式搜索引擎的"深度模式"）。

## 1.2 Deep Research 的任务定义：搜索强度 × 推理强度

尽管产业界先于学术界使用这个词，很长一段时间内 DR "缺乏形式化定义"。微软研究院在 *Characterizing Deep Research*（LiveDRBench，`18936_Characterizing_Deep_Rese.md`）中给出了迄今被引用最多的形式化刻画，其核心主张是：

> **DR 任务的本质特征不是"输出一篇长报告"，而是搜索过程中需要的高扇出（high fan-out over concepts）——即广而推理密集的探索。**

形式化定义（Definition 1）：给定文档语料 C、查询 q，若回答 q 需要处理**大量信息单元**（search intensity，搜索强度），且"寻找信息单元 / 处理信息单元 / 组合信息单元为最终结论"中**至少一个环节需要非平凡推理**（reasoning intensity，推理强度），则 q 是 DR 查询。操作化近似：人类专家使用检索工具求解耗时 **>10 分钟**、涉及 **≥10 次检索查询（约 20 个信息单元）** 即视为 DR。最终答案可以形式化为 ⟨query, claims⟩，其中每条 claim 递归地带有支撑它的 subclaims——报告写作被拆解为"claims 综合（本质挑战）"与"基于 claims 的书面表达（长文本生成问题）"两个子任务，评测只针对前者，从而把推理能力与表面文笔分开度量。

从该定义出发，DR 与既有多类任务的差别一目了然（论文原文用"搜索强度 × 推理强度"的二维图谱定位）：

| 任务类型 | 搜索强度 | 推理强度 | 代表 |
|---|---|---|---|
| 多跳 QA（HotpotQA、MuSiQue） | 低 | 低 | 2-3 跳即可答 |
| 专业阅读 QA（CURIE、CUAD 等） | 低 | 高 | 单一长文档内推理 |
| 解释类问答（ELI5） | 低-中 | 高 | 面向单一概念 |
| 通用 Agent 任务（GAIA、HLE） | 高 | 高 | 但答案是单一最终答案 |
| **Deep Research（信息综合报告类）** | **高** | **高** | 大量信息单元 + 多 claim/subclaim 输出 |

WebAggregator 的作者（`2510.14438v2.md`）进一步强调了 DR 的**组合推理（compositional reasoning）**成分：把分布在不同来源上的零散证据"聚合"为连贯逻辑结论的能力，并指出已有 web 基准（WebWalkerQA、TaskCraft、BrowseComp）任务难度大多落在"实体定位"上（约 30-43% 任务单源即可解），并不真正要求组合推理——这是 DR 评测必须单独建模的能力维度。

## 1.3 意义：为什么 Deep Research 重要

1. **认知劳动的真实替代**：撰写调研报告/综述/合规分析这类工作过去需要专家数小时到数天，DR 把时间压缩到 5-30 分钟（OpenAI 系统卡），这使其成为首批"直接替代高价值白领认知劳动"的 AI 能力之一。
2. **把 LLM 从"知道"推向"查证"**：LLM 的静态参数知识会过时、会幻觉，DR 将模型置于真实信息环境（活网、企业私有数据）中，用检索-验证回路把答案锚定在外部证据上；它同时是长上下文、工具使用、规划与推理能力的"统考科目"。
3. **社会技术层面的影响**：DeepTRACE（`6361_DeepTRACE_Auditing_Deep_R.md`）从"生成式搜索引擎/深度研究系统是社会技术工具"的角度指出：数亿用户开始把 DR 当默认信息入口，其"看似有来源、实则过度自信/片面/引用错位"的行为会实质性地塑造公众的知识获取，甚至制造**回音室**（对辩论性问题只按提问立场作答）与**"来源幻觉"**（列了大量来源制造严谨假象，实际上陈述得不到自身来源支撑）。

## 1.4 应用场景

从 11 篇语料可以归纳出四类典型场景（对应不同的数据环境与用户）：

| 场景 | 任务示例（来自语料） | 数据环境 | 代表基准/系统 |
|---|---|---|---|
| 科研与学术 | 找满足全部物性参数的材料；找使用了若干数据集的论文；判断研究 idea 是否已被做过（prior art）；写综述 | 公开 web + 论文库 | LiveDRBench、DeepResearch Bench、ResearcherBench、SciPIP、OpenScholar |
| 商业与战略分析 | "产品路线图如何修改以符合某监管标准"；竞品/市场趋势研究 | 公开 web | DeepResearch Bench 中的商业子集、Glaive |
| **企业知识工作** | 合规评估、销售策略、CRM、网络安全审计——需要同时检索**公开 web 与企业私有数据**（云盘、邮件、IM、表格、PPT） | web + 企业私有系统 | DRBench（ServiceNow）、CRMArena、AgentCompany |
| 公众信息与事件研究 | "2005-2011 年间由女性作者原著改编的奥斯卡获奖影片全集"；航空事故调查还原 | 公开 web（含长报告） | LiveDRBench ENTITIES/FLIGHTS、BrowseComp、GAIA |
| 意见与政策查询 | 有争议议题的正反证据梳理（注：当前系统表现最差） | 公开 web | DeepTRACE 辩论题集 |

此外，DR 是通往 "AI for Science / AI Scientist"（Phase III）的中继站：FlowSearch（`2510.08521v2.md`）明确把 DR 用于药物靶点发现（TRQA）等科学推理，WebThinker 用 DR 模式做"科学报告生成"。

## 1.5 本地 11 篇论文全景速览

为便于阅读后文，先把本地语料映射到 DR 研究版图：

| 本地文件 | 论文（简称） | 定位 | 一句话贡献 |
|---|---|---|---|
| `md/18936_Characterizing_Deep_Rese.md` | Characterizing Deep Research / LiveDRBench（微软） | 定义+基准 | DR 的形式化定义（搜索×推理强度）；claims 级客观评测；100 题开放网基准，OpenAI DR F1=0.55 为最强 |
| `md/2510.08521v2.md` | FlowSearch（上海 AI Lab） | 系统架构 | 把 DR 建模为**动态结构化知识流（DAG 计划图）**，Planner→Collector→Refiner 多智能体，GAIA 82.42% 刷新当时纪录 |
| `md/2510.14438v2.md` | WebAggregator（CUHK/腾讯） | 数据合成+训练 | 揭示"检索成功≠任务成功"，组合推理才是瓶颈；用自动合成轨迹（10K QA）微调出超越 GPT-4.1 的 agent 模型 |
| `md/NeurIPS-2025-webthinker….md` | WebThinker（人大，NeurIPS 2025） | 训练型系统 | 给推理模型装上 Deep Web Explorer + "思考-检索-写作一体化"，用迭代在线 DPO 强化工具使用；HLE 超 o3-mini-high |
| `md/6361_DeepTRACE_Auditing_Deep_R.md` | DeepTRACE（Salesforce/微软） | 可信度审计 | 以用户研究失败案例为源头建 8 项社会技术指标，审计 9 个公开 GSE/DR：片面性、无支撑陈述、引用错位普遍严重 |
| `md/8149_DRBench_A_Realistic_Bench.md` | DRBench（ServiceNow） | 企业基准 | 首个"公开 web + 私有企业系统"DR 基准（100 任务/1093 insight），揭示 insight 召回率极低、缺"缺失知识检测" |
| `md/Beyond-Single-shot-Writing.md` | MRDRE（NYU 等） | 修订能力基准 | 首次把"多轮按反馈修订报告"列为评测轴：改一处坏一片（break 率 16-38%），推理期修补无效 |
| `md/DR-Arena.md` | DR-Arena（NUS 等） | 动态评测框架 | 用实时信息树自动出题+考官自适应加难，与 LMSYS Search Arena 人工排名 Spearman 0.94，静态基准相关性为负 |
| `md/DREAM.md` | DREAM（AWS Agentic AI） | 评测方法论 | 提出 "Mirage of Synthesis"：静态评委测不出时间衰减/推理缺陷/外部错误；评测也应 agentic（能力对等原则） |
| `md/reportlogic.md` | ReportLogic（Leiden/蚂蚁） | 逻辑质量评测 | 以"可审计性"定义报告逻辑质量（宏/阐述/结构三层 8 维），训练 LogicJudge；LLM 评委易被冗长等表面线索欺骗 |
| `md/2410.23166v2.md` | SciPIP（浙江大学等） | 邻近领域（科研 idea 生成） | 多粒度文献检索 + 双通道 idea 生成（内部知识 vs 检索文献），属于 DR Phase III 的前沿样本 |

---

# 第二部分 Deep Research 的基本流程、机制与最佳实践

## 2.1 通用流水线（所有 DR 系统的公共骨架）

综合 11 篇语料对各家系统的描述，主流 DR 系统共享如下"骨架"（差异体现在每一环的实现细节）：

```
用户查询 q（常附 persona/企业上下文）
   │
   ▼
① 查询分析与澄清 ──────────（部分产品先提问澄清，如 Gemini/OpenAI DR 的追问）
   ▼
② 规划：把 q 分解为子问题/调查域
   │   （顺序清单 | 并行子问题 | 树/图状计划 | 自适应增删改）
   ▼
③ 信息获取循环（核心）：
   │   生成搜索查询 → 检索（搜索 API / 浏览器交互）
   │   → 阅读/解析（点链接、点按钮、翻页、读 PDF/表格/图/音视频）
   │   → 信息筛选与去噪 → 写入"证据记忆"
   │   ↑_________基于新证据再次规划（分支/回溯）___________│
   ▼
④ 综合与报告生成：从证据记忆取 top-k → 组织大纲 → 逐节撰写（或边搜边写）
   ▼
⑤ 引用/出处标注（citation）＋ 可能的修订轮（self-reflection / 用户反馈）
   ▼
⑥ 输出：带内联引用的长报告（结构化 JSON 或 Markdown）
```

以 OpenAI 的 Deep Research 系统卡为公开样例：底层是"为浏览优化的 o3 变体"，在沙箱中操作浏览器与 Python 工具，任务通常 5-30 分钟，轨迹中实时计划、检索、阅读（文本/图像/PDF）、分析（执行代码）、根据遇到的信息回溯改道，最终综合数百个来源成文。Google Gemini Deep Research、Perplexity、xAI 的公开描述大致同构。

## 2.2 四个关键机制维度（它们构成 DR 的设计空间）

综述（Shi et al.）把系统差异归纳为四大组件，结合语料逐一展开：

### (1) 规划机制：从"线性清单"到"动态图流"

- **顺序分解**：把问题切成子查询按序执行（多数早期开源 agent，LangChain ODR 等）。
- **并行子问题 / 树状搜索**：宽而浅；适合覆盖枚举类任务。
- **图/流式计划（FlowSearch 的关键创新）**：把研究过程建模为有向无环图 G=(V,E)：节点 = 带类型的子任务（search/solve/answer），边 = 知识依赖关系。由 **Knowledge Flow Planner** 增量扩展图、**Knowledge Collector** 并行执行"最外层可执行节点"（每个节点产出可复用的知识摘要）、**Knowledge Flow Refiner** 依据中间发现对图做增/删/改节点与边的操作。消融实验给出了该机制的量级：顺序规划 55.76 → 图式规划 61.82 → +动态 Refiner **82.42**（GAIA，o4-mini 基座），说明**结构化依赖建模 + 动态修正**是大幅领先的关键。
- **企业场景的自适应行动规划（AAP）**：DRBench 的消融显示，简单规划（SRP）保真性最好、复杂规划（CRP）抗干扰最好、**自适应规划（AAP）对 insight 召回与报告质量的增益最大**（召回 13.18→15.97，报告质量 88.23→90.08）；但把 CRP/SRP 与 AAP 叠加反而下降——"计划越复杂越不稳"是一个普遍的工程教训。

### (2) 信息获取：检索 API vs 浏览器级探索

- **浅层检索**：单轮/迭代的 search API 检索（经典 RAG、RAG+查询规划）。
- **深层浏览**（WebThinker 的 Deep Web Explorer、FlowSearch 的浏览器工具集、OpenAI DR 的浏览器操作）：模型在网页内**点链接、点按钮、翻页**，跟随证据链进入深网。WebThinker 消融证明：去掉 Deep Web Explorer 使复杂推理平均分从 45.4 掉到 38.3；去掉"点链接"能力也从 45.4 掉到 42.6——**深链探索是 DR 区别于普通 RAG 的能力分水岭**。
- FlowSearch 的 Knowledge Collector 提供 13 种工具（google/wiki/wayback 快照/文档抽取/图片问答/OCR/代码执行等），任务类型驱动工具组合。
- 企业场景则要求通过 API/WebDAV/IMAP 检索私有系统（DRBench），浏览器-only 的通用 web agent 在该场景 insight 召回仅 1.11%——**数据源异构性与应用内导航是另一维度上的"深"**。

### (3) 证据记忆与管理

长任务中必须把早期发现沉淀下来，主流做法：
- **向量库/文档记忆**：DRBench Agent 每次迭代把处理过的内容写入带元数据的 vector store，报告阶段做语义检索，防止"长会话中信息丢失"；WebThinker 用 document memory M 存放所有浏览过的网页，写作工具从中取 top-k。
- **结构化节点知识**：FlowSearch 每个已执行节点只向下游传**摘要化的知识上下文**（而非原始页面），选择性复用先验知识、限制无关信息传播——缓解长链推理中常见的"信息稀释"。
- **Claims/DAG 表示**：LiveDRBench 主张中间产物应以"claim→subclaim"结构记录，把检索-推理过程变成可审计的产物流。

### (4) 报告生成：一次性综述 vs "思考-检索-写作"一体化

- **先搜后写**：多数产品先完成全部检索再让写作模型成文；缺点是检索目标在写作时可能已变化，且长报告易与证据脱节。
- **边想边搜边写（Autonomous Think-Search-and-Draft，WebThinker）**：主推理模型掌握 draft/check/edit 三个写作工具，先写已获足证据的章节，再按需补搜补写。在 Glaive 科学报告任务上 WebThinker 平均分 8.1/10，**超过 Gemini 2.0 Deep Research（7.9）与 Grok3 DeeperSearch（6.5）**；消融显示去掉"边写边搜"后报告质量从 8.1 暴跌到 6.6，是最大单点损伤。t-SNE 分析显示其报告覆盖的信息子空间明显更广。
- 大纲驱动的变体（STORM 的 outline-driven retrieval、WebWeaver 的动态大纲）与此同族，核心都是"让结构先行、内容随证据演化"。

## 2.3 两条实现路线：编排（Orchestration）vs 训练（Training）

语料反复出现的二分法：

**路线 A：Agent 编排 / 提示工程路线**（不改模型权重）
- 代表：HuggingFace Open DeepResearch、LangChain Open Deep Research、DeerFlow、OWL、DRBench Agent、FlowSearch（用现成 LLM 当 planner/collector/refiner）。
- 优点：换基座即升级、可解释性强；缺点：轨迹不稳定、容易死循环（LiveDRBench 提到 HF DR 与 LangChain ODR 在实验中直接因无限循环/系统错误而跑不完）、规划冗余、token 成本高。

**路线 B：训练路线（SFT + RL，把工具使用内化进模型）**
- **DeepResearcher**（GAIR-NLP）：第一个在**真实开放网**上用端到端 RL（GRPO、仅结果奖励：答案 F1）训练 DR agent 的工作；涌现出规划、多源交叉验证、自我反思改道、"无法确定时诚实承认"等行为，相对提示工程基线最高提升 28.9 分。这是"open web RL"范式的源头。
- **WebThinker**：在线迭代 DPO，偏好三元组规则为"正确性优先 → 工具调用更少优先 → 思考更精简优先"；RL 使 GAIA 44.7→48.5、HLE 13.0→15.8，并可在小模型上迁移（R1-7B 经 SFT+RL 冷启动后 GAIA 相对提升 174%）。
- **DR Tulu**（UW，arXiv:2511.19399）：把报告写成"检索-验证-写作"闭环并用 RLHF + evolving rubrics 训练的开源 DR 模型，是开源侧报告质量最强者之一。
- 其他：Search-R1 / R1-Searcher（先训"搜索推理"）、Pangu DeepDiver（自适应搜索强度缩放）、WebAggregator 的"合成轨迹 SFT"、SciPIP（数据库构建+双通道生成，属于领域内"文献检索→idea"的专用化训练数据方案）。

**结论性观察（多篇论文交叉印证）**：最好的系统往往是 **"强推理基座 + 训练内化的工具使用 + 结构化动态计划"** 三者结合；单纯堆 prompt/编排在复杂 DR 上脆弱，单纯堆模型不做工具训练则检索利用不足（WebThinker 论文中 RAG-增强推理模型在 HLE 上反而常低于纯推理基线，说明"浅层检索 × 深度推理"不匹配）。

## 2.4 谁是目前最好的 Deep Research，为什么？

综合多份独立评测（不同时期快照，谨慎比较）：

| 评测 | 最强系统 | 关键数字 | 备注 |
|---|---|---|---|
| LiveDRBench（微软，~2025 夏） | **OpenAI Deep Research** | 整体 F1 0.55（其余：Perplexity 0.355、Gemini 0.263、开源 DeepResearcher+Qwen32B 仅 0.075）；各类目 0.02-0.72 | 开源与闭源差距巨大；o3(high reasoning)+高效提示可到 0.666 |
| DeepTRACE（2025-08-27 快照） | **GPT-5 Deep Research** | 未引用来源 0%、无支撑陈述 12.5%、来源必要性 87.5%、引用准确率 79.1%、引用充分率 87.5%——唯一在多数维度进入"可接受/临界"区间的 DR | Perplexity DR 无支撑陈述高达 97.5%；Copilot(TD) 90.2% |
| DeepResearch Bench RACE（Du et al.） | Gemini 2.5 Pro DR 48.88 / OpenAI DR 46.98 | DR 专用系统领先通用 LLM+搜索 6-9 分 | 中文+英文 100 题 |
| DR-Arena 与 LMSYS Search Arena（2025-12） | GPT-5.1-Search ≈ Gemini-2.5-Pro-Grounding ≈ o3-Search | 人类盲评 Elo 1201/1142/1139 | DR-Arena 自动排名 Spearman 0.94 复现该序 |
| GAIA / HLE / GPQA（2025 下半年） | FlowSearch(o4-mini)：GAIA 82.42；WebThinker-32B-RL：HLE 15.8 超 o3-mini(high) | 结构化图流+Refiner 的 82.42 vs OpenAI DR 67.4 vs Manus 73.3 | 训练型小模型的 GAIA 已逼近产品级 |

**为什么它们更强？——从失败分析反推的机理（这是本报告最想强调的部分）**

LiveDRBench 对推理轨迹做了三种剖析，直接回答"什么决定 DR 成败"：

1. **广度（搜索覆盖）是精确性的第一杠杆**。把每个问题所需的"必要查询"（不查就答不全的查询）枚举出来再比对各家轨迹：最强模型也只覆盖了 **66%** 的必要查询（Perplexity 52%、Gemini 46.8%、开源模型 ~49-53%）；分支数最多的 OpenAI DR 得分最高，作者明确写道 "the key role of breadth in DR answer accuracy"。→ 最好的系统 = 能自动补全"该搜而没搜"的查询集合的系统。
2. **深度（依赖前序查询的追问）决定多因素综合的质量**。闭源模型平均每任务发 24-64 个查询、其中 15-39 个是依赖型追问；开源 DeepResearcher 只有 5-6 个查询、5 个依赖——深度不足直接导致 subclaim 提取不全（例：SCIFACTS Materials 中模型常答对材料名却给错论文、或反之，F1 被压到 0.31-0.02）。
3. **组合推理是"检索之后"的新瓶颈**（WebAggregator）：即便把所有正确答案来源的 URL 全部给模型，Claude-3.7 也只有 42.1% 答对——**错误主要发生在证据的聚合/推导环节而非检索环节**；失败模式可归类为"错误组合（faulty composition，无根据假设）"、"误差累积（如过早四舍五入）"、"无效自我修正"。→ 用"推理密集"的合成数据做 SFT/RL 训练（WebAggregator：SFT 后推理步占比 18.6%→26.2%、工具调用密度反而下降），是把"检索密集"的 agent 变成"推理密集"agent 的有效路径。

综合以上证据，**"最好"的 DR 系统遵循如下设计准则**（可作为工程清单）：

1. **计划要结构化且可动态修订**（图流优于线性清单；执行中可增删节点）；
2. **搜索要广**：显式枚举"必要查询"、多分支并行、容忍回溯；宁多勿漏（recall 是主要失分点）；
3. **浏览要深**：能点进链接/按钮获取原文而非满足于摘要；
4. **证据要可控**：中间结论以摘要/claim 形式持久化，写入可追溯记忆，向下游只传播相关信息；
5. **写作要边想边写**，引用与陈述一一对应、每个陈述可独立验证（DeepTRACE 中 GPT-5(DR) 与低分系统的最大差异正是"每句都有支撑引用"的纪律）；
6. **要经过工具使用强化学习**（结果奖励即可涌现规划/交叉验证/反思），而非纯提示编排；
7. **知道何时收手**：无法找到证据时诚实声明不确定性（DeepResearcher 涌现行为），且校准信心表达（DR 模式下过度自信显著低于 GSE 模式）。

---

# 第三部分 当前缺陷、影响与证据

把 11 篇语料中的失败证据按缺陷维度组织如下（每条附来源与量化证据）：

## 3.1 搜索覆盖不足：只覆盖一半必要查询

- **证据**：LiveDRBench 轨迹分析（`18936…md` Table 5）：全部被测 DR 系统的"必要查询覆盖率"在 46.8%~66% 之间；类别 F1 最低至 0.02（Gemini DR 在材料识别上）。
- **定性例证**：对"找一篇无显式指令、靠示例迁移的图像编辑评测论文"这类问题，只有 Gemini DR 发起了"图像间编辑迁移方法"查询，OpenAI/Perplexity/DeepResearcher 全部漏掉；对"场景分割的野外长视频数据集"问题，Gemini 与 DeepResearcher 全部漏掉关键查询。
- **影响**：系统性漏检 = 报告"看似完整实则缺关键证据"，在枚举类（如"全部满足条件的影片"）与材料发现类任务中直接判错。

## 3.2 事实性与来源支撑缺陷："来源幻觉"与引用错位

- **证据（DeepTRACE）**：对 303 个问题 × 9 个公开系统（快照 2025-08-27）：
  - 无支撑陈述比例：GSE 模式 23.1%~47.0%；**DR 模式反而更糟**——Perplexity DR 97.5%、Copilot Think Deeper 90.2%、YouChat DR 74.6%（GPT-5 DR 是唯一例外 12.5%）；
  - 引用准确率（citation accuracy）全系统只有 40~80%；引用了正确来源的比例普遍低于 50% 被标为"问题级"；
  - 冗余来源：Gemini DR 的 14.5% 来源从未被正文引用，仅 1/3 的来源是"必要来源"；
  - "列很多来源却不引用"造成**虚假严谨感**：来源数量与可靠性几乎无关（Bing GSE 平均列 4 个来源但 1/3 未被引用、仅一半必要）。
- **机理**：长报告逐句标注引用的"引用纪律"未被 RL/训练充分内化；来源必要性（用最小顶点覆盖算出的"缺了它就有陈述无法被支持"的来源占比）在多数系统只有 5.5%~63%。
- **影响**：用户点开引用无法验证→信任侵蚀；"貌似严谨"比"明确不知道"更危险（社会技术视角）。

## 3.3 片面性与过度自信：争议问题的"回音室"

- **证据（DeepTRACE）**：对辩论型问题（ProCon 来源），GSE 的片面回答率 48.7%~90.4%，过度自信（片面+最强信心）率最高 81.6%（Perplexity）；**DR 模式没有解决问题**：片面率 54.7%（GPT-5 DR）~94.8%（Copilot TD）。附录截图展示：GPT-5 DR 对"为什么该禁瓶装水"与"为什么不该禁瓶装水"分别输出各自立场的内容，不做双面覆盖。
- **影响**：迎合提问立场的 sycophancy 会把搜索变成回音室，对有争议公共议题的信息获取形成系统性偏差；对"中立信息入口"的产品承诺是根本性打击。

## 3.4 组合推理失败："检索成功 ≠ 任务成功"

- **证据（WebAggregatorQA）**：即使访问了全部参考 URL（拿到金证据），Claude 正确率仅 42.1%、GPT-4.1 33.3%、Qwen3-32B 仅 9.7%（其检索强而推理弱）；失败归因三类：错误组合（对证据做了无依据的假设）、误差累积（小错滚成致命错）、无效修正（agent 无法放弃错误推理路径，一条道走到黑直至超时/幻觉）。
- **影响**：这是**当前 DR 能力天花板**所在——"检索密集、推理稀疏"是行业普遍状态；DR-Arena 对顶尖模型的失败类型统计也显示 DEPTH（逻辑）与 WIDTH（覆盖）失败各占约 1/3，且两线同败（BOTH）稳定在 20-30%，说明推理与覆盖的合成是最难的部分。

## 3.5 修订不可靠：改一处、坏一片

- **证据（MRDRE）**：5 个主流 DR（OpenAI o4-mini DR、Perplexity Sonar DR、LangChain ODR、Tongyi DR、DR Tulu）× 内容/格式/自我反思三类反馈：
  - 反馈"吸收率"普遍 >90%，但**同时破坏 16%~38% 已有覆盖内容**（break rate）；第二轮平均破坏率内容反馈 ~31%、格式反馈 ~21%；
  - 多轮修订（4 轮）下累计增益远低于理想（oracle），到第 4 轮差距 9%~26%；历史修正"回头被破坏"——Sonar DR 的 all-history 吸收率从 90% 掉到 66%；
  - **引用质量系统性退化**：自我反思后 Sonar DR 有 68% 的报告零引用；OpenAI DR 的受支持 claims 平均每轮 -7.0 条；
  - **推理期修补无效**：prompt engineering（把反馈转成编辑计划）与专用 Reviser 子 agent 都无法根治（破坏率仍 >10%，引用退化依旧）。
- **影响**：真实用户几乎总会提修改意见；"越改越坏"意味着 DR 目前只适合一次性交付，无法承担**迭代式知识工作**（撰写、审阅、再修改的常态）。

## 3.6 评测自身的缺陷：静态基准失灵与 "Mirage of Synthesis"

- **时间错位与污染**：DR-Arena 指出静态基准随时间衰减（金答案过时却惩罚拿到新证据的 agent），且被反复使用的题会进入训练语料（参数记忆作弊）；其对照实验显示 FutureSearch 的 Deep Research Bench 与人工排名相关性为 **-0.90**（负相关！），LiveResearchBench -0.63，而动态生成的 DR-Arena 达到 0.94。
- **表面流畅掩盖深层缺陷**：DREAM 用受控实验证明现有基准的三类盲区：
  - *时间敏感性*：对"过时一个月的报告"，DeepResearch Bench 的 RACE 综合分纹丝不动（50.02→50.04），而 DREAM 的 KIC 从 79.35 单调降到 44.80（知识截止一个月前）再降到 22.34；
  - *推理缺陷*：注入循环论证等逻辑错误后，RACE 只下降 ~9% 且多次出现"畸形报告得分更高"，DREAM-RQ 稳定下降 ~40%；
  - *外部事实错误*：把事实换成"有引用撑腰的似是而非错误"（citation alignment 保持成立），DRB-FACT 分数**完全不变**，DREAM-Factuality 与真实错误率同步单调下降。
- **影响**：基准分数被"Mirage of Synthesis"架空；业界排行榜可能系统性高估模型的真实可靠性。这也是 DR-Arena（实时信息树+自适应考官）、DREAM（agentic 评测）、ReportLogic（逻辑评测）、DeepTRACE（社会技术审计）共同出现的原因。

## 3.7 报告逻辑质量缺陷（新维度的缺失）

- **证据（ReportLogic）**：报告即使事实正确、语句流畅，仍存在三类系统性问题：
  1. *全局不一致*：各段数字局部合理但全局矛盾（例：中国九阶层报告中各阶层占比相加超过 100% 而不自知）；
  2. *平滑但不连贯*：用"此外/从职业发展角度看"等连接词制造过渡假象，实质是维度切换而非推理递进（例：辞职读博分析中风险块与收益块之间缺少决策准则桥）；
  3. *无支撑的因果 warrant*：把"行业扩张/政策支持/技术进步"直接当作"需求上升"的原因，缺中间机制（例：细胞裂解仪市场报告）。
- 模型评测本身：off-the-shelf LLM judge 被**冗长**（length bias 是最有效的攻击）、结构化排版等表面线索欺骗；推理模式评委（o3）反而会"脑补"缺失的推理链从而放过缺陷；人类标注者无 rubric 时 κ=0.37，用上下文感知 rubric 时 κ=0.71。
- **影响**：DR 报告的可审计性（读者能追踪、理解、验证分析过程）是落地于决策场景的前提，目前即便强模型也普遍不合格（逻辑评测下最强模型约 74-75% 人类一致率）。

## 3.8 综合影响小结

1. **对用户**：误信错误/片面/错引信息；验证成本转移给用户（"search fatigue"）；在争议议题上形成回音室。
2. **对开发者**：评测坐标系碎片化（一年内涌现数十个基准、方法学互不兼容、静态基准相互矛盾），模型迭代缺乏可信信号；RL 训练数据与评测数据互相污染的循环加速。
3. **对科研应用**：insight 召回率普遍 <40%（企业场景 GPT-5 最好也仅 37.5%）；"缺失知识检测"几乎全无（DRBench 中没有任何 agent 成功意识到"关键法规不在私有文件里、需要上网查"，尽管这正是问题设置的核心）。
4. **对评测自身**：Mirage of Synthesis——被高估的报告质量掩盖了时间衰减、外部错误与逻辑缺陷，需要 agentic/动态/多维度评测范式。

---

# 第四部分 代表性论文清单与阅读路线

> 说明：以下清单**不局限于本地语料**，是在精读 11 篇本地论文（其引文网络覆盖 2025 全年）基础上，经网络检索补充确认后形成的"代表性论文集"。每篇标注：为什么读（关键信息）＋出处。★= 本地已有全文；建议按"路线 A/B/C"分层阅读。

## A. 入门与总览（先读这 4 篇建立地图）

| # | 论文 | 为什么读 |
|---|---|---|
| A1 ★ | [Characterizing Deep Research: A Benchmark and Formal Definition（LiveDRBench，微软）](md/18936_Characterizing_Deep_Rese.md)（arXiv:2508.04183） | 唯一的 DR **形式化定义**（搜索×推理强度 + claim 评测），全领域引用锚点；附全套开放基准与轨迹分析方法。 |
| A2 | Deep Research Agents: A Systematic Examination and Roadmap（Huang et al.，[arXiv:2506.18096](https://arxiv.org/abs/2506.18096)） | 领域第一份系统综述：单/多智能体架构分类、静态/动态工作流、评测批判与路线图；配套 [awesome-deep-research-agent](https://github.com/ai-agents-2030/awesome-deep-research-agent) 持续更新的文献仓库。 |
| A3 | Deep Research: A Systematic Survey（Shi et al.，[arXiv:2512.02038](https://arxiv.org/abs/2512.02038)） | 更新的三阶段路线图（Agentic Search → Integrated Research → AI Scientist）＋四组件（规划/获取/记忆/生成）＋训练优化分类，100+ 系统与数据集的一站式索引。 |
| A4 | [OpenAI Deep Research System Card](https://cdn.openai.com/deep-research-system-card.pdf) | 产业标杆的一手设计文档：o3 浏览优化、RL 训练、浏览器+Python 沙箱、5-30 分钟轨迹、安全评测（prompt injection 缓解等）——理解"产品级 DR 怎么做"。 |

## B. 系统与训练方法（理解"怎么实现"，含演进谱系）

**B1 前驱（为什么会有 DR）**
- RAG（Lewis et al.，2020）——静态检索增强的起点；
- [WebGPT（OpenAI，2021）](https://arxiv.org/abs/2112.09332)——人类反馈训练浏览器问答，最早的"GPT 上网"；
- [ReAct（Yao et al.，ICLR 2023）](https://arxiv.org/abs/2210.03629)——推理与行动交错，所有 agent 骨架的鼻祖；
- [GAIA（Mialon et al.，ICLR 2024）](https://arxiv.org/abs/2311.12983)——通用助手基准，被所有 DR 评测引用；
- [STORM（Shao et al.，NAACL 2024）](https://arxiv.org/abs/2402.14207)——大纲驱动检索 + 多视角提问，长文写作前驱；
- [BrowseComp（OpenAI，2025）](https://arxiv.org/abs/2504.12516)——"problem inversion"造题法（答案难找易验），LiveDRBench 的方法学源头。

**B2 开源编排型系统**
- HuggingFace Open DeepResearch（blog，2025）、LangChain Open Deep Research（blog，2025）、DeerFlow（字节）、OWL——"通用脚手架"四件套，对比阅读可看出工程取舍（并行检索、压缩、记忆）。
- ★ [FlowSearch（上海 AI Lab，arXiv:2510.08521）](md/2510.08521v2.md)——知识流图（DAG 计划 + 动态 Refiner），GAIA 82.42 的机制拆解；消融表直接量化"图式计划 vs 线性计划"。
- [OpenScholar（Allen AI，arXiv:2411.14199）](https://arxiv.org/abs/2411.14199)——面向文献的检索-综合专用系统，体现"领域化检索器 + 合成数据"路线。

**B3 训练型系统（RL 内化工具使用）——当前最活跃主线**
- [DeepResearcher（GAIR，arXiv:2504.03160）](https://arxiv.org/abs/2504.03160)——真实开放网上端到端 GRPO，结果奖励涌现规划/交叉验证/诚实，开源 DR-RL 开山作；
- ★ [WebThinker（人大，NeurIPS 2025）](md/NeurIPS-2025-webthinker-empowering-large-reasoning-models-with-deep-research-capability-Paper-Conference.md)（arXiv:2504.21776）——推理模型 + Deep Web Explorer + 边想边写 + 在线 DPO 的完整范本；
- [Search-R1（arXiv:2503.09516）](https://arxiv.org/abs/2503.09516)/R1-Searcher——"检索式 RL"与 DR RL 的分野处，建议对比读；
- [DR Tulu（UW，arXiv:2511.19399）](https://arxiv.org/abs/2511.19399)——开源报告型 DR 的 SOTA 方法（evolving rubrics RL），MRDRE 中被测的最佳"修订保持"模型；
- [Pangu DeepDiver（华为，arXiv:2505.24332）](https://arxiv.org/abs/2505.24332)——自适应搜索强度缩放，回答"搜多少轮合适"；
- ★ [WebAggregator（CUHK/腾讯，arXiv:2510.14438）](md/2510.14438v2.md)——合成"推理密集"轨迹数据训练 agent（10K QA/50K 站点），顺带给出了当前最清晰的组合推理失败学。

**B4 专用/邻近系统**
- [AI Scientist（Sakana，arXiv:2408.06292）](https://arxiv.org/abs/2408.06292) / Google AI Co-Scientist——Phase III 全栈科学家；
- ★ [SciPIP（浙大等，arXiv:2410.23166）](md/2410.23166v2.md)——idea 生成：多粒度文献检索（关键词×语义×共引）+ 双通道生成，是"DR 用于科学发现"的代表。

## C. 评测与缺陷研究（理解"怎么测、差在哪"）

**C1 结果型基准（单答案/单一交付物）**
- [DeepResearch Bench（Du et al.，arXiv:2506.11763）](https://arxiv.org/abs/2506.11763)——100 个博士级双语任务，RACE（报告质量）＋FACT（引用准确性）双体系，使用最广的通用 DR 基准；
- [DeepResearchGym（Coelho et al.，arXiv:2505.19253）](https://arxiv.org/abs/2505.19253)——固定语料沙箱 + 免费可复现；
- [BrowseComp-Plus（arXiv:2508.06600）](https://arxiv.org/abs/2508.06600)——10 万页静态语料上的大规模可控评测；
- [ResearcherBench（arXiv:2507.16280）](https://arxiv.org/abs/2507.16280) / [LiveResearchBench（arXiv:2510.14240）](https://arxiv.org/abs/2510.14240) / ResearchRubrics（arXiv:2511.07685）——"实时性/用户中心/专家 rubrics"三条路线代表。

**C2 缺陷与可信度研究（本报告第三部分的证据源）**
- ★ [DeepTRACE（Salesforce/微软，2025）](md/6361_DeepTRACE_Auditing_Deep_R.md)——8 项社会技术审计指标 + 9 系统公开审计数字；
- ★ [MRDRE（NYU 等，2025）](md/Beyond-Single-shot-Writing.md)——多轮修订评测协议（吸收率/破坏率/引用退化）；
- ★ [DREAM（AWS，2025）](md/DREAM.md)——Mirage of Synthesis 的受控实验证据 + 四维评测垂直体系；
- ★ [ReportLogic（Leiden/蚂蚁，2025）](md/reportlogic.md)——逻辑质量三层八维 + LogicJudge + 对抗攻击鲁棒性；
- [Deep Research Comparator（arXiv:2507.05495）](https://arxiv.org/abs/2507.05495)（微软）——细粒度人工标注平台。

**C3 动态/竞技场评测**
- ★ [DR-Arena（NUS 等，2025）](md/DR-Arena.md)——实时信息树 + 自适应考官 + Swiss 锦标赛，与 [Search Arena（LMSYS，arXiv:2506.05334）](https://arxiv.org/abs/2506.05334) 对齐 0.94；
- [DeepWideSearch（arXiv:2510.20168）](https://arxiv.org/abs/2510.20168)——"深度×宽度"二维任务定义（DR-Arena 沿用）；
- [Mind2Web 2（arXiv:2506.21506）](https://arxiv.org/abs/2506.21506)——agent-as-a-judge 的轨迹级评测；
- ★ [DRBench（ServiceNow，2025）](md/8149_DRBench_A_Realistic_Bench.md)——企业私有+公开数据环境（Docker 五应用），insight 级评测三轴（召回/事实性/报告质量）。

**C4 企业/私有数据（接 C1）**
- [TheAgentCompany（arXiv:2412.14161）](https://arxiv.org/abs/2412.14161)、CRMArena（2025）——DR 之外的企业 agent 环境，用于对比理解"企业 DR 的独特难度"。

## 建议阅读路线

- **路线 A：想快速建立领域认知（0.5-1 周）**：A4 → A1 ★ → A2 → B2 中 FlowSearch ★ → WebThinker ★ → C2 中 DeepTRACE ★（挑一份缺陷报告读透）。
- **路线 B：想入门做 DR 系统研究（2-4 周）**：A1-A3 → B1 全部 → B3 全部（按时间序读，重点对比 DeepResearcher vs WebThinker vs DR Tulu 的训练信号设计）→ C1 中 DeepResearch Bench + BrowseComp-Plus → 复现一个开源系统（HF ODR 或 WebThinker）跑 GAIA/WebWalkerQA。
- **路线 C：想做 DR 评测/可信度研究（2-4 周）**：C1 全部 + C2 全部 + C3 全部，重点对照"静态结果型 vs 动态 agentic 型"两类评测哲学的争论（DREAM/DR-Arena 批判前者，DeepResearch Bench 是前者代表）；深入 DREAM 与 DR-Arena 的受控实验设计（时间衰减注入、推理缺陷注入、信息树构造）作为方法学模板。

---

# 第五部分 结论与展望

**核心结论（一页版）**
1. Deep Research 是"高搜索强度 × 高推理强度、输出多 claim 长报告"的信息综合任务，其本质难点在搜索过程的**概念高扇出**，而非写作本身。
2. 当前最佳实践 = 强推理基座 + RL 内化的浏览器级深检索 + 结构化动态计划 + 引用纪律；业界最好系统（OpenAI DR、Gemini DR、FlowSearch、WebThinker 等）彼此差距已缩小，但共同受限于**必要查询覆盖不足（~50-66%）**与**组合推理缺陷**。
3. 最尖锐的缺陷不是"答案错了"而是**可信度系统性问题**：无支撑陈述（最高 97.5%）、引用错位、争议问题片面化、改一处坏一片的修订失败、以及被静态评测掩盖的时效/逻辑/外部事实错误（Mirage of Synthesis）。
4. 评测本身正经历从"静态一次性基准"到"动态、agentic、多维度、可审计"的范式迁移；这是当前领域最有研究红利的位置。

**未来方向（按语料中多篇论文的展望汇总）**
- **训练侧**：把"修订保持"（MRDRE）、"缺失知识检测"（DRBench）、"组合推理"（WebAggregatorQA）作为显式训练信号；过程级 RL 奖励（proximal/multi-turn credit assignment）；小模型蒸馏（WebThinker R1-7B 路径）。
- **评测侧**：统一评测协议（对标 DREAM 四维垂直与 MRDRE 的统一报告评测）；动态信息树/活网基准常态化；LLM-as-judge 的去偏与对抗鲁棒性（ReportLogic 的攻击框架）；把"可审计性/逻辑质量/平衡性"纳入产品级指标（DeepTRACE、ReportLogic）。
- **能力侧**：多模态（图片/图表/视频）深研（WebThinker 已明言缺失）；GUI 级浏览与网页应用内操作（企业场景）；个性化记忆与持续研究（对同一课题的多轮加深而非每轮从头再来）；多 agent 协作研究（FlowSearch/AI Scientist 谱系）。
- **社会学侧**：为"来源-陈述"一致性设定可验证标准，避免把验证成本转嫁给用户；对争议议题保证观点平衡（DeepTRACE 的呼吁）。

---

# 第六部分 本地语料索引与参考文献

## 6.1 本地语料索引（11 篇，均可点击打开）

| 文件 | 对应论文 |
|---|---|
| [md/18936_Characterizing_Deep_Rese.md](md/18936_Characterizing_Deep_Rese.md) | Java et al. (Microsoft Research), *Characterizing Deep Research: A Benchmark and Formal Definition*, arXiv:2508.04183（LiveDRBench） |
| [md/2510.08521v2.md](md/2510.08521v2.md) | Hu et al. (Shanghai AI Lab), *FlowSearch: Advancing Deep Research with Dynamic Structured Knowledge Flow*, arXiv:2510.08521 |
| [md/2510.14438v2.md](md/2510.14438v2.md) | Wang et al. (CUHK/Tencent), *WebAggregator: Enhancing Compositional Reasoning Capabilities of Deep Research Agent Foundation Models*, arXiv:2510.14438 |
| [md/NeurIPS-2025-webthinker-empowering-large-reasoning-models-with-deep-research-capability-Paper-Conference.md](md/NeurIPS-2025-webthinker-empowering-large-reasoning-models-with-deep-research-capability-Paper-Conference.md) | Li et al. (RUC), *WebThinker: Empowering Large Reasoning Models with Deep Research Capability*, NeurIPS 2025 / arXiv:2504.21776 |
| [md/6361_DeepTRACE_Auditing_Deep_R.md](md/6361_DeepTRACE_Auditing_Deep_R.md) | Narayanan Venkit et al. (Salesforce/Microsoft), *DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Citations and Evidence* |
| [md/8149_DRBench_A_Realistic_Bench.md](md/8149_DRBench_A_Realistic_Bench.md) | Abaskohi et al. (ServiceNow), *DRBench: A Realistic Benchmark for Enterprise Deep Research* |
| [md/Beyond-Single-shot-Writing.md](md/Beyond-Single-shot-Writing.md) | Chen et al. (NYU et al.), *Beyond Single-shot Writing: Deep Research Agents are Unreliable at Multi-turn Report Revision*（MRDRE） |
| [md/DR-Arena.md](md/DR-Arena.md) | Gao et al. (NUS/SMU/SUTD), *DR-Arena: an Automated Evaluation Framework for Deep Research Agents* |
| [md/DREAM.md](md/DREAM.md) | Ben Avraham et al. (AWS Agentic AI/Georgia Tech), *DREAM: Deep Research Evaluation with Agentic Metrics* |
| [md/reportlogic.md](md/reportlogic.md) | Zhao et al. (Leiden Univ./Ant Group/CISPA), *ReportLogic: Evaluating Logical Quality in Deep Research Reports* |
| [md/2410.23166v2.md](md/2410.23166v2.md) | Wang et al., *SciPIP: An LLM-based Scientific Paper Idea Proposer*, arXiv:2410.23166 |

## 6.2 网络检索补充的主要外部文献

1. Huang, Y. et al. *Deep Research Agents: A Systematic Examination and Roadmap*. arXiv:2506.18096. https://arxiv.org/abs/2506.18096
2. Shi, Z. et al. *Deep Research: A Systematic Survey*. arXiv:2512.02038. https://arxiv.org/abs/2512.02038
3. OpenAI. *Deep Research System Card*. https://cdn.openai.com/deep-research-system-card.pdf
4. Zheng, Y. et al. *DeepResearcher: Scaling Deep Research via Reinforcement Learning in Real-world Environments*. arXiv:2504.03160. https://arxiv.org/abs/2504.03160
5. Du, M. et al. *DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents*. arXiv:2506.11763. https://arxiv.org/abs/2506.11763
6. Xu, R. & Peng, J. *A Comprehensive Survey of Deep Research: Systems, Methodologies, and Applications*. arXiv:2506.12594. https://arxiv.org/abs/2506.12594
7. Wei, J. et al. *BrowseComp: A Simple Yet Challenging Benchmark for Browsing Agents*. arXiv:2504.12516. https://arxiv.org/abs/2504.12516
8. Mialon, G. et al. *GAIA: a Benchmark for General AI Assistants*. ICLR 2024. https://arxiv.org/abs/2311.12983
9. Shao, Y. et al. *Assisting in Writing Wikipedia-like Articles from Scratch with Large Language Models*（STORM）. arXiv:2402.14207. https://arxiv.org/abs/2402.14207
10. Asai, A. et al. *OpenScholar: Synthesizing Scientific Literature with Retrieval-augmented LMs*. arXiv:2411.14199. https://arxiv.org/abs/2411.14199
11. Coelho, J. et al. *DeepResearchGym: A Free, Transparent, and Reproducible Evaluation Sandbox for Deep Research*. arXiv:2505.19253. https://arxiv.org/abs/2505.19253
12. Xu, T. et al. *ResearcherBench: Evaluating Deep AI Research Systems on the Frontiers of Scientific Inquiry*. arXiv:2507.16280. https://arxiv.org/abs/2507.16280
13. Wang, J. et al. *LiveResearchBench: A Live Benchmark for User-Centric Deep Research in the Wild*. arXiv:2510.14240. https://arxiv.org/abs/2510.14240
14. Sharma, M. et al. *ResearchRubrics: A Benchmark of Prompts and Rubrics for Evaluating Deep Research Agents*. arXiv:2511.07685. https://arxiv.org/abs/2511.07685
15. Shao, R. et al. *DR Tulu: Reinforcement Learning with Evolving Rubrics for Deep Research*. arXiv:2511.19399. https://arxiv.org/abs/2511.19399
16. Lan, T. et al. *DeepWideSearch: Benchmarking Depth and Width in Agentic Information Seeking*. arXiv:2510.20168. https://arxiv.org/abs/2510.20168
17. Miroyan, M. et al. *Search Arena: Analyzing Search-Augmented LLMs*. arXiv:2506.05334. https://arxiv.org/abs/2506.05334
18. Li, X. et al. *Search-o1: Agentic Search-Enhanced Large Reasoning Models*. arXiv:2501.05366. https://arxiv.org/abs/2501.05366
19. Chen, Z. et al. *BrowseComp-Plus: A More Fair and Transparent Evaluation Benchmark of Deep-Research Agent*. arXiv:2508.06600. https://arxiv.org/abs/2508.06600
20. Shi, W. et al. *Pangu DeepDiver: Adaptive Search Intensity Scaling via Open-Web Reinforcement Learning*. arXiv:2505.24332. https://arxiv.org/abs/2505.24332
21. Wu, J. et al. *WebWalker: Benchmarking LLMs in Web Traversal*. ACL 2025（WebWalkerQA）. https://arxiv.org/abs/2504.15337
22. Tao, Z. et al. *WebShaper: Agentically Data Synthesizing via Information-Seeking Formalization*. arXiv:2507.15061. https://arxiv.org/abs/2507.15061
23. Lu, C. et al. *The AI Scientist: Towards Fully Automated Open-ended Scientific Discovery*. arXiv:2408.06292. https://arxiv.org/abs/2408.06292
24. Nakano, R. et al. *WebGPT: Browser-assisted Question-answering with Human Feedback*. arXiv:2112.09332. https://arxiv.org/abs/2112.09332
25. Yao, S. et al. *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023. https://arxiv.org/abs/2210.03629

> 附注：arXiv 编号以检索结果与各论文参考文献交叉核对为准；个别编号（如 2504.15337）来自引用文献转录，使用前请以 arXiv 页面为准。本地语料中的评测数字均为各论文当时快照（如 DeepTRACE 为 2025-08-27），模型快速迭代下会过时，请按引用时间解读。

*——报告完——*
