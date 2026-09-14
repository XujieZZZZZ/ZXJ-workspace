GPU_MEM_SIZE = 80 # GB

# EVOLVE-BLOCK-START
"""
PRISM (human / paper) solution, adapted to the ADRS `compute_model_placement` interface.

Paper, implementation section: "For model placement, Prism sorts models in descending order of
SLO-weighted token rate (token_rate * token_size / TPOT SLO), then greedily assigns each model
to the GPU whose KV Pressure Ratio (KVPR) is minimized; it migrates only when the KVPR
improvement exceeds a threshold tau, and updates the GPU's SLO-weighted token rate and remaining
shared KV memory after each assignment."

KVPR itself is described only in prose (the formula is corrupted in the source); "from
Algorithm 1 and surrounding text, KVPR is the ratio of the GPU's aggregate SLO-weighted token
memory usage rate (w_token_rate_i) to its remaining shared KV memory (shared_kv_i), where
w_token_rate_i is accumulated as token_rate * token_size / SLO."

Interface notes: `compute_model_placement(gpu_num, models)` is a one-shot placement with no
cross-call state, so the migration rule ("migrates only when the KVPR improvement exceeds tau")
and the local request arbitration (shared per-GPU queue, TTFT-deadline chunked-prefill
scheduling) have no counterpart here and are not implemented; only the paper's placement
algorithm is. Model eviction by idle threshold likewise needs a time axis that this interface
does not provide.
"""

def compute_model_placement(gpu_num, models):
    """
    Compute a model placement that minimizes the maximum KVPR across all GPUs.

    Args:
        gpu_num: Number of GPUs
        models: List of models to place

    Returns:
        A placement of models to GPUs
    """

    # 1) Sort models by SLO-weighted token rate in descending order.
    #    PRISM: token_rate * token_size / TPOT SLO
    def slo_weighted_token_rate(m):
        return m.req_rate * m.model_size / m.slo

    sorted_models = sorted(models, key=slo_weighted_token_rate, reverse=True)

    # 2) Initialize per-GPU states
    placement = {gpu_id: [] for gpu_id in range(gpu_num)}
    shared_kv = [GPU_MEM_SIZE for _ in range(gpu_num)]      # remaining shared KV memory per GPU
    weighted_token_rate = [0.0 for _ in range(gpu_num)]     # sum of token_rate*size/SLO per GPU

    # 3) Greedy: assign each model to the GPU whose KVPR is minimized, then update that GPU's
    #    SLO-weighted token rate and its remaining shared KV memory.
    for model in sorted_models:
        best_idx = None
        best_kvpr = float('inf')

        for gpu_id in range(gpu_num):
            if model.model_size <= shared_kv[gpu_id] and shared_kv[gpu_id] > 0:
                kvpr = weighted_token_rate[gpu_id] / shared_kv[gpu_id]
                if kvpr < best_kvpr:
                    best_kvpr = kvpr
                    best_idx = gpu_id

        # Failure: if no GPU can fit, raise an error instead of overcommitting
        if best_idx is None:
            raise ValueError(
                f"Unable to place model of size {model.model_size} GB on any GPU. "
                f"Remaining per-GPU memory: {shared_kv}"
            )

        placement[best_idx].append(model)
        weighted_token_rate[best_idx] += slo_weighted_token_rate(model)
        shared_kv[best_idx] -= model.model_size

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
