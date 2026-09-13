# Can't-Be-Late (NSDI'24)

This folder hosts the OpenEvolve reproduction of the “Can’t Be Late” spot/on-demand scheduling problem. It contains the evolution driver, the simulator, and utilities for large-scale evaluation.

---

## Local setup

1. **Install simulator dependencies and unpack the traces.**

   ```bash
   cd openevolve/examples/ADRS/cant-be-late/simulator
   uv sync --active
   mkdir -p data
   [ -d data/real ] || tar -xzf real_traces.tar.gz -C data
   ```

2. **Provide the API keys required by the prompts** (either export them manually or source a `.env`).

   ```bash
   export OPENAI_API_KEY=...
   export GEMINI_API_KEY=...
   ```

3. **(Optional) Run an evolution round.**

   ```bash
   cd openevolve/examples/ADRS/cant-be-late
   uv run openevolve-run initial_greedy.py evaluator.py \
     --config config.yaml \
     --output openevolve_output \
     --iterations 100 \
     --log-level INFO
   ```

   The first iteration may score poorly until the evaluator finishes loading every trace.

---

## Remote full evaluation with SkyPilot

We provide a SkyPilot workflow that launches a 64 vCPU `c6i.16xlarge`, installs the project via `uv`, runs `full_eval.py`, and copies the JSON report back to your workstation.

### Prerequisites

```bash
pip install "skypilot[aws]"
sky check
```

Ensure AWS credentials are available so `sky` can provision the instance.

### Launch the evaluation

```bash
python scripts/run_skypilot_full_eval.py --cluster adrs-eval
```

The script streams logs, compares the target strategy against both `initial_greedy.py` and `referenced_up.py`, downloads `skypilot_artifacts/full_eval_remote.json`, and prints a concise emoji summary (average cost, improvement ranges, overhead = 0.02 slice, etc.).

To tear the node down afterwards:

```bash
python scripts/run_skypilot_full_eval.py --cluster adrs-eval --teardown
# or
sky down adrs-eval -y
```

---

## Evaluation only (no evolution run)

To score an existing strategy file you do not need the OpenEvolve loop, a config, or any
LLM API key — `evaluator.py` is a plain module and `full_eval.py` is a CLI wrapper around it.

Two environment notes:

- Use the interpreter from the simulator venv (`simulator/.venv/bin/python`). It already has
  numpy/pandas/wandb and has no `pip`, so do not try to install into it.
- `evaluator.py` imports `openevolve.evaluation_result.EvaluationResult` at module level.
  Where OpenEvolve is not installed, prepend `PYTHONPATH=shims` so the stub package in
  `shims/` is used; the evaluator source itself stays untouched. With a real OpenEvolve
  installation, drop the prefix.

### What the strategy file must expose

`main.py` loads the file with `importlib`; the subprocess always runs with cwd =
`simulator/`, so the file's own `from sky_spot...` imports resolve. Beyond that it needs:

- one class subclassing `sky_spot.strategies.strategy.Strategy`, with
  `_step(self, last_cluster_type, has_spot) -> ClusterType`, a `NAME`, and a
  `_from_args(cls, parser)` classmethod (see `initial_greedy.py`);
- if the file defines several `Strategy` subclasses, the loader takes the **alphabetically
  first** one (`dir()` order) — keep exactly one;
- `# EVOLVE-BLOCK` markers matter only for evolution edits, not for evaluation;
- scoring is `evaluate_stage2` only. The cheaper `evaluate_stage1` gate (compile the file and
  look for `class` / `Strategy` / `_step`) is applied by the cascade evaluator, not by routes
  2 and 3 below.

Paths in the commands below follow the upstream OpenEvolve layout; substitute the directory
that contains this README.

### 1. Single trace, single config (sanity check, ~3 s)

```bash
cd openevolve/examples/ADRS/cant-be-late/simulator
.venv/bin/python main.py \
  --strategy-file=/abs/path/to/my_strategy.py --env=trace \
  --trace-file=data/real/ddl=search+task=48+overhead=0.02/real/us-west-2a_k80_1/traces/random_start/0.json \
  --task-duration-hours=48 --deadline-hours=52 --restart-overhead-hours=0.02 --silent
```

The cost is the value after `mean:` in the final line. This is the exact command
`sim_worker.run_single_simulation` issues, one subprocess per (trace, config) pair.

### 2. Score a strategy (what the evolution loop calls)

```bash
cd openevolve/examples/ADRS/cant-be-late
PYTHONPATH=shims simulator/.venv/bin/python evaluator.py /abs/path/to/my_strategy.py
```

