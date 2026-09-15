"""
TXN solution generated from the *human* related-work section (merged_human_re/c252b8a901feea74),
adapted to the ADRS `get_random_costs()` interface.

Solution text this file implements, verbatim where quoted:

  Step 1 access-set extraction: "each transaction is represented by a list of operations op_{i,k};
  each operation is a read or write on a record and has a predicted duration p_{i,k}. These
  expected access sets come from deterministic stored procedures, query plans, or hot-key
  inference from transaction type and arguments."
  Step 2 conflict graph: "Put an edge between transactions i and j if they contain operations on
  the same record and at least one of those operations is a write. Read-read pairs do not create
  edges. For each edge, record the concrete pairs of operations that conflict. Then decompose the
  conflict graph into connected components."
  Step 3 makespan: "For each transaction, add an internal arc op_{i,k} -> op_{i,k+1} with arc
  delay p_{i,k}. For every recorded conflicting pair of operations op_{i,k} and op_{j,l}, if
  transaction i appears before transaction j in pi, add an external arc op_{i,k} -> op_{j,l} with
  delay p_{i,k}. ... For unbounded worker threads, the makespan of pi is the length of the longest
  path through this DAG."
  Step 4 NEH: "compute the total weight l_i of each transaction as the sum of its operation
  durations. Sort all transactions of the component in decreasing l_i, breaking ties by number of
  incident conflict edges. Start with an empty sequence. For each transaction t in this sorted
  list, try inserting t at every possible position of the current sequence, evaluate M(pi) for the
  partial component containing only transactions already inserted, and keep the position with the
  smallest makespan."
  Step 5 iterated greedy: "choose d = max(2, floor(n/5)) positions uniformly ... remove the
  transactions at those positions from pi, leaving a partial sequence pi_R. Shuffle the removed
  transactions and insert them one by one back into pi_R using the same NEH best-position rule.
  ... Accept pi_new if M(pi_new) is less than or equal to the best makespan seen so far; otherwise
  accept it with probability exp(-(M(pi_new)-M(pi_best))/T), where T is a temperature parameter
  that starts at a fraction of the initial makespan and decreases by a factor after each
  non-improving round. ... After acceptance, optionally run one local pass that tries adjacent
  swaps in pi and keeps any swap that lowers the makespan. If no improvement occurs for a fixed
  number of rounds, or the time budget is exhausted, stop and return the best pi."
  Step 6 dispatch: the best pi of every component is the schedule; non-conflicting components are
  "optimized separately and their DAGs later merged by a worker scheduler".
  Step 7 parameters: "window size ... time budget for the iterated-greedy search per component,
  the destruction fraction d with default max(2, n/5), the initial acceptance temperature, and the
  cooling factor."

Interface notes:

* Access sets and op durations come from the environment: `Workload.txns[t]` is the transaction's
  operation list `(op_type, key, pos, txn_len)` and the simulator executes one position per time
  unit, so p_{i,k} = 1 for every operation. Operations equal to "*" are dropped by the workload
  loader itself and never reach this program.
* Step 3 gives M(pi) in two regimes; this interface exposes no worker count, so the unbounded
  regime (longest path) is used, and the discrete-event list scheduler of the bounded-worker
  regime has no counterpart.
* Step 6's MVTSO/early-write-visibility version manager and the runtime abort of transactions
  whose real access set differs from the predicted one are execution-time machinery; the
  interface only asks for an execution order, so the schedule returned is the permutation pi.
* The makespan *reported* is the environment's ground truth `Workload.get_opt_seq_cost(schedule)`,
  exactly as the seed program does - the DAG model is the optimizer's proxy and is never reported.
* Step 7's numeric values are not given in the solution; the values used here are the ones the
  text only describes qualitatively, and are labelled below.
"""

import random
import time

from txn_simulator import Workload
from workloads import WORKLOAD_1, WORKLOAD_2, WORKLOAD_3

# --- Step 7 parameters (the solution names them but gives no numbers) ---
TIME_BUDGET_PER_WORKLOAD = 15.0   # seconds of iterated-greedy per component-set
INITIAL_TEMPERATURE_FRAC = 0.1    # "starts at a fraction of the initial makespan"
COOLING_FACTOR = 0.9              # "decreases by a factor after each non-improving round"
STAGNATION_LIMIT = 300            # "no improvement occurs for a fixed number of rounds"


