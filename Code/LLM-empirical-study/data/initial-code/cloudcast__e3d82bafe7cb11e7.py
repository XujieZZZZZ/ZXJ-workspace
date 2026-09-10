# EVOLVE-BLOCK-START
"""Deadline-constrained minimum-cost coded multicast for one-time bulk replication.

Source
------
paper      : Cloudcast.md
pdf_id     : e3d82bafe7cb11e7
solution   : LLM-generated from the LLM's own (search-enabled) related work,
             ``data/LLM_data/merged_llm_re_withsearch/e3d82bafe7cb11e7.json``
             fields ``solution.idea`` and ``solution.implementation``.

What the LLM proposed
---------------------
Cast one-time bulk replication as a deadline-constrained, cost-minimizing
multicast on the directed overlay whose edges carry a real per-GB egress fee and
an achievable bandwidth:

  * decision variables ``r_{u,v} >= 0`` -- average coded rate on edge (u,v);
  * objective ``min Σ E(u,v) · r_{u,v}`` (per-byte egress is linear in bytes, so
    the deadline only enters through the required rate ``R = F / T``);
  * constraints: rate bound ``r_{u,v} <= B(u,v)``, per-VM egress cap
    ``Σ_v r_{u,v} <= out(u)``, and multicast cut constraints -- "every terminal
    must receive rate R" -- necessary and sufficient under random linear network
    coding, which is what makes this a *linear* program;
  * solve by cut generation on T, binary-searching T for the smallest feasible
    deadline when the requested T is too aggressive;
  * realise the rates as a store-and-forward plan over the overlay.

Fidelity note (adaptation to this benchmark)
--------------------------------------------
``search_algorithm`` must return a ``BroadCastTopology`` -- explicit edge paths
for each ``(destination, partition)`` -- so a per-edge *rate* vector has to be
projected onto a path set.  Parts of the LLM's pipeline that the interface
cannot express are not faked:

  * The cut-constrained LP is solved in its equivalent compact multi-commodity
    form (one flow per terminal, terminals sharing edge capacities, cost charged
    on the shared usage).  This is the standard equivalence for coded multicast
    -- Lun et al.'s cut formulation and the shared-capacity multi-commodity LP
    have the same optimum -- so it is a change of solver, not of the model.  The
    LLM's explicit cut generation is not reproduced.
  * The rate vector becomes paths by decomposing each terminal's flow and
    splitting that destination's partitions across the resulting paths in
    proportion to their flow.  The plan delivers ``F`` over ``T`` at rate
    ``R = F/T`` and each partition carries ``F / num_partitions``, so the split
    reproduces the LP's byte distribution up to rounding.
  * The bootstrap / token-bucket / random-linear-coding mechanics of part 3 are
    scheduling details the topology interface has no place for; only the
    resulting overlay (who sends to whom) is emitted.
  * The interface exposes no deadline and the LLM's formulation needs one.
    Following the LLM's own fallback -- "run a binary search on T to find the
    smallest feasible deadline" -- the planner uses the largest multicast rate
    the capacities allow (the tightest achievable deadline) and minimises egress
    subject to it.  A looser deadline would lower the egress term but raise the
    runtime term; see the report.
  * Per-VM aggregate caps are not observable through this interface (they live in
    the evaluator's config, not in ``G``), so only the per-edge rate bound is
    enforced here.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

FEASIBILITY_SLACK = 0.999  # stay just inside the capacity polytope
FLOW_EPS = 1e-9


class SingleDstPath(dict):
    partition: int
    edges: list  # [[src, dst, edge data]]


class BroadCastTopology:
    """Same interface as the benchmark helper, with string partition keys.

    Partition keys must be strings: the evaluator looks them up as
    ``str(partition_id)``.
    """

    def __init__(self, src, dsts, num_partitions=4, paths=None):
        self.src = src
        self.dsts = dsts
        self.num_partitions = num_partitions
        if paths is not None:
            self.paths = paths
        else:
            self.paths = {dst: {str(i): None for i in range(num_partitions)} for dst in dsts}

    def get_paths(self):
        return self.paths

    def set_num_partitions(self, num_partitions):
        self.num_partitions = num_partitions

    def set_dst_partition_paths(self, dst, partition, paths):
        self.paths[dst][str(partition)] = paths

    def append_dst_partition_path(self, dst, partition, path):
        partition = str(partition)
        if self.paths[dst][partition] is None:
            self.paths[dst][partition] = []
        self.paths[dst][partition].append(path)


def _build_problem(G):
    """Flatten the graph into a stable node/edge indexing shared by both LPs."""
    nodes = list(G.nodes())
    node_index = {n: i for i, n in enumerate(nodes)}
    edge_list = [(u, v, {"cost": d["cost"], "throughput": d["throughput"]})
                 for u, v, d in G.edges(data=True)]
    return nodes, node_index, edge_list


def _solve_flow_lp(node_index, edge_list, src, dsts, rate_or_none):
    """Solve one multicast flow LP.

    ``rate_or_none`` is ``None`` to maximise the deliverable rate, or a float to
    minimise egress cost while delivering that rate to every terminal.

    Variables are ``r^t_e`` -- terminal ``t``'s rate on edge ``e`` -- plus, when
    maximising, a trailing ``R``.  Terminals share edge capacities
    (``Σ_t r^t_e <= B_e``), which is the compact form of the LLM's cut
    constraints.
    """
    from scipy.optimize import linprog
    from scipy.sparse import csr_matrix

    n_nodes = len(node_index)
    n_terms = len(dsts)
    n_edges = len(edge_list)
    maximising = rate_or_none is None

    n_var = n_terms * n_edges + (1 if maximising else 0)
    rate_var = n_var - 1

    # --- capacity sharing -------------------------------------------------
    rows, cols, vals = [], [], []
    for e in range(n_edges):
        for t in range(n_terms):
            rows.append(e)
            cols.append(t * n_edges + e)
            vals.append(1.0)
    a_cap = csr_matrix((vals, (rows, cols)), shape=(n_edges, n_var))

    # --- flow conservation per terminal ------------------------------------
    # Net outflow is +R at the source and -R at the terminal; these must hold
    # with equality, so they go into A_eq.  (As an inequality the solver is free
    # to satisfy them by pushing flow backwards into the source instead.)
    rows, cols, vals = [], [], []
    b_eq = np.zeros(n_nodes * n_terms)
    for t in range(n_terms):
        for node in node_index:
            row = t * n_nodes + node_index[node]
            for e, (u, v, _d) in enumerate(edge_list):
                if u == node:
                    rows.append(row)
                    cols.append(t * n_edges + e)
                    vals.append(1.0)
                if v == node:
                    rows.append(row)
                    cols.append(t * n_edges + e)
                    vals.append(-1.0)
        src_row = t * n_nodes + node_index[src]
        dst_row = t * n_nodes + node_index[dsts[t]]
        if maximising:
            # net_outflow(src) - R = 0, net_outflow(terminal) + R = 0
            rows += [src_row, dst_row]
            cols += [rate_var, rate_var]
            vals += [-1.0, 1.0]
        else:
            b_eq[src_row] = rate_or_none
            b_eq[dst_row] = -rate_or_none
    a_eq = csr_matrix((vals, (rows, cols)), shape=(n_nodes * n_terms, n_var))

    a_ub = a_cap.tocsc()
    b_ub = np.array([d["throughput"] for _u, _v, d in edge_list])

    if maximising:
        obj = np.zeros(n_var)
        obj[rate_var] = -1.0
    else:
        # E(u,v) is charged on the shared per-edge usage, sum_t r^t
        obj = np.zeros(n_var)
        for e, (_u, _v, d) in enumerate(edge_list):
            for t in range(n_terms):
                obj[t * n_edges + e] = d["cost"]

    res = linprog(obj, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                  bounds=[(0.0, None)] * n_var, method="highs")
    if not res.success:
        return None
    if maximising:
        return float(-res.fun)
    return res.x[: n_terms * n_edges].reshape(n_terms, n_edges)


def _decompose(flow, src, dst, edge_list):
    """Split one terminal's flow into ``(edge chain, rate)`` pairs.

    Repeatedly walks a residual path from ``src`` to ``dst`` and takes the
    minimum residual along it, which reproduces the flow as explicit paths.
    """
    residual = {}
    for e, (u, v, _d) in enumerate(edge_list):
        if flow[e] > FLOW_EPS:
            residual[(u, v)] = flow[e]

    adjacency = {}
    for u, v, _d in edge_list:
        adjacency.setdefault(u, []).append(v)

    paths = []
    for _ in range(len(edge_list) + len(edge_list) // 2 + 8):
        parent = {src: None}
        queue = [src]
        while queue and dst not in parent:
            nxt = []
            for node in queue:
                for v in adjacency.get(node, ()):
                    if v in parent or residual.get((node, v), 0.0) <= FLOW_EPS:
                        continue
                    parent[v] = node
                    nxt.append(v)
            queue = nxt
        if dst not in parent:
            break

        chain = []
        node = dst
        while parent[node] is not None:
            chain.append((parent[node], node))
            node = parent[node]
        chain.reverse()

        bottleneck = min(residual[edge] for edge in chain)
        for edge in chain:
            residual[edge] -= bottleneck
        paths.append((chain, bottleneck))

    return paths


def _assign_partitions(path_flows, num_partitions):
    """Split ``num_partitions`` chunks across paths in proportion to their rates.

    Largest-remainder rounding, so the chunk counts sum to ``num_partitions``.
    """
    if not path_flows:
        return []
    total = sum(f for _p, f in path_flows)
    if total <= 0:
        return [path_flows[0][0]] * num_partitions

    exact = [num_partitions * f / total for _p, f in path_flows]
    counts = [int(np.floor(x)) for x in exact]
    remainder = num_partitions - sum(counts)
    order = sorted(range(len(exact)), key=lambda i: (-(exact[i] - counts[i]), i))
    for i in order[:remainder]:
        counts[i] += 1

    assignment = []
    for (chain, _f), count in zip(path_flows, counts):
        assignment.extend([chain] * count)
    return assignment


def _fallback_topology(src, dsts, G, num_partitions):
    """Cheapest-hop path per destination, used only if the LP cannot be solved.

    Keeps the returned topology structurally valid so the evaluator always gets a
    complete (source -> every destination, every partition) plan.
    """
    bc_topology = BroadCastTopology(src, dsts, num_partitions)
    h = G.copy()
    h.remove_edges_from(list(h.in_edges(src)) + list(nx.selfloop_edges(h)))
    for dst in dsts:
        path = nx.dijkstra_path(h, src, dst, weight="cost")
        edges = [[path[i], path[i + 1], G[path[i]][path[i + 1]]]
                 for i in range(len(path) - 1)]
        for partition in range(num_partitions):
            bc_topology.set_dst_partition_paths(dst, partition, edges)
    return bc_topology


def search_algorithm(src, dsts, G, num_partitions):
    """Min-cost coded multicast, realised as per-partition overlay paths."""
    _nodes, node_index, edge_list = _build_problem(G)

    peak_rate = _solve_flow_lp(node_index, edge_list, src, dsts, None)
    if not peak_rate:
        return _fallback_topology(src, dsts, G, num_partitions)

    flows = _solve_flow_lp(node_index, edge_list, src, dsts,
                           peak_rate * FEASIBILITY_SLACK)
    if flows is None:
        return _fallback_topology(src, dsts, G, num_partitions)

    bc_topology = BroadCastTopology(src, dsts, num_partitions)
    for t, dst in enumerate(dsts):
        path_flows = _decompose(flows[t], src, dst, edge_list)
        if not path_flows:
            return _fallback_topology(src, dsts, G, num_partitions)
        assignment = _assign_partitions(path_flows, num_partitions)
        if len(assignment) != num_partitions:
            assignment = (assignment + [assignment[-1]] * num_partitions)[:num_partitions]
        for partition, chain in enumerate(assignment):
            edges = [[u, v, G[u][v]] for u, v in chain]
            bc_topology.set_dst_partition_paths(dst, partition, edges)

    return bc_topology


# EVOLVE-BLOCK-END


def create_broadcast_topology(src, dsts, num_partitions=4):
    """Create a broadcast topology instance"""
    return BroadCastTopology(src, dsts, num_partitions)


def run_search_algorithm(src, dsts, G, num_partitions):
    """Run the search algorithm and return the topology"""
    return search_algorithm(src, dsts, G, num_partitions)
