# SpeedCast: A Cost-Aware, High-Throughput Overlay Multicast Algorithm for Bulk Cloud Data Replication

**System Architecture Design**

July 24, 2026

## 1. Algorithmic Context & Motivation

Existing cloud overlay multicast approaches (such as Cloudcast [1]) model network optimization using non-linear Integer Programming or coarse, stripe-iterative heuristics that do not scale well as the number of destination regions increases. On the other hand, graph-theoretic Directed Steiner Tree (DiST) solvers like **SpeedSteiner** [2] offer extremely fast $O(k^{1/2})$-approximation algorithms using 2-level trees (bunches), but they operate strictly on static graph edge weights and ignore:

1.  **Per-GB egress pricing structures** across heterogenous cloud boundaries (intra-cloud vs. inter-cloud).
2.  **Dynamic link capacities and VM egress/ingress constraints** under an explicit Service Level Objective (SLO) replication time budget.

To bridge this gap, we propose **SpeedCast**, a cost-aware, capacity-bounded, two-level tree multicast optimization algorithm. SpeedCast combines the speed and theoretical density-pruning mechanism of **SpeedSteiner** with the multi-cloud pricing and bandwidth elasticity models of **Cloudcast**.

## 2. Core Mathematical Formulation

### 2.1 Optimization Inputs & Constants

- **Graph Topology** $G = (V, E)$: Cloud regions as vertices $V$, directed inter-region paths as edges $E$.
- **Source & Terminals**: Source region $r \in V$, set of destination regions $T \subseteq V$ where $|T| = k$.
- **Constraints**: Data transfer size $M$ (in GB), target replication SLO budget $\Delta t$ (in seconds).
- **Pricing & Capacity Profiles**:
    - $C_{u,v}$: Egress price per GB from region $u$ to region $v$.
    - $B_{u,v}$: Bottleneck throughput profile between $u$ and $v$ (in Gbps).
    - $E_u, I_u$: Max egress and ingress bandwidth limits per VM in region $u$.
    - $P_u$: VM runtime instance cost rate (\$/second).

### 2.2 Effective Edge Cost Metric

Instead of treating path costs purely as monetary egress, SpeedCast calculates a **Time-Constrained Effective Cost** $W(u, v)$ for transferring a stripe of size $S$:

$$
W(u, v) = S \cdot C_{u,v} + \left( \frac{S}{8 \cdot B_{u,v}} \right) \cdot P_u
$$

If the required transfer rate $\frac{S}{\Delta t}$ exceeds the max capacity supported by link bandwidth $B_{u,v}$ or node egress/ingress limits ($E_u, I_v$), the edge capacity limit is enforced dynamically.

## 3. Algorithm Design: SpeedCast

