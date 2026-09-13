GPU_MEM_SIZE = 80 # GB

# EVOLVE-BLOCK-START
"""
Fluid residency planner (LLM solution for the PRISM paper).

The solution replaces the binary "time share or space share" choice by a residency
planner that decides *which full models are space-shared into GPU memory*:

  * every candidate model is scored by the pressure it adds per unit of memory it
    occupies, p_m * expected_arrivals_m / w_m, and candidates are promoted greedily in
    decreasing order of that score (p_m is the SLO priority, i.e. 1/slo_m here,
    a_m the request rate, w_m the GPU parameter footprint);
  * a memory reserve of a fixed fraction of aggregate GPU memory is kept free so that
    promotions can overlap with execution (make-before-break) instead of forcing
    active work to be terminated -- it is only spent once no model fits behind it;
  * models that cannot be promoted stay queued and are not forced onto a full GPU.

Mapped onto the single-shot placement interface of this task, one planning epoch is
one call: the resident set is the placement, and assigning each promoted model to the
GPU that leaves the lowest resulting KV-cache pressure is the space-sharing decision.
"""

RESERVE_FRACTION = 0.10  # share of each GPU kept free for transition overlap


def compute_model_placement(gpu_num, models):
    """
    Compute a model placement that minimizes the maximum KVPR across all GPUs.

    Args:
        gpu_num: Number of GPUs
        models: List of models to place

    Returns:
        A placement of models to GPUs
    """
    # 1) promote candidates in decreasing order of p_j * a_j / w_j
    candidates = sorted(
        models,
        key=lambda m: (m.req_rate / m.slo) / m.model_size,
        reverse=True)

    placement = {gpu_id: [] for gpu_id in range(gpu_num)}
    used_mem = [0.0 for _ in range(gpu_num)]
    pressure = [0.0 for _ in range(gpu_num)]   # sum of r_j / s_j per GPU

    reserve = RESERVE_FRACTION * GPU_MEM_SIZE
    # first epoch: keep the transition reserve; then, with no candidate left behind it,
    # fall back to the plain residency decision for the models that are still queued
    pending = list(candidates)
    for keep_reserve in (True, False):
        queued = []
        limit = GPU_MEM_SIZE - (reserve if keep_reserve else 0.0)
        for model in pending:
            best_gpu, best_pressure = None, float('inf')
            for gpu_id in range(gpu_num):
                free_after = limit - used_mem[gpu_id] - model.model_size
                if free_after <= 0:       # the model must still leave room for its KV cache
                    continue
                resulting = (pressure[gpu_id] + model.req_rate / model.slo) / free_after
                if resulting < best_pressure:
                    best_pressure = resulting
                    best_gpu = gpu_id

            if best_gpu is None:          # no GPU can take it: it stays queued
                queued.append(model)
                continue

            placement[best_gpu].append(model)
            used_mem[best_gpu] += model.model_size
            pressure[best_gpu] += model.req_rate / model.slo
        pending = queued

    return placement

# EVOLVE-BLOCK-END


if __name__ == "__main__":
    # Test the algorithm

    from evaluator import generate_test_gpu_models
    from evaluator import calculate_kvcache_pressure
    from evaluator import safe_float
    import numpy as np

    test_cases = generate_test_gpu_models()
    all_kvpr = []
    for i, (gpu_num, gpu_models) in enumerate(test_cases):

        results = compute_model_placement(gpu_num, gpu_models)
        max_kvpr = calculate_kvcache_pressure(results)
        all_kvpr.append(safe_float(max_kvpr))

    avg_kvpr = np.mean(all_kvpr)
    if avg_kvpr != 0:
        avg_kvpr = 1.0 / avg_kvpr


    print(f"Max KVPR: {avg_kvpr:.3f}")
