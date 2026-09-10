# Beyond Single-shot Writing: Deep Research Agents are Unreliable at Multi-turn Report Revision

Bingsen Chen<sup>1,2,∗</sup>, Boyan Li<sup>3,†,∗</sup>, Ping Nie<sup>5</sup>, Yuyu Zhang<sup>6</sup>, Xi Ye<sup>3,4,‡</sup>, Chen Zhao<sup>1,2,‡</sup>

<sup>1</sup>New York University <sup>2</sup>NYU Shanghai <sup>3</sup>University of Alberta

<sup>4</sup>Princeton University <sup>5</sup>University of Waterloo <sup>6</sup>Verdent AI, Inc.

## Abstract

Existing benchmarks for Deep Research Agents (DRAs) treat report generation as a single-shot writing task, which fundamentally diverges from how human researchers iteratively draft and revise reports via self-reflection or peer feedback. Whether DRAs can reliably revise reports with user feedback remains unexplored. We introduce MR DRE, an evaluation suite that establishes multi-turn report revision as a new evaluation axis for DRAs. MR DRE consists of (1) a unified long-form report evaluation protocol spanning comprehensiveness, factuality, and presentation, and (2) a human-verified feedback simulation pipeline for multi-turn revision. Our analysis of five diverse DRAs reveals a critical limitation: while agents can address most user feedback, they also regress on 16–27% of previously covered content and citation quality. Over multiple revision turns, even the best-performing agents leave significant headroom, as they continue to disrupt content outside the feedback’s scope and fail to preserve earlier edits. We further show that these issues are not easily resolvable through inference-time fixes such as prompt engineering and a dedicated sub-agent for report revision.<sup>1</sup>

## 1 Introduction

Recent advances in the agentic capabilities of language models have led to the rise of Deep Research Agents (DRAs) (OpenAI, 2025; Perplexity, 2025; Team et al., 2025; Shao et al., 2025). DRAs tackle complex research queries by extensively searching and browsing the web, then synthesizing large volumes of information into long-form reports with rich citations and well-organized structure.

However, what dimensions to evaluate these complex systems against remains an open problem. Early attempts (Li et al., 2025b; Team et al., 2025) used multi-hop QA benchmarks (Wei et al., 2025a; Chen et al., 2025; Phan et al., 2025; Mialon et al., 2023) to evaluate DRAs’ multi-step retrieval and reasoning ability. However, such benchmarks rely on short-form answers and fail to capture the report-writing capabilities of DRAs. More recent work has begun to evaluate long-form report generation directly (Du et al., 2025; Yao et al., 2025; Sharma et al., 2025; Xu et al., 2025), but uniformly treat it as a single-shot task: given a query, agents gather information and produce a report in one pass. This departs from human practice, where reports are produced through iterative revision, often guided by self-reflection or feedback.

In this work, we propose multi-turn report revision as a new evaluation axis for DRAs. In this setting, DRAs revise an initial report over multiple turns in response to user feedback. This capability is important for two reasons. First, in practical deployment, users do not often accept an initial response as-is (Lee et al., 2025a), and may request additional details or changes in structure. Agents that cannot effectively incorporate such feedback while preserving the quality of the rest of the report provide limited utility. Second, iterative revision offers a natural mechanism for improving report quality with additional compute. While test-time scaling has proven effective for reasoning (Snell et al., 2025; Muennighoff et al., 2025), its impact on report generation remains unexplored. We therefore ask: Can current deep research agents reliably improve their reports via user feedback?

To study this, we introduce Multi-turn Revision of Deep Research Agent Evaluation (MR DRE), a new evaluation suite supporting iterative report writing. For report evaluation, MR DRE unifies evaluation practices from prior benchmarks, which have adopted divergent metrics, into a lean protocol covering three dimensions: comprehensiveness, factuality, and presentation (Figure 2, left). To enable multi-turn report revision evaluation, MR DRE provides a human-verified feedback simulation pipeline that generates realistic user feedback on report content and formatting (Figure 2, right).

With MR DRE, we evaluate five diverse DRAs and find that current systems cannot reliably revise reports in response to user feedback. Although agents address over 90% of requested edits, content or format revisions frequently reduce overall report quality: 16–27% of previously covered content is broken, and citation quality degrades. Moreover, when extending revision to multiple turns, some agents show minimal to negative progress, and even the bestperforming agents leave significant gaps as they continue to disrupt content outside feedback’s scope and fail to preserve edits made in earlier turns. Finally, these failures persist despite inference-time remedies, including extensive prompt engineering and a dedicated reviser

![](images/9e79dcd4bf623b9e46c45848c12bb4ae1b2a97d93879c78b994e4ecdeeda2ebc.jpg)  
Figure 1: Illustrative example of multi-turn revision failure in Deep Research Agents. The revised report incorporates the user feedback but removes previously covered content that is outside the feedback’s scope.

sub-agent. These findings suggest that reliable multi-turn revision will require more fundamental changes in DRA training and scaffold design, which we advocate as a priority for future research.

In summary, our main contributions are:

• A novel evaluation axis for DRAs. We identify multi-turn report revision as an important yet underexplored capability of DRAs.

• MR DRE evaluation suite. MR DRE unifies prior evaluation practices into a concise threedimensional protocol for Deep Research report generation and includes a human-verified feedback simulation pipeline for multi-turn revision.

• Comprehensive analysis of current DRAs’ multi-turn revision ability. We reveal systematic limitations in current DRAs’ ability to revise reports from user feedback and show that inferencetime fixes are insufficient

![](images/0ff9f9ee958479795fcb842483437f75835395bcfed8fc714fccc59c24daa4a9.jpg)  
Figure 2: MR DRE Evaluation Suite. In multi-turn report revision, a DRA iteratively drafts and revises a report r for question q given user feedback f (top left). MR DRE provides a unified Deep Research report evaluation protocol (bottom left) along three dimensions: Comprehensiveness, Factuality, and Presentation. To evaluate multi-turn revision performance, MR DRE provides a pipeline to simulate content, format, and self-reflection feedback (right).

## 2 Task Definition

We begin by formalizing deep research and defining our multi-turn report revision task: Unlike standard search-augmented language models that are tasked with generating short-form (Yang et al., 2018; Wei et al., 2025a) or paragraph-long answers (Fan et al., 2019; Han et al., 2024), a Deep Research Agent is a system of one or multiple LLMs augmented with web searching tools that autonomously retrieves and analyzes vast online information and synthesizes findings into a comprehensive, well-cited research report.

Formally, given a user’s initial query q, a DRA A generates a report $r _ { 1 } = \mathcal { A } ( q )$ . Current deep research benchmarks evaluate only this single output r , treating report writing as a one-shot task. We extend this paradigm to multi-turn report revision. After receiving the initial report $r _ { 1 } , \mathfrak { i }$ a user may provide feedback f , prompting the agent to revise the report and yield $r _ { 2 } \stackrel { - } { = } \mathcal { A } ( q , r _ { 1 } , f _ { 1 } )$ This process can continue iteratively: at turn t, the agent produces $\boldsymbol { r } _ { t } = \boldsymbol { A } ( \boldsymbol { q } , \boldsymbol { r } _ { 1 } , f _ { 1 } , \dots , \boldsymbol { r } _ { t - 1 } , f _ { t - 1 } )$ , conditioning on all previous turns of drafts and feedback.

## 3 A Unified Deep Research Report Evaluation Protocol

In this section, we introduce the first component of MR DRE, a comprehensive protocol for Deep Research report evaluation. We start with introducing our curated data (§3.1), and then detail the evaluation dimensions (§3.2).

<table><tr><td></td><td>Checklist Comp.</td><td>Claim Fact.</td><td>Report Pres.</td><td>Ref.-free</td><td>Multi-turn</td></tr><tr><td>ResearchRubrics (Sharma et al., 2025)</td><td>√</td><td>✕</td><td>✕</td><td>√</td><td>✕</td></tr><tr><td>RACE&amp;FACT (Du et al., 2025)</td><td>√</td><td>√</td><td>√</td><td>✕</td><td>✕</td></tr><tr><td>RigorousBench (Yao et al., 2025)</td><td>√</td><td>✕</td><td>√</td><td>√</td><td>✕</td></tr><tr><td>ResearcherBench (Xu et al., 2025)</td><td>√</td><td>✕</td><td>✕</td><td>√</td><td>✕</td></tr><tr><td>DR-ReportEval (Fan et al., 2025)</td><td>✕</td><td>√</td><td>√</td><td>✕</td><td>✕</td></tr><tr><td>DeepEval (Wang et al., 2025)</td><td>√</td><td>√</td><td>√</td><td>√</td><td>✕</td></tr><tr><td>MR DRE</td><td>√</td><td>√</td><td>√</td><td>√</td><td>√</td></tr></table>

Table 1: Comparison of MR DRE and previous Deep Research report evaluation protocols. MR DRE checks all five aspects: checklist-based comprehensiveness evaluation, claim-level factuality assessment, report presentation scoring, requiring no reference answer, and support for multi-turn report revision (§4).

## 3.1 Data Curation

To enable reliable evaluation, we guide our data curation with two criteria. First, each question must be paired with a question-specific checklist: a set of content criteria that a high-quality report should satisfy. Such checklists provide ground-truth coverage targets tailored to each question and have proven effective for evaluating complex, long-form generations (Ruan et al., 2025; Lee et al., 2025b). Second, the questions and checklists must be sufficiently complex that DRAs are unlikely to cover all checklist items on their first attempt, leaving meaningful room for iterative revision.

Following these criteria, we include expert-annotated research questions from three datasets: ResearchRubrics (Sharma et al., 2025), RigorousBench (Yao et al., 2025), and ResearcherBench (Xu et al., 2025). These datasets feature expert-annotated research-intensive questions paired with evaluation checklists for improvement. Table 4 summarizes the dataset statistics.

## 3.2 Evaluation Dimensions & Pipeline

We combine best practices from prior benchmarks into three dimensions: comprehensiveness, fac tuality, and presentation. These dimensions capture a minimal set of qualities that characterize an excellent research report: it should cover all essential information, make accurate citations and well-supported claims, and present content in a clear, well-organized manner. We illustrate our evaluation protocol in Figure 2 (left), and compare MR DRE’s unified protocol with previous benchmarks’ evaluation in Table 1. Note that our protocol is generally applicable to all Deep Research report generation tasks and can easily integrate new datasets.

Comprehensiveness A high-quality research report should cover all relevant aspects of a research question. We measure this using the coverage score of question-specific checklists. A question $q ^ { \prime } \mathbf { s }$ checklist $\mathcal { C } _ { q } = \{ ( c _ { i } , w _ { i } ) \} _ { i = 1 } ^ { n }$ consists of n criteria, where each criterion c<sub>i</sub> has a weight $w _ { i }$ reflecting its importance. Following prior work (Sharma et al., 2025; Yao et al., 2025), we adopt ternary grading to allow partial credit: an LLM judge $\mathcal { I } _ { \mathrm { c o v } }$ evaluates each criterion against the question q and report r, assigning a score $s _ { i } = \mathcal { I } _ { \mathrm { c o v } } ( q , r , c _ { i } ) \in \{ 0 , 0 . 5 , 1 \}$ corresponding to absent, partial, o complete coverage. The coverage score is the weighted average:

$$
\operatorname{COV} (r) = \frac {\sum_ {i = 1} ^ {n} w _ {i} \cdot s _ {i}}{\sum_ {i = 1} ^ {n} w _ {i}}.
$$

Factuality A high-quality research report should make accurate claims backed by reliable citations. Based on the in-line citations, we evaluate factuality from two angles: citation faithfulness that measures the proportion of cited claims that are actually supported by their referenced sources, and claim groundedness that measures the proportion of all claims that can be verified against external evidence.