`evaluate_stage2` sweeps `ENV_PATHS` (4 envs) × `CHANGEOVER_DELAYS` (0.02 / 0.2 / 0.4) ×
`JOB_CONFIGS` (d=48 h with dl = 52 / 70 / 92 h) × `TRACE_TARGET` (30) traces = 1080
simulations (≈2 min on 20 cores), run through a process pool, and prints one metrics JSON:

- `avg_cost`, `cost_std`, `min_cost`, `max_cost` over all runs;
- `score = -avg_cost` and `combined_score = score - 0.25 * cost_std` — the number evolution
  maximises;
- `scenario_stats` per (env, duration, deadline, overhead) cell.

A single run that crashes, exceeds 300 s, or prints no `mean:` aborts everything with
`runs_successfully: 0` and `score: -100000` (the `error` field says which trace failed).

Knobs: `TRACE_TARGET`, `ENV_PATHS`, `CHANGEOVER_DELAYS`, `JOB_CONFIGS` at the top of
`evaluator.py`; `EVALUATOR_MAX_WORKERS` (default 48, capped at `cpu_count`) and
`EVALUATOR_TIMEOUT` env vars; `EVALUATOR_PROGRESS=1` for a stderr progress counter.

### 3. Full report with baseline comparison

```bash
PYTHONPATH=shims simulator/.venv/bin/python full_eval.py /abs/path/to/my_strategy.py \
  --baseline initial_greedy.py --baseline referenced_up.py \
  --output /tmp/report.json --progress --log-level WARNING
```

- `--trace-cap N` sets traces per env per overhead; omitting it means "all eligible traces"
  (all 300 here — every trace is 92.3 h, so nothing is filtered out). `--trace-cap 30` gives
  270 sims ≈ 0.5 min per strategy on 20 cores; the default (no cap) is 10× that, ≈ 5.5 min.
- Always pass `--baseline` explicitly: the built-in default is an `openevolve/examples/...`
  path that does not exist in this checkout.
- `full_eval.py` narrows `ENV_PATHS` to a single env (`us-west-2b_k80_1`), so its averages do
  not match route 2's four-env averages.
- Report layout: `summary` (target), plus per baseline a `summary`, `comparison`
  (per-trace `baseline_cost` / `new_cost` / `improvement` / `improvement_ratio`, with
  `avg_improvement_ratio`, `min/max`), and `overhead_0_02` (stats restricted to d = 0.02).

Verified example (`--trace-cap 30`, one baseline): `referenced_up.py` averages $136.06 vs
`initial_greedy.py` $128.94, i.e. −5.5 % on the per-trace mean.

---

## One command: full evaluation of a strategy file

Set `STRATEGY` to your file — its interface must match `initial_greedy.py` (see "What the
strategy file must expose"). Everything else is pinned: simulator venv, OpenEvolve shim, the
whole trace set, both baselines, and a JSON report. Measured: **~5.5 min per strategy, ~16 min
for the whole command** (2700 runs each: 3 deadlines × 3 overheads × 300 traces on
`us-west-2b_k80_1`, 20 cores).

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/cant-be-late && \
STRATEGY=/abs/path/to/my_strategy.py && \
PYTHONPATH=shims simulator/.venv/bin/python full_eval.py "$STRATEGY" \
  --baseline initial_greedy.py --baseline referenced_up.py \
  --output /tmp/full_eval_report.json --progress --log-level WARNING && \
simulator/.venv/bin/python -c '
import json
d = json.load(open("/tmp/full_eval_report.json"))
print(json.dumps(d["summary"], indent=2))
for b in d["baselines"]:
    print(b["path"], json.dumps({k: v for k, v in b["comparison"].items() if k != "per_trace"}))
'
```

The command exits non-zero if `STRATEGY` crashes or fails to finish any run, so a broken file
stops before the report is printed. `/tmp/full_eval_report.json` additionally holds
`baselines[].comparison.per_trace` (per-trace `baseline_cost` / `new_cost` / `improvement`),
which is what you want for significance tests or plots.

Reference run of exactly this command, with `STRATEGY=referenced_up.py`:
`avg_cost = $137.01 ± $33.35` (n = 2700) against `initial_greedy.py` `$129.92`, i.e.
−5.4 % on the per-trace mean; the `referenced_up.py` baseline reports 0.00 improvement on
every trace, as it must. The whole command took 16 min.

For a quick pass instead, append `--trace-cap 30` to `full_eval.py` (~0.5 min per strategy); to
score exactly the way the evolution loop does, use route 2 above instead (4 envs, 1080 runs).
