import time
import random

from txn_simulator import Workload
from workloads import WORKLOAD_1, WORKLOAD_2, WORKLOAD_3

"""
SMF (human / paper) solution, adapted to the ADRS `get_random_costs` interface.

Paper: "SMF greedily builds a schedule by repeatedly appending the unscheduled transaction
whose addition produces the smallest incremental makespan. To keep search tractable and
deployable online, SMF makes decisions from predicted hot-key conflict patterns instead of
full read/write sets, relies on a small random sample of candidates, and computes only the
incremental cost of the latest conflicting operation per hot key."

    it seeds the schedule with a random transaction, then repeatedly samples s = 5
    unscheduled transactions uniformly at random, computes for each candidate the incremental
    makespan that would result from appending it to the current schedule using the predicted
    hot-key operations and the makespan model from Section 2.1 (operations take unit time,
    conflicting operations are serialized, transactions have internal operation order), and
    appends the candidate with the smallest increase, breaking ties randomly. Transactions
    with no predicted hot keys are assumed not to affect makespan and execute immediately. For
    each hot key, only the latest transaction's conflicting operation is retained when
    computing costs because earlier conflicts were already accounted for when that transaction
    was added to the schedule.

Interface notes (this benchmark only exposes the workloads, no application hints, traces or
cluster metadata):

  * the R-SMF classifier (trace -> metadata vector -> clustering -> canonical hot-key op set)
    cannot be trained here; the predicted hot-key operation set of a transaction is taken to
    be its own operations on hot keys, i.e. perfect prediction. The environment's own hot-key
    definition is used (Workload.hot_keys_thres);
  * MVSchedO is a runtime concurrency-control protocol (SCHED_KEY / pred_ops / commit
    validation) and has no counterpart in an interface that only returns an execution order,
    so it is not implemented;
  * the returned makespan is the environment's ground-truth cost of the chosen schedule
    (Workload.get_opt_seq_cost), exactly as the reference seed reports it -- Section 2.1's
    model is used to *choose* the order, not to report a number.

The scheduler is deterministic given the RNG state the evaluator fixes (EVAL_SEED).
"""

# SMF: number of unscheduled transactions sampled per scheduling decision
SAMPLE_SIZE = 5


def _hot_key_ops(txn_ops, hot_keys_thres):
    """Predicted hot-key operations of a transaction: (op_type, key, pos) on hot keys."""
    return [(op, key, pos) for (op, key, pos, _) in txn_ops if int(key) <= hot_keys_thres]


def _incremental_makespan(candidate, schedule_state, workload):
    """Section 2.1 model: append `candidate` to the current schedule and report the increase.

    Operations take unit time, conflicting operations on a hot key are serialized, and a
    transaction keeps its internal operation order (the op at position p of a transaction
    starting at S runs at S + p - 1). Only the latest conflicting operation per hot key is
    retained: `schedule_state` maps a hot key to the lock end of the most recent operation on
    it, past conflicts having been accounted for when their transaction was appended.
    """
    txn_ops = workload.txns[candidate]
    txn_len = txn_ops[0][3]
    latest_end = schedule_state["hot_key_end"]
    makespan = schedule_state["makespan"]

    txn_start = 1
    for (_op, key, pos) in _hot_key_ops(txn_ops, workload.hot_keys_thres):
        if key in latest_end:
            # this operation must start after the previous conflicting operation finished
            txn_start = max(txn_start, latest_end[key] + 1 - pos + 1)
    txn_end = txn_start + txn_len - 1
    # a transaction with no predicted hot keys never conflicts: it executes immediately
    return max(0, txn_end - makespan), txn_start, txn_end


def _commit(candidate, schedule_state, workload, txn_start):
    """Record the appended transaction's hot-key lock ends in the schedule state."""
    latest_end = schedule_state["hot_key_end"]
    for (_op, key, pos) in _hot_key_ops(workload.txns[candidate], workload.hot_keys_thres):
        lock_end = txn_start + pos - 1
        if key not in latest_end or lock_end > latest_end[key]:
            latest_end[key] = lock_end


def get_best_schedule(workload, num_seqs):
    """
    SMF: sample s candidates per step, append the one with the smallest incremental makespan.

    Returns:
        Tuple of (lowest makespan, corresponding schedule)
    """
    def smf(num_samples):
        # seed the schedule with a random transaction
        start_txn = random.randint(0, workload.num_txns - 1)
        txn_seq = [start_txn]
        remaining_txns = [x for x in range(0, workload.num_txns)]
        remaining_txns.remove(start_txn)

        schedule_state = {"hot_key_end": {}, "makespan": 0}
        _inc, start, end = _incremental_makespan(start_txn, schedule_state, workload)
        schedule_state["makespan"] = max(schedule_state["makespan"], end)
        _commit(start_txn, schedule_state, workload, start)

        for _ in range(0, workload.num_txns - 1):
            # sample s unscheduled transactions uniformly at random
            idxs = random.sample(range(len(remaining_txns)), min(num_samples, len(remaining_txns)))
            best_idx = None
            best_cost = None
            best_start = None
            for idx in idxs:
                t = remaining_txns[idx]
                cost, txn_start, txn_end = _incremental_makespan(t, schedule_state, workload)
                if best_cost is None or cost < best_cost or (cost == best_cost and random.random() < 0.5):
                    best_cost = cost
                    best_idx = idx
                    best_start = txn_start
            assert best_idx is not None

            # append the sampled candidate with the smallest increase, ties broken randomly
            t = remaining_txns.pop(best_idx)
            txn_seq.append(t)
            schedule_state["makespan"] = max(schedule_state["makespan"], best_start + workload.txns[t][0][3] - 1)
            _commit(t, schedule_state, workload, best_start)

        assert len(set(txn_seq)) == workload.num_txns
        # report the ground-truth makespan of the schedule SMF built
        overall_cost = workload.get_opt_seq_cost(txn_seq)
        return overall_cost, txn_seq

    return smf(SAMPLE_SIZE)


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
