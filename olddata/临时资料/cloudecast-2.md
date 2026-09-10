# Cost-Gain Guided Shared Relay Multicast (CGSRM)

*A Cost-Aware Incremental Multicast Topology Construction Algorithm for Multi-Cloud Data Distribution*

---

# 1. Motivation

The baseline algorithm independently computes the shortest path from the source to every destination. Although each path is locally optimal, the overall multicast topology contains numerous duplicated expensive inter-cloud transmissions. Consequently, the same costly outgoing edge from the source (or another cloud provider) is repeatedly paid for.

SpeedSteiner demonstrates that constructing a shared multicast tree instead of independent shortest paths can significantly reduce total tree cost by maximizing path sharing. However, its recursive greedy framework is computationally expensive and does not consider heterogeneous cloud egress pricing.

Cloudcast shows that cloud multicast should exploit relay regions (overlay waypoints) to minimize inter-cloud egress costs. Nevertheless, its MILP formulation is too computationally expensive for online topology generation and unsuitable for the heuristic search required by this task.

Therefore, we design a new heuristic that combines:

- global path sharing,
- relay-based forwarding,
- cloud cost awareness,
- incremental tree optimization,

without requiring expensive optimization solvers.

The resulting algorithm is called

> **Cost-Gain Guided Shared Relay Multicast (CGSRM).**

---

# 2. Core Insight

Instead of asking

> "What is the cheapest path for one destination?"

CGSRM asks

> "Which relay node can reduce the total multicast cost for multiple destinations simultaneously?"

A relay node is valuable if:

- many destinations can be reached cheaply from it,
- reaching the relay from the current multicast tree is inexpensive,
- it replaces multiple expensive outgoing transmissions,
- adding it introduces little additional cost.

Thus, relay nodes are selected according to their **global multicast gain**, not merely their shortest-path distance.

---

# 3. Design Philosophy

CGSRM constructs the multicast topology incrementally.

Initially,

```
Tree = {Source}
```

At every iteration, the algorithm evaluates every candidate relay node and estimates how much multicast cost it can save.

The relay producing the largest **Cost-Gain Score** is merged into the multicast tree.

The process repeats until all destinations become connected.

Finally, redundant relay branches are removed through a pruning stage.

---

# 4. Algoithm Framework

CGSRM consists of five stages.

---

## Stage 1 — Global Cost Distance Computation

Compute shortest-path costs from

- Source → every node
- Every node → every destination

using Dijkstra.

Unlike the baseline, these distances are only used as estimates for topology construction instead of directly forming the multicast routes.

Output:

- Distance matrix
- Parent information for path reconstruction

---

## Stage 2 — Relay Candidate Evaluation

Every non-source node is treated as a potential relay.

For relay node r:

### Reachability Set

Find all uncovered destinations satisfying

```
Cost(r,d)
<
Cost(Tree,d)
```

where

```
Cost(Tree,d)
```

is the current minimum connection cost from the multicast tree.

These destinations are potential beneficiaries of relay r.

---

### Relay Expansion Cost

The additional cost required to connect relay r into the current multicast tree is

```
ExpansionCost(r)
```

which equals

```
minimum distance
(Tree → r)
```

rather than

```
Source → r
```

allowing relay reuse.

---

### Shared Saving

For every reachable destination

```
d
```

the relay saves

```
Saving(d,r)
=
CurrentCost(d)
-
Cost(r,d)
```

The total multicast benefit is

```
TotalSaving(r)
=
Σ Saving(d,r)
```

---

### Relay Efficiency

Instead of choosing the relay with the largest total saving,

CGSRM evaluates

```
RelayScore(r)
=
TotalSaving(r)
-------------------------
ExpansionCost(r)+ε
```

where

ε prevents division by zero.

This metric favors relay nodes with

- large shared benefit
- low expansion overhead

rather than merely minimizing local path length.

---

# Stage 3 — Incremental Shared Tree Growth

Select

```
BestRelay
=
argmax RelayScore
```

The relay is connected into the multicast tree.

Then

- all benefited destinations are attached through the relay
- covered destinations are removed
- multicast tree expands

This procedure is repeated until

```
all destinations covered
```

Unlike recursive Steiner algorithms, CGSRM only performs one greedy relay insertion per iteration, making it computationally efficient.

---

# Stage 4 — Local Topology Refinement

After all destinations are connected, the tree may contain redundant relay branches.

CGSRM performs a local refinement.

For every relay node:

temporarily remove it.

If

- all destinations remain reachable

and

```
TotalCost(new tree)
<
TotalCost(old tree)
```

the relay is permanently removed.

This produces a compact multicast topology.

---

# Stage 5 — Partition Assignment

The evaluation focuses primarily on total egress cost.

Therefore,

all partitions reuse the same optimized multicast tree.

Advantages:

- zero additional optimization cost
- guaranteed correctness
- maximum path sharing
- no duplicated expensive inter-cloud transfers

If desired, future extensions could distribute partitions across multiple relay trees.

---

# 5. Cost-Gain Metric

The key innovation is the **Cost-Gain Score**.

Instead of minimizing path length,

CGSRM maximizes

```
Shared Benefit
------------------------
Relay Expansion Cost
```

Formally,

```
Score(r)

      Σ(CurrentCost(d)-Cost(r,d))
= -----------------------------------
      ExpansionCost(r)+ε
```

A relay is selected only if

```
Score(r)>0
```

otherwise direct routing is used.

This naturally balances

- relay usefulness
- relay insertion cost
- multicast sharing

without requiring any predefined thresholds.

---

# 6. Complete Algorithm

```
Input:
    Source s
    Destinations D
    Directed graph G
    Number of partitions P

Output:
    BroadcastTopology

1. Compute shortest-path distances from the source and reverse distances to all destinations.

2. Initialize multicast tree with only the source.

3. Mark every destination as uncovered.

4. While uncovered destinations remain:

      Evaluate every node as a relay candidate.

      Compute:
          ExpansionCost
          Reachable destinations
          TotalSaving
          RelayScore

      Select the relay with the maximum positive score.

      If no relay has a positive score:
             connect the nearest uncovered destination directly.

      Otherwise:
             connect the relay to the multicast tree;
             attach all benefited destinations through the relay;
             update uncovered destinations.

5. Perform local pruning:
      remove redundant relay nodes whenever total cost decreases
      while preserving reachability.

6. Assign the optimized multicast tree to every partition.

7. Construct and return the BroadCastTopology.
```

---

# 7. Implementation Plan

1. **Graph Preprocessing**
   - Remove self-loops and incoming edges to the source.
   - Precompute shortest-path distances and predecessor information for path reconstruction.

2. **Tree Initialization**
   - Create a multicast tree containing only the source.
   - Maintain the set of uncovered destinations and the current tree nodes.

3. **Relay Candidate Scoring**
   - For each node not yet in the tree, compute:
     - minimum expansion cost from the existing tree,
     - destinations that would benefit from this relay,
     - total cost saving,
     - Cost-Gain Score.
   - Select the relay with the highest positive score.

4. **Incremental Tree Expansion**
   - Insert the selected relay and reconstruct the corresponding shortest paths.
   - Attach all destinations that benefit from this relay.
   - Update the tree structure and uncovered destination set.

5. **Fallback Strategy**
   - If no relay provides a positive gain, directly connect the nearest uncovered destination using its shortest path.

6. **Tree Refinement**
   - Iteratively remove redundant relay nodes whose removal preserves connectivity and further reduces total cost.

7. **Partition Replication**
   - Replicate the final optimized multicast tree for all partitions when constructing the `BroadCastTopology`, ensuring correctness while maximizing path sharing.