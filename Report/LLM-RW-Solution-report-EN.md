# Semantic Distribution of LLM-Generated Related Work and Solution Execution Results


---

## 1. Core Conclusions

1. **LLM-generated related work and human related work are a "sparse sampling of the same region" in semantic space, not two separate regions.** The set-centroid cosine is 0.982, and affinity to the Observation is 0.865 (H) vs 0.869 (L) — nearly identical; but the volume is only 0.23× that of humans (7–8 per paper vs 36), and strict same-title overlap is only 5.6%.
2. **The bias is systematic**: the median citation count of LLM-selected works is **6.3×** that of humans (902 vs 144), the share of works from the last 3 years is 41.5% vs 28.8%, and the within-paper publication-year span is 9.5 years vs 31.0 years. It picks **highly-cited classics + recent hotspots**, skipping the middle band and the long tail.
3. **This distribution characteristic directly explains the Solution performance later**: the LLM's idea is assembled from **mature mechanism templates** inside the correct method space (which is exactly how its two winning cases won), but it carries no "quantitative facts about this system" — 0/80 claims contain any number, and coverage reaches only 24.1% of human atomic assertions.
4. **Of the 5 runnable tasks tested: 1 true win, 1 metric win, 3 true losses.** cloudcast is a structural true win (rewrites the objective function, cost −23%); llm_sql's score margin comes 100% from the runtime term, with its hit rate actually 1.7pp lower; prism/txn/cant-be-late are genuinely worse than seed, and two of them have large margins from the same mechanism — surrogate objective / parameter assumptions inconsistent with the real system.
5. **The common root cause of failure is not "not understanding the problem" but "surrogate-objective mismatch"**: all three negative cases build a self-consistent mechanism narrative on a surrogate quantity that does not correspond to the real cost function. The LLM's idea is **correct at the semantic layer and not closed-loop at the numerical/causal layer**.

---

## 2. Semantic Distribution of LLM-Generated Related Work vs Human Distribution

### 2.1 Figures and Setup

Encoding: SPECTER2 (specter2_base) 768-dim → t-SNE (a SciBERT batch is also included, with consistent conclusions). The overview figure uses an "island layout": one independent region per paper, color = paper, filled = Human, hollow = LLM (with search), ★ = Observation.

![works semantic-space overview](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_2d_overview.png)
![claims semantic-space overview](../Code/LLM-empirical-study/evaluator/outputs/visualization/claims_2d_overview.png)

**Conclusion: inside each "island", the orange points (LLM) and the blue points (Human) are interleaved in the same region, and both surround the ★ (Observation) — i.e. the distributions are aligned and co-located, and there is no phenomenon of "the LLM drifting to another topic".** The per-paper figures (`works_2d_<paper>.png` ×8) show the same thing at higher zoom: LLM points fall near the density center of the human point cloud, while human points in the long-tail directions have no counterpart.

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

Publication-year distribution figure: ![works year distribution](../Code/LLM-empirical-study/evaluator/outputs/visualization/works_time_distribution.png)

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

### 3.1 Results Table

| Paper | Task | Metric (higher is better) | LLM solution | seed baseline | SOTA | Relative change (vs seed) | Verdict |
|---|---|---|---:|---:|---:|---|---|
| Cloudcast  | `cloudcast` | `combined_score` = 1/(1+cost) | **0.00124095** | 0.00095524 | 0.00159429 | Cost \$1045.86 → **\$804.83 (−23%)** | ✅ Win |
| LLM-SQL | `llm_sql` | `combined_score` | **0.68783** | 0.67174 | 0.729 | **+2.4%**; runtime 351.6 s → 21.4 s (**16×**); hit rate 0.707 → 0.690 | ✅ Win |
| Prism | `prism` | `combined_score` = 1/mean(kvpr) + success_rate | 20.627 | 21.892 | 26.26 | mean kvpr 0.04787 → 0.05095, combined score −5.8% | ❌ Loss |
| TXN | `txn_scheduling` | `combined_score` = 1e6/(1+makespan) | 1718.21 | 2793.30 | 4238.6| makespan **357 → 581 (+63%)** | ❌ Loss |
| Can't-Be-Late  | `cant-be-late` | `combined_score` = −(avg_cost+0.25·std) | −153.53 | −106.75 | -95.69 | Average cost \$96.52 → **\$140.82 (+46%)** | ❌ Loss |

Summary: **1 true win (cloudcast), 1 "metric win" (llm_sql, entirely from the runtime term), 3 true losses.** Neither win comes from tuning; both come from introducing a new structure (shared edges, ordering objective).

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
