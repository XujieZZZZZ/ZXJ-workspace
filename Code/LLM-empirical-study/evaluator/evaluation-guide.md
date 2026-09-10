# RQ2 实验测评框架指南

## 子任务一：RQ2-1（相关工作与 Claim 生成能力测评）

**输入**：Observation  
**输出**：LLM 生成的 Related Works ($S_L$) + LLM 生成的 Core Claim ($C_L$)  
**GroundTruth**：人类编写的 Related Works ($S_H$) + 人类编写的 Core Claim ($C_H$)

---

### 1.1 数据预处理与实体匹配 Pipeline (Entity Resolution)

在对比文献前，必须将非结构化的引用文本转化为 Semantic Scholar (S2) 规范化的实体 ID。

记录搜索失败率，记录在semantic schorlar无法检索到的论文，认为是论文为编造或者失败，用于参考其质量。

1. **结构化提取**：从 $S_H$ 和 $S_L$ 中解析出论文的元数据三元组：$\text{Metadata} = (\text{Title}, \text{Authors}, \text{Year})$。
2. **S2 API 匹配**：调用 API 获取 `s2_id`、`doi`、`citationCount`、`venue` 及 `SPECTER2 Embedding` ($v_p$)。
3. **三级匹配判定算法**：判定 $p_l \in S_L$ 与 $p_h \in S_H$ 是否为同一篇论文（生成判定矩阵 $M_{i,j} \in \{0, 1\}$）：
   * **Level 1 (ID 精确匹配)**：$\text{DOI}(p_l) == \text{DOI}(p_h)$ 或 $\text{S2ID}(p_l) == \text{S2ID}(p_h)$。
   * **Level 2 (字符串与年份模糊匹配)**：
     $$\text{JaroWinkler}(\text{Title}_l, \text{Title}_h) \ge 0.90 \quad \text{且} \quad |\text{Year}_l - \text{Year}_h| \le 1$$
   * **Level 3 (语义向量匹配)**：
     $$\cos(v_{p_l}, v_{p_h}) = \frac{v_{p_l} \cdot v_{p_h}}{\|v_{p_l}\| \|v_{p_h}\|} \ge 0.92$$

定义匹配成功的交集 $S_M = S_H \cap S_L = \{p_l \in S_L \mid \exists p_h \in S_H, \text{Match}(p_l, p_h) = 1\}$。


---


### 1.2 相关工作硬性检索指标 (Retrieval Precision & Recall)

* **召回率 (Recall)**：
  $$R = \frac{|S_M|}{|S_H|}$$
* **准确率 (Precision)**：
  $$P = \frac{|S_M|}{|S_L|}$$
* **Jaccard 相似度**：
  $$J(S_H, S_L) = \frac{|S_M|}{|S_H \cup S_L|}$$

---

### 1.3 相关工作分布、语义与质量指标

#### 1. 发表时间分布差异 (Temporal Distribution)
* **近 3 年最新论文占比 (Recency Ratio)**：
  $$\text{RR}(S) = \frac{|\{p \in S \mid \text{Year}_{\text{current}} - \text{Year}_p \le 3\}|}{|S|}$$