Specifically, we adapt VeriScore (Song et al., 2024) for Deep Research report evaluation. Given a report $r ,$ we first extract the set of atomic claims $\mathcal { E } ( r ) = \{ e _ { 1 } , e _ { 2 } , \dots , e _ { m } \}$ using an $\mathrm { L L M } ,$ where each claim $e _ { i }$ is associated with zero, one, or multiple cited URLs. An LLM judge $\mathcal { I } _ { \mathrm { f a c t } }$ then evaluates each claim against the crawled content of its cited sources, classifying it as supported, contradicted, or insufficiently evidenced. We define citation faithfulness (left) and claim groundedness (right) as:

$$
\mathrm{FA} (r) = \frac {| \mathcal {S} |}{| \mathcal {E} _ {\text { cited }} (r) |}, \quad \mathrm{GR} (r) = \frac {| \mathcal {S} |}{| \mathcal {E} (r) |}
$$

where $\mathcal { E } _ { \mathrm { c i t e d } } ( r ) \subseteq \mathcal { E } ( r )$ is the subset of claims with at least one citation, and $ { \mathcal { S } } \subseteq  { \mathcal { E } } ( r )$ denotes the subset of supported claims. We provide additional technical details in Appendix B.2.

Presentation A high-quality research report should organize dense information into a readable, well-structured format with professional language. We consolidated and refined prior works’ (Fan et al., 2025; Yao et al., 2025; Wang et al., 2025) divergent criteria to arrive at a unified checklist of 10 questions (listed in Table 5). For each criterion $p _ { j }$ in the checklist $\mathcal { P } = \{ p _ { 1 } , \ldots , p _ { 1 0 } \}$ , an LLM judge $\mathcal { I } _ { \mathrm { p r e s } }$ assigns a binary score. The overall presentation score is calculated as:

$$
\mathrm{PRE} (r) = \frac {1}{| \mathcal {P} |} \sum_ {j = 1} ^ {| \mathcal {P} |} \mathcal {J} _ {\mathrm{pres}} (r, p _ {j})
$$

## 4 Extending Evaluation to Multi-turn Report Revision

MR DRE also introduces an automated yet human-validated pipeline for multi-turn report revision evaluation. In this section, we introduce (1) a reliable way to simulate realistic user feedback (illustrated in Figure 2, right), and (2) metrics to measure revision success.

## 4.1 Feedback Simulation

We design a feedback simulation pipeline that generates diverse and realistic user feedback on Deep Research reports. We consider three feedback categories corresponding to distinct revision settings: content, format, and self-reflection.

Content Feedback requests adding new information or correcting existing content. Under this setting, a successful revision must address the feedback targets while preserving unrelated report content. To simulate such feedback, we leverage the checklist-based evaluation from §3.2. Given a report draft, we first evaluate all checklist criteria using $\mathcal { I } _ { \mathrm { c o v } } ,$ , which we also ask for a justification for each score. We then uniformly sample k uncovered criteria asfeedback targets, denoted $\mathcal { T } ^ { ( t ) } \subset \mathcal { C } _ { q }$ for turn $t ,$ and prompt a feedback simulator LLM to generate natural feedback based on the question, the sampled feedback targets, and their corresponding scores and justifications. Grounding feedback in scoring justification rather than raw criteria text produces more natural requests that reflect how users would articulate what is missing.

Format Feedback targets the report’s structure, style, or presentation. We expect DRAs to incorporate the formatting feedback without disrupting existing content coverage. We curate 21 seed format feedback examples covering common user requests $( \mathrm { e . g . , }$ adding bullet points, improving sectioning, or including $\mathrm { T L } ; \mathrm { D R }$ summaries. Full list in Table 6). Given a report draft, we randomly sample three seed examples and prompt the LLM to select the most applicable one, then expand it into a piece of feedback specific to the report draft. Using seed examples guides the simulator toward generating realistic feedback, while random sampling ensures diversity.

Self-Reflection Feedback provides no explicit revision guidance. The feedback is simply: “Please reflect on your current report and revise it.” This setting tests whether DRAs can autonomously identify and address deficiencies.

Human Validation. We conduct human annotation to validate simulated content and format feedback along four dimensions: naturalness, draft-specificity, actionability, and, for format feedback, content preservation. Our pipeline achieves near-ceiling scores across all dimensions with high inter-annotator agreement. Details are in Appendix C.3.

## 4.2 Measuring the Success of Revision

We introduce two additional metrics to measure the effectiveness of revision via the questionspecific checklists. Let $s _ { i } ^ { ( t ) }$ denote the coverage score of criterion $c _ { i }$ for report $r ^ { ( t ) }$

Incorporation Rate measures whether the revision successfully incorporates feedback at turn t:

