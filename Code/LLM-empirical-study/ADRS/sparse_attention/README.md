# OpenEvolve for Sparse Attention Design

## Setup

### 1. Fetch the simulator submodule
git submodule update --init --recursive

### 2. Replace your `openevolve-run.py` file with the one provided in this directory.
This has 2 line change for handling cuda based processes.

### 3. Install dependencies:
```
conda init
pip install torch 
pip install pyyaml numpy openai scipy transformers matplotlib pandas seaborn datasets rouge nltk bert_score jieba fuzzywuzzy python-Levenshtein
pip install flash-attn --no-build-isolation
```

### Sample command line
```
python ./openevolve-run.py  ./sparse-attention-hub/sparse_attention_hub/sparse_attention/research_attention/maskers/openevolve/openevolve_masker.py ./evaluator.py --config ./config_3.yaml --iterations 10

```

---

## Evaluation only (no evolution run)

`evaluator.py` is directly runnable — `python evaluator.py <masker_file>` is a thin `argv[1]`
wrapper around `evaluate(program_path)` — so no extra runner is needed.

**Status: it cannot run in this checkout yet.** Three separate gaps, each verified:

- `sparse-attention-hub/` is empty — the submodule was never fetched, so
  `import sparse_attention_hub…` raises `ModuleNotFoundError`. That import sits at
  `evaluator.py:214`, *outside* the `try`, so you get a traceback rather than the graceful
  `combined_score: -100` fallback (that fallback only covers exceptions raised inside
  `run_benchmark_and_collect_metrics`). Fix with `git submodule update --init --recursive`.
- `flash_attn`, `rouge`, `bert_score`, `jieba` and `fuzzywuzzy` are installed in neither conda
  env on this machine (`ai4system` also lacks `nltk`), and the adapter hardcodes
  `attn_implementation="flash_attention_2"`.
- The model is hardcoded to `meta-llama/Llama-3.1-8B-Instruct` (gated on HF, so a token is
  needed) and runs on CUDA.

Once the submodule and packages are in place, run it with an **absolute** path to the masker
file, from this directory:

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/sparse_attention && \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python evaluator.py /abs/path/to/openevolve_masker.py
```

A relative path does **not** work: `evaluate()` does `os.chdir("./sparse-attention-hub/")` before
its `os.path.isfile(program_path)` check, so `./sparse-attention-hub/…/openevolve_masker.py`
(as in the sample command above) resolves against the wrong directory and dies with
`FileNotFoundError: No such file: …`. That same `chdir` also means the process's working
directory is only restored on the success path — any exception escaping `evaluate()` leaves it
inside `sparse-attention-hub/`.

### What the tested file must define

A class `OpenEvolveMasker`. The evaluator loads the file and swaps it into the masker registry:

```python
MaskerRegistry._registry[OpenEvolveMaskerConfig] = module.OpenEvolveMasker
```

so it replaces the built-in implementation of the OpenEvolve masker inside the four-masker
composition (`LocalMaskerConfig(0.001)` + `SinkMaskerConfig(0.001)` + `OracleTopKConfig(0.05)`
+ `OpenEvolveMaskerConfig()`). Everything else — model, benchmarks, request sizes — is fixed in
`evaluator.py`; the strategy file only contributes that class.

### Contract check that runs today

With the submodule absent, the checks that are still meaningful are syntax, loadability, and the
presence of the class. This reports which of those holds and treats the missing-hub import as
"skip" rather than a failure:

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/sparse_attention && \
STRATEGY=/abs/path/to/openevolve_masker.py \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python - <<'PY'
import ast, importlib.util, os, sys, traceback
p = os.environ["STRATEGY"]
try:
    ast.parse(open(p).read(), p)
except SyntaxError as e:
    print(f"FAIL syntax: {e}"); sys.exit(1)
print("PASS syntax")
spec = importlib.util.spec_from_file_location("cand_masker", p)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except ModuleNotFoundError as e:
    print(f"SKIP exec: import blocked ({e}) - expected until the submodule is populated")
    sys.exit(0)
except Exception:
    print("FAIL exec:"); traceback.print_exc(); sys.exit(1)
cls = getattr(mod, "OpenEvolveMasker", None)
if cls is None or not isinstance(cls, type):
    print(f"FAIL symbol: OpenEvolveMasker is {cls!r}, expected a class"); sys.exit(1)
print(f"PASS symbol: OpenEvolveMasker = {cls.__module__}.{cls.__qualname__}")
PY
```

Verified against four inputs: a stub defining the class → `PASS syntax` + `PASS symbol`; a file
importing from `sparse_attention_hub` → `PASS syntax` + `SKIP exec`; a syntax error → `FAIL
syntax` (exit 1); a file without the class → `PASS syntax` + `FAIL symbol` (exit 1).

### How the score is computed

Each run loads the model and runs two benchmarks (`LongBench(["passage_retrieval_en"])` and
`Ruler(["4096"])`), each capped at `max_requests=2`, `max_context_length=16000`, writing
`research_attention_density` and `research_attention_output_error` per layer into
`micro_metrics.jsonl`. Per benchmark: `density = -mean(density)`, `error = -mean(error)`,
`combined_score = -(mean_error + mean_density) / 2`; the two benchmarks are then averaged
weight-for-weight. So the score is **negative**, in `(-100, 0]`, and *higher (closer to zero) is
better* — a sparse, low-error masker scores near 0, and the failure fallback is exactly `-100`.
Run artefacts land in `openevolve_results/<n>/` with `n` incrementing per evaluation, relative
to the chdir'd directory (i.e. under `sparse-attention-hub/`).