# ---------------------------------------------------------------------------
# Steps 1-2: access sets, conflict graph, connected components
# ---------------------------------------------------------------------------

def build_ops(workload):
    """Step 1 - access sets. Each op is (op_type, key) with predicted duration p_{i,k} = 1."""
    return [[(op_type, key) for (op_type, key, _pos, _len) in txn] for txn in workload.txns]


def build_conflicts(ops_of):
    """
    Step 2 - conflict graph. Returns, per transaction, the set of keys it conflicts on (the
    concrete conflicting operation pairs are recovered from those keys during evaluation), the
    number of incident conflict edges, and the conflict-connected components.
    """
    num_txns = len(ops_of)
    writes = [set(k for t, k in ops if t == "w") for ops in ops_of]
    keys = [set(k for _t, k in ops) for ops in ops_of]
    by_key = {}
    for i, ks in enumerate(keys):
        for k in ks:
            by_key.setdefault(k, []).append(i)

    adj = [set() for _ in range(num_txns)]
    for k, txns in by_key.items():
        if len(txns) < 2:
            continue
        writers = [i for i in txns if k in writes[i]]
        if not writers:
            continue                      # read-read pairs do not create edges
        for i in txns:
            for j in writers:
                if i != j:
                    adj[i].add(j)
                    adj[j].add(i)

    incident = [len(a) for a in adj]

    seen = [False] * num_txns
    components = []
    for start in range(num_txns):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp = []
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in adj[v]:
                if not seen[w]:
                    seen[w] = True
                    stack.append(w)
        components.append(sorted(comp))
    return adj, incident, components


# ---------------------------------------------------------------------------
# Step 3: makespan of a permutation under the DAG model
# ---------------------------------------------------------------------------

def dag_makespan(order, ops_of):
    """
    Longest path through the DAG built from the total order `order`:
      internal arc op_{i,k} -> op_{i,k+1} with delay p_{i,k}
      external arc op_{i,k} -> op_{j,l} with delay p_{i,k} whenever transaction i precedes j and
      the two operations conflict (same key, at least one write)
    Only operations of transactions already placed in `order` exist in the DAG.
    """
    # Per key, the latest finish time among operations placed so far, split by "may precede a
    # read" (writes only) and "may precede anything" (any operation).
    latest_any = {}
    latest_write = {}
    makespan = 0
    for txn in order:
        prev_end = 0
        pending = []
        for op_type, key in ops_of[txn]:
            if op_type == "r":
                ext = latest_write.get(key, 0)      # read-read does not conflict
            else:
                ext = latest_any.get(key, 0)
            start = ext if prev_end == 0 else max(prev_end, ext)
            end = start + 1                          # p_{i,k} = 1
            pending.append((op_type, key, end))
            prev_end = end
            if end > makespan:
                makespan = end
        for op_type, key, end in pending:
            if end > latest_any.get(key, 0):
                latest_any[key] = end
            if op_type == "w" and end > latest_write.get(key, 0):
                latest_write[key] = end
    return makespan


# ---------------------------------------------------------------------------
# Steps 4-5: NEH construction and iterated-greedy refinement
# ---------------------------------------------------------------------------

def _best_position(seq, ops_of, txn, cache):
    """NEH best-position rule: insert `txn` where the partial sequence's makespan is smallest."""
    best_pos = 0
    best_cost = None
    for pos in range(len(seq) + 1):
        candidate = seq[:pos] + [txn] + seq[pos:]
        key = (tuple(candidate),)
        if key in cache:
            cost = cache[key]
        else:
            cost = dag_makespan(candidate, ops_of)
            cache[key] = cost
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_pos = pos
    return best_pos, best_cost


def neh_construction(component, ops_of, incident, txn_len):
    """Step 4."""
    ordered = sorted(component, key=lambda t: (-txn_len[t], -incident[t]))
    seq = []
    cache = {}
    for txn in ordered:
        pos, _ = _best_position(seq, ops_of, txn, cache)
        seq.insert(pos, txn)
    return seq