$$
\text { INC } = \left\{ \begin{array}{l l} \frac {1}{| \mathcal {T} ^ {(t)} |} \sum_ {c _ {i} \in \mathcal {T} ^ {(t)}} \mathbb {1} \left[ s _ {i} ^ {(t)} = 1 \right], & \text { Content   feedback } \\ \mathcal {J} _ {\text { inc }} (f _ {t}, r _ {t - 1}, r _ {t}), & \text { Format   feedback } \end{array} \right.
$$

For content feedback, this is the proportion of feedback targets $\mathscr { T } ^ { ( t ) }$ that achieve full coverage after revision. For format feedback, an LLM judge ${ \mathcal { I } } _ { \mathrm { i n c } }$ assesses whether the formatting suggestion is followed (binary scoring).

Break Rate is the proportion of previously covered criteria whose scores degrade after revision:

$$
\mathrm{BRK} = \frac {\left| \left\{c _ {i} : s _ {i} ^ {(t - 1)} > 0 \wedge s _ {i} ^ {(t)} <   s _ {i} ^ {(t - 1)} \right\} \right|}{\left| \left\{c _ {i} : s _ {i} ^ {(t - 1)} > 0 \right\} \right|}
$$

A break rate of 0 indicates that the revision preserves all previously covered content, while a high break rate suggests making destructive edits that fix one issue at the cost of disrupting others.

All metrics are defined per sample and reported as an average across the dataset. Prompt templates are in Appendix F.

## 5 Experiments

Using MR DRE, we study our central research question: how reliably can current DRAs revise reports via user feedback? We first examine various DRAs’ revision performance under three distinct feedback settings, and then analyze how revision behavior changes as we scale the number of turns (§5.2) and feedback targets (§5.3).

Settings. We evaluate five DRAs under three revision settings: self-reflection (Reflect), content feedback (Content ), and format feedback (Format). In the Content setting, each content feedback message targets k checklist criteria that the previous-turn draft fails to satisfy. Due to the high cost of running proprietary DRAs, we conduct only the second-turn experiments on the three complete datasets in Table 4. For experiments with up to 4 turns and varying the number of feedback targets (k), we use a sub-sampled Core Set (25 questions from each dataset, totaling 75 questions). Details about the subset creation are in Appendix A.2.

<table><tr><td rowspan="2">DRA</td><td rowspan="2">Turn</td><td rowspan="2">Type</td><td colspan="4">ResearchRubrics</td><td colspan="4">RigorousBench</td><td colspan="4">ResearcherBench</td><td rowspan="2">Avg. Inc.</td><td rowspan="2">Avg. Brk.</td></tr><tr><td>Cov.</td><td>Fa.</td><td>Gr.</td><td>Pre.</td><td>Cov.</td><td>Fa.</td><td>Gr.</td><td>Pre.</td><td>Cov.</td><td>Fa.</td><td>Gr.</td><td>Pre.</td></tr><tr><td rowspan="4">OpenAI DR</td><td rowspan="2">1</td><td>-</td><td>62.3</td><td>63.6</td><td>28.8</td><td>97.9</td><td>42.2</td><td>63.5</td><td>33.5</td><td>97.2</td><td>68.5</td><td>80.3</td><td>41.4</td><td>95.6</td><td>-</td><td>-</td></tr><tr><td>Reflect</td><td>-1.5</td><td>-10.3</td><td>-8.4</td><td>+1.0</td><td>-0.8</td><td>-2.4</td><td>-4.4</td><td>+0.7</td><td>-3.9</td><td>-7.0</td><td>-5.3</td><td>+2.9</td><td>-</td><td>14.9</td></tr><tr><td rowspan="2">2</td><td>Content $_1$ </td><td>-6.6</td><td>-10.3</td><td>-6.1</td><td>-5.1</td><td>-2.0</td><td>-16.9</td><td>-11.7</td><td>-5.4</td><td>-9.1</td><td>-16.4</td><td>-11.0</td><td>-4.6</td><td>93.6</td><td>29.7</td></tr><tr><td>Format</td><td>-2.2</td><td>-19.9</td><td>-13.0</td><td>+0.2</td><td>-3.6</td><td>-8.8</td><td>-8.4</td><td>0.0</td><td>-3.9</td><td>-14.4</td><td>-7.1</td><td>+1.4</td><td>98.5</td><td>14.8</td></tr><tr><td rowspan="4">Sonar DR</td><td rowspan="2">1</td><td>-</td><td>70.9</td><td>71.7</td><td>56.4</td><td>90.8</td><td>55.2</td><td>76.4</td><td>64.1</td><td>90.3</td><td>80.0</td><td>75.3</td><td>64.8</td><td>89.6</td><td>-</td><td>-</td></tr><tr><td>Reflect</td><td>-5.2</td><td>-55.6</td><td>-48.1</td><td>+4.6</td><td>-7.3</td><td>-60.8</td><td>-54.0</td><td>+2.5</td><td>-5.2</td><td>-67.4</td><td>-59.1</td><td>+6.0</td><td>-</td><td>20.5</td></tr><tr><td rowspan="2">2</td><td>Content $_1$ </td><td>-11.5</td><td>-26.7</td><td>-19.7</td><td>+0.2</td><td>-8.3</td><td>-23.3</td><td>-21.9</td><td>-1.1</td><td>-10.4</td><td>-8.5</td><td>-3.9</td><td>+0.6</td><td>92.6</td><td>34.3</td></tr><tr><td>Format</td><td>-16.2</td><td>-35.6</td><td>-28.8</td><td>-6.1</td><td>-13.9</td><td>-35.9</td><td>-32.6</td><td>-9.4</td><td>-13.4</td><td>-30.0</td><td>-27.1</td><td>-3.1</td><td>85.5</td><td>27.8</td></tr><tr><td rowspan="4">LC ODR</td><td rowspan="2">1</td><td>-</td><td>60.9</td><td>72.5</td><td>39.7</td><td>99.5</td><td>43.0</td><td>74.2</td><td>46.1</td><td>99.8</td><td>71.0</td><td>82.6</td><td>51.8</td><td>99.8</td><td>-</td><td>-</td></tr><tr><td>Reflect</td><td>+3.2</td><td>-4.8</td><td>-4.5</td><td>0.0</td><td>+3.8</td><td>-3.3</td><td>-1.0</td><td>0.0</td><td>+3.8</td><td>-8.5</td><td>-10.4</td><td>-0.2</td><td>-</td><td>8.5</td></tr><tr><td rowspan="2">2</td><td>Content $_1$ </td><td>-11.5</td><td>-6.5</td><td>-8.4</td><td>-1.3</td><td>-5.3</td><td>-5.2</td><td>-7.1</td><td>-1.9</td><td>-8.7</td><td>-9.1</td><td>-19.4</td><td>-0.5</td><td>93.0</td><td>38.6</td></tr><tr><td>Format</td><td>-5.8</td><td>-1.4</td><td>-3.8</td><td>-1.9</td><td>-3.5</td><td>-5.1</td><td>-8.6</td><td>-2.1</td><td>-9.9</td><td>-4.2</td><td>-14.4</td><td>-2.4</td><td>91.1</td><td>23.9</td></tr><tr><td rowspan="4">Tongyi DR</td><td rowspan="2">1</td><td>-</td><td>58.5</td><td>-</td><td>-</td><td>99.3</td><td>39.4</td><td>-</td><td>-</td><td>99.2</td><td>68.4</td><td>-</td><td>-</td><td>99.9</td><td>-</td><td>-</td></tr><tr><td>Reflect</td><td>-0.3</td><td>-</td><td>-</td><td>-1.2</td><td>+0.2</td><td>-</td><td>-</td><td>+0.1</td><td>-0.7</td><td>-</td><td>-</td><td>+0.2</td><td>-</td><td>9.9</td></tr><tr><td rowspan="2">2</td><td>Content $_1$ </td><td>-9.2</td><td>-</td><td>-</td><td>-5.3</td><td>-0.9</td><td>-</td><td>-</td><td>-1.2</td><td>-5.0</td><td>-</td><td>-</td><td>-0.8</td><td>90.2</td><td>31.5</td></tr><tr><td>Format</td><td>-6.7</td><td>-</td><td>-</td><td>-2.6</td><td>-5.8</td><td>-</td><td>-</td><td>-2.5</td><td>-9.8</td><td>-</td><td>-</td><td>-4.1</td><td>94.3</td><td>23.2</td></tr><tr><td rowspan="4">DR Tulu</td><td rowspan="2">1</td><td>-</td><td>60.7</td><td>64.7</td><td>46.3</td><td>98.2</td><td>42.8</td><td>63.4</td><td>49.2</td><td>96.7</td><td>67.5</td><td>79.0</td><td>62.1</td><td>98.5</td><td>-</td><td>-</td></tr><tr><td>Reflect</td><td>-0.7</td><td>-3.9</td><td>-0.4</td><td>-1.1</td><td>-0.7</td><td>-2.6</td><td>+0.3</td><td>-1.9</td><td>-0.1</td><td>-5.7</td><td>-3.5</td><td>-1.1</td><td>-</td><td>11.4</td></tr><tr><td rowspan="2">2</td><td>Content $_1$ </td><td>-2.7</td><td>-5.8</td><td>-2.6</td><td>-3.5</td><td>+2.5</td><td>-4.0</td><td>-1.7</td><td>-1.1</td><td>+1.0</td><td>-4.6</td><td>-6.8</td><td>0.0</td><td>90.3</td><td>23.5</td></tr><tr><td>Format</td><td>-1.0</td><td>-2.2</td><td>+2.2</td><td>-1.3</td><td>-2.2</td><td>+1.0</td><td>+2.7</td><td>-1.7</td><td>-3.1</td><td>-5.7</td><td>-2.6</td><td>+0.7</td><td>94.9</td><td>14.0</td></tr></table>

Table 2: Main Results. We report the Coverage (Cov.), Citation Faithfulness (Fa.), Claim Groundedness (Gr.), and Presentation (Pre.) score in percentage points. Incorporation (Inc.) and Break (Brk.) rate results are averaged across three datasets. For the second turn, we show the score changes from the first turn results for all evaluation metrics and feedback types, where improvement is colored in green and reduction is colored in red.

Evaluated Agents. We evaluate five DRA systems under three categories: (1) Proprietary scaffold and model(s): OpenAI o4-mini Deep Research (OpenAI DR) (OpenAI, 2025) and Sonar Deep Research by Perplexity (Sonar DR) (Perplexity, 2025). Such systems reveal little information about the agents’ details. (2) Open scaffold, proprietary models: LangChain Open Deep Research (LC ODR) (LangChain, 2025). It orchestrates a system of research, summarization, and finding compression agents, and a report-writing agent. We used GPT-4.1-Nano for summarization and GPT-4.1-mini for the rest. (3) Open scaffold and models: Tongyi Deep Research (Tongyi DR) (Team et al., 2025) and DR Tulu (Shao et al., 2025), which are post-trained for Deep Research report generation. Tongyi DR is not trained to write reports citations, so we omit its citation-related results.

## 5.1 Main Results

Table 2 shows the first and second turn results under three feedback settings. We observe that:

DRAs struggle to reliably improve, or even preserve, report comprehensiveness across almost all feedback settings. Across different DRAs, feedback types, and datasets, coverage scores predominantly decrease from Turn 1 to Turn 2. Under self-reflection, only LC ODR achieves a modest coverage gain (+3.6%), while all other DRAs exhibit decreases or negligible changes. Even in the Content setting, where the feedback explicitly identifies an unsatisfied checklist criterion, all agents except DR Tulu suffer coverage drops ranging from -2.0% to -11.5%. Format feedback, which by design should preserve content, leads to universal coverage drop across DRAs (-1.0% to -16.2%). Sonar DR, although achieving the best performance in the initial turn, also shows the largest performance drop across all feedback settings. These patterns indicate a systematic limitation in current DRAs’ ability to revise reports based on different types of user feedback.

![](images/aceb1593c885167f4bf8bd16bd4c21fe34c17ff91cd9f31654feb12e6c26913b.jpg)  
Figure 3: Results for extending to 4 turns of revision under Content<sub>1</sub> setting. We report the (top) checklist coverage (actual vs. oracle), (middle) incorporation rate, and (bottom) break rate.

While DRAs can follow most of the feedback instructions, they fail to preserve content outside the feedback’s scope. To understand why coverage degrades after revision, we examine the incorporation and break rates. All DRAs demonstrate strong instruction-following capabilities: incorporation rates mostly exceed 90% for both content and format feedback. However, this success comes at the cost of disrupting previously satisfied content. Break rates average 31% under content feedback and 21% under format feedback, as a substantial fraction of earlier coverage is lost after revision. Interestingly, break rates are lower under self-reflection, suggesting that more specific revision targets induce more aggressive edits that inadvertently affect unrelated content.

Revision significantly degrades citation faithfulness and claim groundedness. Beyond content coverage, factuality metrics also deteriorate after revision. The underlying causes vary across agents, such as fewer supported claims, and we provide a detailed analysis in Appendix E.1. Notably, Sonar DR exhibits the most severe degradation, especially after self-reflection, with faithfulness plummeting by up to -67.4% and groundedness by up to -59.1%. Further inspection reveals that Sonar DR produces reports with no citations 68% of the time after receiving self-reflection feedback.

## 5.2 How well can DRAs revise reports when extending to multiple turns?

We extend revision up to four turns under the Content<sub>1</sub> and Reflect setting. We found that:

![](images/9fe273bc228b5570005e803eaba606cc1ba45605eb6d600602075a0d3fbe2572.jpg)

![](images/eabb5c3393b0a8da20526cb5c3efc27938eb6b086c15ee5ecf2a637c9a128639.jpg)  
Figure 4: Coverage (Left), Break rate, and Incorporation rate (Right) with varying k. Break and incorporation rates are averaged across 5 DRAs since they all show the same trend.

DRAs fail to effectively accumulate coverage gains over multiple turns of content feedback. In the top row of Figure 3, we show each agent’s coverage score (solid line) alongside the oracle score (dashed line), which represents the upper bound performance assuming perfect incorporation and zero break rate from Turn 1 onward. Tongyi DR and Sonar DR show minimal or even negative progress over multiple turns, while others achieve gradual coverage improvements with additional content feedback rounds. However, all agents lag far behind the oracle, and this gap shows no sign of closing over turns: by Turn 4, the gap between actual and oracle scores ranges from 9% (OpenAI DR) to 26% (Sonar DR).

As shown in the bottom two rows of Figure 3, the persistent gap from the oracle traces to both imperfect incorporation rates and non-trivial break rates across all agents. Notably, all DRAs break previously satisfied content at around 20-30% by Turn 4. Tongyi DR and Sonar DR have consistently high break rates that offset any gains from incorporating content feedback over turns, whereas OpenAI DR, DR Tulu, and LC ODR show decreasing break rates (from 33% to 21% on average).

DRAs break not only content outside of feedback’s scope but also feedback targets from previous turns. To measure this, we report the all-history incorporation rate: the proportion of feedback targets from all previous turns that remain satisfied at turn t. While the current-turn incorporation rate stays stable around 90%, all-history incorporation drops substantially. For instance, Sonar DR’s all-history incorporation rate falls from 90% at Turn 2 to 66% by Turn 4. This gap indicates that agents fail to preserve previous fixes while addressing new feedback, even though earlier feedback remains in the input context.

We present additional multi-turn results in Appendix E.2. We found that citation faithfulness and claim groundedness decrease over turns across all DRAs under the Content<sub>1</sub> setting. Also, multiple turns of self-reflection similarly degrade coverage, citation faithfulness, and claim groundedness. These findings further underscore the unreliability of current DRAs in multi-turn report revision.

## 5.3 How reliable are DRAs given feedback with multiple targets?

We then examine how content feedback targeting multiple criteria affects revision performance.

Increasing the number of feedback targets leads to higher coverage gains across all DRAs. As shown in Figure 4, all DRAs consistently achieve higher coverage as more unsatisfied criteria are given in the feedback. To understand this pattern, we examine the incorporation and break rates as k increases: Incorporation rates remain high regardless of k, as agents can effectively handle multiple feedback targets at once. Interestingly, break rates also decrease with larger k, suggesting that agents make less disruptive edits when given more targets to fix.

## 6 Can Inference-time Fixes Improve Revision Performance?

Our analysis reveals that DRAs cannot reliably revise reports based on user feedback, due to disruptive edits on existing content and citations, compounded by imperfect incorporation of the feedback. In this section, we investigate whether simple inference-time fixes can address these limitations without heavily modifying the underlying DRA system. Specifically, we test two approaches:

Prompt Engineering (PE) converts user feedback into a structured edit plan before revision. This approach decomposes the feedback into concrete, step-by-step instructions using an LLM (see example in Figure D.1), with the hypothesis that explicit guidance may help agents make more targeted edits without affecting unrelated content.

Reviser Sub-agent (Reviser) delegates the revision task to a separate LLM. Since DRAs are optimized for multi-step tool calling and reasoning rather than localized editing, we hypothesize that an LLM with strong instruction-following capabilities can better incorporate user feedback while preserving content outside the feedback’s scope.

<table><tr><td rowspan="2">DRA</td><td rowspan="2">Setting</td><td colspan="6">Core Set</td></tr><tr><td>Cov.</td><td>Fa.</td><td>Gr.</td><td>Pre.</td><td>Inc.</td><td>Brk.</td></tr><tr><td rowspan="7">OpenAI DR</td><td>Initial</td><td>50.0</td><td>74.6</td><td>37.7</td><td>97.0</td><td>-</td><td>-</td></tr><tr><td>Content1</td><td>-3.7</td><td>-22.2</td><td>-13.9</td><td>-3.5</td><td>91.9</td><td>29.6</td></tr><tr><td>+PE</td><td>+2.2</td><td>-26.3</td><td>-13.8</td><td>-1.8</td><td>93.2</td><td>16.1</td></tr><tr><td>+Reviser</td><td>+5.1</td><td>-30.4</td><td>-9.4</td><td>+1.0</td><td>94.6</td><td>10.7</td></tr><tr><td>Format</td><td>-4.5</td><td>-19.9</td><td>-12.6</td><td>-0.3</td><td>97.3</td><td>19.1</td></tr><tr><td>+PE</td><td>-3.7</td><td>-31.7</td><td>-17.3</td><td>-0.3</td><td>100.0</td><td>14.5</td></tr><tr><td>+Reviser</td><td>-3.1</td><td>-16.3</td><td>-11.9</td><td>-0.7</td><td>98.7</td><td>16.8</td></tr><tr><td rowspan="7">DR Tulu</td><td>Initial</td><td>50.1</td><td>68.7</td><td>53.2</td><td>97.7</td><td>-</td><td>-</td></tr><tr><td>Content1</td><td>+0.6</td><td>-4.1</td><td>-4.0</td><td>-2.3</td><td>88.0</td><td>25.6</td></tr><tr><td>+PE</td><td>+3.4</td><td>+1.3</td><td>+0.9</td><td>-3.4</td><td>88.0</td><td>14.1</td></tr><tr><td>+Reviser</td><td>+5.8</td><td>-8.4</td><td>-11.3</td><td>-2.1</td><td>92.0</td><td>9.5</td></tr><tr><td>Format</td><td>-0.9</td><td>-1.8</td><td>+1.5</td><td>-0.9</td><td>94.0</td><td>13.1</td></tr><tr><td>+PE</td><td>-0.8</td><td>-0.6</td><td>+0.5</td><td>-1.5</td><td>96.0</td><td>12.1</td></tr><tr><td>+Reviser</td><td>-0.3</td><td>-1.4</td><td>-20.1</td><td>-1.3</td><td>100.0</td><td>12.6</td></tr></table>

Table 3: PE and Reviser results. Second turn’s score change from Initial (turn 1) is shown for the four main metrics, along with incorporation (Inc.) and break (Brk.) rates. Best values are bolded within each agent and setting.

Experimental Setup. We evaluate the two fixes on OpenAI DR and DR Tulu under the Content<sub>1</sub> and Format settings using the Core Set. For PE, we use GPT-4.1 to transform simulated feedback into structured edit plans before sending them to the DRA. For the Reviser, we implement a ReAct agent (Yao et al.,

2023) with Qwen3-30B-A3B-Instruct, a model with strong instruction-following capabilities (84.7% on IFEval (Zhou et al., 2023)), augmented with Google Search to retrieve additional information when needed. We include details and prompts in Appendix D.

## 6.1 Findings

Both approaches can improve coverage by reducing break rates and improving incorporation rates. As shown in Table 3, both PE and the Reviser enable DRAs to achieve coverage improvements for both content and format feedback settings, compared to when no fix is applied. These improvements stem from consistently higher incorporation rates and lower break rates. The Reviser generally outperforms PE in coverage scores, likely because the model is optimized for instruction-following and thus can execute edit requests more faithfully without introducing disruptive changes.

However, these fixes fall short of fully addressing the challenges in multi-turn revision. First, even with the best-performing Reviser, agents still break over 10% of previously covered criteria on average, especially under the format feedback setting, where both fixes yield smaller gains. Second, neither approach resolves citation degradation: for OpenAI DR, both PE and the Reviser still show substantial drops in citation faithfulness and claim groundedness compared to the initial report. These persistent gaps indicate that inference-time mitigations alone cannot fully address the multi-turn revision challenges. Achieving reliable report revision that preserves both content coverage and citation quality will likely require more fundamental advances in training algorithms or scaffold design.

## 7 Related Works

Deep Research Report Evaluation The emergence of DRAs has motivated long-form report benchmarking with varied evaluation approaches. Some rely on gold-standard reference reports to judge comprehensiveness (Du et al., 2025; Li et al., 2025a), while others adopt checklist-based evaluation (Hashemi et al., 2024; Lee et al., 2025b; Arora et al., 2025) specifies question-specific criteria to measure content coverage (Wang et al., 2025; Yao et al., 2025; Xu et al., 2025; Sharma et al., 2025). A complementary axis concerns factual verifiability. Prior works assessed it via citation quality (Gao et al., 2023; Ye et al., 2024; Liu et al., 2023), which is widely adopted in recent Deep Research evaluations (Fan et al., 2025; Yao et al., 2025; Xu et al., 2025; Li et al., 2025a). Our MR DRE builds upon these evaluation practices to arrive at a unified protocol, meanwhile extending the scope to multi-turn report revision, an ability that remains underdeveloped for current DRAs.

Revision Abilities of LLMs Prior works have found that LLMs can improve their reasoning, coding, and agentic task performance through self-reflection (Madaan et al., 2023; Zelikman et al., 2024; Shinn et al., 2023). Yet, similar to our findings, some have also shown contradictory results that such gains can be fragile, as LLMs often fail to identify their own mistakes and thus struggle to self-correct reliably (Huang et al., 2024; Lee et al., 2025a). Also, another line of work obtains feedback from external tools or critic models for LLMs to revise their outputs (Gou et al., 2024; Nathani et al., 2023; Jiang et al., 2023; Wadhwa et al., 2024). In this work, we extend the discussion to Deep Research multi-turn report revision, examining both self-reflection and user feedback settings. Although Qiao et al. (2025) and Han et al. (2025) explored iterative drafting for DRAs, they did not consider multi-turn user feedback settings, where we reveal critical limitations and provide a comprehensive testbed for future development.

## 8 Conclusions

In this paper, we propose multi-turn report revision as an essential yet overlooked capability of DRAs. We introduce MR DRE, an evaluation suite featuring a unified evaluation protocol for long-form reports and a human-verified feedback generation pipeline for simulating user feedback in multi-turn revision. Across five diverse DRAs and three feedback settings, current systems cannot reliably improve reports through revision. While DRAs mostly address the given feedback, they frequently regress on unrelated content and citation quality. These gaps are not easily closed by simple fixes such as prompt engineering or dedicated sub-agents. We view multi-turn report revision as a critical missing piece in developing useful DRAs, and MR DRE aims to drive progress toward agents that can both conduct complex research and reliably adapt to users’ evolving needs.

## Limitations

Understanding the Causes of Unreliability While our work reveals critical limitations in DRAs’ multi-turn revision ability, the causes of the high break rate, imperfect incorporation rate, and citation degradation are not yet fully understood (see error cases in Appendix G.2). We encourage future work to systematically analyze these underlying causes, which would inform the development of new training algorithms or agent scaffolds for reliable multi-turn revision.

Model Scaling Effects on Revision Ability Due to the high cost of running proprietary models on Deep Research tasks, we did not investigate how scaling up the backbone model affects revision reliability. For instance, we used o4-mini-deep-research instead of the stronger o3-deep-research for OpenAI DR, and LC ODR uses GPT-4.1-mini as its backbone. How model scaling affects revision ability remains unclear and warrants further investigation.

Missing Considerations in Evaluation Protocol First, our feedback simulation assumes that the questions and checklists are high-quality. Future work could enhance the feedback simulation pipeline to be robust to varying checklist quality, potentially incorporating LLM-based checklist evaluation (Lee et al., 2025b; Wei et al., 2025b). Second, MR DRE does not penalize excessive report length. We observe that Sonar DR consistently achieves higher coverage, partially because its reports are substantially longer than those of other DRAs (on average 9452 tokens for Sonar DR vs 4516 tokens for other DRAs per report), though it also has a lower presentation score due to consistently failing p in Table 5. However, ideal length varies across questions and user preferences, making it difficult to define an evaluation scheme. Future work could build upon the MR DRE protocol to enhance length-aware evaluation.

## References

Rahul K. Arora, Jason Wei, Rebecca Soskin Hicks, Preston Bowman, Joaquin Quiñonero-Candela, Foivos Tsimpourlas, Michael Sharman, Meghan Shah, Andrea Vallone, Alex Beutel, Johannes Heidecke, and Karan Singhal. Healthbench: Evaluating large language models towards improved human health, 2025. URL https://arxiv.org/abs/2505.08775.

Zijian Chen, Xueguang Ma, Shengyao Zhuang, Ping Nie, Kai Zou, Andrew Liu, Joshua Green, Kshama Patel, Ruoxi Meng, Mingyi Su, Sahel Sharifymoghaddam, Yanxi Li, Haoran Hong, Xinyu Shi, Xuye Liu, Nandan Thakur, Crystina Zhang, Luyu Gao, Wenhu Chen, and Jimmy Lin. Browsecomp-plus: A more fair and transparent evaluation benchmark of deep-research agent, 2025. URL https://arxiv.org/abs/2508.06600.

Mingxuan Du, Benfeng Xu, Chiwei Zhu, Xiaorui Wang, and Zhendong Mao. Deepresearch bench: A comprehensive benchmark for deep research agents, 2025. URL https://arxiv.org/abs/2506. 11763.

Angela Fan, Yacine Jernite, Ethan Perez, David Grangier, Jason Weston, and Michael Auli. ELI5: Long form question answering. In Anna Korhonen, David Traum, and Lluís Màrquez (eds.), Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics, pp. 3558–3567, Florence, Italy, July 2019. Association for Computational Linguistics. doi: 10.18653/v1/P19-1346. URL https://aclanthology.org/P19-1346/.

Tianyu Fan, Xinyao Niu, Yuxiang Zheng, Fengji Zhang, Chengen Huang, Bei Chen, Junyang Lin, and Chao Huang. Understanding deepresearch via reports, 2025. URL https://arxiv.org/abs/ 2510.07861.

Tianyu Gao, Howard Yen, Jiatong Yu, and Danqi Chen. Enabling large language models to generate text with citations. In Houda Bouamor, Juan Pino, and Kalika Bali (eds.), Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing, pp. 6465–6488, Singapore, December 2023. Association for Computational Linguistics. doi: 10.18653/v1/2023.emnlp-main. 398. URL https://aclanthology.org/2023.emnlp-main.398/.

Zhibin Gou, Zhihong Shao, Yeyun Gong, Yelong Shen, Yujiu Yang, Nan Duan, and Weizhu Chen. Critic: Large language models can self-correct with tool-interactive critiquing, 2024. URL https: //arxiv.org/abs/2305.11738.

Rujun Han, Yuhao Zhang, Peng Qi, Yumo Xu, Jenyuan Wang, Lan Liu, William Yang Wang, Bonan Min, and Vittorio Castelli. RAG-QA arena: Evaluating domain robustness for long-form retrieval augmented question answering. In Yaser Al-Onaizan, Mohit Bansal, and Yun-Nung Chen (eds.), Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing, pp. 4354– 4374, Miami, Florida, USA, November 2024. Association for Computational Linguistics. doi: 10.18653/v1/2024.emnlp-main.249. URL https://aclanthology.org/2024.emnlp-main.249/.

Rujun Han, Yanfei Chen, Zoey CuiZhu, Lesly Miculicich, Guan Sun, Yuanjun Bi, Weiming Wen, Hui Wan, Chunfeng Wen, Solène Maître, et al. Deep researcher with test-time diffusion. arXiv preprint arXiv:2507.16075, 2025.

Helia Hashemi, Jason Eisner, Corby Rosset, Benjamin Van Durme, and Chris Kedzie. LLM-rubric: A multidimensional, calibrated approach to automated evaluation of natural language texts. In Lun-Wei Ku, Andre Martins, and Vivek Srikumar (eds.), Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers), pp. 13806–13834, Bangkok, Thailand, August 2024. Association for Computational Linguistics. doi: 10.18653/v1/2024. acl-long.745. URL https://aclanthology.org/2024.acl-long.745/.

