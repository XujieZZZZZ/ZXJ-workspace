#!/usr/bin/env python3
"""Standalone driver for the ADRS benchmark evaluators (no Docker required).

Each task under ``tasks/`` is a self-contained copy of the upstream ADRS
evaluator (see README.md for provenance).  Every evaluator speaks the same
container-protocol JSON on stdout, so this driver just:

  1. runs ``<task>/evaluator.py <program>`` with cwd set to the task directory,
  2. captures stdout/stderr to a per-run log,
  3. parses the JSON verdict and writes it to the results directory.

Because the evaluators resolve their data (profiles, datasets, traces) relative
to their own file location, step 1 must keep the program path absolute.

Usage
-----
    # one task
    python run_eval.py --task prism --program /path/to/code.py

    # every program in a folder, task inferred from the ``<task>__*.py`` prefix
    python run_eval.py --program-dir /path/to/initial-code --out /path/to/output

    # all tasks, using the bundled reference (upstream) seeds -- sanity check
    python run_eval.py --all-reference
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.join(CURRENT_DIR, "tasks")

#: Task name -> evaluator entry file inside ``tasks/<name>/``.
TASKS = {
    "prism": "evaluator.py",
    "cloudcast": "evaluator.py",
    "txn_scheduling": "evaluator.py",
    "llm_sql": "evaluator.py",
    "cant-be-late": "evaluator.py",
}

#: Paper PDF id (from ``data/LLM_data``) -> ADRS task it is evaluated on.
PAPER_TO_TASK = {
    "f948850caef3d25f": "prism",
    "e3d82bafe7cb11e7": "cloudcast",
    "b93fea400aedf898": "cant-be-late",
    "d18c13d036b3708f": "llm_sql",
    "c252b8a901feea74": "txn_scheduling",
}

#: Wall-clock budget per task, tuned so a complete evaluation always finishes.
DEFAULT_TIMEOUT = {
    "prism": 600,
    "cloudcast": 1800,
    "txn_scheduling": 1800,
    "llm_sql": 3600,
    "cant-be-late": 7200,
}


def _split_task_prefix(name: str) -> str | None:
    """Infer the task from a ``<task>__<anything>.py`` filename."""
    stem = os.path.splitext(os.path.basename(name))[0]
    for task in TASKS:
        if stem == task or stem.startswith(f"{task}__") or stem.startswith(f"{task}_"):
            return task
    return None


def _parse_verdict(stdout: str) -> dict | None:
    """Return the last container-protocol JSON object printed on stdout."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "combined_score" in obj:
            return obj
    return None


