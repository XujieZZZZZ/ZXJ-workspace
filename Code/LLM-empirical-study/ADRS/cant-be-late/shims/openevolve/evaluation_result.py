"""Stub of `openevolve.evaluation_result` (only what the evaluator uses)."""


class EvaluationResult:
    """Container with `.metrics` and `.artifacts`, as used by the evaluator."""

    def __init__(self, metrics=None, artifacts=None):
        self.metrics = dict(metrics or {})
        self.artifacts = dict(artifacts or {})

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"EvaluationResult(metrics={self.metrics}, artifacts={self.artifacts})"
