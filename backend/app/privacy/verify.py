"""Post-operation verification (CLAUDE.md 18.5).

Scans every application-owned surface for the *tracked* identifiers of the
removed person: source files, every text column of every database table,
the database file and its WAL/SHM, and derived artifact/cache folders.
Reports counts per surface, never matched content.

Accurate scope: this is a strong application-level check over identifiers
the system knows and owns. It is not proof that no unknown nickname or
indirect reference exists, and not a cryptographic erasure claim.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.privacy.targets import fold


@dataclass
class VerificationReport:
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(count == 0 for count in self.counts.values())


def needles(canonical_name: str, names: list[str], emails: list[str]) -> list[str]:
    """The person's *tracked* identifiers only: canonical name, reviewed
    aliases, emails. A bare first or last name that has not been reviewed
    into an alias is deliberately not scanned for -- it may belong to
    someone else, and the contract verifies what the system tracks
    (CLAUDE.md 18.5), not every conceivable reference."""
    return [v for v in dict.fromkeys(x.strip() for x in [canonical_name, *names, *emails]) if v]


def _contains(haystack: bytes, needle_list: list[str]) -> int:
    """Case- and diacritic-insensitive substring count. Bytes are decoded
    leniently (database pages are mostly UTF-8 text) so 'Sørensen' also
    matches the corpus's own 'Sorensen' spelling."""
    text = fold(haystack.decode("utf-8", errors="ignore"))
    return sum(text.count(fold(needle)) for needle in needle_list)


def scan_files(root: Path, needle_list: list[str]) -> int:
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += _contains(path.read_bytes(), needle_list)
    return total


def scan_database_rows(conn: sqlite3.Connection, needle_list: list[str]) -> int:
    """Every text value in every real table, including FTS content columns."""
    total = 0
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'evidence_fts_%'"
        )
    ]
    for table in tables:
        for row in conn.execute(f'SELECT * FROM "{table}"'):
            for value in tuple(row):
                if isinstance(value, str):
                    total += _contains(value.encode("utf-8"), needle_list)
    return total


def scan_database_files(db_path: Path, needle_list: list[str]) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(str(db_path) + suffix)
        if path.exists():
            total += _contains(path.read_bytes(), needle_list)
    return total


def verify(
    *,
    conn: sqlite3.Connection,
    db_path: Path,
    source_dir: Path,
    artifact_dirs: list[Path],
    needle_list: list[str],
    person_id: str,
) -> VerificationReport:
    report = VerificationReport()
    report.counts["source_files"] = scan_files(source_dir, needle_list)
    report.counts["database_rows"] = scan_database_rows(conn, needle_list)
    report.counts["database_files"] = scan_database_files(db_path, needle_list)
    report.counts["artifacts_and_cache"] = sum(scan_files(d, needle_list) for d in artifact_dirs)
    report.counts["person_rows"] = conn.execute(
        "SELECT (SELECT COUNT(*) FROM people WHERE person_id = ?) "
        "+ (SELECT COUNT(*) FROM person_aliases WHERE person_id = ?) "
        "+ (SELECT COUNT(*) FROM evidence_people WHERE person_id = ?)",
        (person_id, person_id, person_id),
    ).fetchone()[0]
    return report
