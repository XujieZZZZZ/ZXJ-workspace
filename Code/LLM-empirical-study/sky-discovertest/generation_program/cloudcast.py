# EVOLVE-BLOCK-START
"""
Cost-minimal coded multicast for one-time bulk replication (LLM solution for CloudCast).

The solution formulates bulk replication as a deadline-constrained, cost-minimizing
multicast on a directed overlay graph in which every edge carries the real per-GB
egress fee E(u,v) and the achievable bandwidth B(u,v):

    minimize    sum_{u,v} E(u,v) * r_{u,v}                     (egress spend, linear in
                                                                the bytes per edge)
    subject to  r_{u,v} <= B(u,v)                              (rate bound, per edge)
                sum_v r_{u,v} <= out(u)                        (per-VM egress cap)
                sum_{u in S, v not in S} r_{u,v} >= R          (multicast cut conditions,
                                                for every terminal t and every cut S
                                                that contains a seed and not t)

with R = F / T, solved by cut generation: capacities (a)-(c) first, then, whenever the
max-flow to some terminal is below R, add the violated min-cut inequality and resolve.
If no feasible plan exists, binary search T for the smallest feasible deadline.

On this task's interface one multicast "stream" is one partition of the dataset, so the
LP is realised partition by partition: the cut conditions become "each partition must be
able to reach every terminal over the selected edges" (a cut-covering support, i.e. a
Steiner arborescence from the seed region to all destinations -- network coding lets
relays recode, so one edge occurrence serves every downstream terminal instead of one
copy per terminal), the rate bound becomes a load budget k_e / B_e per edge and the
binary search on R becomes a search over how much congestion pressure is tolerated.
The seeds are the source region's parallel outgoing edges: partitions leave it over
different first hops whenever a single hop would be the bottleneck.
"""

import networkx as nx
from typing import Dict, List

# congestion pressure of the rate bound r_e <= B_e: edge weight used while choosing an
# arborescence is E(u,v) * (1 + PRESSURE * load_e / B_e); raised only when the plan
# cannot reach the deadline, i.e. the binary search over the feasible rate
PRESSURE_LADDER = [0.0, 0.05, 0.2, 1.0, 5.0]
# tolerated slowdown of the chosen plan with respect to the fastest feasible schedule
DEADLINE_SLACK = 2.0


def _usable_graph(G, src):
    """Overlay graph restricted to the priced, actually transmissible edges.

    A transfer that is impossible (no bandwidth) or unpriced cannot take part in the
    optimisation; edges into the seed region are dropped like the reference seed does.
    """
    h = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        cost = data.get("cost")
        throughput = data.get("throughput")
        if u == v or v == src:
            continue
        if cost is None or throughput is None or throughput <= 0 or cost < 0:
            continue
        h.add_edge(u, v, cost=float(cost), throughput=float(throughput))
    return h


def _relaxed_weights(h, load, pressure):
    """Edge weights of the LP objective, relaxed by the rate-bound multiplier."""
    weights = {}
    for u, v, data in h.edges(data=True):
        congested = load.get((u, v), 0.0) / data["throughput"]
        weights[(u, v)] = data["cost"] * (1.0 + pressure * congested)
    return weights


def _multicast_arborescence(h, src, dsts, weights):
    """Cut-covering support of one multicast stream: greedy Steiner arborescence.

    Repeatedly attaches the cheapest path from the current support to the nearest
    terminal that is not covered yet, then prunes everything that no terminal needs.
    """
    terminals = [d for d in dsts if d in h and nx.has_path(h, src, d)]
    if not terminals:
        return {}, set()

    selected = set()
    tree_nodes = {src}
    uncovered = set(terminals)

    while uncovered:
        dist, paths = nx.multi_source_dijkstra(
            h, tree_nodes, weight=lambda u, v, d: weights.get((u, v), float("inf")))
        target, best = None, None
        for t in uncovered:
            if t in dist and (best is None or dist[t] < best):
                target, best = t, dist[t]
        if target is None:
            break  # no remaining terminal is reachable from the seed
        path = paths[target]
        for i in range(len(path) - 1):
            selected.add((path[i], path[i + 1]))
        tree_nodes.update(path)
        uncovered.difference_update(path)  # terminals sitting on the path are covered

    # prune: keep only the edges of the cheapest routes inside the selected support
    support = h.edge_subgraph(list(selected)).copy()
    routes = {}
    for t in terminals:
        path = nx.dijkstra_path(support, src, t, weight="cost")
        for i in range(len(path) - 1):
            routes.setdefault((path[i], path[i + 1]), None)
    pruned = {e for e in selected if e in routes}
    edges = {}
    for (u, v) in pruned:
        edges[(u, v)] = h[u][v]
    return edges


