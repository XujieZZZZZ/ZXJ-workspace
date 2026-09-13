# Adaptive Weight Compression 

## Note: Work in Progress

This code is currently **work in progress** and will be shared once the research work is officially released. The implementation of `ptq.py` is based on a heavily modified version of [SpinQuant](https://github.com/facebookresearch/SpinQuant). 

The complete implementation including the proprietary adaptive quantization algorithm and optimized kernels will be made available upon release of the research work.

---

## Evaluation only (no evolution run)

**Status: the end-to-end evaluation cannot run in this checkout.** `bq_program.py` shells out
to `torchrun ... ptq.py ...`, and neither `ptq.py`, the optimized rotation (`8B_R.bin`) nor the
`meta-llama/Meta-Llama-3-8B` weights ship with this example. Everything below was verified
against what is present.

### How the pieces fit

- `bq_evaluator.evaluate(program_path)` is the OpenEvolve entry point (no CLI, no OpenEvolve
  import). It runs `program.run_compression()` in a subprocess with a **300 s** timeout and
  reads back `bitrate`, `wikitext_ppl`, `ptb_ppl`.
- `bq_program.run_compression()` writes the evolved source string
  `adaptive_bitrate_model_code` to `adaptive_bitrate_model.py` **in the working directory**,
  then runs `torchrun --nproc_per_node=<#GPUs> ptq.py --input_model meta-llama/Meta-Llama-3-8B
  ... --use_bq`, streaming the child's output and scraping `Average bitrate:`, `wikitext:` and
  `ptb:` out of its stdout.
- So run from this directory: `ptq.py` is resolved relative to the cwd, and
  `adaptive_bitrate_model.py` is written there too.

### The full command (runnable once `ptq.py` and its assets exist)

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/hp_quantization && \
STRATEGY=/abs/path/to/my_strategy.py && \
PATH=/home/zhangxujie/miniconda3/envs/ai4system/bin:$PATH \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python -c '
import json, sys, bq_evaluator
print(json.dumps(bq_evaluator.evaluate(sys.argv[1]), indent=2))
' "$STRATEGY"
```

Note the explicit `PATH`: `run_compression` spawns the child with `shell=True`, so `torchrun`
has to be on `PATH`, which passing the interpreter path alone does not give you (without it the
child dies immediately with `/bin/sh: 1: torchrun: not found`, return code 127). With `PATH`
set it instead fails with `can't open file '.../ptq.py': No such file or directory` on every
rank — verified, and the state of this checkout today. Both cases surface as
`ValueError: could not convert string to float: 'N/A'`, because unparsed metrics stay `"N/A"`.

### Contract check that runs today (~2 s, no GPU, no model)

This only exercises the interface of the evolved function, not its quality, but it catches a
malformed or broken `adaptive_bitrate_model_code` before spending a quantisation run on it:

```bash
cd /home/zhangxujie/ai4research/ZXJ-workspace/Code/LLM-empirical-study/ADRS/hp_quantization && \
STRATEGY=/abs/path/to/my_strategy.py \
/home/zhangxujie/miniconda3/envs/ai4system/bin/python - <<'PY'
import importlib.util, os, torch
p = os.environ["STRATEGY"]
spec = importlib.util.spec_from_file_location("cand", p)
cand = importlib.util.module_from_spec(spec); spec.loader.exec_module(cand)
code = getattr(cand, "adaptive_bitrate_model_code", None)
assert isinstance(code, str) and code.strip(), \
    "file must define `adaptive_bitrate_model_code` (a Python source string)"
ns = {}
exec(compile(code, "adaptive_bitrate_model_code", "exec"), ns)
fn = ns["adaptive_bitrate_model"]
torch.manual_seed(0)
W = torch.randn(256, 256); X = torch.randn(1024, 256)   # weights [out, in], inputs [tokens, in]
h = torch.rand(W.shape[0]); m = torch.rand(W.shape[0])  # per-column hessian / magnitude scores
ratio, rank = fn(X, W, h, m, 0)
ratio = float(ratio); rank = torch.as_tensor(rank).flatten()
ok_ratio = 0.0 <= ratio <= 1.0
ok_rank = rank.numel() == h.numel() and torch.equal(rank.sort().values, torch.arange(h.numel()))
print(f"{p}: ratio={ratio:.4f} in[0,1]={ok_ratio} | rank len={rank.numel()} permutation={ok_rank}")
PY
```

Verified on the shipped `bq_program.py`: `ratio=0.1200 in[0,1]=True | rank len=256
permutation=True`. A file without the string fails with the assertion message; a string with
invalid Python fails with a `SyntaxError` pointing into the embedded code.

### Scoring

`get_combined_score(bitrate, ptb_ppl, wikitext_ppl)` first applies hard cutoffs — `bitrate >
2.6`, `wikitext_ppl > 10.5` or `ptb_ppl > 18` returns `0.0` — then returns
`0.5 * norm(wikitext) + 0.3 * norm(ptb) + 0.2 * norm(bitrate)` with `norm(wikitext) =
1 - (x - 6) / 4.5`, `norm(ptb) = 1 - (x - 10) / 8`, `norm(bitrate) = 1 - (x - 2) / 0.6` (all
floored at 0). The score is `1.0` only at `bitrate ≤ 2.0, ptb ≤ 10, wikitext ≤ 6`, and `0.0` at
the cutoffs themselves. The comment above the function claims weights 0.5 / 0.1 / 0.4; the code
and the config's system prompt agree on 0.5 / 0.3 / 0.2. Checked numerically: a stub returning
`(2.40, 14.0, 8.0)` scores `0.494444`, and `bitrate=2.61`, `ptb=19.0`, `wikitext=11.0` each
score `0.0`.

Two inconsistencies worth knowing before tuning anything: the config sets
`evaluator.timeout: 900` but the timeout actually enforced on the compression subprocess is the
hardcoded 300 s in `bq_evaluator.py:174`, which is far too short for the 8B path it launches
(`bq_program.py` keeps a commented-out `meta-llama/Llama-3.2-1B` configuration, presumably the
intended quick path). And `evaluate()` reports **every** failure as
`{"bitrate": 0.0, "ptb_ppl": 0.0, "wikitext_ppl": 0.0, "eval_time": 0.0, "combined_score": 0.0}`
— there is no `error` key and the exit code stays 0, so a crashed evaluation is
indistinguishable from a genuinely terrible one by looking at the result alone; the child's
stdout/stderr is printed by the evaluator and is the only place the cause appears.