def iterated_greedy(component, ops_of, sequence, deadline, rng):
    """Step 5."""
    n = len(component)
    if n < 3:
        return sequence
    d = max(2, n // 5)
    best_seq = list(sequence)
    best_cost = dag_makespan(best_seq, ops_of)
    cur_seq = list(best_seq)
    cur_cost = best_cost
    temperature = INITIAL_TEMPERATURE_FRAC * max(1, best_cost)
    stagnated = 0
    cache = {}
    while time.time() < deadline and stagnated < STAGNATION_LIMIT:
        positions = rng.sample(range(n), min(d, n))
        removed_set = set(positions)
        removed = [cur_seq[p] for p in positions]
        partial = [t for i, t in enumerate(cur_seq) if i not in removed_set]
        rng.shuffle(removed)
        for txn in removed:
            pos, _ = _best_position(partial, ops_of, txn, cache)
            partial.insert(pos, txn)
        new_cost = dag_makespan(partial, ops_of)
        if new_cost <= best_cost:
            cur_seq, cur_cost = partial, new_cost
            best_seq, best_cost = list(partial), new_cost      # "less than or equal to the best"
            stagnated = 0
            # optional local pass: adjacent swaps that lower the makespan
            if time.time() < deadline:
                i = 0
                while i < n - 1 and time.time() < deadline:
                    cand = list(best_seq)
                    cand[i], cand[i + 1] = cand[i + 1], cand[i]
                    c = dag_makespan(cand, ops_of)
                    if c < best_cost:
                        best_seq, best_cost = cand, c
                        cur_seq, cur_cost = list(cand), c
                    i += 1
        else:
            delta = new_cost - best_cost
            if rng.random() < pow(2.718281828459045, -delta / max(temperature, 1e-9)):
                cur_seq, cur_cost = partial, new_cost
            temperature *= COOLING_FACTOR    # cools after each non-improving round
            stagnated += 1
    return best_seq


def schedule_workload(workload, deadline, rng):
    ops_of = build_ops(workload)
    _adj, incident, components = build_conflicts(ops_of)
    txn_len = [len(ops) for ops in ops_of]
    if not ops_of:
        return list(range(workload.num_txns))

    # "non-conflicting components are optimized independently and later merged": the per-workload
    # budget is shared evenly over the components that are still left.
    components.sort(key=lambda c: -len(c))
    schedule = []
    for idx, comp in enumerate(components):
        remaining = max(0.0, deadline - time.time())
        left = len(components) - idx
        per_component_deadline = time.time() + remaining / left if left else deadline
        seq = neh_construction(comp, ops_of, incident, txn_len)
        seq = iterated_greedy(comp, ops_of, seq, per_component_deadline, rng)
        schedule.extend(seq)                      # components merged by concatenation
    return schedule


# ---------------------------------------------------------------------------
# Interface entry point
# ---------------------------------------------------------------------------

def get_random_costs():
    """
    Get optimal schedule using greedy cost sampling strategy.

    Returns:
        Tuple of (lowest makespan, corresponding schedule)
    """
    start_time = time.time()
    workload = Workload(WORKLOAD_1)
    workload2 = Workload(WORKLOAD_2)
    workload3 = Workload(WORKLOAD_3)

    rng = random.Random(random.random())
    deadlines = [
        start_time + TIME_BUDGET_PER_WORKLOAD,
        start_time + 2 * TIME_BUDGET_PER_WORKLOAD,
        start_time + 3 * TIME_BUDGET_PER_WORKLOAD,
    ]
    schedules = [
        schedule_workload(workload, deadlines[0], rng),
        schedule_workload(workload2, deadlines[1], rng),
        schedule_workload(workload3, deadlines[2], rng),
    ]

    # The interface reports the makespan of the returned schedules; the value reported is the
    # environment's own ground-truth cost of that schedule (as the seed program does).
    cost1 = workload.get_opt_seq_cost(schedules[0])
    cost2 = workload2.get_opt_seq_cost(schedules[1])
    cost3 = workload3.get_opt_seq_cost(schedules[2])
    print(cost1, cost2, cost3)
    return cost1 + cost2 + cost3, schedules, time.time() - start_time


if __name__ == "__main__":
    makespan, schedule, elapsed = get_random_costs()
    print(f"Makespan: {makespan}, Time: {elapsed}")
