"""Post-pseudonymisation verification (AGENTS.md/CLAUDE.md 18.0.6).

Confirms the ORIGINAL identity is absent from every public surface the
application owns, while the subject's own alias, evidence, and
relationships remain fully present. This is a strong application-level
check over identifiers the system tracked before the operation ran -- not
a mathematical/cryptographic erasure proof, and it never opens the vault:
the needle list it scans for comes from the caller (app/privacy/
pseudonymise.py), which is the only thing here that may have touched vault
plaintext, and only for the duration of one already-authorized operation.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerificationReport:
    counts: dict[str, int] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(count == 0 for count in self.counts.values()) and all(self.checks.values())


def needles(display_name: str, names: list[str], emails: list[str]) -> list[str]:
    """The subject's *tracked* original identifiers only: display name,
    every person_aliases row, emails. A bare first or last name that was
    never reviewed into an alias is deliberately not scanned for -- it may
    belong to someone else, and this contract verifies what the system
    tracked (CLAUDE.md 18.0.6), not every conceivable reference."""
    return [v for v in dict.fromkeys(x.strip() for x in [display_name, *names, *emails]) if v]


def _contains(haystack: bytes, needle_list: list[str]) -> int:
    """Case-insensitive, Unicode-aware substring count. Bytes are decoded
    leniently (database pages are mostly UTF-8 text) so 'Öberg' matches
    'öberg' -- a raw bytes.lower() would only fold ASCII."""
    text = haystack.decode("utf-8", errors="ignore").lower()
    return sum(text.count(needle.lower()) for needle in needle_list if needle)


def scan_files(root: Path, needle_list: list[str]) -> int:
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += _contains(path.read_bytes(), needle_list)
    return total


def scan_filenames(root: Path, needle_list: list[str]) -> int:
    """Like scan_files, but the *path itself*, not its content -- a name
    baked into a filename (e.g. a transcript literally named
    "kwame-1on1-notes.txt") is invisible to every content-byte scan, since
    those only ever read what is inside a file. Architecturally, a leak
    found here cannot be silently auto-fixed by renaming: document_id is
    derived from the filename stem (CLAUDE.md 7.3), so renaming a source
    file would change document_id and therefore every Evidence ID under it,
    violating the "Evidence IDs are stable" invariant. This check exists so
    such a leak fails the operation loudly (fail closed) rather than
    silently reporting success while the filename still identifies someone
    -- consistent with the project's own stance that failing safely beats
    an unsupported repair."""
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            # Filenames in this corpus are kebab-case ("marco-rossi-...txt"),
            # so a needle built from natural "Marco Rossi" text would never
            # substring-match the hyphenated form. Normalize '-'/'_' to a
            # space on both sides before comparing, matching-surface only
            # for this filename check -- scan_files/scan_database_rows must
            # not do this, since a hyphen inside ordinary prose is a real
            # character, not a separator.
            normalized = path.name.replace("-", " ").replace("_", " ").encode("utf-8")
            total += _contains(normalized, needle_list)
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


# Tables/columns where a display_alias is *supposed* to persist forever --
# it is the stable, permanent identifier and stays even after an admin
# reversal restores the active identity (CLAUDE.md 18.0.7: "preserve the
# stable display alias unless a separately audited rotation is required").
# scan_content_rows below is scan_database_rows' narrower sibling for
# app/privacy/reverse.py's own verification, which needs to confirm the
# alias is gone from *content* without treating this permanent bookkeeping
# as a leak.
_ALIAS_BOOKKEEPING_COLUMNS = {
    "people": {"display_alias"},
    "privacy_operations": {"display_alias"},
}


def scan_content_rows(conn: sqlite3.Connection, needle_list: list[str]) -> int:
    """Like scan_database_rows, but skips the columns where a subject's own
    display_alias is expected to live permanently, so this can be used to
    verify "the alias no longer appears in any evidence/derived content"
    without that permanent bookkeeping itself counting as a false positive."""
    total = 0
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'evidence_fts_%'"
        )
    ]
    for table in tables:
        skip_columns = _ALIAS_BOOKKEEPING_COLUMNS.get(table, set())
        columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        for row in conn.execute(f'SELECT * FROM "{table}"'):
            for column, value in zip(columns, tuple(row), strict=True):
                if column in skip_columns:
                    continue
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
    vault_path: Path,
    artifact_dirs: list[Path],
    needle_list: list[str],
    subject_id: str,
    display_alias: str,
    pre_operation_evidence_people: set[tuple[str, str, str]],
) -> VerificationReport:
    report = VerificationReport()

    report.counts["source_files"] = scan_files(source_dir, needle_list)
    # Filenames are a distinct surface from file *content* -- see
    # scan_filenames's docstring for why a hit here fails the operation
    # rather than being silently repaired.
    report.counts["source_filenames"] = scan_filenames(source_dir, needle_list)
    report.counts["database_rows"] = scan_database_rows(conn, needle_list)
    report.counts["database_files"] = scan_database_files(db_path, needle_list)
    report.counts["artifacts_and_cache"] = sum(scan_files(d, needle_list) for d in artifact_dirs)
    report.counts["artifact_filenames"] = sum(scan_filenames(d, needle_list) for d in artifact_dirs)
    # The vault directory itself must contain only ciphertext -- scanning it
    # for the *plaintext* needle list confirms the encrypted bundle never
    # leaked the original name/email/alias as a raw substring anywhere on
    # disk (e.g. beside the vault file, in a stray temp/export artifact).
    vault_dir = Path(vault_path).parent
    report.counts["vault_directory_plaintext"] = scan_files(vault_dir, needle_list)

    person = conn.execute(
        "SELECT privacy_state, display_alias, display_name FROM people WHERE subject_id = ?",
        (subject_id,),
    ).fetchone()
    report.checks["subject_is_pseudonymised"] = bool(person) and person["privacy_state"] == (
        "PSEUDONYMISED"
    )
    report.checks["display_alias_matches"] = bool(person) and person["display_alias"] == (
        display_alias
    )
    report.checks["display_name_cleared"] = bool(person) and person["display_name"] is None
    report.checks["no_original_aliases_remain"] = (
        conn.execute(
            "SELECT COUNT(*) FROM person_aliases WHERE subject_id = ?", (subject_id,)
        ).fetchone()[0]
        == 0
    )

    surviving = {
        (row["evidence_id"], row["subject_id"], row["relation"])
        for row in conn.execute(
            "SELECT evidence_id, subject_id, relation FROM evidence_people WHERE subject_id = ?",
            (subject_id,),
        )
    }
    report.checks["evidence_people_relationships_preserved"] = (
        pre_operation_evidence_people <= surviving
    )

    return report