Jie Huang, Xinyun Chen, Swaroop Mishra, Huaixiu Steven Zheng, Adams Wei Yu, Xinying Song, and Denny Zhou. Large language models cannot self-correct reasoning yet, 2024. URL https: //arxiv.org/abs/2310.01798.

Zhengbao Jiang, Frank Xu, Luyu Gao, Zhiqing Sun, Qian Liu, Jane Dwivedi-Yu, Yiming Yang, Jamie Callan, and Graham Neubig. Active retrieval augmented generation. In Houda Bouamor, Juan Pino, and Kalika Bali (eds.), Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing, pp. 7969–7992, Singapore, December 2023. Association for Computational Linguistics. doi: 10.18653/v1/2023.emnlp-main.495. URL https://aclanthology.org/2023. emnlp-main.495/.

LangChain. Open deep research, 2025. URL https://blog.langchain.com/open-deep-research/.

Young-Jun Lee, Seungone Kim, Byung-Kwan Lee, Minkyeong Moon, Yechan Hwang, Jong Myoung Kim, Graham Neubig, Sean Welleck, and Ho-Jin Choi. Refinebench: Evaluating refinement capability in language models. In First Workshop on Multi-Turn Interactions in Large Language Models, 2025a. URL https://openreview.net/forum?id=Ycred6ETQR.

Yukyung Lee, JoongHoon Kim, Jaehee Kim, Hyowon Cho, Jaewook Kang, Pilsung Kang, and Najoung Kim. CheckEval: A reliable LLM-as-a-judge framework for evaluating text generation using checklists. In Christos Christodoulopoulos, Tanmoy Chakraborty, Carolyn Rose, and Violet Peng (eds.), Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing, pp. 15782–15809, Suzhou, China, November 2025b. Association for Computational Linguistics. ISBN 979-8-89176-332-6. doi: 10.18653/v1/2025.emnlp-main.796. URL https: //aclanthology.org/2025.emnlp-main.796/.

