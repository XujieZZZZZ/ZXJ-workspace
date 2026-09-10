# Theoretical Derivation, Literature Foundations, and Algorithmic Realization for LLM Prompt Cache Optimization via DataFrame Reordering

**Algorithm Design & Research Specification**

July 24, 2026

## Abstract

Structured tabular data serialization into natural language prompts for Large Language Model (LLM) inference often incurs significant computational redundancy during multi-row processing. By exploiting modern LLM KV Cache prefix-sharing architectures (e.g., Prompt Cache, RadixAttention), optimizing the row and column ordering of tabular inputs can dramatically increase prefix hit rates. This document details the mathematical derivation, academic literature foundations, detailed step-by-step framework, and formal pseudocode for the $NewEvolved$ optimization methodology, eliminating computational bottlenecks without requiring full dynamic programming recursion.

## 1. Problem Formulation & Mathematical Motivation

Consider a tabular dataset $\mathcal{D} \in \mathcal{X}^{N \times M}$ comprising $N$ rows and $M$ columns. During LLM batch processing or sequential row processing, each row $r_i$ ($1 \le i \le N$) is serialized into a text prompt $\mathbf{T}(r_i) = [t_{i,1}, t_{i,2}, \dots, t_{i,L_i}]$, where $t_{i,k}$ represents the $k$-th token.

Autoregressive Transformer inference computes Key-Value (KV) cache tensors for each token. When evaluating prompt $\mathbf{T}(r_i)$ sequentially after $\mathbf{T}(r_{i-1})$, the attention mechanism can reuse the cached KV states of the longest common prefix (LCP):

$$
\text{LCP}(\mathbf{T}(r_{i-1}), \mathbf{T}(r_i)) = \max \{ k \mid t_{i-1, j} = t_{i, j}, \, \forall j \le k \}
$$

The optimization target is to find a row permutation $\pi \in S_N$ and per-row column permutations $\sigma_i \in S_M$ that maximize the aggregate Prefix Hit Ratio (PHR) while minimizing the time complexity cost $T_{exec}$:

$$
\max_{\pi, \sigma_1, \dots, \sigma_N} \quad \text{Score} = \alpha \cdot \frac{\sum_{i=2}^{N} |\text{LCP}(\mathbf{T}_{\sigma_{i-1}}(r_{\pi(i-1)}), \mathbf{T}_{\sigma_i}(r_{\pi(i)}))|}{\sum_{i=1}^{N} |\mathbf{T}_{\sigma_i}(r_{\pi(i)})|} + (1 - \alpha) \cdot \text{TimeScore}(T_{exec})
$$

where $\alpha = 0.95$ balances cache hit performance against runtime overhead.

## 2. Literature Foundations & Theoretical Derivation

The design of the $NewEvolved$ algorithm derives directly from core concepts across four major research domains:

### 2.1 LLM KV Cache Sharing & Radix Trees

- **Prompt Cache (Gim et al., 2024):** Demonstrates that long prefix reusability across prompts reduces prefill time by avoiding redundant $Q \cdot K^\top$ attention score evaluations over shared prefix sequences.
- **SGLang / RadixAttention (Zheng et al., 2023/2024):** Establishes that maintaining prompt state as a Radix Trie enables $O(L)$ runtime prefix matching. Consequently, tabular data ordering must aim to construct a coherent, deep prefix tree across consecutive rows.

### 2.2 Information Theory & Entropy-Based Sorting

- **Shannon Entropy (Shannon, 1948):** High-entropy columns contain highly diverse values, whereas low-entropy columns exhibit high predictability and recurring values.
- **Derivation:** Placing low-entropy attributes at the far left of serialized prompts maximizes the probability that adjacent rows share identity across initial positions. The normalized Shannon entropy $H(C_j)$ for column $C_j$ is given by:

$$
H(C_j) = -\frac{1}{\log_2 N} \sum_{v \in V(C_j)} P(v) \log_2 (P(v) + \epsilon)
$$

### 2.3 Graph Theory & Constraint Satisfaction

