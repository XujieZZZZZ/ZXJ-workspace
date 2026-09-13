# Expert Parallelism Load Balancer (EPLB)

This example demonstrates how to use OpenEvolve to optimize the Expert Parallelism Load Balancer (EPLB) algorithm.

## Setup

Install PyTorch:

```bash
uv pip install torch
```

Download the workload file from [Hugging Face](https://huggingface.co/datasets/abmfy/eplb-openevolve):

```bash
wget https://huggingface.co/datasets/abmfy/eplb-openevolve/resolve/main/expert-load.json
```

---

## Evaluation only (no evolution run)

`evaluator.py` exposes `evaluate(program_path)` and nothing else — there is no CLI and no
OpenEvolve dependency, so testing a single file is a short `python -c` wrapper. Two
prerequisites:

- `expert-load.json` (234 MB) must sit in the working directory: `WORKLOAD_PATH` is a relative
  path and it is checked at import time, so `import evaluator` raises `FileNotFoundError`
  before anything else if the file is missing.
- The interpreter needs torch. On this machine either
  `/home/zhangxujie/miniconda3/envs/ai4system/bin/python` (torch 2.10) or
  `/home/zhangxujie/miniconda3/envs/zxj/bin/python` (torch 2.12) works; the base conda env and
  the other virtualenvs here have no torch. The evaluation is CPU-only, so the CUDA build
  does not matter.

### One command: evaluate a strategy file (~21 s)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/eplb && \
STRATEGY=/abs/path/to/my_strategy.py && \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, evaluator
print(json.dumps(evaluator.evaluate(sys.argv[1]), indent=2))
' "$STRATEGY"
```

### What the tested file must define

`rebalance_experts(weight, num_replicas, num_groups, num_nodes, num_gpus)`, called as
`rebalance_experts(workload, 288, 8, 4, 32)`, returning `(phy2log, log2phy, logcnt)`. The
evaluator uses only the last two: `log2phy` is `[58, 256, 33]` int64 (replica ids, unused slots
padded with `-1`) and `logcnt` is `[58, 256]` int64 (replicas per logical expert). `weight` is a
`[58, 256]` int64 tensor. A file without the function scores 0 with
``error: Missing `rebalance_experts` function``.

### How the score is computed

`load_workloads` sums every 100 consecutive steps of the 1174-step trace into 12 workloads; the
evaluator then runs 11 pairs, rebalancing with workload *t* and measuring balancedness against
workload *t+1* (`avg_load / max_load`, summed over the 58 layers' physical experts).

- `balancedness_score` — mean over the 11 pairs.
- `speed_score` — `0.02 / avg_time`, where `avg_time` is the time of **rebalance +
  `simulate_inference`** for one pair (the timer wraps both calls, `evaluator.py:125-136`). The
  evaluator's own `simulate_inference` Python loop takes ~0.71 s of the ~1.30 s, so this term
  is capped near `0.02 / 0.71 ≈ 0.028` even for an instant rebalance.
- `combined_score` — `(balancedness_score + speed_score) / 2`, i.e. ~90 % balancedness at the
  reference point below.

Reference run on `initial_program.py`: `balancedness_score = 0.2506`, `speed_score = 0.0155`,
`combined_score = 0.1331`, per-pair balancedness spread 0.085 – 0.367, ~21 s wall clock (2 s to
parse the workload, 11 × ~1.3 s). `balancedness_score` is deterministic for a given file;
`speed_score` moves with wall-clock noise (0.0155 / 0.0157 on two consecutive runs), so compare
candidates on repeated runs rather than a single one.

Every failure mode — missing function, syntax error, or any exception raised inside the
program — returns `{balancedness_score: 0.0, speed_score: 0.0, combined_score: 0.0, error: ...}`
with exit code 0, so read the dict rather than `$?`. The `error` string carries the failing
exception message.