Minghao Li, Ying Zeng, Zhihao Cheng, Cong Ma, and Kai Jia. Reportbench: Evaluating deep research agents via academic survey tasks, 2025a. URL https://arxiv.org/abs/2508.15804.

Xiaoxi Li, Jiajie Jin, Guanting Dong, Hongjin Qian, Yongkang Wu, Ji-Rong Wen, Yutao Zhu, and Zhicheng Dou. Webthinker: Empowering large reasoning models with deep research capability, 2025b. URL https://arxiv.org/abs/2504.21776.

Nelson Liu, Tianyi Zhang, and Percy Liang. Evaluating verifiability in generative search engines. In Houda Bouamor, Juan Pino, and Kalika Bali (eds.), Findings of the Association for Computational Linguistics: EMNLP 2023, pp. 7001–7025, Singapore, December 2023. Association for Computational Linguistics. doi: 10.18653/v1/2023.findings-emnlp.467. URL https://aclanthology.org/2023.findings-emnlp.467/.

Aman Madaan, Niket Tandon, Prakhar Gupta, Skyler Hallinan, Luyu Gao, Sarah Wiegreffe, Uri Alon, Nouha Dziri, Shrimai Prabhumoye, Yiming Yang, Shashank Gupta, Bodhisattwa Prasad Majumder, Katherine Hermann, Sean Welleck, Amir Yazdanbakhsh, and Peter Clark. Selfrefine: Iterative refinement with self-feedback. In Thirty-seventh Conference on Neural Information Processing Systems, 2023. URL https://openreview.net/forum?id=S37hOerQLB.

Grégoire Mialon, Clémentine Fourrier, Craig Swift, Thomas Wolf, Yann LeCun, and Thomas Scialom. Gaia: a benchmark for general ai assistants, 2023. URL https://arxiv.org/abs/2311.12983.

Niklas Muennighoff, Zitong Yang, Weijia Shi, Xiang Lisa Li, Li Fei-Fei, Hannaneh Hajishirzi, Luke Zettlemoyer, Percy Liang, Emmanuel Candes, and Tatsunori Hashimoto. s1: Simple test-time scaling. In Christos Christodoulopoulos, Tanmoy Chakraborty, Carolyn Rose, and Violet Peng (eds.), Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing, pp. 20286–20332, Suzhou, China, November 2025. Association for Computational Linguistics. ISBN 979-8-89176-332-6. doi: 10.18653/v1/2025.emnlp-main.1025. URL https: //aclanthology.org/2025.emnlp-main.1025/.

Deepak Nathani, David Wang, Liangming Pan, and William Wang. MAF: Multi-aspect feedback for improving reasoning in large language models. In Houda Bouamor, Juan Pino, and Kalika Bali (eds.), Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing, pp. 6591–6616, Singapore, December 2023. Association for Computational Linguistics. doi: 10.18653/v1/2023.emnlp-main.407. URL https://aclanthology.org/2023.emnlp-main.407/.

OpenAI. Deep research system card, 2025. URL https://openai.com/index/ deep-research-system-card/.

Perplexity. Introducing perplexity deep research, 2025. URL https://www.perplexity.ai/hub/ blog/introducing-perplexity-deep-research.

Long Phan, Alice Gatti, Ziwen Han, Nathaniel Li, Josephina Hu, Hugh Zhang, Chen Bo Calvin Zhang, Mohamed Shaaban, John Ling, Sean Shi, Michael Choi, Anish Agrawal, Arnav Chopra, Adam Khoja, Ryan Kim, Richard Ren, Jason Hausenloy, Oliver Zhang, Mantas Mazeika, Summer Yue, Alexandr Wang, Dan Hendrycks, and dataset contributors. Humanity’s last exam, 2025. URL https://arxiv.org/abs/2501.14249.

Zile Qiao, Guoxin Chen, Xuanzhong Chen, Donglei Yu, Wenbiao Yin, Xinyu Wang, Zhen Zhang, Baixuan Li, Huifeng Yin, Kuan Li, et al. Webresearcher: Unleashing unbounded reasoning capability in long-horizon agents. arXiv preprint arXiv:2509.13309, 2025.

Jie Ruan, Inderjeet Nair, Shuyang Cao, Amy Liu, Sheza Munir, Micah Pollens-Dempsey, Tiffany Chiang, Lucy Kates, Nicholas David, Sihan Chen, Ruxin Yang, Yuqian Yang, Jasmine Gump, Tessa Bialek, Vivek Sankaran, Margo Schlanger, and Lu Wang. Expertlongbench: Benchmarking language models on expert-level long-form generation tasks with structured checklists, 2025. URL https://arxiv.org/abs/2506.01241.

Rulin Shao, Akari Asai, Shannon Zejiang Shen, Hamish Ivison, Varsha Kishore, Jingming Zhuo, Xinran Zhao, Molly Park, Samuel G. Finlayson, David Sontag, Tyler Murray, Sewon Min, Pradeep Dasigi, Luca Soldaini, Faeze Brahman, Wen tau Yih, Tongshuang Wu, Luke Zettlemoyer, Yoon Kim, Hannaneh Hajishirzi, and Pang Wei Koh. Dr tulu: Reinforcement learning with evolving rubrics for deep research, 2025. URL https://arxiv.org/abs/2511.19399.

Manasi Sharma, Chen Bo Calvin Zhang, Chaithanya Bandi, Clinton Wang, Ankit Aich, Huy Nghiem, Tahseen Rabbani, Ye Htet, Brian Jang, Sumana Basu, Aishwarya Balwani, Denis Peskoff, Marcos Ayestaran, Sean M. Hendryx, Brad Kenstler, and Bing Liu. Researchrubrics: A benchmark of prompts and rubrics for evaluating deep research agents, 2025. URL https://arxiv.org/abs/ 2511.07685.

Noah Shinn, Federico Cassano, Ashwin Gopinath, Karthik R Narasimhan, and Shunyu Yao. Reflexion: language agents with verbal reinforcement learning. In Thirty-seventh Conference on Neural Information Processing Systems, 2023. URL https://openreview.net/forum?id=vAElhFcKW6.

Charlie Victor Snell, Jaehoon Lee, Kelvin Xu, and Aviral Kumar. Scaling LLM test-time compute optimally can be more effective than scaling parameters for reasoning. In The Thirteenth International Conference on Learning Representations, 2025. URL https://openreview.net/forum?id= 4FWAwZtd2n.

Yixiao Song, Yekyung Kim, and Mohit Iyyer. VeriScore: Evaluating the factuality of verifiable claims in long-form text generation. In Yaser Al-Onaizan, Mohit Bansal, and Yun-Nung Chen (eds.), Findings ofthe Associationfor Computational Linguistics: EMNLP 2024, pp. 9447–9474, Miami, Florida, USA, November 2024. Association for Computational Linguistics. doi: 10.18653/v1/ 2024.findings-emnlp.552. URL https://aclanthology.org/2024.findings-emnlp.552/.

Tongyi DeepResearch Team, Baixuan Li, Bo Zhang, Dingchu Zhang, Fei Huang, Guangyu Li, Guoxin Chen, Huifeng Yin, Jialong Wu, Jingren Zhou, Kuan Li, Liangcai Su, Litu Ou, Liwen Zhang, Pengjun Xie, Rui Ye, Wenbiao Yin, Xinmiao Yu, Xinyu Wang, Xixi Wu, Xuanzhong Chen, Yida Zhao, Zhen Zhang, Zhengwei Tao, Zhongwang Zhang, Zile Qiao, Chenxi Wang, Donglei Yu, Gang Fu, Haiyang Shen, Jiayin Yang, Jun Lin, Junkai Zhang, Kui Zeng, Li Yang, Hailong Yin, Maojia Song, Ming Yan, Minpeng Liao, Peng Xia, Qian Xiao, Rui Min, Ruixue Ding, Runnan Fang, Shaowei Chen, Shen Huang, Shihang Wang, Shihao Cai, Weizhou Shen, Xiaobin Wang, Xin Guan, Xinyu Geng, Yingcheng Shi, Yuning Wu, Zhuo Chen, Zijian Li, and Yong Jiang. Tongyi deepresearch technical report, 2025. URL https://arxiv.org/abs/2510.24701.

Manya Wadhwa, Xinyu Zhao, Junyi Jessy Li, and Greg Durrett. Learning to refine with fine-grained natural language feedback. In Yaser Al-Onaizan, Mohit Bansal, and Yun-Nung Chen (eds.), Findings of the Association for Computational Linguistics: EMNLP 2024, pp. 12281–12308, Miami, Florida, USA, November 2024. Association for Computational Linguistics. doi: 10.18653/v1/ 2024.findings-emnlp.716. URL https://aclanthology.org/2024.findings-emnlp.716/.

Jiayu Wang, Yifei Ming, Riya Dulepet, Qinglin Chen, Austin Xu, Zixuan Ke, Frederic Sala, Aws Albarghouthi, Caiming Xiong, and Shafiq Joty. Liveresearchbench: A live benchmark for usercentric deep research in the wild, 2025. URL https://arxiv.org/abs/2510.14240.

Jason Wei, Zhiqing Sun, Spencer Papay, Scott McKinney, Jeffrey Han, Isa Fulford, Hyung Won Chung, Alex Tachard Passos, William Fedus, and Amelia Glaese. Browsecomp: A simple yet challenging benchmark for browsing agents, 2025a. URL https://arxiv.org/abs/2504.12516.

Tianjun Wei, Wei Wen, Ruizhi Qiao, Xing Sun, and Jianghong Ma. Rocketeval: Efficient automated LLM evaluation via grading checklist. In The Thirteenth International Conference on Learning Representations, 2025b. URL https://openreview.net/forum?id=zJjzNj6QUe.

Tianze Xu, Pengrui Lu, Lyumanshan Ye, Xiangkun Hu, and Pengfei Liu. Researcherbench: Evaluating deep ai research systems on the frontiers of scientific inquiry, 2025. URL https: //arxiv.org/abs/2507.16280.

Zhilin Yang, Peng Qi, Saizheng Zhang, Yoshua Bengio, William Cohen, Ruslan Salakhutdinov, and Christopher D. Manning. HotpotQA: A dataset for diverse, explainable multi-hop question answering. In Ellen Riloff, David Chiang, Julia Hockenmaier, and Jun’ichi Tsujii (eds.), Proceedings of the 2018 Conference on Empirical Methods in Natural Language Processing, pp. 2369–2380, Brussels, Belgium, October-November 2018. Association for Computational Linguistics. doi: 10.18653/v1/ D18-1259. URL https://aclanthology.org/D18-1259/.

Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik R Narasimhan, and Yuan Cao. React: Synergizing reasoning and acting in language models. In The Eleventh International Conference on Learning Representations, 2023. URL https://openreview.net/forum?id=WE\_vluYUL-X.

Yang Yao, Yixu Wang, Yuxuan Zhang, Yi Lu, Tianle Gu, Lingyu Li, Dingyi Zhao, Keming Wu, Haozhe Wang, Ping Nie, Yan Teng, and Yingchun Wang. A rigorous benchmark with multidimensional evaluation for deep research agents: From answers to reports, 2025. URL https://arxiv.org/abs/2510.02190.

Xi Ye, Ruoxi Sun, Sercan Arik, and Tomas Pfister. Effective large language model adaptation for improved grounding and citation generation. In Kevin Duh, Helena Gomez, and Steven Bethard (eds.), Proceedings of the 2024 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies (Volume 1: Long Papers), pp. 6237–6251, Mexico City, Mexico, June 2024. Association for Computational Linguistics. doi: 10.18653/v1/ 2024.naacl-long.346. URL https://aclanthology.org/2024.naacl-long.346/.

