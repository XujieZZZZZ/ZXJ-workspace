# PRISM: KV-cache-aware model placement

OpenEvolve reproduction of the PRISM model-placement problem: given `gpu_num` GPUs with 80 GB
each and a list of models (size, request rate, SLO), pack them so the **maximum KV-cache
pressure (KVPR)** across GPUs is minimised, where
`KVPR(gpu) = Σ(req_rate / slo) / (80 - Σ(model_size))` over the models on that GPU. The evolved
artifact is a function `compute_model_placement(gpu_num, models)`; `initial_program.py` is the
greedy seed, `initial_program_naive.py` the first-fit baseline, `best_program.py` the best
program found by the original run.

---

## Evaluation only (no evolution run)

`evaluator.py` exposes `evaluate(program_path)` — no CLI, no OpenEvolve import — so testing a
single file is a short `python -c` wrapper. Run it from this directory (`import evaluator` is
resolved from the cwd), with an interpreter that has numpy: on this machine
`/home/zhangxujie/miniconda3/envs/ai4system/bin/python` (the seeded numpy RNG makes results
identical across runs and machines).

### One command: evaluate a strategy file (~0.5 s)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/prism && \
STRATEGY=/abs/path/to/my_strategy.py && \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator
print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))
' "$STRATEGY"
```

`initial_program.py` also has a `__main__` self-test that prints only the inverted KVPR
(`python initial_program.py`), which is a quick sanity check of that one file.

### What the tested file must define

`compute_model_placement(gpu_num, models)` returning a `dict[int, list[Model]]`. It is called as
`compute_model_placement(gpu_num=…, models=…)` (keyword arguments) for each of 50 generated test
cases, with a **10 s per-call timeout**. A file without the function scores 0 with
``error: Missing compute_model_placement function``; if every call raises or times out the result
is `error: All test signals failed` (a crash on *some* cases only lowers `success_rate`).

### How the score is computed

Test cases are deterministic (`np.random.seed(42)` in `generate_test_gpu_models`): for each of 50
cases, `gpu_num ∈ [5, 10)`, `2 * gpu_num` models with `model_size ∈ [10, 30)` GB,
`req_rate ∈ [1, 10)`, `slo ∈ [5, 10)`. Per case the evaluator takes the max KVPR over the GPUs
in the returned dict (a GPU with no free memory scores `1e6`), averages that over the cases, and
**inverts** it:

```
combined_score = 1 / mean(max_kvpr over cases) + success_rate
```

So higher is better, the inverted-KVPR term is unbounded, and `success_rate` contributes at most
1.0. `execution_time` is measured and returned but does **not** enter the score.

### Verified reference numbers (this checkout)

| program | `max_kvpr` (inverted) | `success_rate` | `combined_score` |
| --- | --- | --- | --- |
| `initial_program.py` (greedy KVPR seed) | 20.892 | 1.0 | **21.892** |
| `best_program.py` | 24.718 | 1.0 | **25.718** |
| `initial_program_naive.py` (first fit) | 3.1e-06 | 1.0 | **1.000003** |
| one model per `gpu_id`, ignoring `gpu_num` | 39.289 | 1.0 | **40.289** |
| return `{}` (place nothing) | 0.0 | 1.0 | **1.0** |

Repeat runs of `initial_program.py` give a bit-identical `combined_score` of
`21.891622105209393` (only `execution_time` moves), so differences here are real.

### Gotchas

- **The metric is gameable and the shipped seed is not optimal under it.** The evaluator only
  looks at the GPUs present in the returned dict, so adding keys beyond `gpu_num` — e.g. one
  model per `gpu_id` for `gpu_id in range(len(models))` — spreads the load over more GPUs and
  scores **40.29**, well above the intended `best_program.py` (25.72). `verify_gpu_mem_constraint`
  exists in `evaluator.py` but is never called: over-packing is punished only indirectly (a full
  GPU yields `kvpr = 1e6`), while *omitting* models is not punished at all (an empty placement
  scores `1.0` from `success_rate` alone). If you use this evaluator for a study, expect
  candidates to find the extra-GPU shortcut.
- **The 10 s timeout does not bound wall clock.** `run_with_timeout` submits to a
  `ThreadPoolExecutor` inside a `with` block, so exiting it waits for the worker anyway; a 1 s
  timeout on a 3 s function was measured to return (via `TimeoutError`) after 3.00 s. A function
  that never returns hangs `evaluate()` outright — which in turn trips the config's
  `evaluator.timeout: 90`, and a *slow but valid* program can also exceed it (50 calls × 10 s
  worst case = 500 s).
- Failures always come back with an explicit `error` field and exit code 0, so read the returned
  dict rather than `$?`.
