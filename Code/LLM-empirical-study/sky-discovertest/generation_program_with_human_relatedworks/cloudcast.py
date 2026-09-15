# EVOLVE-BLOCK-START
"""
Cloudcast solution generated from the *human* related-work section
(merged_human_re/e3d82bafe7cb11e7), adapted to the ADRS `search_algorithm` interface.

Solution text this file implements, verbatim where quoted:

  "Graph construction. ... Represent every VM as a node; add the destination storage endpoints as
   terminal nodes ... Build a complete directed graph among all nodes. For each directed edge
   u->v, maintain: per-GB egress price price(u,v), profiled achievable throughput bw(u,v), and
   per-VM caps egress_cap(u), ingress_cap(v)."
  "Deadline-derived capacities. For an operation deadline T seconds, convert every rate capacity
   into a volume capacity: edge_volume(u,v)=bw(u,v)*T GB; egress_volume(v)=egress_cap(v)*T GB;
   ingress_volume(v)=ingress_cap(v)*T GB."
  "Tree-column LP. ... minimize sum_t f_t * sum_{e in t} price_e subject to sum_t f_t = S, for
   every directed edge e: sum_{t contains e} f_t <= edge_volume(e), for every VM v: sum_t f_t *
   outdeg_t(v) <= egress_volume(v), ... f_t >= 0."
  "Candidate tree generation. The LP is solved by linear programming over an incrementally
   generated pool of trees. Seed trees include: the direct multicast tree from each source VM to
   all destinations; a star through every relay region, root->relay->all destinations; and
   two-hop relay variants with different fan-out partitions. Then a randomized greedy
   directed-Steiner construction is run repeatedly for each source VM: start with the root,
   repeatedly pick the unconnected destination whose cheapest directed path from the current tree
   has the smallest current adjusted cost, and add that path; small random perturbations to edge
   costs are applied to create diverse trees. ... the generated trees are additionally capped at a
   small depth bound such as two or three overlay hops unless no feasible tree can be found. After
   each LP solve, dual prices from the capacity constraints are used to adjust edge weights; the
   greedy construction is rerun and any tree with a negative reduced cost is added to the pool.
   The process repeats until no beneficial tree is found or a maximum pool size is reached."
  "Stripe-to-tree mapping. After solving the LP, retain trees with positive f_t. Assign the source
   object's byte string a contiguous range of size roughly f_t to each selected tree ..."
  "Execution. The controller installs a per-VM forwarding job list: for every selected tree, and
   for each edge parent->child in that tree, create a job that transfers the tree's byte range."

Interface mapping (`search_algorithm(src, dsts, G, num_partitions)`; the only exposed quantities
are the region graph with per-edge `cost` ($/GB) and `throughput` (Gbps), the source region, the
destination regions and the number of stripes):

* A node of G is a region that hosts one VM; `src` is the single root source VM, `dsts` are the
  destination terminals, and every other region is a potential relay VM. So the "complete directed
  graph among all nodes" is the profiled region graph G itself.
* price(u,v) = `G[u][v]["cost"]`, bw(u,v) = `G[u][v]["throughput"]`. The per-VM caps
  egress_cap/ingress_cap and the operation deadline T are *not* exposed, so the edge/VM capacity
  constraints cannot be evaluated; they are carried in the LP below in the form the interface
  allows (see `_tree_column_lp`). With no cap or deadline to bind them, every capacity row is
  slack, which is the regime the solution describes for a deadline that the plan meets by
  construction.
* The LP objective `sum_t f_t * sum_{e in t} price_e` is scale-free in the object size S (S is a
  common factor), so S is normalised to 1 and the LP returns the trees that get positive volume
  and their relative volumes.
* Byte ranges do not exist in this interface: the stripes are the `num_partitions` partitions, so
  the stripe-to-tree mapping distributes the partitions over the selected trees in proportion to
  their f_t (and the remainder to the tree carrying the most volume).
* The per-VM forwarding job list is emitted as the per-(destination, partition) path that the
  simulator replays; a destination's path is its route inside its assigned tree.
"""

