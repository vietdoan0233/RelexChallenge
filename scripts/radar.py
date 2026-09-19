#!/usr/bin/env python
"""Precompute Reconsideration Radar findings (docs/RECONSIDERATION_RADAR.md).

    python scripts/radar.py --limit 4

Sends retrieved evidence excerpts and curated signals to the configured
organizer reasoning service, then stores validated findings in the runtime
database. Never run per page load: findings are precomputed so the Radar view
opens with candidates already surfaced. Replaces any earlier Radar findings.
"""

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db import migrations  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.ingestion.embeddings import OpenAICompatibleEmbeddingProvider  # noqa: E402
from app.privacy import ops  # noqa: E402
from app.radar import service  # noqa: E402
from app.reasoning.llm import OpenAICompatibleChatClient  # noqa: E402
from app.retrieval.service import RetrievalService  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Precompute Radar findings")
    parser.add_argument("--db-path", default=str(settings.database_path_resolved))
    parser.add_argument("--source", default=str(settings.source_data_dir_resolved))
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()

    if not (settings.gpt_api_key and settings.gpt_base_url and settings.gpt_model):
        parser.error("the organizer reasoning service is not configured")
    ops.assert_unlocked(Path(args.db_path).parent / "privacy_ops")

    llm = OpenAICompatibleChatClient(
        api_key=settings.gpt_api_key,
        base_url=settings.gpt_base_url,
        model_name=settings.gpt_model,
    )
    embedder = None
    if settings.has_complete_embedding_configuration:
        embedder = OpenAICompatibleEmbeddingProvider(
            api_key=settings.gpt_api_key,
            base_url=settings.gpt_base_url,
            model_name=settings.gpt_embedding_model,
        )
    conn = connect(args.db_path)
    try:
        migrations.initialize(conn)
        result = service.run_radar(
            conn, RetrievalService(conn, embedder), llm, Path(args.source), limit=args.limit
        )
        cards = service.load_findings(conn, Path(args.source))
    finally:
        conn.close()

    print(
        f"Surfaced {len(result.surfaced)} finding(s); dropped for missing evidence: "
        f"{result.dropped_unsupported}"
    )
    for card in cards:
        print(f"  [{card.assessment}] {card.outcome}: {card.proposal[:110]}")
    for proposal, reason in result.rejected:
        print(f"  rejected by the Skeptic: {proposal[:80]} -- {reason[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