SpeedCast operates by decomposing bulk data into $S_{num}$ discrete stripes and iteratively solving for a minimum-density 2-level subtree (a "bunch" rooted at $r$ via a single waypoint $v \in V$ to a subset of destination terminals $T' \subseteq T$).

It uses a **Coordinated Multi-Source Shortest Path (CMSSP)** queue across cloud providers, paired with a dynamic **Egress-Aware Density Lower Bound** to prune the search space early.

### 3.1 Density Metric

For a 2-level candidate tree $\mathcal{T}_v$ transferring data stripe $S$ through waypoint $v$ to a subset of $j$ uncovered destination terminals $T_j \subseteq T$:

$$
\text{den}(\mathcal{T}_v) = \frac{W(r, v) + \sum_{t \in T_j} W(v, t)}{|T_j|}
$$

## 4. Implementation Steps & Workflow

**Step 1: Pre-clustering & Topology Reduction**

1.  Group cloud regions with identical billing tiers and network profiles into virtual clusters (e.g., aggregating AWS European availability zones) to bound $|V| \le 20$.
2.  Partition the total transfer dataset $M$ into $S_{num}$ equal-sized stripes (e.g., $S_{num} = 8 \text{ to } 16$).

**Step 2: Coordinated Priority Queue Initialization**

1.  Maintain a global priority queue $Q$ tracking backward shortest paths $d(v, t)$ from all uncovered terminals $t \in T$ to all candidate waypoint nodes $v \in V$.
2.  Compute the single-source forward distance $d(r, v) = W(r, v)$ from the source region $r$ to all candidate waypoints $v \in V$.

**Step 3: Lazy Density-Bound Pruning Loop**

For each greedy iteration (to cover remaining terminals $T_{rem} \subseteq T$):

1.  Pop the next shortest path pair $(v, t)$ from $Q$.
2.  Append terminal $t$ to waypoint $v$'s candidate set $T_v$.
3.  Check if adding $t$ decreases the tree density $\text{den}(\mathcal{T}_v)$:
    - If yes, update $\mathcal{T}_v = \{r \to v \to T_v\}$.
    - If no, update the lower bound $\text{den}_{LB}(\mathcal{T}_v | b)$ where $b = W(v, t)$:
    
    $$
    \text{den}_{LB}(\mathcal{T}_v | b) = \frac{d(\mathcal{T}_v) + (|T_{rem}| - |T(\mathcal{T}_v)|) \cdot b}{|T_{rem}|}
    $$

4.  **Early Termination Condition**: If the density of the current best partial tree $\text{den}(\mathcal{T}_{GRD})$ satisfies:
    
    $$
    \text{den}(\mathcal{T}_{GRD}) \le \min_{u \in V} \text{den}_{LB}(\mathcal{T}_u | b)
    $$
    
    Break the queue exploration loop immediately.

**Step 4: Link Capacity Check & VM Provisioning**

1.  Validate that candidate tree $\mathcal{T}_{GRD}$ satisfies the time deadline $\Delta t$ given the aggregate VM bandwidth capacities.
2.  If link throughput limits are breached, reduce the stripe size or allocate additional parallel VMs in region $v$ up to $\text{LIMIT}_v^{VM}$.
3.  Add $\mathcal{T}_{GRD}$ to the global multicast plan and remove covered terminals $T(\mathcal{T}_{GRD})$ from $T_{rem}$.

**Step 5: Iterative Execution & Router Dispatch**

1.  Repeat Steps 2–4 until all terminals $T$ are covered ($T_{rem} = \emptyset$).
2.  Pass the generated 2-level overlay plan to the **Cloudcast Control Plane** (Provisioner) to instantiate ephemeral VMs, set up routing DAGs, and pipeline chunk transfers using LZ4 compression.

## 5. Pseudocode Implementation

```pseudocode
Algorithm SpeedCast Optimization Algorithm

Procedure SpeedCast(r, T, M, Δt, V)
    S_num ← 10
    S ← M / S_num
    T_rem ← T
    Plan ← []
    Precompute W(r, v) for all v ∈ V
    
    While |T_rem| > 0 do
        Q ← PriorityQueue()
        for each t ∈ T_rem, v ∈ V do
            cost ← ComputeEffectiveCost(v, t, S, Δt)
            Q.push((cost, v, t))
        end for
        
        T_v ← {v: [] for v ∈ V}
        den_v ← {v: ∞ for v ∈ V}
        best_tree ← Null, best_density ← ∞
        
        While Q is not empty do
            (cost, v, t) ← Q.pop()
            if t ∉ T_rem or t ∈ T_v[v] then
                continue
            end if
            
            Append t to T_v[v]
            cost_tree ← W(r, v) + sum_{t' ∈ T_v[v]} ComputeEffectiveCost(v, t', S, Δt)
            current_density ← cost_tree / |T_v[v]|
            
            if current_density < den_v[v] then
                den_v[v] ← current_density
                if current_density < best_density then
                    best_density ← current_density
                    best_tree ← (v, T_v[v])
                end if
            end if
            
            den_LB ← (cost_tree + (|T_rem| - |T_v[v]|) * cost) / |T_rem|
            if best_density ≤ den_LB then
                break // Early termination pruning
            end if
        end while
        
        (v*, T_covered) ← best_tree
        Append (v*, T_covered) to Plan
        T_rem ← T_rem \ T_covered
    end while
    return Plan
End Procedure