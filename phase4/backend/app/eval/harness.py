"""Eval harness.

Loads a YAML-labeled query set, runs it through `app.search_service.search`,
and reports per-query + aggregate metrics. The labels are by *category*
or *brand* so we don't have to enumerate every product id by hand — a
result is "relevant" if any of its expected substrings shows up in the
canonical title or category.

Why this shape:

- The product graph is fixture-driven and small, so labelling at the
  category level keeps the eval set maintainable.
- Substring matching is permissive on purpose — it gives the *ranker*
  credit for surfacing anything in the right neighbourhood, which is
  what we actually care about ranking. Tighter labels can come later.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.eval.metrics import ndcg, precision_at_k
from app.search_service import SearchHit, search

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """One labeled query."""

    query: str
    relevant_terms: list[str]
    mode: str = "hybrid"
    description: str | None = None
    # Optional per-query filters mirroring /search params.
    max_price: float | None = None
    min_rating: float | None = None
    platform: str | None = None


@dataclass
class QueryResult:
    case: EvalCase
    ndcg_at_5: float
    precision_at_3: float
    hit: bool
    returned: int
    top_titles: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    cases: list[QueryResult]

    @property
    def mean_ndcg_at_5(self) -> float:
        if not self.cases:
            return 0.0
        return sum(c.ndcg_at_5 for c in self.cases) / len(self.cases)

    @property
    def mean_precision_at_3(self) -> float:
        if not self.cases:
            return 0.0
        return sum(c.precision_at_3 for c in self.cases) / len(self.cases)

    @property
    def hit_rate(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.hit) / len(self.cases)

    @property
    def coverage(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.returned > 0) / len(self.cases)

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "ndcg_at_5": round(self.mean_ndcg_at_5, 3),
                "precision_at_3": round(self.mean_precision_at_3, 3),
                "hit_rate": round(self.hit_rate, 3),
                "coverage": round(self.coverage, 3),
                "n": len(self.cases),
            },
            "cases": [
                {
                    "query": c.case.query,
                    "ndcg_at_5": round(c.ndcg_at_5, 3),
                    "precision_at_3": round(c.precision_at_3, 3),
                    "hit": c.hit,
                    "returned": c.returned,
                    "top_titles": c.top_titles[:3],
                }
                for c in self.cases
            ],
        }


# ---- Loading --------------------------------------------------------------


_DEFAULT_PATH = Path(__file__).resolve().parent / "queries.yaml"


def load_cases(path: Path | None = None) -> list[EvalCase]:
    """Parse a YAML eval set into EvalCase objects."""
    target = path or _DEFAULT_PATH
    with open(target, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []

    cases: list[EvalCase] = []
    for entry in raw:
        if not isinstance(entry, dict) or "query" not in entry or "relevant" not in entry:
            logger.warning("Skipping malformed eval entry: %s", entry)
            continue
        cases.append(
            EvalCase(
                query=str(entry["query"]),
                relevant_terms=[str(t).lower() for t in entry["relevant"]],
                mode=str(entry.get("mode", "hybrid")),
                description=entry.get("description"),
                max_price=entry.get("max_price"),
                min_rating=entry.get("min_rating"),
                platform=entry.get("platform"),
            )
        )
    return cases


# ---- Scoring --------------------------------------------------------------


def _is_relevant(hit: SearchHit, terms: list[str]) -> bool:
    title = (hit.product.canonical_title or "").lower()
    brand = (hit.product.brand or "").lower()
    category = (hit.product.category or "").lower()
    haystack = " ".join((title, brand, category))
    return any(term in haystack for term in terms)


def _grade(case: EvalCase, hits: list[SearchHit]) -> QueryResult:
    """Convert a hit list into per-query metrics.

    Relevances are binary (1.0 / 0.0) — for a small labeled set, graded
    relevance adds bookkeeping without much signal.
    """
    relevances = [1.0 if _is_relevant(h, case.relevant_terms) else 0.0 for h in hits]
    score_ndcg = ndcg(relevances, k=5)
    score_p3 = precision_at_k(relevances, k=3)
    return QueryResult(
        case=case,
        ndcg_at_5=score_ndcg,
        precision_at_3=score_p3,
        hit=any(r > 0 for r in relevances),
        returned=len(hits),
        top_titles=[h.product.canonical_title for h in hits[:5]],
    )


def evaluate(
    db: Session,
    *,
    cases: list[EvalCase] | None = None,
    page_size: int = 10,
) -> EvalReport:
    """Run the eval set against `search()` and aggregate metrics.

    `page_size=10` is enough headroom for NDCG@5; we don't need to pull
    the full result list to compute either headline metric.
    """
    test_cases = cases if cases is not None else load_cases()
    results: list[QueryResult] = []
    for case in test_cases:
        from decimal import Decimal as _D

        out = search(
            db,
            raw_query=case.query,
            mode=case.mode,  # type: ignore[arg-type]
            max_price=_D(str(case.max_price)) if case.max_price is not None else None,
            min_rating=_D(str(case.min_rating)) if case.min_rating is not None else None,
            platform=case.platform,
            page=1,
            page_size=page_size,
        )
        results.append(_grade(case, out.hits))
    return EvalReport(cases=results)
