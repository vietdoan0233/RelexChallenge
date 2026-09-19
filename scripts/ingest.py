#!/usr/bin/env python
"""Evidence archive ingestion CLI.

    python scripts/ingest.py
    python scripts/ingest.py --skip-embeddings
    python scripts/ingest.py --source data/source --db-path data/app.db

Rebuild-safe: re-running this is how the archive regenerates evidence_units
and identities after a deletion. See app/db/migrations.py for what does and
does not get dropped between runs.
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
from app.ingestion.service import ingest  # noqa: E402


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Ingest the evidence archive")
    parser.add_argument("--source", default=str(settings.source_data_dir_resolved))
    parser.add_argument("--db-path", default=str(settings.database_path_resolved))
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    provider = None
    if not args.skip_embeddings:
        if settings.has_complete_embedding_configuration:
            provider = OpenAICompatibleEmbeddingProvider(
                api_key=settings.gpt_api_key,
                base_url=settings.gpt_base_url,
                model_name=settings.gpt_embedding_model,
            )
            print("Generating embeddings with the configured organizer service.")
        elif settings.has_any_embedding_configuration:
            parser.error(
                "Incomplete GPT embedding configuration; missing "
                f"{', '.join(settings.missing_embedding_configuration_fields)}. "
                "Use --skip-embeddings for offline ingestion."
            )
        else:
            print("Organizer GPT API configuration is not available yet; skipping embeddings.")

    conn = connect(args.db_path)
    try:
        report = ingest(conn, Path(args.source), provider)
    finally:
        conn.close()

    print(f"Documents by type: {report.documents_by_type}")
    print(f"Evidence units by type: {report.evidence_units_by_type}")
    print(f"FTS rows: {report.fts_row_count}")
    print(f"People: {report.people_count}, aliases: {report.alias_count}")
    print(f"Relationship counts: {report.relation_counts}")
    if report.unresolved_alias_candidates:
        print(f"Unresolved alias candidates (left unmerged): {report.unresolved_alias_candidates}")
    if report.reviewed_text_only:
        print(
            f"Reviewed text-only people (from the identity manifest): {report.reviewed_text_only}"
        )
    if report.reviewed_short_aliases:
        print(
            f"Reviewed short-form aliases (from the identity manifest): "
            f"{report.reviewed_short_aliases}"
        )
    if report.rejected_candidates:
        print(
            f"Rejected free-text candidates (never added to people): {report.rejected_candidates}"
        )
    if report.parse_warnings:
        print(f"Parse warnings: {report.parse_warnings}")
    if report.embeddings.skipped:
        print(
            "Embeddings: skipped (--skip-embeddings or GPT provider pending); "
            f"persisted rows: {report.embeddings.persisted_rows}."
        )
    elif report.embeddings.error:
        print(
            f"Embeddings: FAILED after {report.embeddings.succeeded}/"
            f"{report.embeddings.attempted}; persisted rows: "
            f"{report.embeddings.persisted_rows}; {report.embeddings.error}"
        )
    else:
        print(
            f"Embeddings generated: {report.embeddings.succeeded}/"
            f"{report.embeddings.attempted}; persisted rows: "
            f"{report.embeddings.persisted_rows}"
        )


if __name__ == "__main__":
    main()