Eric Zelikman, Eliana Lorch, Lester Mackey, and Adam Tauman Kalai. Self-taught optimizer (STOP): Recursively self-improving code generation. In First Conference on Language Modeling, 2024. URL https://openreview.net/forum?id=46Zgqo4QIU.

Jeffrey Zhou, Tianjian Lu, Swaroop Mishra, Siddhartha Brahma, Sujoy Basu, Yi Luan, Denny Zhou, and Le Hou. Instruction-following evaluation for large language models, 2023. URL https://arxiv.org/abs/2311.07911.

## A Data Curation Details

## A.1 Dataset Details

We show the dataset statistics of the three datasets of MR DRE in Table 4.

<table><tr><td>Dataset</td><td>Size</td><td># Items/ Question</td><td>Domains</td></tr><tr><td>ResearchRubrics</td><td>101</td><td>25.67</td><td>General</td></tr><tr><td>RigorousBench</td><td>214</td><td>14.32</td><td>General</td></tr><tr><td>ResearcherBench</td><td>65</td><td>13.33</td><td>AI&amp;ML</td></tr></table>

Table 4: Dataset statistics. # Items / Question denotes the average number of instance-specific checklist items per question.

Note that for RigorousBench, we used their “Query-Specific Rubrics” as our question-specific checklist, and excluded the more coarse scoring checklist named “General-Report Rubrics” in Yao et al. (2025). They labeled the score for satisfying each checklist criterion, which we use as the question weight. For all our experiments, we used a sub-sampled set of 100 questions in RigorousBench due to the high cost of Deep Research experiments, which is a sufficient size comparable to the other two datasets.

## A.2 Core Set Construction

We construct a core set by uniformly sampling 25 questions from each dataset (ResearcherBench, ResearchRubrics, and RigorousBench) such that for each sampled question, the initial report produced by every evaluated DRA fails to satisfy at least four evaluation criteria.

## B Evaluation Protocol Details

Below, we describe details of our evaluation protocol. For all LLM judges $( \mathcal { I } _ { \mathrm { c o v } } , \mathcal { I } _ { \mathrm { f a c t } } , \mathcal { I } _ { \mathrm { p r e s } } )$ and the claim extractor mentioned in §3, we instantiate with GPT-4.1-mini $( { \bar { \mathsf { g p t } } } - 4 . 1 - \mathsf { m i n i } - 2 \theta 2 ^ { \cdot } 5 - \theta 4 - 1 4 )$ following DR Tulu, which is strong at instruction-following and long-context understanding, balancing accuracy and cost. We use temperature= 0 for all judgements to minimize randomness and promote reproducibility.

## B.1 Comprehensiveness Evaluation

For comprehensiveness evaluation, we evaluate the checklist coverage score using an LLM judge $\mathcal { I } _ { \mathrm { c o v } }$ for each report-criterion pair. The prompt template is presented in Figure 14.

Note that we append a small reminder text (Figure 5) to the user message for evaluating negativeweight criteria. This is because the LLM Judge sometimes scores 1 when the report avoids what the criterion asks about, which is the opposite of what we expect it to do.

## B.2 Factuality Evaluation

Here, we describe the detailed pipeline for factuality evaluation. We first split each report into sections using double new lines. Then, for each section, we extract atomic claims alongside their cited URL(s) with the claim extractor LLM (prompt template shown in Figure 18&19). For each claim, we gather its cited URLs and fetch the URL content using the Jina Reader $\mathrm { A P I } ^ { 2 }$ . To reduce the cost of running LLM judges, we summarize the crawled URL content with a lightweight model, GPT-4.1-Nano, to reduce context length. We then prompt $\mathcal { I } _ { \mathrm { f a c t } }$ to label each claim as Supported, Contradicted, or Insufficient, given the crawled URL content (Prompt in Figure 20&21). As introduced in §3.2, we report citation faithfulness as the fraction of supported claims among claims with at least one URL, and claim groundedness as the fraction of supported claims among all extracted claims.

![](images/6fdf72fc6f3711ebcfaa2de9aebe8a007c6b3e11d11117bd2d745dd276a3b020.jpg)  
Figure 5: Negative-weight Reminder Text.

## B.3 Presentation Evaluation

In Table 5, we show the full list of our presentation questions, each with its detailed source or rationale for inclusion. These questions are carefully consolidated and refined from LiveResearch-Bench Wang et al. (2025), RigorousBench Yao et al. (2025), DeepResearch-ReportEval Fan et al. (2025), with some new questions that we find missing from all prior works. Note that $p _ { 6 }$ and $p _ { 7 }$ are questions that might not apply to some reports; we exclude them if the judgement score is -1.

## B.4 Handling Negative Weights in Evaluation Metrics

Some Deep Research benchmarks, notably ResearchRubrics Sharma et al. (2025) in our evaluation suite, may assign negative weights to certain checklist criteria to penalize undesirable content such as misinformation or irrelevant topics. For a criterion $c _ { i }$ with negative weight $w _ { i } < 0$ , a score of $s _ { i } = 1$ (full coverage) indicates the report contains the undesirable content and should be penalized, while $s _ { i } = 0$ indicates the report correctly avoids it. Below we describe how each metric accommodates negative weights. The actual results in our experiment sections use the formulations below instead of the simplified version in $\ S 3$ without considering negative weights.

## B.4.1 Coverage Score

For the coverage score, the numerator $\textstyle \sum _ { i = 1 } ^ { n } w _ { i } \cdot s _ { i }$ naturally handles negative weights: when $w _ { i } < 0$ and $s _ { i } > 0 .$ , the product $w _ { i } \cdot s _ { i }$ is negative, reducing the overall score. However, the denominator must be adjusted to normalize only by the maximum achievable score, which comes from positiveweight criteria alone (since the best outcome for negative-weight criteria is $s _ { i } = 0 .$ , contributing nothing to the numerator). The full formula is:

$$
\operatorname{COV} (r) = \frac {\sum_ {i = 1} ^ {n} w _ {i} \cdot s _ {i}}{\sum_ {i : w _ {i} > 0} w _ {i}}
$$

This formulation ensures that the coverage score ranges from negative values (when the report contains penalized content) to 1 (when the report fully covers all positive-weight criteria and avoids all negative-weight criteria).

## B.4.2 Incorporation Rate

For content feedback, the incorporation rate measures whether feedback targets reach their ideal coverage score after revision. The ideal score depends on the sign of the weight:

$$
\bar {s} _ {i} = \left\{ \begin{array}{l l} 1, & \text {if w_{i} >0} \\ 0, & \text {if w_{i} <  0} \end{array} \right.
$$

For positive-weight criteria, the ideal is full coverage $( s _ { i } = 1 )$ ). For negative-weight criteria, the ideal is zero coverage $\overset { \smile } ( s _ { i } = 0 )$ , meaning the report should remove or avoid the undesirable content. The incorporation rate at turn t becomes:

$$
\mathrm{INC} = \frac {1}{| \mathcal {T} ^ {(t)} |} \sum_ {c _ {i} \in \mathcal {T} ^ {(t)}} \mathbb {1} \left[ s _ {i} ^ {(t)} = \bar {s} _ {i} \right]
$$

Note that feedback targets $\mathscr { T } ^ { ( t ) }$ are sampled from criteria that have not yet reached their ideal score, which for negative-weight criteria means $s _ { i } ^ { ( t - 1 ) } > 0$

## B.4.3 Break Rate

The break rate measures the degradation of previously achieved coverage. The definitions of "previously achieved" and "coverage degradation" are adapted based on the weight sign:

Previously Achieved Coverage For positive-weight criteria, previously achieved coverage means $s _ { i } ^ { ( t - 1 ) } > 0$ (at least partial coverage of desirable content). For negative-weight criteria, previously achieved coverage means $s _ { i } ^ { ( t - 1 ) } < 1$ (not fully covering undesirable content, i.e., partially or fully avoiding the misconception). Let $\mathscr { C } _ { + } ^ { ( t - 1 ) }$ denote the set of criteria with previously achieved coverage:

$$
\mathcal {C} _ {+} ^ {(t - 1)} = \{c _ {i}: (w _ {i} > 0 \land s _ {i} ^ {(t - 1)} > 0) \lor (w _ {i} <   0 \land s _ {i} ^ {(t - 1)} <   1) \}
$$

Coverage Degradation For positive-weight criteria, degradation occurs when coverage decreases $( s _ { i } ^ { ( t ) } < \bar { s _ { i } } ^ { ( t - 1 ) } )$ ). For negative-weight criteria, degradation occurs when coverage increases $( s _ { i } ^ { ( t ) } >$ $s _ { i } ^ { ( { \dot { t } } - 1 ) } )$ , meaning the revision introduced more undesirable content. Both cases can be unified using the weight sign: degradation occurs when $w _ { i } \cdot s _ { i } ^ { ( t ) } < w _ { i } \cdot s _ { i } ^ { ( t - 1 ) }$ , i.e., when the weighted contribution to the coverage score decreases. The full break rate formula is:

$$
\mathrm{BRK} = \frac {\left| \left\{c _ {i} \in \mathcal {C} _ {+} ^ {(t - 1)} : w _ {i} \cdot s _ {i} ^ {(t)} <   w _ {i} \cdot s _ {i} ^ {(t - 1)} \right\} \right|}{\left| \mathcal {C} _ {+} ^ {(t - 1)} \right|}
$$

## C Feedback Simulation Pipeline Details

## C.1 Content Feedback

To simulate content feedback, we prompt GPT-4.1-mini with the question, k sampled feedback targets with each score, weight, and scoring justification. We show the prompt for k = 1 in Figure 11 and k > 1 in Figure 12.

## C.2 Seed Format Feedback

Two of our authors wrote the following 21 diverse and realistic seed format feedback pieces. We present them in Table 6.

## C.3 Human Validation Results

Our goal is to simulate the most realistic follow-up that a human user would ask the DRA to revise the report against. Therefore, we defined the following four dimensions to assess the feedback’s quality:

Naturalness: The language and wording should be natural and human-like, as if it were a natural follow-up response from the user themselves, or a thoughtful peer/supervisor.

Draft-specificness: The feedback should be tailored to the question and the current draft of the report, targeting aspects that the current draft misses and have clear room for improvement.

Actionability:The feedback should be concrete and actionable, phrased as implementable suggestions and avoiding vague comments such as “improve clarity” without explaining how.

Content-preserving (only applicable to format feedback): The feedback must not require any edits to existing content in the current draft. It should only incur changes in the form, structure, organization, tone, or style of the writing.

From all Content and Format feedback generated for five DRAs across three datasets, we randomly sampled 50 content feedback instances and 50 format feedback instances. Two authors, each holding at least a Bachelor’s degree in a science-related field, independently annotated each feedback instance alongside its corresponding report on the four dimensions above using binary scores (satisfied or not satisfied). We report agreement rate as the percentage of instances where both annotators assign identical scores across all four dimensions. For instances with disagreement, we take the lower score to provide a conservative estimate of feedback quality. We present the results in Table 7.

We found that our feedback simulation pipeline generally achieves a near-perfect score across all dimensions with a high inter-annotator agreement rate. This validates our feedback simulation pipeline as a realistic component for multi-turn report revision.

## D Proposed Fixes Details

## D.1 Prompt Engineering (PE) on Feedback Details

The prompt engineering (PE) fix pipeline refines raw user feedback into an executable revision instruction in two steps. First, we feed the original query, the full research report, and the user’s feedback into a prompt refiner (GPT-4.1) with a fixed system prompt (Figure 26) that forces the output into a structured, localized edit plan. Second, we append a fixed, hard-coded constraint suffix to this structured plan, which makes the downstream editor follow only the specified actions, avoid global rewrites, and output only the revised report. The concatenation of the structured edit plan and the constraint suffix (Figure 27) forms the final refined prompt used for report revision.

## D.2 Reviser Subagent Details