import random
from typing import Dict, List

import networkx as nx
import pulp

# "capped at a small depth bound such as two or three overlay hops unless no feasible tree can be
# found"
MAX_OVERLAY_HOPS = 3
# "a maximum pool size is reached"
MAX_POOL_SIZE = 250
# number of relay regions that seed trees are built through (the graph has whole regions, not a
# handful of VMs; the solution's star/two-hop seeds are enumerated over its relay set)
MAX_SEED_RELAYS = 10
# "a randomized greedy directed-Steiner construction is run repeatedly"
STEINER_RESTARTS = 30
# "small random perturbations to edge costs are applied"
STEINER_PERTURBATION = 0.3
# "-1 not lower than the on-demand price" style cut-offs are not observable here; the pool is
# pruned by exact edge-set deduplication and by keeping the cheapest trees only
LP_ROUNDS = 3


def _usable_graph(G, src):
    """The profiled overlay graph: transmissible, priced cross-region edges."""
    h = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        cost = data.get("cost")
        throughput = data.get("throughput")
        if u == v or v == src:
            continue
        if cost is None or throughput is None or throughput <= 0 or cost < 0:
            continue
        h.add_edge(u, v, cost=float(cost))
    return h


def _path_edges(h, u, v, weights=None):
    """Cheapest directed path u -> v as a list of edges, or None."""
    try:
        path = nx.dijkstra_path(h, u, v, weight=weights or "cost")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    return [(path[i], path[i + 1]) for i in range(len(path) - 1)]


def _tree_cost(h, tree):
    return sum(h[u][v]["cost"] for (u, v) in tree)


def _close_tree(h, src, dsts, tree):
    """Close a partial edge set into a delivery tree: every destination gets a route."""
    support = nx.DiGraph()
    for (u, v) in tree:
        support.add_edge(u, v, cost=h[u][v]["cost"])
    out = set(tree)
    for d in dsts:
        if d in support and src in support and nx.has_path(support, src, d):
            out.update(_path_edges(support, src, d) or [])
    return out


# ---------------------------------------------------------------------------
# Candidate tree generation
# ---------------------------------------------------------------------------

def _direct_tree(h, src, dsts):
    """The direct multicast tree from the source VM to all destinations."""
    tree = set()
    for d in dsts:
        p = _path_edges(h, src, d)
        if p:
            tree.update(p)
    return tree


def _star_tree(h, src, dsts, relay):
    """A star through a relay region: root -> relay -> all destinations."""
    if relay == src or relay not in h:
        return None
    first = _path_edges(h, src, relay)
    if first is None:
        return None
    tree = set(first)
    for d in dsts:
        p = _path_edges(h, relay, d)
        if p is None:
            return None
        tree.update(p)
    return tree


def _two_hop_tree(h, src, dsts, r1, r2):
    """Two-hop relay variant with a fan-out partition: destinations split between r1 and r2."""
    first = _path_edges(h, src, r1)
    if first is None:
        return None
    link = _path_edges(h, r1, r2)
    if link is None:
        return None
    tree = set(first) | set(link)
    for d in dsts:
        p1 = _path_edges(h, r1, d)
        p2 = _path_edges(h, r2, d)
        if p1 is None and p2 is None:
            return None
        if p1 is not None and (p2 is None or _tree_cost(h, p1) <= _tree_cost(h, p2)):
            tree.update(p1)
        else:
            tree.update(p2)
    return tree