* **时间分布推土机距离 (Earth Mover's Distance / Wasserstein Distance)**：
  衡量 LLM 与 Human 论文发表年份累积分布函数（CDF） $F_L(x)$ 和 $F_H(x)$ 的偏差：
  $$W_1(P_H, P_L) = \int_{-\infty}^{+\infty} |F_H(x) - F_L(x)| dx$$

#### 2. 语义结构与聚类差异 (Semantic Structure & Diversity)
* **类内语义聚焦度 (Intra-Class Density)**：评估文献集内部主题的集中程度。
  $$\text{Sim}_{\text{intra}}(S) = \frac{2}{|S|(|S|-1)} \sum_{1 \le i < j \le |S|} \cos(v_{p_i}, v_{p_j})$$
* **类间语义相似度 (Inter-Class Centroid Similarity)**：评估 LLM 与 Human 文献集整体主题方向的重合度。
  $$\text{Sim}_{\text{inter}}(S_H, S_L) = \cos\left(\frac{1}{|S_H|}\sum_{p \in S_H} v_p, \; \frac{1}{|S_L|}\sum_{p \in S_L} v_p\right)$$
* **Observation 贴合度 (Relevance to Observation)**：评估文献是否紧扣观察到的问题。
  $$\text{Rel}(S, \text{Obs}) = \frac{1}{|S|} \sum_{p \in S} \cos(v_p, v_{\text{obs}})$$

#### 3. 客观学术质量 (Objective Literature Quality)
* **平均对数引用量 (Mean Log Citations)**：
  $$\text{MLC}(S) = \frac{1}{|S|} \sum_{p \in S} \ln(1 + \text{CitationCount}(p))$$
* **顶会顶刊占比 (Top-Venue Ratio)**：
  $$\text{TVR}(S) = \frac{|\{p \in S \mid \text{Venue}(p) \in \text{CCF-A/B or Core A*}\}|}{|S|}$$

---

### 1.4 Core Claim 质量评估

#### 1. 论文事实忠实度 (Faithfulness via DeBERTa NLI)
将 Claim ($C_L$) 作为 Hypothesis，引用的论文摘要 ($A_p$) 作为 Premise，使用预训练 NLI 模型计算蕴含概率：
$$\text{Faithfulness}(C_L, S_L) = \frac{1}{|S_L|} \sum_{p \in S_L} P_{\text{NLI}}(\text{Entailment} \mid \text{Premise}=A_p, \text{Hypothesis}=C_L)$$

#### 2. 人类 Claim 覆盖率 (Atomic Claim Recall)
1. 使用 LLM 将人类 Claim $C_H$ 拆解为 $N$ 个原子断言集合 $A(C_H) = \{a_1, a_2, \dots, a_N\}$。
2. 逐一判定 $C_L$ 是否支持 $a_i$：
   $$\text{Coverage}(C_L, C_H) = \frac{\sum_{i=1}^{N} \mathbb{I}(C_L \Rightarrow a_i)}{N}$$
   *其中 $\mathbb{I}(\cdot)$ 为指示函数，$\Rightarrow$ 表示语义包含或推导成立。*

#### 3. 逻辑关联度评分 (Logical Relevance via G-Eval)
利用 LLM-as-a-Judge 评估由 $\text{Obs}$ 推导至 $C_L$ 的逻辑合理性，采用标准思维链（CoT）评分 Prompt 输出 1–5 分：
$$S_{\text{logic}}(C_L) \in [1, 5]$$

---

## 二、 子任务二：RQ2-2（基于人类 Related Work 的 Solution 生成能力测评）

**输入**：Observation + 人类 Related Works ($S_H$)  
**输出**：LLM 生成的 Solution ($\text{Sol}_L$)  
**GroundTruth**：人类编写的 Solution ($\text{Sol}_H$)

---

### 2.1 方案质量多维度评估 (4-Dimension Rubric Score)

针对 $\text{Sol}_L$，使用强语言模型（如 GPT-4o / Claude 3.5 Sonnet）根据预设的标准规约（Rubric）进行 1–5 分量化打分，向量定义为 $\vec{S} = (s_1, s_2, s_3, s_4)$：

| 指标名称 | 符号 | 评测定义与计算逻辑 |
| :--- | :--- | :--- |
| **针对性 (Targetedness)** | $s_{\text{tgt}}$ | 评估 $\text{Sol}_L$ 是否精准应对 Observation 提到的核心矛盾，公式：$s_{\text{tgt}} \in [1, 5]$ |
| **技术可行性 (Feasibility)** | $s_{\text{feas}}$ | 评估方案在数学、逻辑与工程原理上是否存在漏洞，公式：$s_{\text{feas}} \in [1, 5]$ |
| **创新性 (Novelty)** | $s_{\text{nov}}$ | 评估方案是否突破简单堆叠 Baseline 的平庸解，公式：$s_{\text{nov}} \in [1, 5]$ |
| **继承性 (Groundedness)** | $s_{\text{grd}}$ | 评估方案是否显式且逻辑合理地利用了输入的 $S_H$ 中的技术路线，公式：$s_{\text{grd}} \in [1, 5]$ |

**综合质量得分 (Weighted Total Score)**：
$$\text{Score}_{\text{Sol}}(\text{Sol}_L) = w_1 s_{\text{tgt}} + w_2 s_{\text{feas}} + w_3 s_{\text{nov}} + w_4 s_{\text{grd}} \quad (\text{权重 } \sum w_k = 1)$$

---

### 2.2 与 Human Solution 的语义与解法对齐度

#### 1. 语义嵌入相似度
使用学术领域文本模型（如 `SciNBERT`）提取文本向量：
$$\text{Sim}_{\text{semantic}}(\text{Sol}_L, \text{Sol}_H) = \cos(v_{\text{Sol}_L}, v_{\text{Sol}_H})$$

#### 2. 关键技术要素覆盖率 (Key Technical Aspect Recall)
1. 将 $\text{Sol}_H$ 抽取为 $K$ 个关键技术要素集合 $T(\text{Sol}_H) = \{t_1, t_2, \dots, t_K\}$（如：损失函数改进、新网络模块、启发式算法等）。
2. 计算 $\text{Sol}_L$ 对这些关键要素的匹配覆盖率：
   $$\text{AspectRecall}(\text{Sol}_L, \text{Sol}_H) = \frac{\sum_{j=1}^{K} \mathbb{I}(t_j \text{ is addressed in } \text{Sol}_L)}{K}$$

---

## 三、 子任务三：RQ2-3（LLM RW 与 Human RW 对 Solution 产出的影响对比与归因分析）

**输入 A**：Observation + LLM 生成的 Related Works ($S_L$) $\rightarrow$ 输出：$\text{Sol}_{\text{LLM\_RW}}$  
**输入 B**：Observation + 人类 Related Works ($S_H$) $\rightarrow$ 输出：$\text{Sol}_{\text{Human\_RW}}$（即 RQ2-2 产出）  
**目标**：对比两次 LLM 产出 Solution 的质量差异，并分析相关工作的质量如何传导影响最终 Solution。

---

### 3.1 两次 LLM 产出 Solution 的成对对比 (Pairwise Comparison)

为消除 LLM 作为裁判时的位置偏置（Position Bias），对每一个 Observation 样本采用 **位置对调（Swap Position）双盲评估**：

1. **第一次评估**：Input(A=$\text{Sol}_{\text{LLM\_RW}}$, B=$\text{Sol}_{\text{Human\_RW}}$) $\rightarrow$ 获得四维度评分及偏好判断 $O_1 \in \{\text{Win}_A, \text{Tie}, \text{Win}_B\}$。
2. **第二次评估**：Input(A=$\text{Sol}_{\text{Human\_RW}}$, B=$\text{Sol}_{\text{LLM\_RW}}$) $\rightarrow$ 获得偏好判断 $O_2 \in \{\text{Win}_A, \text{Tie}, \text{Win}_B\}$。
3. **一致性判定**：仅当两次评估无位置冲突时判定有效，否则标记为 `Tie`。

#### 1. 胜率计算 (Win Rate)
对样本总量为 $N$ 的数据集：
$$\text{WinRate}_{\text{LLM\_RW}} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Sol}_{\text{LLM\_RW}} \succ \text{Sol}_{\text{Human\_RW}})}{N}$$

