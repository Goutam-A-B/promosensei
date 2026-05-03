"""Run the ranking eval harness against the current DB and print metrics.

Usage:

    python scripts/run_eval.py                  # human-readable
    python scripts/run_eval.py --json           # JSON for CI artefacts
    python scripts/run_eval.py --queries path   # custom query set

Exit code is 0 on success, 1 if either headline metric falls below the
threshold configured in `app.config` (`eval_min_ndcg_at_5`,
`eval_min_precision_at_3`). The same thresholds back the pytest in
`tests/test_eval_regression.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python scripts/run_eval.py` from the backend root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.eval import evaluate, load_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="PromoSensei ranking eval harness")
    parser.add_argument("--queries", type=Path, default=None, help="Path to a YAML query set")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--page-size", type=int, default=10)
    args = parser.parse_args()

    settings = get_settings()
    cases = load_cases(args.queries) if args.queries else None
    db = SessionLocal()
    try:
        report = evaluate(db, cases=cases, page_size=args.page_size)
    finally:
        db.close()

    payload = report.as_dict()

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        s = payload["summary"]
        print(f"Ranking eval — {s['n']} queries")
        print(f"  NDCG@5:        {s['ndcg_at_5']}")
        print(f"  Precision@3:   {s['precision_at_3']}")
        print(f"  Hit rate:      {s['hit_rate']}")
        print(f"  Coverage:      {s['coverage']}")
        print()
        print("Per-query (worst first):")
        for case in sorted(payload["cases"], key=lambda c: (c["ndcg_at_5"], c["precision_at_3"])):
            mark = "OK " if case["hit"] else "MISS"
            print(
                f"  [{mark}] ndcg={case['ndcg_at_5']:.2f} p@3={case['precision_at_3']:.2f}  {case['query']!r}"
            )

    failed_ndcg = payload["summary"]["ndcg_at_5"] < settings.eval_min_ndcg_at_5
    failed_p3 = payload["summary"]["precision_at_3"] < settings.eval_min_precision_at_3
    if failed_ndcg or failed_p3:
        print(
            f"\nREGRESSION: ndcg@5 >= {settings.eval_min_ndcg_at_5} "
            f"and p@3 >= {settings.eval_min_precision_at_3} required",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
