# LLM-SQL: prefix-cache-aware column reordering

OpenEvolve reproduction of the "reorder DataFrame columns to maximise LLM prompt-cache prefix
hits" problem. A table is serialised row by row (all columns concatenated, no separators), and
the score counts how much of each row is already a prefix of a previously seen row: the longer
the shared prefixes, the more of the prompt the LLM provider serves from cache. The evolved
artifact is a class `Evolved` with a `reorder(df, ...)` method; `quick_greedy.py` holds the
hand-written baseline and `solver.py`/`utils.py` the shared helpers and the hit-rate metric.

---

## Evaluation only (no evolution run)

`evaluator.py` exposes `evaluate(program_path)`: it loads the file, calls
`Evolved().reorder(...)` on each of the five datasets in `datasets/`, and scores the reordered
frames with `utils.evaluate_df_prefix_hit_cnt`. No OpenEvolve import, so a single file can be
scored with a short `python -c` wrapper.

The `if __name__ == "__main__"` block is **not** a single-file tester: it ignores its argv and
benchmarks `quick_greedy.QuickGreedy` against `initial_program.Evolved` on the same five
datasets, printing a different formula (`0.5 * hit_rate + 0.5 / (1 + runtime)`).

Two prerequisites:

- Run from this directory. The dataset paths (`datasets/*.csv`) are relative, and the evaluated
  file's own imports (`from solver import Algorithm`, …) resolve against the cwd.
- The interpreter needs pandas and networkx. On this machine
  `/home/zhangxujie/miniconda3/envs/ai4system/bin/python` has both (pandas 2.1.4, networkx
  2.8.8); `envs/zxj` also does but ships pandas 3.x, which is untested with this code.

### One command: evaluate a strategy file (~10 min)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/llm_sql && \
STRATEGY=/abs/path/to/my_strategy.py && \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator
print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))
' "$STRATEGY"
```

### What the tested file must define

A module-level class `Evolved`, instantiated with no arguments, whose
`reorder(df, early_stop=100000, distinct_value_threshold=0.7, row_stop=4, col_stop=2, col_merge=...)`
returns `(reordered_df, ...)` — the evaluator uses only the first element. The `col_merge`
values per dataset are the merged-column groups listed in `evaluator.py:89-95`. A file without
`Evolved` scores 0 with ``error: Missing algorithm function``; an exception on any dataset
aborts the remaining ones and returns `error: 1 or more files failed to run`.

### How the score is computed

Per dataset: `hit_rate = evaluate_df_prefix_hit_cnt(df)[1] / 100`, i.e. (sum of per-row longest
common prefixes with all earlier rows) / (total serialised string length).

```
combined_score = 0.95 * mean(hit_rates over the 5 datasets)
               + 0.05 * (12 - min(12, mean(reorder_runtime))) / 12
```

The runtime term is dead weight in practice: it only pays out below 12 s per dataset, and even
the shipped `initial_program.py` averages ~72 s, so `combined_score ≈ 0.95 * mean_hit_rate`
(`0.95 * 0.70711 = 0.67175` on the reference run below). A candidate that is 10× faster but
drops hit rate by one point is scored *worse* — optimise the hit rate, not the clock.

### Verified reference run (`initial_program.py`, this checkout)

| dataset | hit count | hit rate | reorder time |
| --- | --- | --- | --- |
| `datasets/movies.csv` | 7,329,908 | 79.39 % | 19.8 s |
| `datasets/beer.csv` | 1,606,626 | 70.73 % | 64.2 s |
| `datasets/BIRD.csv` | 26,821,775 | 79.63 % | 2.9 s |
| `datasets/PDMX.csv` | 3,009,090 | 39.59 % | 252.6 s |
| `datasets/products.csv` | 13,367,016 | 84.20 % | 18.4 s |

`combined_score = 0.671749`, `runs_successfully = 1.0`, `total_runtime = 357.87 s`; ~10 min
wall clock end to end (the rest goes to the trie pass over each frame).

**These numbers move between runs.** A repeat gave `combined_score = 0.671044` with hit rates
0.79424 / 0.70763 / 0.79095 / 0.39643 / 0.84257 — a ~0.001 spread on the same file, and BIRD's
hit count changed (26,821,775 vs 26,642,416) while its serialised length did not, which points
at the measurement itself. Two independent sources: `reorder(..., parallel=True)` is the default
(so the column order it produces is scheduling-dependent — the total string lengths differ
slightly between runs), and `evaluate_df_prefix_hit_cnt` inserts into and queries one shared
`Trie` from a `ThreadPoolExecutor` with no locking. Treat differences below ~0.002 as noise and
compare candidates with several repetitions.

### Gotchas

- `config.yaml` sets `evaluator.timeout: 60`, but one evaluation takes ~10 minutes here. If
  your OpenEvolve version enforces that timeout in seconds, every candidate would be killed
  before it returns — raise it (or shrink the datasets) before trusting a run.
- `average_hit_rate` divides by `len(test_files)` (5) even when a dataset is skipped because
  the file is missing (`continue`, without touching `failed_files`), so a missing CSV silently
  deflates the score instead of failing.
- `evaluate_df_prefix_hit_cnt` accumulates `total_string_length` from a `ThreadPoolExecutor`
  callback via `nonlocal` (racy), and its `process_row` both queries and inserts the same `Trie`
  from every thread, so the hit count is scheduling-dependent — this is one of the two reasons
  the score is not reproducible run to run (see above).
