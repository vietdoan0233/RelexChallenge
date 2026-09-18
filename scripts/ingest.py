#!/usr/bin/env python
"""KEEPER ingestion CLI.

    python scripts/ingest.py
    python scripts/ingest.py --skip-embeddings
    python scripts/ingest.py --source data/source --db-path data/keeper.db

Rebuild-safe: re-running this is how KEEPER regenerates evidence_units
after a deletion. See app/db/migrations.py for what does and does not get
dropped between runs.
"""

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.ingestion.embeddings import GeminiEmbeddingProvider  # noqa: E402
from app.ingestion.service import ingest  # noqa: E402


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Ingest the KEEPER evidence archive")
    parser.add_argument("--source", default=str(settings.source_data_dir_resolved))
    parser.add_argument("--db-path", default=str(settings.database_path_resolved))
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    provider = None
    if not args.skip_embeddings:
        if settings.google_api_key and settings.gemini_embedding_model:
            provider = GeminiEmbeddingProvider(settings.google_api_key, settings.gemini_embedding_model)
        else:
            print("No GOOGLE_API_KEY/GEMINI_EMBEDDING_MODEL configured; skipping embeddings.")

    conn = connect(args.db_path)
    try:
        report = ingest(conn, Path(args.source), provider)
    finally:
        conn.close()

    print(f"Documents by type: {report.documents_by_type}")
    print(f"Evidence units by type: {report.evidence_units_by_type}")
    print(f"FTS rows: {report.fts_row_count}")
    print(f"People: {report.people_count}, aliases: {report.alias_count}")
    if report.unresolved_alias_candidates:
        print(f"Unresolved alias candidates (left unmerged): {report.unresolved_alias_candidates}")
    if report.text_only_mentions:
        print(f"Text-only mentions found (not auto-added to roster): {report.text_only_mentions}")
    if report.parse_warnings:
        print(f"Parse warnings: {report.parse_warnings}")
    if report.embeddings.skipped:
        print("Embeddings: skipped (--skip-embeddings or no API key configured).")
    elif report.embeddings.error:
        print(f"Embeddings: FAILED - {report.embeddings.error}")
    else:
        print(f"Embeddings generated: {report.embeddings.succeeded}/{report.embeddings.attempted}")


if __name__ == "__main__":
    main()
