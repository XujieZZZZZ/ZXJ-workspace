# Transaction scheduling (makespan minimisation)

OpenEvolve reproduction of the transaction-scheduling problem: given workloads of transactions
(each a sequence of `r-<key>` / `w-<key>` operations), order them so the resulting makespan —
the time until the last transaction finishes once conflicting read/write locks are respected —
is minimised. `txn_simulator.Workload.get_opt_seq_cost(seq)` is the ground-truth cost function;
`workloads.py` holds three fixed 100-transaction workloads, and `initial_program.py` the greedy
sampling seed that evolves.

---

## Evaluation only (no evolution run)

`evaluator.py` has a CLI, so a single file needs no wrapper:

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/txn_scheduling && \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python evaluator.py /abs/path/to/my_strategy.py
```

It prints the metrics JSON (and, above it, the subprocess's stdout). Only numpy is needed —
`envs/ai4system` has it — and both relative and absolute program paths work. The child process
adds the program's own directory *and* this directory to `sys.path`, so a file living elsewhere
can still `from txn_simulator import Workload` / `from workloads import WORKLOAD_1`.

### What the tested file must define

`get_random_costs()`, called with no arguments, returning `(makespan, [schedule1, schedule2,
schedule3], time_taken)` — one schedule per workload in `workloads.py`, each a list of
transaction indices. Correctness is checked only structurally: `validate_schedule` requires
every index of `0..num_txns-1` to appear in the schedule, i.e. each schedule must be a
permutation of the 100 transactions.

### How the score is computed

```
combined_score = 1000 / (1 + makespan) * 1000 = 1e6 / (1 + makespan)
```

So it is always positive and higher is better. `validity` is computed and returned but **does
not enter `combined_score`** in `evaluate()` (it is only used by `evaluate_stage1`, which zeroes
the score for an invalid schedule). Any exception, timeout (600 s), or crash returns all zeros.
`evaluate_stage2` is just `evaluate`.

### Verified reference run (`initial_program.py`, this checkout)

```json
{"makespan": 357.0, "schedule": 3.0, "time_taken": 1.26, "validity": 1.0,
 "eval_time": 1.42, "combined_score": 2793.2960893854747}
```

`makespan` is the sum over the three workloads, `schedule` is the *number* of schedules
returned (3, not their length), and the whole evaluation takes ~1.4 s.

**The evaluation is seeded and reproducible.** The seed program draws from `random` without
seeding, which made the score vary by ~7 % run to run (`combined_score` 2666.67 / 2544.53 /
2747.25 / 2816.90 → makespan 374 / 392 / 363 / 354). The subprocess wrapper in `evaluator.py`
now fixes the RNG state right before calling the candidate, via the module-level constant
`EVAL_SEED = 2026`:

```python
random.seed(EVAL_SEED)
np.random.seed(EVAL_SEED)
```

so every candidate is compared on the same sequence of draws. With the seed in place,
`initial_program.py` returns `makespan = 357.0` and `combined_score = 2793.2960893854747` on
every run (only `time_taken`, the program's own timer, moves); a candidate that shuffles with
`random.shuffle` and sums `random.random()` values reproduces its score bit-for-bit too, and
changing `EVAL_SEED` changes it as expected. If you want a different seed, edit that one line —
but note that the reference numbers above are for seed 2026. Running `python initial_program.py`
standalone still bypasses all of this and stays noisy.

### Gotchas

- **The makespan is taken on faith.** `evaluate()` never recomputes the cost from the returned
  schedule, although `Workload.get_opt_seq_cost` is right there in `txn_simulator.py`. A file
  that returns `(0, [list(range(100))] * 3, 0.0)` — structurally *valid* permutations with a
  fabricated makespan — scores **1,000,000** and passes `evaluate_stage1` unchanged, versus
  2,747 for the honest seed. Even the cascade gate in `config.yaml` (thresholds 0.5 / 0.75 / 0.9,
  `cascade_evaluation: true`) does not catch it, because a valid schedule yields `validity = 1.0`.
  A run that returns garbage schedules without a claimed-zero makespan is caught only when
  `validate_schedule` fails and `evaluate_stage1` is the stage being scored — a direct
  `python evaluator.py` call on such a file still reports `combined_score: 1000000.0`.
- `run_with_timeout` hardcodes a **600 s** timeout while `config.yaml` sets `evaluator.timeout:
  300`; if your OpenEvolve version enforces the latter, a slow candidate is killed by the harness
  before the interior timeout fires.
- The evaluator spawns a subprocess per evaluation, so importing a heavy candidate module pays
  that cost on every call, and the returned `time_taken` is the program's own timer, not the
  evaluator's (`eval_time` is).
