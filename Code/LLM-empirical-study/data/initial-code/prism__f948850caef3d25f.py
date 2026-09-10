# EVOLVE-BLOCK-START
"""Fluid multi-LLM residency planner (static admission pass).

Source
------
paper      : Prism.md
pdf_id     : f948850caef3d25f
solution   : LLM-generated from the LLM's own (search-enabled) related work,
             ``data/LLM_data/merged_llm_re_withsearch/f948850caef3d25f.json``
             fields ``solution.idea`` and ``solution.implementation``.

What the LLM proposed
---------------------
A two-timescale serving control plane:
  * slow timescale -- a *model-residency planner* recomputes the resident set
    R from a short-term demand forecast, per-model SLO weight ``p_m``, memory
    footprint ``w_m`` and transition cost.  Models are added greedily in
    decreasing order of ``p_m * expected_arrivals / w_m`` and a fixed memory
    reserve (10% of aggregate GPU memory) is held back for make-before-break
    transition overlap.  Promotion/demotion use hysteresis so a model is
    demoted only after ``T_idle`` idle epochs;
  * fast timescale -- Orca-style iteration-level batching over the resident set,
    so a resident model never suffers a load stall.

Fidelity note (adaptation to this benchmark)
--------------------------------------------
The ADRS ``prism`` interface is a *single* call that must return one placement
of every model; there is no epoch loop, no request stream, no demotion, and no
queue.  The two-timescale controller therefore cannot be expressed literally.
We instantiate the part the interface *can* express -- the residency planner's
admission rule -- and keep its three defining ingredients:

  1. the same greedy ordering ``p_m * a_m / w_m`` (descending),
  2. the same 10% memory reserve, held back so a slot is always available for
     an incoming model rather than filled to the brim,
  3. the same balance objective the planner minimises: keep every GPU's
     reservation pressure as low as possible so the working set stays fluid.

The dynamic machinery (EWMA forecasting, ``T_idle`` hysteresis, promotion and
demotion, the bounded queue) has no counterpart in a one-shot placement and is
intentionally *not* faked here.  This is a faithful one-shot projection of the
planner, not the full control plane; scores should be read accordingly.
"""

from __future__ import annotations

GPU_MEM_SIZE = 80  # GB, matches the evaluator
PRIORITY_DENSITY_EPS = 1e-12

# The planner's own knobs, carried over verbatim from the implementation text.
MEMORY_RESERVE_FRACTION = 0.10  # "a fixed fraction (e.g., 10%) of aggregate GPU memory"


def _priority_density(model) -> float:
    """``p_m * expected_arrivals / w_m``.

    ``p_m`` is the SLO priority: a tighter SLO (smaller ``slo``) means the model
    is more urgent, so ``p_m = 1 / slo``.  Expected arrivals ``a_m`` over the
    forecast horizon is the observed request rate ``req_rate`` scaled by the
    horizon; the horizon is constant across models within one planning call, so
    it cancels in the ordering and is omitted.
    """
    return (1.0 / model.slo) * model.req_rate / ((model.model_size) + PRIORITY_DENSITY_EPS)


def _kvpr(models_on_gpu, used_mem: float) -> float:
    """Instantaneous reservation pressure of one GPU (same shape as the metric)."""
    free = GPU_MEM_SIZE - used_mem
    if free <= 0:
        return float("inf")
    weighted_rate = sum(m.req_rate / m.slo for m in models_on_gpu)
    return weighted_rate / free


def compute_model_placement(gpu_num, models):
    """Compute a model placement that minimizes the maximum KVPR across all GPUs.

    Args:
        gpu_num: Number of GPUs
        models: List of models to place

    Returns:
        A placement of models to GPUs
    """
    # Greedy admission in decreasing order of the planner's priority density
    # p_m * a_m / w_m -- the LLM's residency-planner ordering.
    ordered = sorted(models, key=_priority_density, reverse=True)

    placement: dict[int, list] = {gpu_id: [] for gpu_id in range(gpu_num)}
    used_mem = [0.0] * gpu_num

    # The reserve is held back during planning so a slot is always free for an
    # incoming model (make-before-break).  It is a *soft* budget: if a model
    # cannot be admitted within it, admission falls through to the hard limit
    # instead of dropping the model, because this interface has no queue to
    # park it in.
    soft_capacity = GPU_MEM_SIZE * (1.0 - MEMORY_RESERVE_FRACTION)

    for model in ordered:
        # Prefer the GPU with the lowest resulting reservation pressure that can
        # still accommodate the model inside the reserve.
        best_idx = None
        best_pressure = float("inf")
        for gpu_id in range(gpu_num):
            if used_mem[gpu_id] + model.model_size > soft_capacity:
                continue
            pressure = _kvpr(placement[gpu_id], used_mem[gpu_id] + model.model_size)
            if pressure < best_pressure:
                best_pressure = pressure
                best_idx = gpu_id

        if best_idx is None:
            # Reserve exhausted everywhere; fall back to the hard memory limit
            # (the bounded-queue case the controller would have queued instead).
            for gpu_id in range(gpu_num):
                if used_mem[gpu_id] + model.model_size > GPU_MEM_SIZE:
                    continue
                pressure = _kvpr(placement[gpu_id], used_mem[gpu_id] + model.model_size)
                if pressure < best_pressure:
                    best_pressure = pressure
                    best_idx = gpu_id

        if best_idx is None:
            # No GPU can host the model at all -- surface it rather than
            # silently overcommitting memory.
            raise ValueError(
                f"Unable to place model {model.model_name!r} of size "
                f"{model.model_size} GB on any of {gpu_num} GPUs. "
                f"Remaining per-GPU memory: "
                f"{[GPU_MEM_SIZE - u for u in used_mem]}"
            )

        placement[best_idx].append(model)
        used_mem[best_idx] += model.model_size

    return placement


# EVOLVE-BLOCK-END
