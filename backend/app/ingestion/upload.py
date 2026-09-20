"""Add uploaded documents to the canonical evidence archive.

An upload is never inserted into SQLite directly. Files are validated in a
staging directory, moved into ``data/source/`` (the canonical source), and the
existing ``ingest()`` rebuild then derives documents, evidence units, FTS and
embeddings from that source -- so an uploaded document goes through exactly
the same path, and gets the same stable evidence IDs, as the original archive.

Success is reported only after both halves are done: the files are on disk in
the canonical source *and* ingestion has committed them to the database. If
either half fails, only the files this request added are removed.
"""

import logging
import os
import re
import sqlite3
import tempfile
import threading
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.db import migrations
from app.db.connection import connect
from app.ingestion import service
from app.ingestion.embeddings import EmbeddingProvider
from app.privacy import ops

_LOGGER = logging.getLogger(__name__)

# The archive is ~45 documents of a few KB each; these are generous ceilings
# whose job is to stop an accidental or hostile oversized request.
MAX_FILES = 20
MAX_FILE_BYTES = 1024 * 1024

# API value -> canonical source subdirectory (see ingestion.service._PARSERS).
DOCUMENT_TYPE_DIRS = {"email": "emails", "transcript": "transcripts", "report": "reports"}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_STEM_LENGTH = 80

# One ingestion at a time: it drops and rebuilds the derived tables, so two
# overlapping runs would corrupt each other.
_ingest_lock = threading.Lock()


