"""
Anytime weighted-coloring schedule planner (LLM solution for the TXN paper).

The solution inserts a planning layer between admission and concurrency control and
makes the plan itself the input of the execution engine:

  * the planning problem lives on the *conflict graph* of the batch: a vertex per
    transaction, an edge whenever two transactions overlap with at least one write
    ((R_i n W_j) u (W_i n R_j) u (W_i n W_j) non-empty);
  * a schedule is an ordered list of color classes, each colour class an independent
    set that runs concurrently, and the classes run one after another, so
    makespan(C_1..C_k) = sum_c max_{i in C_c} p_i with the estimated uncontended
    duration p_i;
  * stage 4a builds an incumbent with a weighted DSATUR greedy (vertices in
    non-increasing p_i, ties by descending conflict degree; each vertex goes into the
    compatible class with the smallest marginal increase, else opens a class);
  * stage 4b runs a beam search over partial colorings (next vertex = the one with the
    most coloured neighbours; successors = every compatible class plus one new class;
    the B cheapest partial schedules survive; a partial schedule whose cost already
    reaches the incumbent is discarded);
  * stage 4c improves the incumbent with single-vertex moves, pair swaps and class
    merges until no improving move is found;
  * stage 4d would solve small windows exactly by branch and bound with clique lower
    bounds -- windows of 100 transactions stay with the anytime planner.

The planner always keeps its best feasible schedule, so it degrades gracefully when
the search budget is exhausted.
"""

import time
import random

from txn_simulator import Workload
from workloads import WORKLOAD_1, WORKLOAD_2, WORKLOAD_3

# planner knobs (the solution exposes them as configuration)
BEAM_WIDTH = 6
LOCAL_SEARCH_ROUNDS = 25
EXACT_THRESHOLD = 12          # windows below this size may be solved exactly
PLANNER_BUDGET_S = 90.0       # per workload


def _conflict_graph(workload):
    """Undirected conflict graph of a batch: edge iff a shared key has a write."""
    readers, writers = {}, {}
    for txn_id, txn in enumerate(workload.txns):
        for (op_type, key, _pos, _len) in txn:
            if op_type == "w":
                writers.setdefault(key, set()).add(txn_id)
            else:
                readers.setdefault(key, set()).add(txn_id)

    adjacency = [set() for _ in workload.txns]
    for key, writer_set in writers.items():
        involved = writer_set | readers.get(key, set())
        for i in involved:
            adjacency[i].update(involved - {i})
    return adjacency


def _class_cost(classes):
    return sum(max(cls.values()) for cls in classes)


def _weighted_dsatur(adjacency, durations):
    """Stage 4a: incumbent from a weighted DSATUR greedy."""
    n = len(adjacency)
    order = sorted(range(n), key=lambda i: (-durations[i], -len(adjacency[i])))
    classes = []  # each class: {txn: duration}
    for v in order:
        best_class, best_marginal = None, None
        for index, members in enumerate(classes):
            if adjacency[v] & members.keys():
                continue
            marginal = max(0.0, durations[v] - max(members.values()))
            if best_marginal is None or marginal < best_marginal:
                best_marginal, best_class = marginal, index
        if best_class is None:
            classes.append({v: durations[v]})
        else:
            classes[best_class][v] = durations[v]
    return classes


def _beam_search(adjacency, durations, incumbent_cost):
    """Stage 4b: beam search over partial colorings, bounded by the incumbent cost."""
    n = len(adjacency)
    frontier = [([], 0.0)]  # (classes, cost)
    coloured = 0
    while coloured < n:
        successors = []
        for classes, cost in frontier:
            coloured_vertices = set().union(*[set(c) for c in classes]) if classes else set()
            remaining = [v for v in range(n) if v not in coloured_vertices]
            # next vertex: largest number of neighbours already coloured
            vertex = max(remaining, key=lambda v: len(adjacency[v] & coloured_vertices))
            for index, members in enumerate(classes):
                if adjacency[vertex] & members.keys():
                    continue
                nxt = [dict(c) for c in classes]
                nxt[index][vertex] = durations[vertex]
                new_cost = cost + max(0.0, durations[vertex] - max(classes[index].values()))
                if new_cost < incumbent_cost:
                    successors.append((nxt, new_cost))
            opened = [dict(c) for c in classes] + [{vertex: durations[vertex]}]
            new_cost = cost + durations[vertex]
            if new_cost < incumbent_cost:
                successors.append((opened, new_cost))
        if not successors:
            break
        successors.sort(key=lambda item: item[1])
        frontier = successors[:BEAM_WIDTH]
        coloured += 1
    if frontier:
        classes, cost = min(frontier, key=lambda item: item[1])
        if classes:
            return classes, cost
    return None, None


