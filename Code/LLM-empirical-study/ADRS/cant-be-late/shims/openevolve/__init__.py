"""Minimal stand-in for the `openevolve` package.

`evaluator.py` imports `openevolve.evaluation_result.EvaluationResult` at module
level, so the evaluator cannot even be imported without OpenEvolve installed.
Putting this directory on `PYTHONPATH` lets `evaluator.py` / `full_eval.py` run
standalone (evaluation only, no evolution) without touching their source.

If the real OpenEvolve is installed, do not add this directory to PYTHONPATH.
"""