class UploadRejected(Exception):
    """A request the archive refuses, with an HTTP status and per-file reasons.
    Messages never echo file content, only filenames the caller sent."""

    def __init__(
        self, status_code: int, message: str, failures: list[dict[str, str]] | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.failures = failures or []
        self.files_removed = False


@dataclass
class IngestPaths:
    source_dir: Path
    db_path: Path
    ops_dir: Path
    staging_root: Path


@dataclass
class StagedFile:
    original_filename: str
    stored_stem: str
    staged_path: Path
    warnings: list[str] = field(default_factory=list)

    @property
    def stored_filename(self) -> str:
        return f"{self.stored_stem}.txt"


def clean_filename(raw: str | None) -> str:
    """Returns a safe stem for a client-supplied filename, or raises ValueError.

    Browsers send only a base name, so a path separator or ``..`` can only come
    from a hand-built request: reject it rather than quietly "fix" it into a
    different name than the caller asked for."""
    if not raw or not raw.strip():
        raise ValueError("The filename is missing.")
    if _CONTROL_CHARS.search(raw):
        raise ValueError("The filename contains control characters.")
    if "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError("The filename must not contain path separators or '..'.")
    name = raw.strip()
    if name.startswith("."):
        raise ValueError("The filename must not start with a dot.")
    if not name.lower().endswith(".txt"):
        raise ValueError("Only .txt files are accepted.")

    stem = unicodedata.normalize("NFKD", name[: -len(".txt")])
    stem = stem.encode("ascii", "ignore").decode("ascii")
    stem = _UNSAFE_CHARS.sub("-", stem).strip("-._")[:_MAX_STEM_LENGTH].strip("-._")
    if not stem:
        raise ValueError("The filename has no usable characters.")
    return stem


def _existing_document_ids(source_dir: Path, conn: sqlite3.Connection) -> set[str]:
    """A document's id is its file stem, and it must be unique across all three
    source folders as well as the database, or two files would collide as one
    document."""
    ids = {p.stem for sub in DOCUMENT_TYPE_DIRS.values() for p in (source_dir / sub).glob("*.txt")}
    ids.update(row[0] for row in conn.execute("SELECT document_id FROM documents"))
    return ids


def _decode(data: bytes) -> str:
    if b"\x00" in data:
        raise ValueError("The file contains binary data.")
    try:
        # utf-8-sig drops a BOM so it cannot end up glued to the first header.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The file is not valid UTF-8 text.") from None
    if not text.strip():
        raise ValueError("The file is empty.")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _validate_parses(text: str, stem: str, document_type: str) -> list[str]:
    """Parse with the real parser for this type, without touching the database.
    A file the parser cannot turn into evidence must not become canonical."""
    parse_fn, _ = service._PARSERS[DOCUMENT_TYPE_DIRS[document_type]]
    try:
        parsed = parse_fn(text, stem, f"{stem}.txt")
    except Exception as exc:
        raise ValueError(
            f"The file could not be parsed as a {document_type} ({type(exc).__name__})."
        ) from None
    if not (parsed.units or parsed.fragments):
        detail = "; ".join(parsed.warnings) or "no evidence could be extracted"
        raise ValueError(f"The file is not a recognizable {document_type}: {detail}.")
    return list(parsed.warnings)


def stage_files(
    uploads: list[tuple[str | None, bytes]],
    document_type: str,
    *,
    taken_ids: set[str],
    staging_dir: Path,
) -> list[StagedFile]:
    """Write each upload to the staging directory and validate the staged copy.
    Either every file passes or the whole request is refused, so a batch is
    never half-added."""
    if document_type not in DOCUMENT_TYPE_DIRS:
        raise UploadRejected(
            400, f"document_type must be one of: {', '.join(sorted(DOCUMENT_TYPE_DIRS))}."
        )
    if not uploads:
        raise UploadRejected(400, "No files were uploaded.")
    if len(uploads) > MAX_FILES:
        raise UploadRejected(413, f"Too many files: at most {MAX_FILES} per upload.")

    staged: list[StagedFile] = []
    failures: list[dict[str, str]] = []
    taken = set(taken_ids)
    for raw_name, data in uploads:
        label = (raw_name or "(unnamed)")[:120]
        try:
            if len(data) > MAX_FILE_BYTES:
                raise ValueError(f"The file is larger than {MAX_FILE_BYTES // 1024} KB.")
            stem = clean_filename(raw_name)
            text = _decode(data)
            # Never overwrite or shadow an existing document: keep the caller's
            # name when it is free, otherwise add a short random suffix.
            unique = stem
            while unique in taken:
                unique = f"{stem}-{uuid.uuid4().hex[:8]}"
            staged_path = staging_dir / f"{unique}.txt"
            staged_path.write_text(text, encoding="utf-8", newline="\n")
            warnings = _validate_parses(
                staged_path.read_text(encoding="utf-8"), unique, document_type
            )
        except ValueError as exc:
            failures.append({"filename": label, "error": str(exc)})
            continue

        taken.add(unique)
        staged.append(
            StagedFile(
                original_filename=label,
                stored_stem=unique,
                staged_path=staged_path,
                warnings=warnings,
            )
        )

    if failures:
        raise UploadRejected(
            400,
            "Nothing was added: "
            + ("1 file was" if len(failures) == 1 else f"{len(failures)} files were")
            + " rejected.",
            failures,
        )
    return staged


def _place(staged_path: Path, target: Path) -> None:
    """Copy via a same-directory temp file, then hard-link into place. The link
    fails if the target exists, so this can never overwrite a source file, and
    a crash cannot leave a half-written .txt for ingestion to pick up."""
    tmp = target.parent / f".tmp-{uuid.uuid4().hex}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as handle:
            handle.write(staged_path.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.link(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


@dataclass
class UploadedFileResult:
    original_filename: str
    stored_filename: str
    document_id: str
    document_type: str
    evidence_units: int
    warnings: list[str]


@dataclass
class UploadResult:
    status: str
    uploaded_filenames: list[str]
    files: list[UploadedFileResult]
    documents_added: int
    evidence_units_added: int
    fts_row_count: int
    embeddings: dict
    parse_warnings: list[str]
    archive: dict


def _archive_counts(conn: sqlite3.Connection) -> dict[str, int]:
    def count(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    return {
        "documents": count("SELECT COUNT(*) FROM documents"),
        "evidence_units": count("SELECT COUNT(*) FROM evidence_units"),
        "embeddings": count("SELECT COUNT(*) FROM evidence_embeddings"),
    }


def _embedding_summary(report, provider: EmbeddingProvider | None, counts: dict) -> dict:
    total, stored = counts["evidence_units"], counts["embeddings"]
    if provider is None:
        status = "skipped"
        message = (
            "Embeddings were skipped because no embedding provider is configured. The new "
            "evidence is searchable by keyword only until embeddings are generated."
        )
    elif report.embeddings.error:
        status = "partial"
        message = (
            f"Embedding generation stopped early ({report.embeddings.error}). The new "
            "evidence is searchable by keyword; semantic search misses some units."
        )
    elif stored < total:
        status = "partial"
        message = f"{total - stored} evidence units have no embedding yet."
    else:
        status = "complete"
        message = "All evidence units have embeddings."
    return {
        "status": status,
        "message": message,
        "new_units_embedded": report.embeddings.succeeded,
        "total_embeddings": stored,
        "total_units": total,
    }


def _remove_added(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _rebuild_after_failure(paths: IngestPaths, provider: EmbeddingProvider | None) -> None:
    """Best effort: after the failed run's files are removed, rebuild so the
    database matches the source again. It is safe to fail -- the caller is told
    the archive needs a manual re-ingest."""
    try:
        conn = connect(str(paths.db_path))
        try:
            service.ingest(conn, paths.source_dir, provider, reuse_existing_embeddings=True)
        finally:
            conn.close()
    except Exception as exc:
        _LOGGER.error("recovery ingest failed error_type=%s", type(exc).__name__)


def add_evidence(
    uploads: list[tuple[str | None, bytes]],
    document_type: str,
    paths: IngestPaths,
    provider: EmbeddingProvider | None,
) -> UploadResult:
    # Source and database may disagree while a privacy operation runs.
    ops.assert_unlocked(paths.ops_dir)

    if not _ingest_lock.acquire(blocking=False):
        raise UploadRejected(409, "Another ingestion is already running; try again shortly.")
    try:
        return _add_evidence_locked(uploads, document_type, paths, provider)
    finally:
        _ingest_lock.release()


def _add_evidence_locked(
    uploads: list[tuple[str | None, bytes]],
    document_type: str,
    paths: IngestPaths,
    provider: EmbeddingProvider | None,
) -> UploadResult:
    conn = connect(str(paths.db_path))
    added: list[Path] = []
    try:
        migrations.initialize(conn)
        before = _archive_counts(conn)

        paths.staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=paths.staging_root, prefix="upload-") as tmp:
            staging_dir = Path(tmp)
            staged = stage_files(
                uploads,
                document_type,
                taken_ids=_existing_document_ids(paths.source_dir, conn),
                staging_dir=staging_dir,
            )
            # A privacy operation may have started while files were staged.
            ops.assert_unlocked(paths.ops_dir)
            target_dir = paths.source_dir / DOCUMENT_TYPE_DIRS[document_type]
            try:
                for item in staged:
                    target = target_dir / item.stored_filename
                    _place(item.staged_path, target)
                    added.append(target)
            except OSError as exc:
                _remove_added(added)
                raise UploadRejected(
                    500, f"Could not save the files to the archive ({type(exc).__name__})."
                ) from None

        try:
            report = service.ingest(
                conn, paths.source_dir, provider, reuse_existing_embeddings=True
            )
            counts = _archive_counts(conn)
            results = _verify_and_summarize(conn, staged, document_type)
        except Exception as exc:
            _LOGGER.error("upload ingestion failed error_type=%s", type(exc).__name__)
            _remove_added(added)
            conn.close()
            _rebuild_after_failure(paths, provider)
            rejected = UploadRejected(
                500,
                "The files were not added: ingestion failed "
                f"({type(exc).__name__}). The archive was left as it was before this upload.",
                [{"filename": item.original_filename, "error": "not ingested"} for item in staged],
            )
            rejected.files_removed = True
            raise rejected from None

        return UploadResult(
            status="ingested",
            uploaded_filenames=[item.stored_filename for item in staged],
            files=results,
            documents_added=counts["documents"] - before["documents"],
            evidence_units_added=counts["evidence_units"] - before["evidence_units"],
            fts_row_count=report.fts_row_count,
            embeddings=_embedding_summary(report, provider, counts),
            parse_warnings=[f"{r.stored_filename}: {w}" for r in results for w in r.warnings],
            archive=counts,
        )
    finally:
        conn.close()


def _verify_and_summarize(
    conn: sqlite3.Connection, staged: list[StagedFile], document_type: str
) -> list[UploadedFileResult]:
    """Confirm from the database itself that every new file became evidence,
    rather than trusting that ingest() returned without an exception."""
    results = []
    for item in staged:
        row = conn.execute(
            "SELECT d.document_id, d.document_type, "
            "(SELECT COUNT(*) FROM evidence_units u WHERE u.document_id = d.document_id) "
            "FROM documents d WHERE d.document_id = ?",
            (item.stored_stem,),
        ).fetchone()
        if row is None or row[2] == 0:
            raise RuntimeError("uploaded document is missing from the database after ingestion")
        results.append(
            UploadedFileResult(
                original_filename=item.original_filename,
                stored_filename=item.stored_filename,
                document_id=row[0],
                document_type=row[1],
                evidence_units=row[2],
                warnings=item.warnings,
            )
        )
    return results