def _routes(edges, src, dsts):
    """Per-terminal directed routes inside one arborescence."""
    support = nx.DiGraph()
    for (u, v), data in edges.items():
        support.add_edge(u, v, **data)
    out = {}
    for t in dsts:
        if t in support and src in support and nx.has_path(support, src, t):
            out[t] = nx.dijkstra_path(support, src, t, weight="cost")
    return out


def _fastest_units(h, src, dsts, num_partitions):
    """Fastest feasible schedule in the same (vol-normalised) units as load_e / B_e.

    One coded stream must reach every terminal, so the multicast rate is bounded by the
    smallest of the terminal min cuts; R = num_partitions / min-cut is the deadline the
    binary search of the LP converges to when the target time is too aggressive.
    """
    best = None
    for t in dsts:
        if t not in h or not nx.has_path(h, src, t):
            continue
        try:
            cut = nx.maximum_flow_value(h, src, t, capacity="throughput")
        except Exception:
            continue
        if cut <= 0:
            continue
        value = num_partitions / cut
        if best is None or value > best:
            best = value
    return best


def _assign_partitions(h, src, dsts, num_partitions, pressure):
    """Assign one arborescence to every partition while respecting the rate bounds."""
    load = {}
    plan = []
    for _ in range(num_partitions):
        weights = _relaxed_weights(h, load, pressure)
        edges = _multicast_arborescence(h, src, dsts, weights)
        if not edges:
            plan.append({})
            continue
        for e in edges:
            load[e] = load.get(e, 0.0) + 1.0
        plan.append(edges)
    return plan, load


def _plan_time(h, load):
    """Slowest edge of the plan, in load_e / B_e units (vol cancels out)."""
    time = 0.0
    for e, count in load.items():
        time = max(time, count / h[e[0]][e[1]]["throughput"])
    return time


def search_algorithm(src, dsts, G, num_partitions):
    h = _usable_graph(G, src)
    bc_topology = BroadCastTopology(src, dsts, num_partitions)

    if h.number_of_nodes() == 0:
        return bc_topology

    fastest = _fastest_units(h, src, dsts, num_partitions)
    plan = None
    for pressure in PRESSURE_LADDER:
        plan, load = _assign_partitions(h, src, dsts, num_partitions, pressure)
        if fastest is None:
            break
        if _plan_time(h, load) <= DEADLINE_SLACK * fastest:
            break

    # emit the plan: one store-and-forward route per panel (dst, partition)
    for partition, edges in enumerate(plan):
        if not edges:
            continue
        routes = _routes(edges, src, dsts)
        for dst, path in routes.items():
            for i in range(len(path) - 1):
                s, t = path[i], path[i + 1]
                bc_topology.append_dst_partition_path(dst, partition, [s, t, G[s][t]])

    return bc_topology


class SingleDstPath(Dict):
    partition: int
    edges: List[List]  # [[src, dst, edge data]]


class BroadCastTopology:
    def __init__(self, src: str, dsts: List[str], num_partitions: int = 4, paths: Dict[str, SingleDstPath] = None):
        self.src = src  # single str
        self.dsts = dsts  # list of strs
        self.num_partitions = num_partitions

        # dict(dst) --> dict(partition) --> list(nx.edges)
        # example: {dst1: {partition1: [src->node1, node1->dst1], partition 2: [src->dst1]}}
        if paths is not None:
            self.paths = paths
            self.set_graph()
        else:
            self.paths = {dst: {str(i): None for i in range(num_partitions)} for dst in dsts}

    def get_paths(self):
        print(f"now the set path is: {self.paths}")
        return self.paths

    def set_num_partitions(self, num_partitions: int):
        self.num_partitions = num_partitions

    def set_dst_partition_paths(self, dst: str, partition: int, paths: List[List]):
        """
        Set paths for partition = partition to reach dst
        """
        partition = str(partition)
        self.paths[dst][partition] = paths

    def append_dst_partition_path(self, dst: str, partition: int, path: List):
        """
        Append path for partition = partition to reach dst
        """
        partition = str(partition)
        if self.paths[dst][partition] is None:
            self.paths[dst][partition] = []
        self.paths[dst][partition].append(path)


# EVOLVE-BLOCK-END
