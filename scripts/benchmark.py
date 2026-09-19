#!/usr/bin/env python
"""Retrieval benchmark CLI (Phase 2 exit criterion).

    python scripts/benchmark.py                 # hybrid, uses the configured provider
    python scripts/benchmark.py --lexical-only  # no network

Reports where the first relevant Evidence Unit ranks for each known topic.
Only the topic queries are ever sent to the embedding provider -- never
evidence text.
"""

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.ingestion.embeddings import OpenAICompatibleEmbeddingProvider  # noqa: E402
from app.retrieval.benchmark import PASS_RANK, evaluate, load_topics  # noqa: E402
from app.retrieval.service import RetrievalService  # noqa: E402

_DEFAULT_TOPICS = _BACKEND_DIR / "tests" / "evaluation" / "retrieval_topics.json"


def _fmt(rank: int | None) -> str:
    return "-" if rank is None else str(rank)


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Benchmark hybrid retrieval on known topics")
    parser.add_argument("--db-path", default=str(settings.database_path_resolved))
    parser.add_argument("--topics", default=str(_DEFAULT_TOPICS))
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--min-pass", type=int, default=0, help="exit 1 if fewer topics pass")
    args = parser.parse_args()

    provider = None
    if not args.lexical_only and settings.has_complete_embedding_configuration:
        provider = OpenAICompatibleEmbeddingProvider(
            api_key=settings.gpt_api_key,
            base_url=settings.gpt_base_url,
            model_name=settings.gpt_embedding_model,
        )

    conn = connect(args.db_path)
    try:
        service = RetrievalService(conn, provider)
        results = evaluate(service, load_topics(Path(args.topics)))
    finally:
        conn.close()

    print(f"{'topic':28} {'fused':>5} {'lex':>4} {'sem':>4} {'visible':>8}  pass")
    for r in results:
        print(
            f"{r.topic_id:28} {_fmt(r.fused_rank):>5} {_fmt(r.lexical_rank):>4} "
            f"{_fmt(r.semantic_rank):>4} {str(r.relevant_in_visible_set):>8}  "
            f"{'PASS' if r.passed else 'FAIL'}"
        )
    passed = sum(r.passed for r in results)
    semantic = all(r.semantic_used for r in results)
    top10 = sum(r.in_top_10 for r in results)
    visible = sum(r.relevant_in_visible_set for r in results)
    print(
        f"\n{passed}/{len(results)} topics have a relevant unit in the fused top {PASS_RANK}; "
        f"{top10}/{len(results)} in the top 10; "
        f"{visible}/{len(results)} in the reasoner-visible set; "
        f"semantic retrieval {'used' if semantic else 'NOT used (lexical-only)'}."
    )
    return 0 if passed >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