For the Reviser, we implemented a simple ReAct agent using Qwen3-30B-A3B-Instruct-2507 as the backbone model and its default function calling template, augmented with Serper $\mathrm { A P I } ^ { 3 }$ to call Google Search for additional information when the user feedback requires some extra information gathering. We set the temperature to 0.7, top-p to 0.95, and the maximum number of generated tokens to 16384. For each revision, we allow the agent to call the search API 10 times at maximum, with each call returning the top 5 web pages. If the maximal number of tool calls is reached, we softly force a final answer by using “You have reached the maximal number of web search calls. Please now produce the revised report based on the information you have and the user feedback.” as the tool output. The system and user prompt templates are in Figure 28 and 29.

## E Additional Results

## E.1 Citation Analysis

We present citation-related statistics in Table 8, reporting the average number of extracted claims $( | \mathcal { E } | )$ , claims with at least one citation $( | \mathcal { E } _ { \mathrm { c i t e d } } | )$ , supported claims $( | S | )$ , and citation counts $( \left| \mathcal { U } \right| )$ for each dataset. These fine-grained statistics reveal that the causes of citation degradation vary across agents.

For OpenAI DR, degradation stems primarily from reductions in both supported claims and overall citation counts, with supported claims declining more severely (on average -7.0 supported claims and -11.2 citation counts).

For Sonar DR, as noted in Section 5.1, 68% of reports generated after self-reflection contain zero citations, causing both factuality metrics to plummet. A similar pattern emerges in the Format setting, where 21% of reports on average lack any cited URLs. While this phenomenon disappears for ResearchRubrics and ResearcherBench under Content , we still observe a substantial reduction in the ratio of supported claims.

For LC ODR, the Reflect setting produces notably more claims than the initial draft, yet the number of supported claims does not increase proportionally, leading to lower citation faithfulness and claim groundedness. In the Content and Format settings, claim counts remain relatively stable or increase slightly, but the number of cited or supported claims drops, yielding similar degradation in citation quality.

For DR Tulu, the relatively stable but mixed number of supported claims across settings explains why it exhibits the most consistent citation quality among all evaluated DRAs.

## E.2 Full Multi-turn Results under Content and Reflect

We present the full results of Content<sub>1</sub> and Reflect up to 4 turns of revision in Figure 6 and Figure 7.

![](images/e1479eafeff7ca6b28b58cea3a969a711a9a020e6f436bf861bcea2cb0a0ff1d.jpg)  
Figure 6: Full multi-turn results for the Reflect setting. Tongyi DR’s citation faithfulness and claim groundedness are omitted since it is not trained to generate citations. Error bars indicate standard errors.

## E.3 Full Multi-item Content Feedback Results

We present the complete results of ${ \mathrm { C o n t e n t } } _ { k }$ with a varying number of feedback targets in Figure 8.

## F Prompt Templates

We present prompt templates in Figure 11-29.

![](images/59df7c5a2d4c3afd7ef24ab03e5ca48f55efac4bd2823c7d4e498e262fee567f.jpg)  
Figure 7: Full multi-turn results for the Content setting. Tongyi DR’s citation faithfulness and claim groundedness are omitted since it is not trained to generate citations. Error bars indicate standard errors.

## G Case Studies

## G.1 More Feedback Examples

We present representative feedback examples used in our multi-turn revision setup (Table 9). The table includes both format feedback and content feedback with one or three targets.

![](images/1734cba1529d7fc2a5290b20147ab32119682b27c3a4b6f9b1ebfe0ea5187634.jpg)  
Figure 8: Full results for content feedback with multiple feedback targets (k).

## G.2 Error Cases

We provide two representative failure cases in multi-turn report revision. Figure 9 shows a missing content case, where the revised report fails to preserve content outside the feedback’s scope and drops a required paragraph. Figure 10 illustrates citation degradation, where the revised report reduces citations and removes in-context citation markers from the original.

<table><tr><td></td><td>Question</td><td>Source/Rationale</td></tr><tr><td> $p_1$ </td><td>Does the report follow a clear, logically ordered structure that is easy to navigate (e.g., problem → approach → results), with sections that match the report&#x27;s stated purpose and directly address the research question?</td><td>Q1 in LiveResearchBench&#x27;s Table 3; GRR 1 and 2 in RigorousBench; Definition of &quot;Clear and Logical Structure&quot; in DeepResearch-ReportEval</td></tr><tr><td> $p_2$ </td><td>Do different sections logically follow or build on one another with minimal redundant restatement, and is any repetition clearly purposeful (e.g., brief recap before a new stage)?</td><td>Definition of &quot;Redundancy&quot; in DeepResearch-ReportEval; Q2 in LiveResearchBench&#x27;s Table 3; Refined so that recap/summary is not counted as redundancy</td></tr><tr><td> $p_3$ </td><td>Where content is naturally parallel (steps, criteria, comparisons, key takeaways), does the report use lists and/or tables to present it in a scannable form rather than dense prose?</td><td>Newly written. This is not present in any previous evaluations, but is essential for penalizing dense paragraphs without proper formatting.</td></tr><tr><td> $p_4$ </td><td>Are headings/subheadings consistent in level and hierarchy (H1/H2/H3), and are comparable sections named with parallel phrasing (e.g., &quot;Method,&quot; &quot;Results&quot; rather than inconsistent mixes like &quot;How they did it,&quot; &quot;Findings&quot;)?</td><td>Further specified GRR8, 42 in RigorousBench. Added that the heading names should be parallel and comparable.</td></tr><tr><td> $p_5$ </td><td>Does the report use concise transition sentences/phrases to signal why the subsequent content follows and to reduce abrupt jumps and make the report easier to follow?</td><td>Further specified GRR7 in RigorousBench and Definition of &quot;Clear and Logical Structure&quot; in DeepResearch-ReportEval.</td></tr><tr><td> $p_6$ </td><td>If there are cross-references, are they consistent and unambiguous (figure/table numbers, section references, in-text citation), with no missing/duplicate numbering and no &quot;see above/below&quot; without an anchor? If no cross-references are present, the score should be -1.</td><td>Extended Q3, 4, 6, 10 in LiveResearchBench&#x27;s Table 3 and GRR24 in RigorousBench to all types of cross-references.</td></tr><tr><td> $p_7$ </td><td>If tables are included, are they structurally complete and interpretable on their own (no blank cells without notation, consistent units/precision, clear headers/labels/notes)? If no tables are included, the score should be -1.</td><td>Extended Q8 in LiveResearchBench&#x27;s Table 3; We do not allow automatic pass but rather discard it if the report does not have tables</td></tr><tr><td> $p_8$ </td><td>Is report formatting correct and consistent (e.g., valid Markdown heading syntax, renderable Markdown tables, consistent numbering, consistent emphasis/code styling, consistent citation format if used)?</td><td>Further specified and extended Q9 in LiveResearchBench&#x27;s Table 3</td></tr><tr><td> $p_9$ </td><td>Is the writing clear and professional at the sentence level (consistent tense/voice, minimal colloquialisms, avoids rhetorical exaggeration), with consistent terminology and abbreviation handling (define once, then reuse consistently)?</td><td>Further specified Q9 in LiveResearchBench&#x27;s Table 3 and GRR48 in RigorousBench. Rewritten so that professionalism is defined more clearly.</td></tr><tr><td> $p_{10}$ </td><td>Are key terms, symbols, and abbreviations formatted consistently (e.g., italicization, capitalization, acronym, bolding), and is there no drifting where the same concept is labeled multiple ways without intent?</td><td>Newly written. Stylistic considerations are missing from previous evaluations, which is important for report presentation.</td></tr></table>

Table 5: Presentation Evaluation Questions