def _local_search(classes, adjacency, durations, deadline):
    """Stage 4c: single-vertex moves, pair swaps and class merges."""
    classes = [dict(c) for c in classes]
    for _ in range(LOCAL_SEARCH_ROUNDS):
        improved = False
        cost = _class_cost(classes)
        # class merges: a merged class drops one contribution from the makespan
        for a in range(len(classes)):
            for b in range(a + 1, len(classes)):
                if any(u in adjacency[v] for u in classes[a] for v in classes[b]):
                    continue
                merged = {**classes[a], **classes[b]}
                if max(merged.values()) < max(classes[a].values()) + max(classes[b].values()):
                    classes = [c for i, c in enumerate(classes) if i not in (a, b)] + [merged]
                    improved = True
                    break
            if improved:
                break
        if improved:
            continue
        # single-vertex moves
        for v in list(range(len(adjacency))):
            src = next((i for i, c in enumerate(classes) if v in c), None)
            if src is None or len(classes[src]) == 1:
                continue
            for dst in range(len(classes)):
                if dst == src or (adjacency[v] & classes[dst].keys()):
                    continue
                trial = [dict(c) for c in classes]
                del trial[src][v]
                trial[dst][v] = durations[v]
                if _class_cost(trial) <= cost:
                    classes = [c for c in trial if c]
                    improved = True
                    break
            if improved:
                break
        if improved:
            continue
        # pair swaps between two classes
        for a in range(len(classes)):
            for b in range(a + 1, len(classes)):
                for u in list(classes[a]):
                    for w in list(classes[b]):
                        if (adjacency[w] & (classes[a].keys() - {u})) or \
                           (adjacency[u] & (classes[b].keys() - {w})):
                            continue
                        trial = [dict(c) for c in classes]
                        del trial[a][u]
                        trial[a][w] = durations[w]
                        del trial[b][w]
                        trial[b][u] = durations[u]
                        if _class_cost(trial) < cost:
                            classes = trial
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if not improved or time.time() > deadline:
            break
    return classes


def _exact_search(adjacency, durations, incumbent_cost):
    """Stage 4d: depth-first branch and bound for small windows (clique bound)."""
    n = len(adjacency)
    best = {"cost": incumbent_cost, "classes": None}

    def clique_bound(remaining):
        # every member of a clique needs its own class: sum their durations
        remaining = list(remaining)
        if not remaining:
            return 0.0
        vertices = sorted(remaining, key=lambda v: -durations[v])
        bound, chosen = 0.0, []
        for v in vertices:
            if all(u in adjacency[v] for u in chosen):
                chosen.append(v)
                bound += durations[v]
        return bound

    def dfs(classes, cost, remaining):
        if not remaining:
            if cost < best["cost"]:
                best["cost"] = cost
                best["classes"] = [dict(c) for c in classes]
            return
        if cost + clique_bound(remaining) >= best["cost"]:
            return
        vertex = max(remaining, key=lambda v: len(adjacency[v] & set().union(*[set(c) for c in classes])) if classes else 0)
        rest = remaining - {vertex}
        for index, members in enumerate(classes):
            if adjacency[vertex] & members.keys():
                continue
            marginal = max(0.0, durations[vertex] - max(members.values()))
            classes[index][vertex] = durations[vertex]
            dfs(classes, cost + marginal, rest)
            del classes[index][vertex]
        classes.append({vertex: durations[vertex]})
        dfs(classes, cost + durations[vertex], rest)
        classes.pop()

    dfs([], 0.0, set(range(n)))
    return best["classes"]


def _classes_to_sequence(classes):
    """Ordered list of colour classes -> the linear schedule the executor replays."""
    sequence = []
    for members in sorted(classes, key=lambda c: -max(c.values())):
        sequence.extend(sorted(members, key=lambda v: -members[v]))
    return sequence


def get_best_schedule(workload, num_seqs):
    """Plan a schedule for one workload with the anytime weighted-colouring planner."""
    deadline = time.time() + PLANNER_BUDGET_S
    adjacency = _conflict_graph(workload)
    durations = [txn[0][3] for txn in workload.txns]

    classes = _weighted_dsatur(adjacency, durations)          # stage 4a
    incumbent_cost = _class_cost(classes)

    beam_classes, beam_cost = _beam_search(adjacency, durations, incumbent_cost)
    # stage 4b: only a plan that covers the whole window may replace the incumbent
    if beam_classes and beam_cost < incumbent_cost and \
            sum(len(c) for c in beam_classes) == len(adjacency):
        classes, incumbent_cost = beam_classes, beam_cost

    if len(adjacency) <= EXACT_THRESHOLD:                      # stage 4d
        exact = _exact_search(adjacency, durations, incumbent_cost)
        if exact is not None and sum(len(c) for c in exact) == len(adjacency):
            classes = exact
    else:
        classes = _local_search(classes, adjacency, durations, deadline)  # stage 4c

    sequence = _classes_to_sequence(classes)
    if sorted(sequence) != list(range(len(adjacency))):
        # a plan must be a feasible permutation of the window: keep the incumbent
        sequence = _classes_to_sequence(_weighted_dsatur(adjacency, durations))
    makespan = workload.get_opt_seq_cost(sequence)
    return makespan, sequence


def get_random_costs():
    start_time = time.time()
    workload_size = 100
    workload = Workload(WORKLOAD_1)

    makespan1, schedule1 = get_best_schedule(workload, 10)
    cost1 = workload.get_opt_seq_cost(schedule1)

    workload2 = Workload(WORKLOAD_2)
    makespan2, schedule2 = get_best_schedule(workload2, 10)
    cost2 = workload2.get_opt_seq_cost(schedule2)

    workload3 = Workload(WORKLOAD_3)
    makespan3, schedule3 = get_best_schedule(workload3, 10)
    cost3 = workload3.get_opt_seq_cost(schedule3)
    print(cost1, cost2, cost3)
    return cost1 + cost2 + cost3, [schedule1, schedule2, schedule3], time.time() - start_time


if __name__ == "__main__":
    makespan, schedule, time = get_random_costs()
    print(f"Makespan: {makespan}, Time: {time}")
