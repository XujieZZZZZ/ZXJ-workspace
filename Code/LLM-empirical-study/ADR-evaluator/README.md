# ADR-evaluator

Standalone, Docker-free copies of the ADRS benchmark evaluators, used to score the
LLM-generated programs in `../data/initial-code/`.

## Why this exists

The upstream benchmarks under `skydiscover/benchmarks/ADRS/` are written as
*containerized* evaluators: each task ships an `evaluator/` directory that is the
Docker build context, and `evaluate.sh` runs `python /benchmark/evaluator.py` with
data resolved against `/benchmark`.

This machine has **no Docker and no sudo**, but the evaluators themselves are plain
Python and previous runs on this host
(`skydiscover/outputs/adaevolve/llm_sql_0825_1331/`) already executed them as host
Python. This directory reproduces that path explicitly and reproducibly.

Nothing under `skydiscover/benchmarks/ADRS/` was modified. Everything here is a copy.

## Layout

```
ADR-evaluator/
├── run_eval.py              unified driver
├── requirements.txt
└── tasks/
    ├── prism/               evaluator.py, wrapper.py, initial_program_reference.py
    ├── cloudcast/           evaluator.py, wrapper.py, utils.py, simulator.py,
    │                        broadcast.py, profiles/, examples/config/
    ├── txn_scheduling/      evaluator.py, wrapper.py, txn_simulator.py, workloads.py
    ├── llm_sql/             evaluator.py, wrapper.py, solver.py, utils.py,
    │                        datasets/, initial_program.py
    └── cant-be-late/        evaluator.py (adapted), sim_worker.py, simulator/
```

Each task directory holds its evaluator plus **every dataset it reads except the
`cant-be-late` traces**, which are the 153 MB simulation corpus described below.

## Usage

```bash
# one task
.venv/bin/python run_eval.py --task prism --program /path/to/program.py

# every program in a folder; the task is inferred from a "<task>__*.py" filename
.venv/bin/python run_eval.py --program-dir ../data/initial-code --out ../output

# sanity check: score the upstream reference seed of every task
.venv/bin/python run_eval.py --all-reference --out /tmp/reference
```

Results land in `--out` (default `ADR-evaluator/results/`) as one JSON per program
plus a `summary.json`, with the evaluator's full stdout/stderr kept in a matching
`.log`. The driver finds the verdict by taking the last container-protocol JSON
object on stdout, which every evaluator emits.

## Environment

`.venv` is a virtualenv over the `zxj` conda interpreter with
**`--system-site-packages`**, so it inherits `numpy`, `scipy`, `torch`, `pulp`,
`yaml`, `tqdm`, `plotly`, `filelock`, `colorama`, `psutil`, `matplotlib`, … and only
overrides what the benchmarks need pinned:

```
pandas >= 2.0, < 3     # pandas 3 raises on the llm_sql reorder path
numpy  < 2
networkx >= 3.2, < 3.4 # cloudcast's requirement
```

`pandas 3.x` breaks `llm_sql` with
`TypeError: Invalid value [...] for dtype 'int64'`; the earlier successful run on
this host predates that upgrade.

## Data

| task | data | source |
|---|---|---|
| `cloudcast` | `profiles/{cost,throughput}.csv`, `examples/config/*.json` (3.1 MB) | `benchmarks/ADRS/cloudcast/download_dataset.sh` pulls these from HuggingFace, which is unreachable from here. Copied from the local checkout at `wyq/ai4system/skydiscover/benchmarks/ADRS/cloudcast/evaluator/`. |
| `llm_sql` | `datasets/{movies,beer,BIRD,PDMX,products}.csv` (67 MB) | copied from the upstream evaluator |
| `txn_scheduling`, `prism` | none | self-contained |
| `cant-be-late` | `simulator/data/real/**` (153 MB traces) + vendored `simulator/sky_spot` | copied from the upstream task |

`cant-be-late`'s upstream `simulator/` is 1.2 GB, almost all of it `exp/` and
`scripts/` run artifacts. Only `main.py`, `sky_spot/`, `configs/` and `data/` are
needed to run a simulation, and only those were copied.

## What was changed relative to upstream

Only `cant-be-late/evaluator.py` was edited, and only to remove a dependency on the
`skydiscover` package so it can run standalone:

* `from skydiscover.evaluation.evaluation_result import EvaluationResult` was
  **inlined verbatim as a local dataclass** (upstream imports it from the
  `skydiscover` package, which is not importable from this directory).
* The `__main__` block now runs `evaluate_stage1` → `evaluate_stage2` and prints one
  container-protocol JSON object, matching what `wrapper.run()` produces for the
  other four tasks, so `run_eval.py` can parse all five identically.

Every other evaluator file is a byte-for-byte copy, and the scoring logic is
untouched in all five.

### Evaluator call contracts

| task | program must provide | scored by |
|---|---|---|
| `prism` | `compute_model_placement(gpu_num, models) -> dict[int, list[Model]]` | 50 seeded cases; `1/avg_kvpr + success_rate` |
| `cloudcast` | `search_algorithm(src, dsts, G, num_partitions) -> BroadCastTopology` | 5 configs; `1/(1+total_cost)` |
| `txn_scheduling` | `get_random_costs() -> (makespan, [sched x3])` | `1000/(1+makespan)*1000` |
| `llm_sql` | `Evolved().reorder(df, ...) -> (df, info)` | `0.95*hit_rate + 0.05*(12-min(12,rt))/12` |
| `cant-be-late` | a `Strategy` subclass with `_step(last, has_spot)` | `-avg_cost - 0.25*std_cost` |

`BroadCastTopology` partition keys **must be strings** — the evaluator looks them up
as `str(partition_id)`, so a program must define its own class with string keys (the
`broadcast.py` helper uses integer keys and would fail validation).