- **Topological Sorting (Kahn's Algorithm, 1962):** When column ordering is constrained by asymmetric dependencies $\text{one\_way\_dep} = \{(U_k, V_k)\}$, the placement of $V_k$ before $U_k$ is invalidated. Topological sorting over the Directed Acyclic Graph (DAG) guarantees constraint compliance while preserving information-theoretic priority.

### 2.4 Sequence Alignment & Dynamic Tail Alignment

- **Local Greedy Matching vs. TSP:** Finding global optimal transitions between tail attributes resembles the Traveling Salesperson Problem (TSP). To maintain linear-logarithmic time efficiency $O(N \log N \cdot M)$, we replace exact global optimization with a dynamic local transition heuristic that matches un-clustered tail attributes dynamically to row $r_{i-1}$.

## 3. Algorithmic Logic & Realization Steps

The algorithm executes through a five-stage pipeline:

### 3.1 Phase 1: Composite Key Synthesis & Dependency Graph Construction

1. **Column Merging:** Merge specified groups in $\text{col\_merge}$ into unified atomic string attributes:

   $$
   C_{\text{merged}} = C_1 \oplus \text{`-'} \oplus C_2 \dots \oplus \text{`-'} \oplus C_k
   $$

2. **DAG Construction:** Translate explicit dependencies $\text{one\_way\_dep}$ into directed edges $(U \to V)$, where $U$ must precede $V$ in the prefix hierarchy.

### 3.2 Phase 2: High-Cardinality Filtering & Information Ranking

1. Compute cardinality ratio $\rho(C_j) = \frac{|V(C_j)|}{N}$.
2. Categorize columns into prefix candidates $\mathcal{C}_{\text{cand}}$ and tail columns $\mathcal{C}_{\text{tail}}$ using distinct value threshold $\tau_{\text{distinct}}$:

   $$
   \mathcal{C}_{\text{tail}} = \{ C_j \mid \rho(C_j) > \tau_{\text{distinct}} \}, \quad \mathcal{C}_{\text{cand}} = \mathcal{C} \setminus \mathcal{C}_{\text{tail}}
   $$

3. Compute normalized entropy $H(C_j)$ for all $C_j \in \mathcal{C}_{\text{cand}}$ and sort them in ascending order of entropy.

### 3.3 Phase 3: Constraint-Guided Topological Sorting

1. Construct adjacency graph $G = (V, E)$ from $\mathcal{C}_{\text{cand}}$ and $\text{one\_way\_dep}$.
2. Compute in-degrees $d_{in}(v)$ for each column $v \in \mathcal{C}_{\text{cand}}$.
3. Execute modified Kahn's algorithm: prioritize zero in-degree nodes based on minimum $H(C_j)$ scores to generate ordered prefix columns $\mathcal{P} = [P_1, P_2, \dots, P_k]$.

### 3.4 Phase 4: Hierarchical Prefix-Trie Row Structuring

1. Sort the rows of DataFrame $\mathcal{D}$ lexicographically using ordered prefix attributes $\mathcal{P}$ as sort keys:

   $$
   \mathcal{D}_{\text{sorted}} = \text{LexicographicalSort}(\mathcal{D}, \text{by}=\mathcal{P})
   $$

   This operation groups identical value tuples contiguously, effectively constructing a continuous left-to-right Prefix Trie across sequential rows.

### 3.5 Phase 5: Dynamic Local Tail Alignment & Chunked Parallel Execution

1. **Dynamic Tail Ordering:** For row $r_i$ ($i > 1$), divide tail columns $\mathcal{C}_{\text{tail}}$ into matching sets $\mathcal{T}_{\text{match}}^{(i)}$ and non-matching sets $\mathcal{T}_{\text{diff}}^{(i)}$ relative to $r_{i-1}$:

   $$
   \mathcal{T}_{\text{match}}^{(i)} = \{ C \in \mathcal{C}_{\text{tail}} \mid r_i[C] == r_{i-1}[C] \}
   $$

   Construct row $r_i$'s tailored column sequence: $\sigma_i = \mathcal{P} \mathbin{\Vert} \mathcal{T}_{\text{match}}^{(i)} \mathbin{\Vert} \mathcal{T}_{\text{diff}}^{(i)}$.

2. **Parallel Chunking:** For large datasets ($N \ge 1000$), partition $\mathcal{D}$ into $K$ contiguous row blocks, process stages 4–5 independently across worker threads, and aggregate the resulting sub-arrays.

## 4. Formal Pseudocode

```pseudocode
Algorithm NewEvolved: Entropy-Trie Column Reordering Framework

Require: DataFrame D ∈ X^(N×M), Dependency list dep, Merge groups merge,
         Threshold τ_distinct, Prefix limit K_stop.
Ensure:  Reordered DataFrame D^*, Per-row column ordering matrices Σ = [σ_1, ..., σ_N].

Step 1: Merge Columns
for each group g ∈ merge do
    Synthesize composite attribute C_merged in D via hyphen concatenation.
end for

Step 2: Partition Columns via Entropy & Cardinality
Initialize candidate set C_cand ← ∅, tail set C_tail ← ∅.
for each column C_j ∈ D do
    if |V(C_j)| / N > τ_distinct then
        C_tail ← C_tail ∪ {C_j}
    else
        Compute normalized entropy H(C_j) ← -1/log_2 N * Σ P(v) log_2 P(v).
        C_cand ← C_cand ∪ {C_j}
    end if
end for

Step 3: Dependency Resolution
Sort C_cand by ascending entropy H(C_j).
P ← TopologicalSort(C_cand, dep).
if K_stop is specified and K_stop < |P| then
    C_tail ← (P[K_stop:]) ∪ C_tail
    P ← P[:K_stop]
end if

Step 4: Lexicographical Prefix Sort
D_sorted ← StableSort(D, keys = P).

Step 5: Dynamic Local Transition Alignment
Initialize Σ ← [], R_out ← [].
for i = 1 to N do
    if i == 1 then
        σ_i ← P || C_tail
    else
        T_match ← { C ∈ C_tail | r_i[C] == r_{i-1}[C] }
        T_diff ← C_tail \ T_match
        σ_i ← P || T_match || T_diff
    end if
    Append row r_i[σ_i] to R_out, append σ_i to Σ.
end for

Return Reconstructed DataFrame D^* from R_out, Ordering matrix Σ.