def run_one(task: str, program: str, out_dir: str, timeout: int | None = None,
            python: str | None = None, quiet: bool = False) -> dict:
    """Evaluate *program* on *task* and return a result record."""
    if task not in TASKS:
        raise SystemExit(f"unknown task {task!r}; choose from {sorted(TASKS)}")

    task_dir = os.path.join(TASKS_DIR, task)
    entry = os.path.join(task_dir, TASKS[task])
    program = os.path.abspath(program)
    python = python or sys.executable
    timeout = timeout or DEFAULT_TIMEOUT.get(task, 3600)

    if not os.path.exists(program):
        raise SystemExit(f"program not found: {program}")

    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(program))[0]
    # Programs are named "<task>__<paper-id>.py"; don't repeat the task prefix.
    tag = stem if stem.startswith(task) else f"{task}__{stem}"
    log_path = os.path.join(out_dir, f"{tag}.log")

    started = time.time()
    if not quiet:
        print(f"[{task}] evaluating {program}", flush=True)

    timed_out = False
    try:
        proc = subprocess.run(
            [python, entry, program],
            cwd=task_dir,               # evaluators resolve data relative to cwd/file
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        returncode = -1

    elapsed = time.time() - started
    verdict = _parse_verdict(stdout)

    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(f"# task: {task}\n# program: {program}\n")
        fh.write(f"# started: {datetime.now(timezone.utc).isoformat()}\n")
        fh.write(f"# elapsed_seconds: {elapsed:.1f}\n# returncode: {returncode}\n")
        fh.write(f"# timed_out: {timed_out}\n")
        fh.write("=" * 70 + "\n# STDOUT\n" + "=" * 70 + "\n")
        fh.write(stdout)
        fh.write("\n" + "=" * 70 + "\n# STDERR\n" + "=" * 70 + "\n")
        fh.write(stderr)

    if verdict is None:
        verdict = {
            "status": "error",
            "combined_score": 0.0,
            "metrics": {"combined_score": 0.0},
            "artifacts": {
                "error": "timeout" if timed_out else "no container-protocol JSON on stdout",
                "returncode": str(returncode),
            },
        }

    record = {
        "task": task,
        "program": program,
        "program_name": os.path.basename(program),
        "paper_id": next((pid for pid, t in PAPER_TO_TASK.items() if t == task), None),
        "status": verdict.get("status", "unknown"),
        "combined_score": verdict.get("combined_score"),
        "metrics": verdict.get("metrics", {}),
        "artifacts": verdict.get("artifacts", {}),
        "elapsed_seconds": round(elapsed, 1),
        "returncode": returncode,
        "timed_out": timed_out,
        "log_file": os.path.basename(log_path),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    result_path = os.path.join(out_dir, f"{tag}.json")
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)

    if not quiet:
        print(
            f"[{task}] status={record['status']} "
            f"combined_score={record['combined_score']} "
            f"({elapsed:.1f}s) -> {result_path}",
            flush=True,
        )
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--task", choices=sorted(TASKS), help="task to evaluate")
    src.add_argument("--program-dir", help="folder of <task>__*.py programs")
    src.add_argument("--all-reference", action="store_true",
                     help="run the bundled upstream reference seed of every task")
    ap.add_argument("--program", help="program to evaluate (with --task)")
    ap.add_argument("--out", default=os.path.join(CURRENT_DIR, "results"),
                    help="results directory (default: ADR-evaluator/results)")
    ap.add_argument("--timeout", type=int, default=None,
                    help="per-task timeout in seconds (default: per-task budget)")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter used to launch the evaluator")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    jobs: list[tuple[str, str]] = []

    if args.all_reference:
        for task in TASKS:
            # llm_sql keeps the upstream name because its evaluator imports it.
            for name in ("initial_program_reference.py", "initial_program.py"):
                ref = os.path.join(TASKS_DIR, task, name)
                if os.path.exists(ref):
                    jobs.append((task, ref))
                    break
            else:
                print(f"[skip] no reference seed for {task}", file=sys.stderr)
    elif args.program_dir:
        for name in sorted(os.listdir(args.program_dir)):
            if not name.endswith(".py") or name.endswith("_reference.py"):
                continue
            task = _split_task_prefix(name)
            if task is None:
                print(f"[skip] cannot infer task from {name}", file=sys.stderr)
                continue
            jobs.append((task, os.path.join(args.program_dir, name)))
        if not jobs:
            raise SystemExit(f"no <task>__*.py programs found in {args.program_dir}")
    else:
        if not args.program:
            raise SystemExit("--program is required with --task")
        jobs.append((args.task, args.program))

    records = []
    for task, program in jobs:
        records.append(run_one(task, program, args.out, timeout=args.timeout,
                               python=args.python, quiet=args.quiet))

    summary_path = os.path.join(args.out, "summary.json")
    if os.path.exists(summary_path) and not args.all_reference:
        try:
            with open(summary_path, encoding="utf-8") as fh:
                merged = {r["task"]: r for r in json.load(fh).get("results", [])}
        except (json.JSONDecodeError, OSError):
            merged = {}
    else:
        merged = {}
    for rec in records:
        merged[rec["task"]] = rec

    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump({"results": list(merged.values())}, fh, indent=2, ensure_ascii=False)

    print("\n" + "=" * 68)
    print(f"{'task':<18}{'status':<10}{'combined_score':>16}   seconds")
    print("-" * 68)
    for rec in records:
        print(f"{rec['task']:<18}{rec['status']:<10}"
              f"{rec['combined_score']:>16.6f}   {rec['elapsed_seconds']:.1f}")
    print("=" * 68)
    print(f"results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