<table><tr><td>ID</td><td>Feedback</td></tr><tr><td>1</td><td>Please rewrite this so the language is clearer and more straightforward, suitable for a reader with no prior knowledge.</td></tr><tr><td>2</td><td>Whenever you introduce a technical concept, add a simple and real-world analogy to illustrate it.</td></tr><tr><td>3</td><td>Standardize heading levels and naming so similar sections use parallel phrasing (e.g., &#x27;Approach&#x27;, &#x27;Results&#x27;, &#x27;Limitations&#x27;).</td></tr><tr><td>4</td><td>Make sure that each section ends with a short summary sentence that emphasizes the main takeaway.</td></tr><tr><td>5</td><td>Add a concise TL;DR at the beginning of the report that states the main question and key takeaways from the report.</td></tr><tr><td>6</td><td>It would help if the report indicated which parts are essential reading and which parts are optional background.</td></tr><tr><td>7</td><td>Highlight key sentences or phrases (e.g., with bold) so I can quickly find the most important take-aways.</td></tr><tr><td>8</td><td>Please add short &#x27;section previews&#x27; at the start of each main section, summarizing in 1–2 lines what will be covered.</td></tr><tr><td>9</td><td>Please keep the core sections concise and move extended explanations, detailed justifications, and long background passages into clearly labeled &#x27;Appendix&#x27; sections at the end.</td></tr><tr><td>10</td><td>Consider adding transition sentences between sections to show how each part connects to the next.</td></tr><tr><td>11</td><td>Add subheadings every 2-3 paragraphs to help readers navigate and find information quickly.</td></tr><tr><td>12</td><td>Include a glossary of key terms at the end for readers who want quick reference.</td></tr><tr><td>13</td><td>Consider using bullet points or numbered lists when presenting multiple related items rather than embedding them in prose.</td></tr><tr><td>14</td><td>Add visual breaks like pull quotes to highlight critical insights so that it&#x27;s easier to find takeaways.</td></tr><tr><td>15</td><td>Apply bold formatting to critical findings, main conclusions, and essential terms on first mention, while using italics for secondary emphasis, technical terms in context, or when citing specific examples.</td></tr><tr><td>16</td><td>Add a &quot;How to Read This Report&quot; section that explains the document&#x27;s structure and what different readers should focus on.</td></tr><tr><td>17</td><td>Vary sentence length and structure to maintain reader interest and create rhythm.</td></tr><tr><td>18</td><td>Use &quot;we&quot; as much as possible than &quot;you&quot; or third-person pronouns to create connection with readers rather than maintaining complete detachment.</td></tr><tr><td>19</td><td>Add a brief &quot;Why This Matters&quot; box at the start of technical sections to motivate readers.</td></tr><tr><td>20</td><td>Close with actionable next steps or recommendations for related information so readers know what to do or read next.</td></tr><tr><td>21</td><td>Create a separate &quot;Frequently Asked Questions&quot; section to address common points of confusion.</td></tr></table>

Table 6: 21 Seed Format Feedback Pieces in MR DRE.

<table><tr><td></td><td>Content</td><td>Format</td></tr><tr><td>Naturalness</td><td>100%</td><td>100%</td></tr><tr><td>Draft-specificness</td><td>92%</td><td>90%</td></tr><tr><td>Actionability</td><td>98%</td><td>98%</td></tr><tr><td>Content-preserving</td><td>-</td><td>100%</td></tr><tr><td>Agreement Rate</td><td>98%</td><td>96%</td></tr></table>

Table 7: Human verification results of simulated feedback quality.

<table><tr><td rowspan="2">Agent</td><td rowspan="2">Setting</td><td colspan="4">ResearchRubrics</td><td colspan="4">RigorousBench</td><td colspan="4">ResearcherBench</td><td colspan="4">Avg</td></tr><tr><td>|E|</td><td> $\mathcal{E}_{\text{cited}}$ </td><td> $\mathcal{S}$ </td><td>|U|</td><td>|E|</td><td> $\mathcal{E}_{\text{cited}}$ </td><td> $\mathcal{S}$ </td><td>|U|</td><td>|E|</td><td> $\mathcal{E}_{\text{cited}}$ </td><td> $\mathcal{S}$ </td><td>|U|</td><td>|E|</td><td> $\mathcal{E}_{\text{cited}}$ </td><td> $\mathcal{S}$ </td><td> $\mathcal{U}$ </td></tr><tr><td rowspan="4">OpenAI DR</td><td>Init</td><td>73.3</td><td>29.5</td><td>20.4</td><td>15.1</td><td>73.8</td><td>36.1</td><td>23.7</td><td>19.1</td><td>44.8</td><td>22.2</td><td>17.7</td><td>11.4</td><td>64.0</td><td>29.3</td><td>20.6</td><td>15.2</td></tr><tr><td>Reflect</td><td>-2.8</td><td>-8.3</td><td>-6.8</td><td>-2.6</td><td>-2.4</td><td>-4.6</td><td>-3.8</td><td>-1.2</td><td>-0.5</td><td>-3.2</td><td>-2.8</td><td>-3.3</td><td>-1.9</td><td>-5.3</td><td>-4.5</td><td>-2.4</td></tr><tr><td>Content $_1$ </td><td>-7.2</td><td>-6.1</td><td>-8.3</td><td>-7.2</td><td>-11.6</td><td>-7.1</td><td>-11.3</td><td>-8.0</td><td>-6.8</td><td>-5.8</td><td>-7.9</td><td>-4.7</td><td>-8.5</td><td>-6.3</td><td>-9.2</td><td>-6.6</td></tr><tr><td>Format</td><td>+2.4</td><td>-8.6</td><td>-9.6</td><td>-7.2</td><td>-4.9</td><td>-7.5</td><td>-8.0</td><td>-9.2</td><td>-0.9</td><td>-3.2</td><td>-4.4</td><td>-3.7</td><td>-1.1</td><td>-6.4</td><td>-7.3</td><td>-6.7</td></tr><tr><td rowspan="4">Sonar DR</td><td>Init</td><td>148.5</td><td>116.5</td><td>85.1</td><td>30.1</td><td>162.8</td><td>136.6</td><td>105.5</td><td>33.4</td><td>148.0</td><td>124.2</td><td>98.4</td><td>32.3</td><td>153.1</td><td>125.8</td><td>96.4</td><td>31.9</td></tr><tr><td>Reflect</td><td>-22.0</td><td>-95.2</td><td>-74.9</td><td>-21.5</td><td>-25.3</td><td>-107</td><td>-92.4</td><td>-22.6</td><td>-43.8</td><td>-106</td><td>-93.6</td><td>-25.6</td><td>-30.4</td><td>-101</td><td>-87.0</td><td>-23.2</td></tr><tr><td>Content $_1$ </td><td>+0.2</td><td>-1.0</td><td>-28.9</td><td>-3.2</td><td>-25.7</td><td>-31.6</td><td>-49.0</td><td>-7.5</td><td>+3.2</td><td>+9.6</td><td>-10.2</td><td>-0.3</td><td>-7.4</td><td>-7.7</td><td>-29.4</td><td>-3.6</td></tr><tr><td>Format</td><td>-30.6</td><td>-35.0</td><td>-51.0</td><td>-9.8</td><td>-40.5</td><td>-46.7</td><td>-62.6</td><td>-8.6</td><td>-24.0</td><td>-26.6</td><td>-48.6</td><td>-4.7</td><td>-31.7</td><td>-36.1</td><td>-54.0</td><td>-7.7</td></tr><tr><td rowspan="4">LC ODR</td><td>Init</td><td>64.3</td><td>33.7</td><td>24.6</td><td>16.3</td><td>61.4</td><td>36.5</td><td>26.8</td><td>19.1</td><td>60.4</td><td>37.0</td><td>30.4</td><td>19.6</td><td>62.0</td><td>35.7</td><td>27.3</td><td>18.3</td></tr><tr><td>Reflect</td><td>+10.5</td><td>+4.4</td><td>+1.2</td><td>+2.3</td><td>+11.6</td><td>+8.6</td><td>+5.4</td><td>+1.9</td><td>+9.6</td><td>+1.4</td><td>-1.7</td><td>-1.3</td><td>+10.6</td><td>+4.8</td><td>+1.7</td><td>+0.9</td></tr><tr><td>Content $_1$ </td><td>+1.8</td><td>-4.4</td><td>-4.3</td><td>-3.5</td><td>+0.2</td><td>-2.9</td><td>-3.8</td><td>-3.5</td><td>+2.7</td><td>-9.2</td><td>-10.2</td><td>-5.9</td><td>+1.6</td><td>-5.5</td><td>-6.1</td><td>-4.3</td></tr><tr><td>Format</td><td>+1.6</td><td>-1.2</td><td>+0.3</td><td>-1.2</td><td>+3.2</td><td>-3.6</td><td>-3.2</td><td>-3.7</td><td>-0.1</td><td>-8.9</td><td>-9.0</td><td>-3.1</td><td>+1.6</td><td>-4.6</td><td>-3.9</td><td>-2.6</td></tr><tr><td rowspan="4">DR Tulu</td><td>Init</td><td>93.7</td><td>65.8</td><td>43.2</td><td>18.6</td><td>89.4</td><td>68.5</td><td>42.5</td><td>19.1</td><td>70.2</td><td>54.3</td><td>43.2</td><td>18.5</td><td>84.5</td><td>62.9</td><td>43.0</td><td>18.7</td></tr><tr><td>Reflect</td><td>-1.7</td><td>+0.9</td><td>-1.3</td><td>+0.0</td><td>+0.4</td><td>+1.6</td><td>+0.3</td><td>+0.4</td><td>-2.2</td><td>-2.5</td><td>-4.0</td><td>-1.7</td><td>-1.2</td><td>+0.0</td><td>-1.6</td><td>-0.4</td></tr><tr><td>Content $_1$ </td><td>+1.0</td><td>+2.9</td><td>-0.9</td><td>+2.7</td><td>+1.4</td><td>+3.9</td><td>-0.5</td><td>+5.3</td><td>+5.9</td><td>+1.9</td><td>-0.5</td><td>+3.2</td><td>+2.8</td><td>+2.9</td><td>-0.6</td><td>+3.8</td></tr><tr><td>Format</td><td>-0.6</td><td>+3.9</td><td>+2.9</td><td>+0.4</td><td>+4.0</td><td>+6.3</td><td>+5.1</td><td>+2.1</td><td>-0.7</td><td>-0.4</td><td>-2.4</td><td>-1.0</td><td>+0.9</td><td>+3.3</td><td>+1.8</td><td>+0.5</td></tr></table>

Table 8: Full Citation-related Results. For each dataset, we report the average number of extracted claims (|E|), claims with at least one citation $( | \mathcal { E } _ { \mathrm { c i t e d } } | )$ , supported claims $( | \breve { S } | )$ , and citation counts (|U|). Avg is the four counts averaged across all samples in three datasets.

<table><tr><td>Feedback type</td><td>Feedback example</td></tr><tr><td>Format</td><td>Including a glossary of key terms at the end of the report would greatly benefit beginners by providing a quick reference to important concepts like forward propagation, backpropagation, and optimization methods, helping to reinforce understanding as they read through the material.</td></tr><tr><td>Format</td><td>Consider applying bold formatting to key technical terms, main product features, and critical advantages when they first appear, while using italics for secondary details like specific APIs or model names; this will help readers quickly identify the most important information and improve overall readability.</td></tr><tr><td>Content1</td><td>Thanks for covering the MYC pathway—it&#x27;s a great start! To make the overview stronger, could you also include how NELF-E affects other important genes or pathways like BRCA1, RAD51, or its role in promoter-proximal pausing in HCC? That would really round out the explanation.</td></tr><tr><td>Content1</td><td>Hey, could you add a part explaining how S1 shows that smaller, high-quality datasets can match the performance of much larger ones? Right now, it mostly talks about large-scale data but misses that important insight about data quality over quantity.</td></tr><tr><td>Content3</td><td>Hey, the report would be way stronger if it included a clear marketing strategy covering at least four channels like social media influencers, local events, digital ads, and food delivery promos, with a quick note on how each helps build the brand. Also, it&#x27;s important to add staffing details for each concept—like specific roles needed for the food truck, fine dining, and fast casual spots—so we get a better sense of the team structure. Lastly, while naming a couple of design firms was helpful, including their contact info and some rough cost estimates would make it easier to move forward and compare options.</td></tr></table>

Table 9: Format and Content feedback examples. We show representative format feedback and content feedback with one or three targets.

![](images/8ebcc48c7877d547dcb097edc1a439b2b59e90600c4a4474a4dac13886df2593.jpg)  
Figure 9: Citation Degradation Example. After revision, the model reduces the number of citations and omits in-context citations from the original response.

![](images/fa9701017509ff45063a058444338960248b0eeb0818a8fd5d1b9d23737e110b.jpg)  
Figure 10: Example of missing content. The revised response preserves the overall narrative but omits the final paragraph from the original.

![](images/1f7a90c134b368e4e02e58c06779b36c647d69acc4497116b2c0d6a113b6f781.jpg)  
Figure 11: Content feedback Simulation System Prompt.

![](images/fddf26f7b28fa407bf38f7a1465ae4046ece558ccfb9b1b867dfdb91ad8ed050.jpg)  
Figure 12: Content<sub>k</sub> feedback Simulation System Prompt.

![](images/85a129af945894c85e0e6df20d9bd01e28db8489b9f136391226a46c9c39c2d9.jpg)  
Figure 13: Format feedback Simulation System Prompt.

![](images/6306915dd69f16a1b3290b85327bd288a0c0f1df25274148c8e6097946fb6b3c.jpg)  
Figure 14: Checklist Evaluation System Prompt

![](images/a6f11a78996d2f701928b8590a40247e3506a6445dd16fb7ec4974b3d44f164c.jpg)  
Figure 15: Checklist Evaluation User Prompt.

![](images/de8d53725e58e4629f3fba8653ee49183211d2a167115234ab30cd57e419cdb2.jpg)  
Figure 16: Rubric Evaluation System Prompt.

![](images/07cb150103a4b84a74d662f0ae88db4b477a5b85d7eb20b1edf0100519455610.jpg)  
Figure 17: Rubric Evaluation User Prompt.

![](images/e6c49c641d5e37b27fa068875a5be3eff11db2e683528ac25df705fec4fa5aa5.jpg)  
Figure 18: Claim Extraction System Prompt.

![](images/07a8786d586da680e3bf9d9e824779cd71ce1c5b654f265c9246289517ed655b.jpg)  
Figure 19: Claim Extraction User Prompt.

![](images/d4051df86c4b091f716b8716c9f9a9f702079ea4f4a12a8f07dea2f637349659.jpg)  
Figure 20: Claim Supportedness Judge System Prompt

![](images/8ecbda5a0d9fdf55161739b1f175c73429884ce16a7bdfd55ec7fd072ece4f90.jpg)  
Figure 21: Claim Supportedness Judge User Prompt.

![](images/d5fa3b3361066533f657d60cafee0da6a6e32b0c45c0111bec8d156c9dee17a1.jpg)  
Figure 22: URL Content Summarization System Prompt

![](images/558839c8b701ba0223ed03d421eff027a86bc16de0ca0079f192f155a82c25a6.jpg)  
Figure 23: URL Content Summarization User Prompt.

![](images/a47e03ceb271ae2b8ea14cf22fcf34b654f7675b34fe1bf9772a520b492e75b4.jpg)  
Figure 24: Pairwise Format Feedback Judge System Prompt.

![](images/6fa0f35b95894f8ec092ef7a8bda1071746c89e359f26d53fe9d41fba356e0da.jpg)  
Figure 25: Pairwise Format Feedback Judge User Prompt.

![](images/0d562e32affe51c1e0bb8ac5e41fe2db4a9786b5dc265db8dc1524048b8a5124.jpg)  
Figure 26: Prompt Engineering System Prompt.

![](images/492a4f40b25ddacbbc5631cde85510efd8ac26e854513f8920b5e2c2d2281d12.jpg)

Figure 27: Prompt Engineering Hard-coded Constraint Suffix.  
![](images/fe841598d375a392fe750bb6cfff9174e09dec4ad614a565516da8b022b0ba85.jpg)  
Figure 28: Reviser Subagent System Prompt.

![](images/ac8a9c2bdcd20e146ffc2a5d746c942b34279a2ec0b6ed9a345a1cba47121779.jpg)  
Figure 29: Reviser Subagent User Prompt.