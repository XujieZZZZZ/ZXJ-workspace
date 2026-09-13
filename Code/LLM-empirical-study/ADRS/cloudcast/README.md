# CloudCast (relay / broadcast)

OpenEvolve reproduction of the CloudCast relay-broadcast problem: broadcast a dataset from one
source region to several destination regions over a directed graph whose edges carry a
`cost` ($/GB) and a `throughput` (Gbps). The evolved artifact is a single function

```python
def search_algorithm(src, dsts, G, num_partitions) -> BroadCastTopology
```

in an `initial_program.py`-style file. The score of a candidate is the transfer cost of the
topology it returns, summed over five configurations (three intra-provider, two
inter-provider) in `examples/config/`.

---

## Evaluation only (no evolution run)

`evaluator.py` exposes `evaluate(program_path)` and nothing else — there is no CLI and no
OpenEvolve dependency, so testing a single file is a short `python -c` wrapper.

`evaluate()` loads the file with `importlib`, calls its `search_algorithm` once per config,
and feeds the returned paths through `BCSimulator` to get a transfer time and a cost.

Two environment facts:

- This folder has no virtualenv and no `requirements.txt`. The stack needed is networkx,
  pandas, colorama and graphviz; on this machine
  `/home/zhangxujie/miniconda3/envs/ai4system/bin/python` has all four (the base conda env and
  the `zxj` env lack networkx and graphviz respectively).
- Run it **from this directory**: `make_nx_graph` reads `profiles/cost.csv` and
  `profiles/throughput.csv`, the five configs are addressed as `examples/config/*.json`, and
  results are written to `paths/` and `evals/` relative to the working directory.

### One command: evaluate a strategy file (~4 s)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/cloudcast && \
STRATEGY=/abs/path/to/my_strategy.py && \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import contextlib, io, json, sys
import evaluator
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    result = evaluator.evaluate(sys.argv[1])
open("/tmp/cloudcast_eval_verbose.log", "w").write(buf.getvalue())
print(json.dumps(result, indent=2))
' "$STRATEGY"
```

The JSON on stdout is the result; the ~1000 lines of simulator output that `evaluate()` prints
go to `/tmp/cloudcast_eval_verbose.log` (run the same snippet without the `redirect_stdout`
wrapper to watch them live).

### What the tested file must define

- A module-level `search_algorithm(src, dsts, G, num_partitions)`. A file without it is
  reported as `Missing search_algorithm function`, before any simulation runs.
- It must build and return its **own** topology object: the evaluator only reads
  `bc_t.src`, `bc_t.dsts`, `bc_t.num_partitions` and `bc_t.paths`, and writes the latter to
  `paths/<config>/search_algorithm.json` as
  `{dst: {"0": [[src, dst, edge_attrs], ...], "1": [...], ...}}`.
- Copy the `BroadCastTopology` from `initial_program.py`, not the one in `broadcast.py`. The
  latter initializes its partitions with `SingleDstPath().fromkeys(range(n))`, i.e. integer
  keys, while every consumer indexes with `str(partition)`; using it fails immediately with
  `KeyError: '0'` on the first `append_dst_partition_path` (verified).

### Result fields

| field | meaning |
| --- | --- |
| `combined_score` | `1 / (1 + total_cost)` — the value evolution maximises |
| `runs_successfully` | `successful_configs / (successful_configs + failed_configs)` |
| `total_cost` | sum of the five per-config costs |
| `avg_cost` | `total_cost / successful_configs` |
| `max_transfer_time` | **sum** of the five per-config max transfer times, despite the name |
| `time_score` | `1 / (1 + max_transfer_time)`; reported but not used by `combined_score` |
| `successful_configs` / `failed_configs` | counts over the five configs |

Failure is always reported inside the dict and never by the exit code, which stays 0:
`{"combined_score": 0.0, "runs_successfully": 0.0, "error": ...}` for a missing
`search_algorithm`, an unloadable file, or any config that raises. The first failing config
aborts the remaining ones (`break`), so a partially evaluated run is still scored 0.

Reference run on `initial_program.py`: `combined_score = 0.000955`,
`total_cost = $1045.86` (`avg_cost = $209.17`), `max_transfer_time = 4461.43` (a sum:
1440.00 + 450.00 + 1028.57 + 685.71 + 857.14), per-config costs
$165.02 / $144.94 / $161.47 / $268.85 / $305.57, ~4 s.

### Side effects

Every evaluation writes `paths/<config>/search_algorithm.json` (five files, ~76 KB total) and
creates an empty `evals/<config>/` for each config, in the working directory. This folder has
no `.gitignore`, so clean those two directories up between batches.