#### 2. 方案得分差值 (Delta Score)
对每个样本 $i$，计算四维度得分差值：
$$\Delta_i^{(k)} = \text{Score}^{(k)}(\text{Sol}_{\text{LLM\_RW}, i}) - \text{Score}^{(k)}(\text{Sol}_{\text{Human\_RW}, i}) \quad (k \in \{\text{tgt, feas, nov, grd}\})$$

---

### 3.2 影响机制与归因分析 (Correlation & Attribution Analysis)

探究 RQ2-1 中 LLM 生成相关工作的质量缺陷是如何传递并影响 RQ2-3 中 Solution 质量的。

[RQ2-1 指标: Recall, Precision, Rel(Obs), W1] ──(相关性分析 r_s)──> [RQ2-3 差值: Delta Score]

#### 斯皮尔曼等级相关系数 (Spearman's Rank Correlation)
将第 $i$ 个样本在 RQ2-1 中算得的评估指标（如 Recall $R_i$、贴合度 $\text{Rel}_i$、时间偏差 $W_{1,i}$）与 RQ2-3 中的得分差值 $\Delta_i$ 进行相关性分析：

$$r_s = 1 - \frac{6 \sum_{i=1}^N d_i^2}{N(N^2 - 1)}$$
*其中 $d_i = \text{rank}(X_i) - \text{rank}(\Delta_i)$，$X_i$ 为 RQ2-1 中的某一测评指标。*

#### 归因假设校验矩阵 (Hypothesis Matrix)

| 假设方向 | 自变量 $X$ (来自 RQ2-1) | 因变量 $Y$ (来自 RQ2-3) | 预期结果与学术含义 |
| :--- | :--- | :--- | :--- |
| **检索召回假说** | 相关工作召回率 $R_i$ | 继承性差值 $\Delta_i^{(\text{grd})}$ | 正相关 ($r_s > 0$)：LLM 遗漏核心文献会导致 Solution 失去继承性。 |
| **贴合度传导假说** | Observation 贴合度 $\text{Rel}_i$ | 针对性差值 $\Delta_i^{(\text{tgt})}$ | 正相关 ($r_s > 0$)：LLM 生成的相关工作越偏离主题，方案针对性越差。 |
| **幻觉/噪音干扰假说**| 准确率 $P_i$ 的倒数（即幻觉率） | 可行性差值 $\Delta_i^{(\text{feas})}$ | 负相关 ($r_s < 0$)：相关工作中的幻觉文献会误导 LLM 产出不可行的方案。 |