# Simulator Interface Guide for Multi-Cloud Data Multicasting Algorithms

## Overview

This guide provides essential constraints and best practices for generating multicast routing algorithms that work correctly with the CloudCast simulator. The simulator evaluates algorithms that construct cost-efficient multicast topologies for transferring data across multiple cloud providers and regions.

The objective is to minimize total egress cost while successfully delivering data from a source region to all destination regions.

---

## 1. Algorithm Interface Requirements

### 1.1 Function Structure

Your algorithm MUST follow this exact structure:

```python
def search_algorithm(src, dsts, G, num_partitions):
    """
    Compute a multicast topology.

    Args:
        src: Source node
        dsts: List of destination nodes
        G: Directed network graph
        num_partitions: Number of data partitions

    Returns:
        BroadCastTopology
    """
    # Your routing logic here
    return bc_topology
```

### Critical Requirements

* Function name MUST be `search_algorithm`
* MUST accept exactly four parameters:

  * `src`
  * `dsts`
  * `G`
  * `num_partitions`
* MUST return a valid `BroadCastTopology` object
* The returned topology must contain valid paths from the source to every destination

---

## 1.2 Input Parameters Explained

| Parameter        | Type       | Description                                    |
| ---------------- | ---------- | ---------------------------------------------- |
| `src`            | str        | Source region containing the data              |
| `dsts`           | list[str]  | Destination regions that must receive the data |
| `G`              | nx.DiGraph | Directed multi-cloud network graph             |
| `num_partitions` | int        | Number of data partitions (stripes)            |

---

## 1.3 Graph Structure

The graph `G` is a directed NetworkX graph.

Each edge contains:

```python
G[u][v]["cost"]
```

* Monetary egress cost

```python
G[u][v]["throughput"]
```

* Transfer throughput capacity

Example:

```python
cost = G[src][dst]["cost"]
throughput = G[src][dst]["throughput"]
```

Algorithms may use any graph-processing technique supported by NetworkX.

---

## 2. Output Constraints

The function MUST return a valid `BroadCastTopology` object.

Example:

```python
bc_topology = BroadCastTopology(
    src,
    dsts,
    num_partitions
)
```

Paths are stored per destination and per partition.

Example structure:

```python
{
    "dst_1": {
        "0": [...],
        "1": [...]
    },
    "dst_2": {
        "0": [...],
        "1": [...]
    }
}
```

---

## 2.1 Critical Output Rules

### RULE 1: Every Destination Must Be Reachable

```python
# ❌ WRONG
return BroadCastTopology(src, dsts, num_partitions)
```

without assigning any paths.

Every destination must receive a complete route originating from the source.

```python
# ✅ CORRECT
bc_topology.append_dst_partition_path(...)
```

for all destinations.

---

### RULE 2: Valid Graph Edges Only

```python
# ❌ WRONG
["nodeA", "nodeB", {}]
```

if edge does not exist in G.

All edges added to the topology must exist in the network graph.

```python
# ✅ CORRECT
[s, t, G[s][t]]
```

---

### RULE 3: Preserve Source-Destination Connectivity

Every path must form a valid sequence:

```text
src
 →
intermediate nodes
 →
destination
```

Disconnected or cyclic paths may cause simulation failures.

---

### RULE 4: Return BroadCastTopology

```python
# ❌ WRONG
return path_list
```

```python
# ❌ WRONG
return nx_graph
```

```python
# ✅ CORRECT
return bc_topology
```

The simulator expects a `BroadCastTopology` object.

---

## 3. Evaluation Metrics

The simulator evaluates algorithms across multiple cloud network configurations.

Configurations include:

```text
intra_aws
intra_azure
intra_gcp
inter_agz
inter_gaz2
```

For each configuration:

1. Generate a multicast topology.
2. Simulate data transfer.
3. Measure total egress cost.
4. Verify successful delivery.

---

### Primary Metric

The evaluator computes:

```python
cost_score = 1.0 / (1.0 + total_cost)
```

and uses:

```python
combined_score = cost_score
```

Therefore:

```text
Lower Total Cost
      ↓
Higher Score
```

---

### Success Rate

Algorithms must successfully process every benchmark configuration.

Failure of any configuration results in:

```python
combined_score = 0.0
```

and evaluation failure.

---

## 4. Recommended Algorithmic Strategies

The baseline algorithm computes an independent minimum-cost path for each destination using Dijkstra shortest-path search.

Potential improvements include:

* Shared multicast trees
* Relay-based forwarding
* Cost-aware region clustering
* Steiner-tree-inspired heuristics
* Multicast path reuse
* Cloud-provider-aware routing

Algorithms that reduce repeated use of expensive inter-cloud links generally achieve lower total cost.

---

## 5. Testing and Validation

### Baseline Test

The baseline implementation can be executed through:

```bash
python evaluator.py initial_program.py
```

### Success Criteria

Your algorithm succeeds if:

1. No Python exceptions occur.
2. A valid BroadCastTopology is returned.
3. Every destination receives all required partitions.
4. All benchmark configurations complete successfully.
5. Total egress cost is lower than the baseline.

---

## 6. Quick Checklist

Before submitting your algorithm, verify:

* [ ] Function named `search_algorithm`
* [ ] Correct signature `(src, dsts, G, num_partitions)`
* [ ] Returns a valid `BroadCastTopology`
* [ ] All destinations are reachable
* [ ] Only valid graph edges are used
* [ ] No missing partitions
* [ ] No invalid node references
* [ ] Handles all benchmark configurations
* [ ] Avoids unnecessary expensive inter-cloud transfers
* [ ] Completes within practical runtime limits
* [ ] Code remains inside the EVOLVE block boundaries
