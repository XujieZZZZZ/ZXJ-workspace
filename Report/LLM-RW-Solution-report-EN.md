# Semantic Distribution of LLM-Generated Related Work and Solution Execution Results


---

## 1. Core Conclusions

1. **LLM-generated related work and human related work are a "sparse sampling of the same region" in semantic space, not two separate regions.** The set-centroid cosine is 0.982, and affinity to the Observation is 0.865 (H) vs 0.869 (L) — nearly identical; but the volume is only 0.23× that of humans (7–8 per paper vs 36), and strict same-title overlap is only 5.6%.
2. **The bias is systematic**: the median citation count of LLM-selected works is **6.3×** that of humans (902 vs 144), the share of works from the last 3 years is 41.5% vs 28.8%, and the within-paper publication-year span is 9.5 years vs 31.0 years. It picks **highly-cited classics + recent hotspots**, skipping the middle band and the long tail.
3. **This distribution characteristic directly explains the Solution performance later**: the LLM's idea is assembled from **mature mechanism templates** inside the correct method space (which is exactly how its two winning cases won), but it carries no "quantitative facts about this system" — 0/80 claims contain any number, and coverage reaches only 24.1% of human atomic assertions.
4. **Of the 5 runnable tasks tested: 1 true win, 1 metric win, 3 true losses.** cloudcast is a structural true win (rewrites the objective function, cost −23%); llm_sql's score margin comes 100% from the runtime term, with its hit rate actually 1.7pp lower; prism/txn/cant-be-late are genuinely worse than seed, and two of them have large margins from the same mechanism — surrogate objective / parameter assumptions inconsistent with the real system. **The same-protocol comparison against the human solutions (§3.4): 1 true win (cloudcast, cost −39%, cheaper than the LLM), 1 tie (llm_sql), 1 wash (cant-be-late), 2 true losses (prism −10%, txn −16%); human vs LLM is 3 wins to 2. A third side (§3.5, the LLM's input replaced by the human-written related work): 1 true win (cloudcast, cost −37.9%, the only LLM run that gets close to the human), 1 tie (txn), 3 true losses; 3 wins to 2 against the LLM-with-its-own-related-work side, 2 wins to 3 against the paper-side human solution.** Taken together, the three sides show that the outcome depends on **how well the surrogate objective aligns with the real cost function**, not on whether a human or a model produced the solution — the only large win shared by all three sides uses the same mechanism (a shared-edge multicast tree that directly matches the evaluator's billing model), while all three sides lose on prism, two of them by departing from the same min-max objective in **opposite directions**.
5. **The common root cause of failure is not "not understanding the problem" but "surrogate-objective mismatch"**: all three negative cases build a self-consistent mechanism narrative on a surrogate quantity that does not correspond to the real cost function. The LLM's idea is **correct at the semantic layer and not closed-loop at the numerical/causal layer**.

---

## 2. Semantic Distribution of LLM-Generated Related Work vs Human Distribution

### 2.1 Figures and Reading Convention (Per Paper, 8 Figures)

Encoding: SPECTER2 (specter2_base) 768-dim → t-SNE (a SciBERT batch is also included, with consistent conclusions).

This section **does not use an "all 8 papers on one overview" figure**: squeezing 8 papers onto a single canvas only shows that "the broad directions agree" and hides "which paper's sampling is sparser and which paper's two sides actually overlap". **The per-paper figures are what discriminates**, so they are grouped below **by the execution verdict from Part 3** — exactly the information a combined figure cannot carry.

Reading convention (identical across all 8 figures): **blue circle = cited by humans only; orange circle = cited by the LLM (with search) only; green square = cited by both sides as the same paper (matched by DOI/S2ID, one square per paper); gold ★ = that paper's Observation anchor (where "the problem itself" sits in semantic space)**. Coordinates have no absolute meaning, only relative proximity; the n in each legend is that figure's point count.

#### ① The two wins / ties

![works semantic space - Cloudcast](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_Cloudcast.png)

![works semantic space - LLM-SQL](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_LLM-SQL.png)

- **Cloudcast** (human 26 / LLM 4 / same paper both sides 3): all 4 orange points sit in the **middle** of the human cloud, with the 3 green squares in the same patch; ★ floats alone at the far left of the canvas — there is an empty gap between the problem itself (bulk replication) and the main body of cited work. The two clouds are co-located; the LLM simply picked 4 works out of it.
- **LLM-SQL** (16 / 5 / 2): the human points form an upper and a lower band; of the 5 orange points, 1 is at the top-left of the upper band, 2 are at the bottom-right of the lower band, and the rest scatter mid-right. **Of the 8 figures, this is the one where the orange points least cluster toward the density center**; its 2 green squares fall mid-canvas.

#### ② The three losses

![works semantic space - Prism](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_Prism.png)

![works semantic space - TXN](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_TXN.png)

![works semantic space - Can't-Be-Late](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_Cant-Be-Late.png)

- **Prism** (34 / 4 / 3): the human points form two very tight clumps, plus 1 blue point isolated at the top-right and 1 at the bottom-left; all 4 orange points are **embedded inside the two clumps**, the 3 green squares gather in the upper clump, and ★ hugs the lower clump's edge — **the closest alignment between the problem and the cited works across all 8 figures**, and it still loses to seed.
- **TXN** (79 / 8 / 1): the largest human set, spread over three blocks; only 8 orange points, 5 of them crowded into the upper-left block right next to ★ and the single green square, with the other 3 scattered in the middle/lower blocks. **The human-only mass sits mainly in the middle and lower blocks — precisely where orange points are scarcest.**
- **Can't-Be-Late** (25 / 4 / 0): **the only figure with zero overlap**, so it has no green square; 29 points are crammed into one small cluster (this paper's related work is highly homogeneous), ★ sits at the cluster's lower edge, and 1 blue point at the top-right plus 1 at the bottom-left float alone outside it.

#### ③ The three with no ADRS task, not executed

![works semantic space - Telemetry](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_Telemetry.png)

![works semantic space - NS3](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_NS3.png)

![works semantic space - MAS](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_MAS.png)

- **Telemetry** (15 / 11 / 1): **the most balanced figure by volume** (11 vs 15); the orange points are not scattered at the fringe but run as a vertical column through the middle of the human cloud.
- **NS3** (23 / 3 / 4): **the highest same-paper overlap** (4 green squares); but the points split into a left and a right island, and 3 of the 4 green squares are on the right island (the one containing ★) while the left island has only 1; the 3 orange points are split too (2 left, 1 right).
- **MAS** (54 / 10 / 2): **the most spread-out human cloud** (54 points across the whole canvas, clearly in an upper and a lower sheet); the 10 orange points appear in both sheets at roughly 1/5 the human density.

#### Per-Paper Counts

| Paper | Verdict | Human works | LLM works | LLM/Human | Same paper both sides |
|---|---|---:|---:|---:|---:|
| Cloudcast | ✅ Win | 29 | 7 | 0.24× | 3 |
| LLM-SQL | ✅ Win (metric) | 18 | 7 | 0.39× | 2 |
| Prism | ❌ Loss | 37 | 7 | 0.19× | 3 |
| TXN | ❌ Loss | 80 | 9 | 0.11× | 1 |
| Can't-Be-Late | ❌ Loss | 25 | 4 | 0.16× | 0 |
| Telemetry | — no task | 16 | 12 | 0.75× | 1 |
| NS3 | — no task | 27 | 7 | 0.26× | 4 |
| MAS | — incomplete env | 56 | 12 | 0.21× | 2 |
| **Total** | | **288** | **65** | **0.23×** | **16** |

**Conclusion (consistent across all 8 figures): in every figure the orange points (LLM) are interleaved with the blue points (human) in the same region and both surround the ★ (Observation) — the distributions are aligned and co-located, and there is no case of "the LLM drifting to another topic".** What differs between papers is not direction but **density and selection**: orange points fall near the density center of the human cloud, while the points humans extend toward the long tail (Prism's top-right/bottom-left, Can't-Be-Late's top-right/bottom-left, TXN's middle/lower blocks, LLM-SQL's upper band) have no counterpart. The volume ratio swings widely, from 0.11× to 0.75×, and the measured verdicts do not track that ratio (LLM-SQL at 0.39× won; Prism at 0.19× and TXN at 0.11× lost) — which shows that **winning depends not on how many works were cited but on whether the borrowed mechanisms match the real cost function (see Part 3).**

### 2.2 Three Levels of Relationship

| Level | Metric | Human | LLM(with search) | Relationship |
|---|---|---:|---:|---|
| **Direction (spatial position)** | Set-centroid cosine | — | **0.982** | Highly aligned |
| | Observation affinity Rel | 0.865 | 0.869 | Nearly identical |
| | Internal cohesion (intra-set cosine) | 0.856 | 0.870 | Comparable (LLM slightly tighter) |
| **Density (coverage)** | Works per paper | 36.0 (288/8) | 8.1 (65/8) | **0.23×** |
| | Strict same-title overlap | 16 work instances: 5.6% recall on the human side, 24.6% precision on the LLM side | | Sparse sampling |
| | Three-level matching (incl. near-title/semantic) | Recall 15.7% / Precision 60.8% / Jaccard 0.140 | | Omission ≠ off-topic |
| **Time** | Median publication year | 2018 | 2016 | Distribution gap W1 = **2.19 years** |
| | Share from the last 3 years | 28.8% | **41.5%** | LLM skews newer |
| | Within-paper publication-year span | 31.0 years | **9.5 years** | LLM takes only a narrow window |
| **Impact** | Median citation count | 144 | **902 (6.3×)** | Strong preference for classics |
| | Share with ≥1000 citations | 16% | 44% | |
| | Share with <50 citations | 26% | 2% | Almost never cites obscure work |

### 2.3 Corroboration from the Data (`merged_llm_re_withsearch` vs `human_data`, all 8 papers checked item by item)

| Dimension | Human | LLM | Ratio / Note |
|---|---:|---:|---|
| claims (sentences) | 200 | 80 | 0.40× |
| works (deduplicated within document) | 288 | 65 | **0.23×** |
| Related-work paragraphs | 68 | 32 | 0.47× |
| Verbatim-identical claims | — | **0/80** | No copying; 2-gram Jaccard only 0.035 |
| Mean claim length (words) | 20.8 | 27.9 | 1.34× (longer, more uniform sentences) |
| Vocabulary richness at equal token budget | — | — | **±2%, no difference** (not "vocabulary poverty") |
| Claim text per cited work | 0.69 claims/work | 1.23 claims/work | 1.8× (says more, cites less) |
| Claims containing a number | 8.0% | **0%** | Directional assertions only, no checkable facts |
| Share of claims naming a cited system | 81.5% | 73.8% | More abstract phrasing |
| Venue-set Jaccard | — | — | 0.145 (99 human vs 27 LLM) |
| Unresolvable on Semantic Scholar | 8.0% | 18.8% | All 12 spot-checked works really exist; a retrieval/API failure, **not fabrication** |

**Key property: the LLM writes a "different related work", not a paraphrase of the human one.** The 16 overlapping work instances, the 0/80 verbatim or near-synonymous claims, and the 0.145 venue Jaccard jointly establish this; but the "difference" happens **on the same semantic manifold** — same direction, different density and selection preference.

### 2.4 Implications for Using LLMs for Idea / Algorithm Generation

| Observation | Implication for idea/algorithm generation |
|---|---|
| Centroid cosine 0.982, Rel on par with humans | **Reliable localization**: the LLM accurately identifies the "method community" the problem belongs to. Ideas do not drift into unrelated fields. |
| Prefers highly-cited classics (6.3×) + recent hotspots, skips the middle band and the long tail | **Mechanisms come from "mature templates", not "long-tail combinations"**. Upside: the proposed mechanisms have abundant precedent, so feasibility has a floor; cost: novelty comes from cross-domain transplantation, not deep domain mining. |
| Publication-year span 9.5 years (humans 31) | **Lacks historical depth**: it does not build a logically connected lineage of the field and cannot deeply understand the domain background |
| 0/80 contain a number, covers only 24.1% of human atomic assertions | **Direction only, no checkable facts**. Assertions at the idea level cannot self-verify and must be eliminated by downstream measurement. |
| Search gives no gain (hallucination/unresolvable rate 18.5% vs 13.3% with search disabled), and related-work quality defects **do not propagate** to solution quality (all 6 Spearman correlations non-significant) | **LLM idea generation does not depend on exhaustive literature**; it relies on the method-template library in its parametric knowledge. Related work acts more like "argumentation material" than "reasoning evidence". |

> Summary: **the alignment of the related-work distribution guarantees that the idea points in the "right direction", while the distribution's sparsity and its classic/hotspot bias determine that the idea comes from a "single source" — it is an excellent method porter, not a discovery agent driven by literature review.**

---

## 3. Execution Results of LLM-Generated Solutions

8 papers → run for real with the official ADRS evaluator, without modifying any test code. **5 are testable: 1 true win, 1 metric win, 3 true losses** (the other 3: Telemetry and NS3 have no corresponding task directory in ADRS; MAS's test environment is incomplete — `evaluator.py` fails at import on the missing `taxonomy_definitions_examples/`, and it additionally depends on an external API key).

This part is **three sides under one protocol**: column 4 of the master table (§3.1) is the solution generated
with the LLM's own related work, column 5 is the same batch of LLMs with the **human-written related work** as
input (§3.5), and column 6 is the **human solution** extracted from the papers (§3.4). The program and result
directories of the three sides are `sky-discovertest/{generation_program,
generation_program_with_human_relatedworks, genration_program_human}` and `sky-discovertest/{output,
output_with_human_relatedworks, output_human}`.

### 3.1 Results Table

The "human solution" column = the score obtained by implementing the solution extracted from each paper in
`data/human_data/` (idea + implementation) against the same interface and running it on the same evaluator
(see §3.4; artifacts in `sky-discovertest/genration_program_human/` and `sky-discovertest/output_human/`).
The "LLM (human RE)" column = the LLM's solution with its **input replaced by the human-written related work**
(`data/LLM_data/merged_human_re/`), i.e. the second control in §3.5.

| Paper | Task | Metric (higher is better) | LLM solution (own RE) | LLM solution (human RE) | Human solution | seed baseline | SOTA | Verdict (LLM own RE / LLM human RE / Human) |
|---|---|---|---:|---:|---:|---:|---:|---|
| Cloudcast  | `cloudcast` | `combined_score` = 1/(1+cost) | 0.00124095 (cost \$1045.86 → \$804.83, −23%) | **0.00153675** (cost \$1045.86 → **\$649.72**, −37.9%) | **0.00156953** (cost → \$636.13, −39%) | 0.00095524 | 0.00159429 | ✅ Win / ✅ **Win** / ✅ **Win** |
| LLM-SQL | `llm_sql` | `combined_score` | **0.68783** (+2.4%; runtime 351.6 s → 21.4 s (**16×**); hit rate 0.707 → 0.690) | 0.66525 (−1.0%; runtime 351.6 s → 52.0 s; hit rate 0.707 → 0.693) | 0.67263 (+0.13%; runtime → 383.3 s; hit rate → **0.708**) | 0.67174 | 0.729 | ✅ Win / ❌ Loss / ≈ Tie |
| Prism | `prism` | `combined_score` = 1/mean(kvpr) + success_rate | **20.627** (mean kvpr 0.04787 → 0.05095, −5.8%) | 19.737 (mean kvpr 0.04787 → 0.05337, −9.8%) | 19.666 (mean kvpr → 0.05357, −10.2%) | 21.892 | 26.26 | ❌ Loss / ❌ Loss / ❌ Loss |
| TXN | `txn_scheduling` | `combined_score` = 1e6/(1+makespan) | 1718.21 (makespan **357 → 581**, +63%) | **2808.99** (makespan **357 → 355**, wash) | 2336.45 (makespan 357 → 427, +20%) | 2793.30 | 4238.6| ❌ Loss / ≈ Tie / ❌ Loss |
| Can't-Be-Late  | `cant-be-late` | `combined_score` = −(avg_cost+0.25·std) | −153.53 (average cost \$96.52 → **\$140.82**, +46%) | −142.84 (average cost \$96.52 → \$139.20, +44%) | **−107.32** (average cost \$96.52 → **\$97.16**, +0.7%) | −106.75 | -95.69 | ❌ Loss / ❌ Loss / ≈ Tie |

Summary: **LLM (own RE): 1 true win (cloudcast), 1 "metric win" (llm_sql, entirely from the runtime term),
3 true losses. LLM (human RE): 1 true win (cloudcast), 1 tie (txn), 3 true losses. Human side: 1 true win
(cloudcast, and by the widest margin), 2 ties, 2 true losses.** No side wins by tuning; the outcome tracks
whether the **real cost function** was modelled correctly: all three sides take a large win on cloudcast with a
shared-edge multicast tree, and all three lose on prism — where the human and the LLM depart from the same
min-max objective in **opposite directions** (the human's sort key multiplies by `model_size`, the LLM's divides
by it).

### 3.1.1 Why the Numbers Are What They Are (Per-Task Breakdown)

For all five tasks `combined_score` is a **nonlinear mapping** of a raw quantity, so a score gap ≠ the gap itself:

| Task | Formula form | Raw-quantity change | Score change | Amplified/compressed |
|---|---|---|---|---|
| cloudcast | 1/(1+cost), hyperbolic | Total cost 1045.86 → 804.83 (**−23.0%**) | +29.9% | Amplified |
| llm_sql | 0.95·hit + 0.05·(12−min(12,rt))/12 | hit 0.70710 → 0.69008 (**−1.7pp**); rt 70.3 s → 4.27 s | +2.4% | See below |
| prism | 1/mean(kvpr) + 1, hyperbolic | mean kvpr 0.04787 → 0.05095 (**+6.4%**) | −5.8% | Amplified (1/x² ≈ 400) |
| txn | 1e6/(1+makespan), hyperbolic | makespan 357 → 581 (**+62.8%**) | −38.5% | Compressed |
| cant-be-late | −(avg_cost + 0.25·std) | Cost 96.52 → 140.82 (**+45.9%**), std 40.92 → 50.87 | −43.9% | Near-linear |

**① Cloudcast: a structural true win.** The simulator bills by "how many partitions traverse each edge × traffic × unit price"; seed's per-destination shortest path makes the same edge pay once for every destination, whereas the LLM's multicast tree lets an edge's occurrence be shared by all downstream destinations, so cost drops directly with the degree of sharing. **It wins by rewriting the objective function, and the cost is the ground-truth value returned directly by the simulator — there is no surrogate step.**

**② LLM-SQL: this "win" comes 100% from the runtime term, and the hit rate is actually lower.**

| Component | seed | LLM | Difference |
|---|---|---|---|
| avg_hit_rate | 0.70710 | 0.69008 | **−0.01702** (×0.95 → **−0.0162**) |
| avg_runtime | 70.32 s (351.578/5) | 4.275 s (21.374/5) | 16.4× faster |
| Runtime term | **0** (70.32 > 12 s cap, truncated) | **+0.03219** | **+0.0322** |
| `combined_score` | 0.67174 | 0.68783 | +0.0161 |

The runtime term is a **cliff, not a gradient**: rt > 12 s is always 0, so seed's 70 s — 6× over the cap — necessarily scores 0, while the LLM collects the full 0.05 as long as it finishes within 12 s. **The LLM's way of winning is not "doing it better" but "doing less work"** (single-pass greedy ordering vs seed's search over an `early_stop=100000` space). Per-dataset hit rates: movies 79.40/79.41 (tie), beer 69.65/70.73 (worse), BIRD 79.59/79.49 (slightly better), PDMX **32.22/39.68 (clearly worse)**, last 84.21/84.24 (tie) — 1 clear regression, 3 ties, 1 slight gain.

**③ Prism: the gap comes from a division in one sort key.** The mean kvpr differs by only 0.00308, which the 1/x mapping amplifies into 1.264 points. The root cause is that the sort key `(req_rate/slo)/model_size` divides by an extra `model_size`, prioritizing small models, whereas the goal is min-max bin packing. The ablation isolates this single factor: switching back to seed's sort key with the same placement rule gives **22.34 (beating seed's 21.89)**; using the LLM's key gives 20.63. **The −1.26 points are entirely attributable to this one division.**

**④ TXN: makespan is the sum of 3 workloads, and the LLM loses on only two of them** (stdout `452 38 91` → 581; `252 57 48` → 357).

| workload | seed | LLM | Change |
|---|---:|---:|---|
| W1 | 252 | **452** | +79% |
| W2 | 57 | **38** | **−33% (better)** |
| W3 | 48 | **91** | +90% |
| Total | 357 | 581 | +63% |

**W1 alone accounts for 78% of the LLM's total (452/581), and W1 is exactly the case where the conflict graph degenerates into a near-complete graph** — the coloring surrogate (sum of per-class maxima) gives 1600 while the true lock-conflict simulation gives only 452; the surrogate and the ground truth differ not merely by 3.5× but also in ordering. seed greedily optimizes the true cost directly, so it is already on the "ground-truth track". Note also that this 581 **does not represent the full strength of the LLM idea**: the beam search prescribed by the solution is pruned empty on W1 (only 1 successor left per layer, dead after 26 layers), so what actually runs is DSATUR + local search — **the heaviest part of the solution never executed at all.**

**⑤ Can't-Be-Late: oscillation triggered by one parameter assumption that fails to hold.** Both components worsen — mean +45.9%, standard deviation +24.3%, the latter contributing an extra −2.5 points through the 0.25 weight (had only the mean worsened, the score would be −140.82, but it is actually −153.53). Mechanism: δ = `restart_overhead` = 72 s (fixed), τ = control period = 600 s; the solution's revoke threshold `2Rδ` and engage threshold `Rδ+Rτ` **cross when τ > δ** (600 is 8.3× 72), and the unstable interval makes the controller switch every 1–2 ticks; trace 0 has **219/313 ticks on ON_DEMAND**. After dropping the `Rτ` term (i.e. doing it the way the solution itself states, "τ is small enough that Rτ ≪ Rδ"): cost 140.82 → 106.54, score −153.53 → −116.99.

### 3.1.2 A Structural Unfairness That Must Be Stated

- **seed is a program that searches directly on that task's ground-truth cost function** (txn's seed calls the true cost directly, cbl's seed is the task's own greedy, llm_sql's seed is the original implementation), whereas **the LLM solution is generated once with zero feedback** (its input is only the Observation + related work, with no evaluator feedback and no iteration).
- The ADRS paper's results come from a "generate–evaluate–revise" loop (dozens to hundreds of iterations); this experiment is **single-shot zero-shot**.
- Hence the accurate statement is: **"the LLM's zero-shot idea versus an already hand-tuned seed: 1 true win, 1 metric win, 3 losses"**, not "the LLM cannot produce good solutions".

### 3.2 Per-Case Conclusions (LLM Analysis)

| Case | Mechanism | Why |
|---|---|---|
| Cloudcast ✅ | Restates bulk replication as **minimum-cost multicast with deadlines** (cut-constraint LP + Steiner tree + rate penalty), letting an edge's occurrence be shared by all downstream destinations | Hits the simulator's real billing model (the same edge traversed by multiple partitions is **billed repeatedly**), where per-destination shortest path is inherently disadvantaged |
| LLM-SQL ✅ | **Prefix-aware physical planner**: greedily orders columns by one-level reuse gain, and sets row order = depth-first traversal of prefix groups | Hits the real source of hit rate (KV prefix reuse), and incidentally cuts runtime to 1/16, triggering the runtime reward |
| Prism ❌ | Sort key `(req_rate/slo)/**model_size**`, with greedy placement by "lowest KVPR after placement" | Dividing by model_size prioritizes small models, which is bad for **min-max bin packing**. Ablation: switching to seed's sort key with the same placement rule gives 22.34 > seed 21.89 |
| TXN ❌ | **Graph-coloring anytime planner** with weighted DSATUR + beam search + local search | The surrogate cost (sum of per-class maxima) is almost uncorrelated with the true cost (**lock-conflict sequential simulation**, where conflicting transactions can partially overlap): W1 surrogate 1600 / true 452 |
| Can't-Be-Late ❌ | "Protected progress / fallback line" control invariant, with dual thresholds toggling ON_DEMAND/SPOT anchors | The two thresholds **cross when τ > δ**, making the state interval unstable → oscillation every 1–2 ticks, with **219/313 ticks on on-demand instances** in trace 0 (seed only uses them near the deadline) |

### 3.3 At the Method Level: Advantages and Bottlenecks of LLM Idea Generation

**Advantages (what the two wins share)**

1. **Problem restatement + cross-domain analogy**: can map a systems problem onto a mature algorithmic paradigm (multicast + cut-constraint LP, prefix-sharing planning, weighted graph coloring, control invariants), and the mapping is mathematically self-consistent.
2. **Grabbing the real source of gain**: Cloudcast identifies "edges are billed repeatedly", LLM-SQL identifies "column/row order determines KV prefix reuse" — both are the dominant term in that task's performance.
3. **Introducing structure rather than tuning**: both wins change the problem's representation (shared edges, ordering objective), not hyperparameters.

**Bottlenecks (ordered by severity; all three negative cases point to them)**

1. **Surrogate-objective mismatch (most fatal)**. What the LLM optimizes is the cost function **it narrated itself**, not the evaluator's true cost. TXN's coloring makespan is almost uncorrelated with the lock-conflict simulation; Prism's sort key points the wrong way. **It gets the problem right at the text level and builds the objective wrong at the numerical level.**
2. **Parameter/timing assumptions that fail to hold, and cannot self-check**. Can't-Be-Late's threshold crossover makes the controller oscillate at high frequency, costing +46%. The solution itself states "τ must be small enough that Rτ ≪ Rδ", but the task's control granularity is fixed at 600 s, 8× δ = 72 s — **the assumption was written down but never verified**. Dropping the Rτ term converges the cost from +46% to +10% (−153.53 → −116.99), proving the mismatch stems from the assumption rather than the logic.
3. **Internally unstable algorithms**. TXN's beam search is pruned empty by "cost lower bound + cheapest first" (measured: only 1 successor per layer, dead after 26 layers), degenerating into DSATUR + local search; during implementation it also produced `validity=0` (an incomplete partial coloring was accepted) — **the generated algorithm itself lacks termination/completeness guarantees.**
4. **Specification gaps filled in by the implementation**. Prism does not specify "which GPU to place a model on", so the implementation fills it in by "lowest pressure". Such undefined spots are a hidden source of score variance: the same idea, landed by different implementations, can cross the seed baseline.

**Unified root cause**: the LLM's idea is **correct at the semantic layer and not closed-loop at the numerical/causal layer**. It can produce a self-consistent mechanism narrative (which is why readers / LLM judges score it highly: Rubric 4.41 > human baseline 4.19), but it has no verifiable grasp of **the true cost function's shape, parameter scales, or constraint boundaries**. This is fully consistent with Part 2: its knowledge source is a **mechanism-template library** made of "highly-cited classics + recent hotspots", and templates give structure, not quantitative facts about this system.

---

### 3.4 Execution Results of the Human (Paper) Solutions — Control

The human-side solutions were run through the same protocol: take `solution.{idea,implementation}` from
`data/human_data/<pdf_id>.json`, implement it against the same interface per the uncommented half of
`sky-discovertest/README.md` (equivalent protocol to the LLM side), and evaluate with the **same evaluator and
the same commands**. Programs are in `sky-discovertest/genration_program_human/`, results in
`sky-discovertest/output_human/`; per-task detail is in that directory's `REPORT.md`. **No test code was
modified**; Telemetry / NS3 / MAS are skipped for the same reasons as before.

**One-line conclusion: on 3 of these 5 tasks the human solution's algorithm substantially coincides with the
ADRS seed** (llm_sql is the very same GGR; prism differs only in the sort key; cant-be-late is the paper's UP
while the seed is a different greedy). So its score is naturally close to seed. The real signal appears where
**the paper's method and the evaluator's ground truth disagree — which is exactly the mechanism that costs the
LLM the most points.**

#### 3.4.1 Results and Verdicts

| Task | Human solution | seed | LLM | Human vs seed | Human vs LLM |
|---|---:|---:|---:|---|---|
| cloudcast | **0.00156953** (\$636.13) | 0.00095524 | 0.00124095 | ✅ **+64.3%** (cost −39.2%) | ✅ Better |
| llm_sql | 0.67263 (hit 0.70803, 383.3 s) | 0.67174 | **0.68783** | ≈ Tie (+0.13%) | ❌ Slightly worse |
| prism | 19.666 | **21.892** | 20.627 | ❌ −10.2% | ❌ Slightly worse |
| txn_scheduling | 2336.45 (makespan 427) | **2793.30** | 1718.21 | ❌ −16.4% | ✅ Better |
| cant-be-late | −107.32 (avg \$97.16) | **−106.75** | −153.53 | ❌ 0.5% behind (wash) | ✅ **Much better** |

**Human side: 1 true win (cloudcast), 1 tie (llm_sql), 1 wash (cant-be-late), 2 true losses (prism, txn);
human vs LLM is 3 wins to 2.**

#### 3.4.2 Three Protocol Facts That Must Be Stated

1. **For llm_sql, the ADRS seed *is* the paper's own code.** The class docstring of `initial_program.py` says
   "GGR algorithm" and it implements the GGR from the solution. The two differ only in the **FD-inference term**
   that the solution states explicitly but the seed leaves off (`HITCOUNT = (len(v)² + average length of the
   FD-inferred fields over R_v)·(|R_v|−1)`; in the seed `dep_graph` is commented "NOTE: not used"). This
   implementation adds that term and switches the selection to a per-`(v, c)` scan, keeping the rest of the
   structure identical to the seed. So "human ≈ seed (+0.13%)" is a **property of the task itself**, not a
   shortcut taken by the implementation.
2. **For cant-be-late, ADRS also ships the paper's own UP code as `referenced_up.py`.** Running it through the
   same command gives **−104.94** (avg \$94.68), this implementation (strictly the solution text: a 2d safety net,
   hysteresis taking precedence over taking spot) gives −107.32, and the seed gives −106.75 — all three within a
   ±2% band, a three-way cross-check. The difference comes from two places where the solution text and the paper's
   code disagree (the code uses 1d in the safety net, and `if has_spot: return SPOT` makes the hysteresis
   ineffective). Both are reported as found, with no selective polishing.
3. **All 5 seeds "stand on the ground-truth track".** The seed is either the paper's own code (llm_sql, prism)
   or calls the environment's true cost function directly (txn's seed uses `get_opt_seq_cost`; cloudcast's seed is
   a per-destination shortest path). Both solutions — human and LLM — are **generated once with zero feedback**
   and can only use a **surrogate quantity they narrated themselves**. The accurate phrasing is therefore:
   **"the paper's method translated in one shot" against "the seed its authors already tuned": 1 win, 1 tie,
   2 losses, 1 wash.**

#### 3.4.3 The Conclusion Gets Sharper When the Two Sides Are Read Together

Side by side, winning **does not depend on whether a human or a model produced the solution, but on how well the
surrogate objective aligns with the real cost function**:

| Case | Human solution's surrogate | Distance from ground truth | LLM solution's surrogate | Distance from ground truth | Outcome |
|---|---|---|---|---|---|
| cloudcast | Egress spend on the overlay graph (exactly what the evaluator bills) | **Same quantity** | Same (multicast cuts / rate penalty) | Same quantity | **Both beat** seed |
| llm_sql | The prefix hit count (exactly what the evaluator measures) | **Same quantity** | Same | Same quantity | Human hit rate 0.708 vs LLM 0.690; the LLM collects the runtime bonus for being fast |
| prism | `Σ(req_rate·size/slo)/free memory` (evaluator uses `Σ(req_rate/slo)/free memory`) | Off by a `model_size` factor | `Σ((req_rate/slo)/size)` ordering | Off by a `/size` factor | **Both lose**, in opposite directions |
| txn | Incremental makespan over hot keys and the latest conflict per key | Keeps the real conflict structure, only truncated | "Sum of per-class maxima" | Almost uncorrelated with ground truth | Human −16%, LLM −38% |
| cant-be-late | UP's progress invariant `cp ≥ ep(t)` | Self-consistent parameters, no oracle needed | Thresholds `Rδ+Rτ` / `2Rδ` cross when τ>δ | Assumption written down but never verified | Human wash, LLM −46% |

Three conclusions can be written down directly:

1. **The human solution fails for the same reason as the LLM, only less severely.** On prism and txn the human
   also loses to seed, and for the same reason — "the paper's/model's surrogate ≠ the evaluator's ground truth"
   (prism is off by a `model_size` factor; txn replaces the true cost with a hot-key surrogate). The difference is
   magnitude: human −10%/−16% versus LLM −5.8%/−38%. **How far the surrogate is from ground truth predicts the
   score better than who wrote it.**
2. **The human solution's only large win over seed comes precisely from having no surrogate and rewriting the real
   billing structure** — cloudcast's multicast tree lets an edge occurrence be shared by downstream destinations,
   and that is exactly what the evaluator bills. This is the same mechanism by which the LLM won cloudcast; the
   human version (clustering + hop constraining + a flow-conservation MILP) simply finds a cheaper tree than the
   LLM version (a greedy Steiner tree): \$636 vs \$805.
3. **"Humans also have −39% of headroom" shows the seed is not a ceiling, but "humans also lose" shows the paper's
   method does not win automatically.** The conclusions about the LLM in Parts 2 and 3 should therefore be narrowed
   to: **the LLM's weakness is not "it cannot do research", it is "it cannot obtain this system's quantitative
   facts"** — whereas the human paper's advantage is precisely that **its authors are that system's authors**: they
   know that billing happens per edge, and they know the magnitudes of τ and δ. This is exactly §2.4's "the LLM
   covers only 24.1% of human atomic assertions, 0/80 claims contain a number" cashing out in execution results.

---

### 3.5 Execution Results of the LLM Solutions Conditioned on **Human Related Work** (second control)

One more run of the same protocol: the LLM's input is switched from "the related work it wrote itself" to the
**human-written related work** — `data/LLM_data/merged_human_re/<pdf_id>.json` (whose `related_works_source`
points at `data/human_data/`; all 8 papers' related work on the LLM side was conditioned on the human related
work). Programs live in `sky-discovertest/generation_program_with_human_relatedworks/`, results in
`sky-discovertest/output_with_human_relatedworks/`, per-task detail in that directory's `REPORT.md`.
**Same evaluator, same commands, no test code modified**; Telemetry / NS3 / MAS are skipped as before (MAS
re-checked this round: in 3 of its 4 variants `evaluator.py` fails at import on the missing
`ADRS/taxonomy_definitions_examples/`, and the only importable one, `multi_agent_evolution`, needs the
non-existent `LLM-empirical-study/example_mas/programdev` dataset and calls `gpt-4o-mini` for judging, with
`OPENAI_API_KEY` unset).

**One-line conclusion: switching to the human related work does push the LLM's output toward the human solution
(cloudcast cost \$804.83 → \$649.72, txn makespan 581 → 355), but it does not turn the LLM into the human — the
human side ties seed on both llm_sql and cant-be-late, while this side trails those two by 1.0% and 33.9%
respectively. And the *shape* of this side's failures differs from the previous round: llm_sql falls back from
"metric win" to a true loss (its hit rate is still low, and its runtime of 4.3 s → 10.4 s is no longer fast
enough), cant-be-late goes from "controller oscillating at high frequency" to "latched on on-demand at the first
preemption", and prism loses in both rounds — both LLM versions **divide** the sort key by `model_size`, departing
from the min-max objective in the same direction, whereas the human side **multiplies** by it.**

#### 3.5.1 Results and Verdicts

| Task | LLM (human RE) | seed | LLM (own RE) | Human (paper) | vs seed | vs LLM (own RE) | vs Human (paper) |
|---|---:|---:|---:|---:|---|---|---|
| cloudcast | **0.00153675** (\$649.72) | 0.00095524 | 0.00124095 | **0.00156953** | ✅ **+60.8%** (cost −37.9%) | ✅ Better | ❌ Slightly worse (−2.1%) |
| llm_sql | 0.66525 (hit 0.69325) | 0.67174 | **0.68783** | 0.67263 | ❌ −1.0% (hit −1.39pp) | ❌ Worse (on hit rate) | ❌ Slightly worse |
| prism | 19.737 | **21.892** | 20.627 | 19.666 | ❌ −9.8% | ❌ Slightly worse | ✅ Slightly better (+0.4%) |
| txn_scheduling | **2808.99** (makespan 355) | 2793.30 (357) | 1718.21 (581) | 2336.45 (427) | ≈ **Wash** (0…+0.8%) | ✅ **Much better (−39%)** | ✅ Better |
| cant-be-late | −142.84 (avg \$139.20) | **−106.75** | −153.53 | −107.32 | ❌ −33.9% (see §3.5.3) | ✅ Better | ❌ Worse |

**This side: 1 true win, 1 tie, 3 true losses; 3 wins to 2 against the LLM (own RE); 2 wins (txn, prism) to 3
against the paper-side human solution.**

#### 3.5.2 Per-Task Conclusions

| Case | Mechanism | Why |
|---|---|---|
| Cloudcast ✅ | **Tree-column LP**: a pool of candidate trees (direct multicast tree / a star through each relay region / two-hop relay with a fan-out partition / randomized greedy directed-Steiner, depth cap 3 hops) + the cheapest tree reused by every stripe | Same mechanism as the human side — it matches how the simulator actually bills (an edge traversed by several partitions is paid for once). It costs 2.1% more than the human side, and the difference is only in how the tree is solved: candidate-pool enumeration vs an exact multicast MILP |
| LLM-SQL ❌ | **Prefix layout planner**: greedy field order by shared token mass (with live-group splitting), row order = DFS of the prefix trie | The whole gap sits on PDMX (31.97 vs 39.59). The ablation shows it is **not the row order** (our rows 31.95 / full-row sort 31.97 / original rows 31.98, all but identical), nor the prefix greedy (a global greedy order is worse still, 29.47), but the solution's own last sentence: "**All remaining fields are appended after the chosen prefix fields in their original schema order**" — seed's GGR reorders the remaining columns at every recursion level, this solution only optimises the first 32 |
| Prism ❌ | **Residency utility** `U_m = (Q_m+α·pred)·priority_m/(W_m+K_m)` + spread the active models across GPUs | The ablation attributes the whole gap to one factor: with seed's sort key (`req_rate/slo`) and the same placement rule, the run **reproduces seed bit-for-bit** (21.891622105209393); the staging buffer is immaterial (19.7433 without it). The extra division by `W_m` inside `U_m` is the right key for "should this model stay resident" and the wrong key for "how do I pack so the maximum KVPR is smallest". Note the human side departs from the same objective in the **opposite direction** (multiplying by `model_size`) |
| TXN ≈ | **Conflict graph → per-component DAG longest path → NEH + iterated greedy (SA acceptance)**, `d=max(2,n/5)` | Per workload: W1 **234 vs 252**, W2 **51 vs 57** (both better), W3 **69 vs 48** (worse). The surrogate makespan takes a **max** over components (unbounded parallel workers) while the ground truth is an **additive** lock-conflict simulation, so cross-component order is invisible to the surrogate and it optimises only the largest component. Because each component still keeps the real conflict structure internally, the net result is a wash rather than a collapse (contrast the own-RE side's fully misaligned surrogate → 581) |
| Can't-Be-Late ❌ | **Failover-horizon two-mode automaton**: any spot preemption → start the on-demand tail immediately (latch) | See below |

#### 3.5.3 Two Places Where Implementing the Spec Literally Costs You (the two most valuable findings of this round)

**(1) cant-be-late: two sentences in the same solution prescribe opposite behaviour, and they are 44% apart.**

| Reading | Source text | Behaviour | avg_cost | combined |
|---|---|---|---:|---:|
| (A) primary | IMPLEMENTATION: "*if a preempted job was relying on spot, the controller **immediately starts an on-demand tail***" | any preemption → switch to on-demand and stay there | **\$139.20** | **−142.84** |
| (B) control | IDEA: "*an on-demand instance as a guaranteed tail that is **scheduled as late as possible***" | no latch; on-demand is only actually used once `T` is reached | **\$96.54** | **−106.77** |
| reference | ADRS seed | safety-line greedy | \$96.52 | −106.75 |

A 44% cost difference comes from **how one sentence is read**, and (B) is almost bit-identical to seed. This side
takes (A) as its primary result (the README requires implementing the algorithm the solution states, and the
IMPLEMENTATION section is the algorithm spec while the IDEA section is the motivation). Mechanism: the ADRS
setting is a 48 h task with a 52 h deadline and frequent spot preemptions, and the latch turns "there is no spot
in this one tick" into "everything from here on is on-demand" — `cost_std = 14.56` (seed: 40.92) is precisely the
fingerprint of that constant high price: the outcome no longer varies with trace quality. Compared with the
own-RE side's −153.53 this side is better, but it is better at "**locking in once and not moving**" (slightly
lower mean, much smaller variance) rather than at being smarter — the other one oscillates (mean 140.82, std
50.87).

**(2) llm_sql: the solution's first three modules (profiler / prefix planning / materialisation) all work; it
loses on the silence at the end of the last sentence.**

The PDMX ablation (this side's column order + various row orders): 31.95 / 31.97 / 31.98 — the row order
contributes essentially nothing; a global greedy column order is worse still at 29.47. In other words **"which
columns go into the prefix" is effective; "what happens to the rest" is where the loss is**: the solution says
"All remaining fields are appended after the chosen prefix fields in their original schema order", and those 19
columns carry a lot of shareable token mass on PDMX. seed's GGR has no such silence (it reorders the columns at
every recursion level). This is a genuine trade-off between "implement the text" and "score well", and this
implementation follows the text without altering it.

#### 3.5.4 Three Sides Side by Side: What Changing the Input Changed

| Task | seed | LLM (own RE) | LLM (human RE) | Human (paper) | Effect of the input switch |
|---|---:|---:|---:|---:|---|
| cloudcast | 0.00095524 | 0.00124095 | 0.00153675 | **0.00156953** | **Clearly better**, moving toward the human (2.1% away) |
| llm_sql | 0.67174 | **0.68783** | 0.66525 | 0.67263 | Hit rate 0.690 → 0.693 (slightly better), but runtime rises from 4.3 s to 10.4 s and the "metric win" disappears |
| prism | **21.8916** | 20.6274 | 19.7366 | 19.6662 | Slightly worse, but closer to the human |
| txn | 2793.30 | 1718.21 | **2808.99** | 2336.45 | **Much better** (+63%), and now ahead of the human |
| cant-be-late | **−106.75** | −153.53 | −142.84 | −107.32 | Better, but still below seed |

The score moved in 4 of the 5 tasks, mostly upward. But **it did not bring the LLM level with the human**: the
human side ties seed on both llm_sql and cant-be-late, while this side trails by 1.0% and 33.9% respectively.
With only 5 tasks and one generation per task, this is a directional observation, not evidence that "human
related work is worth more".

---

#### 3.5.5 Tips

1. **txn's makespan depends on wall-clock.** What the solution prescribes is a *time budget* (15 s per
   workload); the evaluator fixes the RNG with `EVAL_SEED=2026`, so the program's random draws are reproducible
   and **the only non-determinism is where the search gets cut off by the clock**: 5 reruns on an idle machine
   give 354 / 355 / 355 / 357 / 357 (median 355 → 2808.99), degrading to 365 → 2732.24 when another process
   competes for CPU. Comparisons against seed (357 → 2793.30) must be run on an idle machine.
2. **Reporting convention for the score**: txn's `makespan` is always reported as the environment's ground truth
   `Workload.get_opt_seq_cost(schedule)` (the same thing seed does); the surrogate DAG is used only for
   **ordering**, never for reporting — that evaluator does not verify the reported number and a fabricated one
   scores 1e6, which neither this implementation nor the human side does.
3. **Prism's "cold models get zero replicas" cannot be landed.** That evaluator only looks at the GPUs present in
   the returned dict, so omitting models costs nothing at all (returning `{}` also scores 1.0) and an empty GPU
   is literally KVPR = 0. Implementing the residency policy's "cold models get zero replicas" literally is exactly
   that shortcut; this implementation follows the interface semantics of "every model must be placed" instead
   (no shortcut taken), and the directory's REPORT says so.
4. **The three papers previously recorded as "no usable evaluator in ADRS" were re-verified item by item this
   round** (not carried over from the old conclusion): Telemetry/NS3 have no directory; all 4 MAS variants are
   blocked on a missing dataset / missing taxonomy / missing API key.