def _hop_bounded_reach(h, target, max_hops, weights):
    """
    For every node u, the cheapest path u -> target that uses at most `max_hops` edges, under
    `weights`. Layered shortest-path search on the reversed graph (= the solution's hop-capped
    candidate paths for the greedy directed-Steiner construction).
    """
    rev = h.reverse(copy=False)
    dist = [{} for _ in range(max_hops + 1)]
    parent = [{} for _ in range(max_hops + 1)]
    dist[0][target] = 0.0
    for layer in range(max_hops):
        frontier = dist[layer]
        if not frontier:
            break
        for u in list(frontier):
            for w in rev.successors(u):
                w_u = weights.get((w, u), h[w][u]["cost"])
                nd = frontier[u] + w_u
                cur = dist[layer + 1].get(w)
                if cur is None or nd < cur:
                    dist[layer + 1][w] = nd
                    parent[layer + 1][w] = u
    out = {}
    for layer in range(1, max_hops + 1):
        for node, cost in dist[layer].items():
            if node not in out or cost < out[node][0]:
                edges = []
                cur, lev = node, layer
                while lev > 0:
                    nxt = parent[lev][cur]
                    edges.append((cur, nxt))
                    cur, lev = nxt, lev - 1
                out[node] = (cost, edges)
    return out


def _randomized_steiner(h, src, dsts, weights, max_hops):
    """
    Greedy directed-Steiner construction: start with the root, repeatedly pick the unconnected
    destination whose cheapest directed path from the current tree has the smallest adjusted cost
    (the cost of the edges that are not already in the tree) and add that path.
    """
    tree = set()
    nodes = {src}
    unconnected = set(dsts)
    reach = {d: _hop_bounded_reach(h, d, max_hops, weights) for d in unconnected}
    while unconnected:
        best_dst, best_path, best_cost = None, None, None
        for d in unconnected:
            for u in nodes:
                entry = reach[d].get(u)
                if entry is None:
                    continue
                marginal = sum(h[a][b]["cost"] for (a, b) in entry[1] if (a, b) not in tree)
                if best_cost is None or marginal < best_cost:
                    best_cost, best_dst, best_path = marginal, d, entry[1]
        if best_dst is None:
            return None
        tree.update(best_path)
        nodes.update(u for e in best_path for u in e)
        unconnected.discard(best_dst)
    return tree


def _candidate_pool(h, src, dsts, rng, weights, pool, seen, seed_trees=True):
    """
    Grow the candidate pool: seed trees (direct multicast tree, a star through every relay
    region, two-hop relay variants with fan-out partitions) and freshly perturbed randomized
    greedy directed-Steiner trees. Trees are deduplicated by their edge set.
    """
    added = 0

    def add(tree):
        nonlocal added
        if not tree:
            return
        closed = _close_tree(h, src, dsts, tree)
        key = frozenset(closed)
        if key in seen or len(pool) >= MAX_POOL_SIZE:
            return
        seen.add(key)
        pool.append(closed)
        added += 1

    if seed_trees:
        add(_direct_tree(h, src, dsts))
        relays = [n for n in h.nodes() if n != src and n not in dsts]
        relays.sort(key=lambda n: sum(h[n][v]["cost"] for v in h.successors(n)) / max(1, h.out_degree(n)))
        relays = relays[:MAX_SEED_RELAYS]
        for r in relays:
            add(_star_tree(h, src, dsts, r))
        for i, r1 in enumerate(relays):
            for r2 in relays[i + 1:]:
                add(_two_hop_tree(h, src, dsts, r1, r2))

    for _ in range(STEINER_RESTARTS):
        perturbed = {
            (u, v): h[u][v]["cost"] * (1.0 + rng.uniform(-STEINER_PERTURBATION, STEINER_PERTURBATION))
            for (u, v) in h.edges()
        }
        if weights:
            for e, w in weights.items():
                perturbed[e] = perturbed.get(e, h[e[0]][e[1]]["cost"]) + w
        tree = _randomized_steiner(h, src, dsts, perturbed, MAX_OVERLAY_HOPS)
        if tree is None:                                   # "unless no feasible tree can be found"
            tree = _randomized_steiner(h, src, dsts, perturbed, max(len(h), 1))
        add(tree)
        if len(pool) >= MAX_POOL_SIZE:
            break
    return added


# ---------------------------------------------------------------------------
# Tree-column LP
# ---------------------------------------------------------------------------

