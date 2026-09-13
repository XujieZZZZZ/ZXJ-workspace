# Cant Be Late Multi-Region

This example demonstrates how to use OpenEvolve to optimize the Can't Be Late scheduling problem (NSDI'24) in a multi-region setting.

## Setup

1. Install simulator dependencies and unpack the real traces so the evaluator can find them:

```bash
cd openevolve/examples/ADRS/cant-be-late-multi/simulator
tar -xzf real_traces.tar.gz data
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt
```

2. Make sure you have the API keys expected by the run (replace with your own values or source a `.env` file).

```bash
source .env # If you have a .env file

echo "$GEMINI_API_KEY"
```

## Run the evolution

Change into the example directory so the generated `openevolve_output/` sits alongside the scripts:

```bash
cd openevolve/examples/ADRS/cant-be-late-multi
uv run openevolve-run initial_program.py evaluator.py --config config.yaml --output openevolve_output --iterations 100 --log-level INFO
```

The first iteration may show low scores until the evaluator finishes loading the trace data extracted above.

---

## Evaluation only (no evolution run)

`evaluator.py` has a standalone `__main__`, so one strategy file can be scored without
OpenEvolve, without `config.yaml`, and without any LLM API key. Three things about this
checkout:

- `simulator/sky_spot/strategies/__init__.py` no longer imports
  `multi_region_rc_cr_quality_bar` and `multi_region_rc_cr_threshold_optimized`: those two
  modules are missing from the checkout, and importing them made every `import sky_spot` —
  hence every simulation — fail. Put the two lines back only if you add those files.
- Set `WANDB_MODE`: `simulator/main.py` calls `wandb.init()` unconditionally at import time.
  `WANDB_MODE=disabled` is enough and writes nothing; `WANDB_MODE=offline` also works but
  leaves a `simulator/wandb/offline-run-*` directory behind for every simulation. Either way
  each simulation also drops a ~430 KB JSON detail file in `simulator/exp/` (34 per stage 2,
  ~8 MB), so clean that directory out between long batches.
- There is no virtualenv in this folder. The commands below use the single-region example's
  interpreter, which has the same dependency set (numpy / pandas / wandb / ray); substitute
  your own environment if you have one (`pip install -r simulator/requirements.txt`).

### One command: full evaluation of a strategy file (~1 min)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/cant-be-late-multi && \
STRATEGY=/abs/path/to/my_strategy.py && \
WANDB_MODE=disabled /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/cant-be-late/simulator/.venv/bin/python evaluator.py "$STRATEGY" \
  2> /tmp/multi_eval_stderr.log
```

The result JSON is printed on stdout — add `> /tmp/multi_eval_result.txt` to keep it; the
simulator logs go to the stderr file. What runs, in the same order as OpenEvolve's cascade:

- `evaluate_stage1` runs one simulation (`stage_1_quick_check`: `us-east-1a` + `us-east-1c`,
  trace `0.json`) and returns `runs_successfully: 1.0` only if it exits 0 with a parseable
  `mean:`; otherwise it returns `0.0` plus the raw simulator output.
- `evaluate_stage2` runs only after stage 1 passes: the six scenarios of `FULL_TEST_SCENARIOS`
  (2 / 2 / 3 / 3 / 5 / 9 regions, 34 simulations), averaging each scenario and then the six
  scenario averages, and returns `{"runs_successfully": 1.0, "combined_score": -avg_cost}`.
  If every scenario fails, `runs_successfully` is still `1.0` but `combined_score` is the
  sentinel `-1e9` — another reason to read the JSON rather than the exit code.
- A stage-1 failure prints `Stage 1 Failed. Skipping Stage 2.` **and still exits 0** — judge
  the run by `runs_successfully` / `combined_score` in the output, not by `$?`.

The strategy file must define one `MultiRegionStrategy` subclass (see `initial_program.py`)
with `_step(self, last_cluster_type, has_spot) -> ClusterType`; `_from_args` is inherited, and
`self.env` / `self.task` are only usable from `_step` onwards, never in `__init__`. If the
file contains several strategy classes, the loader takes the alphabetically first one.

Reference run of this checkout on `initial_program.py`: stage 1 PASSED; per-scenario averages
$128.42 / $56.58 / $64.25 / $122.84 / $110.18 / $47.99, final average cost **$88.38**,
`combined_score = -88.3779`; ~1 min (98 s on a cold first run, 51 s after the traces and the
Python caches are warm).

### Single simulation, no evaluator (~3 s)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/cant-be-late-multi/simulator && \
WANDB_MODE=disabled /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/cant-be-late/simulator/.venv/bin/python main.py \
  --strategy-file=/abs/path/to/my_strategy.py --env=multi_trace \
  --task-duration-hours=48 --deadline-hours=52 --restart-overhead-hours=0.2 \
  --trace-files data/converted_multi_region_aligned/us-east-1a_v100_1/0.json \
                data/converted_multi_region_aligned/us-east-1c_v100_1/0.json
```

One `--trace-files` path per region; the cost is the value after `mean:`. This is exactly the
command `run_simulation` issues per scenario trace, so it is the fastest way to debug a file
that fails inside stage 2.