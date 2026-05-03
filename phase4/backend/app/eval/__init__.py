"""Ranking-quality eval harness.

A small, hand-labeled query set + offline scoring so we can detect
ranking regressions before they ship. Specifically the four numbers
that matter for shopping search:

- **NDCG@5** — "are the relevant results near the top?"
- **Precision@3** — "is the first thing the user sees actually right?"
- **Hit rate** — "did we return *any* relevant result at all?"
- **Coverage** — "how many queries returned anything?"

CI calls `evaluate()` from a pytest, asserts the metrics are above the
thresholds in `app.config`, and fails the build on regression.
"""
from app.eval.harness import (
    EvalCase,
    EvalReport,
    QueryResult,
    evaluate,
    load_cases,
)
from app.eval.metrics import dcg, ndcg, precision_at_k

__all__ = [
    "EvalCase",
    "EvalReport",
    "QueryResult",
    "dcg",
    "evaluate",
    "load_cases",
    "ndcg",
    "precision_at_k",
]