def _tree_column_lp(h, pool):
    """
    minimize sum_t f_t * sum_{e in t} price_e  s.t.  sum_t f_t = 1, f_t >= 0.

    The edge and per-VM capacity rows of the solution's LP need `bw(u,v)`, the per-VM
    ingress/egress caps and the operation deadline T; none of them is exposed by this interface,
    so the only row that can be written down is the demand equality (the volumes are normalised
    by the object size S). The solver returns the selected trees and their volumes; with every
    capacity row slack, the LP puts all volume on the cheapest tree in the pool.
    """
    if not pool:
        return []
    prob = pulp.LpProblem("cloudcast_tree_column", pulp.LpMinimize)
    f = {i: pulp.LpVariable(f"f_{i}", lowBound=0) for i in range(len(pool))}
    prob += pulp.lpSum(_tree_cost(h, pool[i]) * f[i] for i in range(len(pool)))
    prob += pulp.lpSum(f[i] for i in range(len(pool))) == 1.0
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=10))
    if pulp.LpStatus[status] not in ("Optimal",):
        return []
    return [(pool[i], f[i].value()) for i in range(len(pool)) if (f[i].value() or 0.0) > 1e-9]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def search_algorithm(src, dsts, G, num_partitions):
    h = _usable_graph(G, src)
    bc_topology = BroadCastTopology(src, dsts, num_partitions)
    if h.number_of_nodes() == 0 or src not in h:
        return bc_topology

    rng = random.Random(0)

    # Candidate generation + column generation: the pool is grown, the LP is solved, and the
    # greedy construction is rerun with edge weights adjusted by the new dual prices of the
    # capacity rows, as the solution prescribes. The capacity rows need bw(u,v), the per-VM caps
    # and the deadline, none of which this interface exposes, so there are no dual prices to
    # adjust the weights with; the rerun is therefore a fresh batch of perturbed Steiner trees,
    # and the loop ends on the solution's other termination test - no new beneficial tree.
    pool, seen = [], set()
    _candidate_pool(h, src, dsts, rng, {}, pool, seen, seed_trees=True)
    selected = _tree_column_lp(h, pool)
    for _ in range(LP_ROUNDS - 1):
        adjusted = {}
        added = _candidate_pool(h, src, dsts, rng, adjusted, pool, seen, seed_trees=False)
        if added == 0:
            break
        selected = _tree_column_lp(h, pool)

    if not selected:                       # nothing was selected: fall back to the cheapest tree
        if pool:
            best = min(pool, key=lambda t: _tree_cost(h, t))
            selected = [(best, 1.0)]
        else:
            selected = []

    # Stripe-to-tree mapping: the partitions play the role of the object's stripes, so the trees
    # with positive f_t take a share of the partitions proportional to their volume.
    total = sum(v for _, v in selected) or 1.0
    assignment = []
    used = 0
    for tree, vol in selected:
        share = int(round(num_partitions * vol / total))
        if share == 0 and vol > 0 and used < num_partitions:
            share = num_partitions - used          # the remainder goes to the selected trees
        share = min(share, num_partitions - used)
        assignment.append((tree, share))
        used += share
    if used < num_partitions and assignment:
        tree, share = assignment[0]
        assignment[0] = (tree, share + (num_partitions - used))

    # Execution: install the per-VM forwarding job list - every destination gets the route it
    # takes inside the tree that carries its stripe.
    partition = 0
    for tree, share in assignment:
        if share <= 0 or not tree:
            continue
        support = nx.DiGraph()
        for (u, v) in tree:
            support.add_edge(u, v, cost=h[u][v]["cost"])
        for _ in range(share):
            for d in dsts:
                if d not in support or src not in support or not nx.has_path(support, src, d):
                    continue
                for (u, v) in _path_edges(support, src, d) or []:
                    bc_topology.append_dst_partition_path(d, partition, [u, v, G[u][v]])
            partition += 1

    # every destination must still have a route on every stripe
    for d in dsts:
        for partition in range(num_partitions):
            if bc_topology.paths[d][str(partition)]:
                continue
            p = _path_edges(h, src, d)
            if p is None:
                continue
            for (u, v) in p:
                bc_topology.append_dst_partition_path(d, partition, [u, v, G[u][v]])

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
