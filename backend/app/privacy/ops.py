"""Privacy-operation lock and crash-safe state (CLAUDE.md 18.10-18.11).

A deletion/anonymization is a staged, exclusive operation. While its lock
file exists, source and database may disagree, so nothing may serve
queries or ingest. Every write here is an atomic same-directory replace
(never an append), and the lock is released last -- after verification.

The plan file is temporary protected personal data: it lives for one
operation only and is removed, then confirmed gone by a final scan,
before the lock is released.
"""

import json
import os
import tempfile
from pathlib import Path

LOCK_NAME = "lock.json"
PLAN_NAME = "plan.json"

PLANNING = "PLANNING"
SOURCE_IN_PROGRESS = "SOURCE_IN_PROGRESS"
SOURCE_DONE = "SOURCE_DONE"
DB_DONE = "DB_DONE"
CLEANUP_DONE = "CLEANUP_DONE"
VERIFIED = "VERIFIED"
FINALIZING = "FINALIZING"

# Order matters: recovery resumes from the earliest incomplete state.
STATES = [
    PLANNING,
    SOURCE_IN_PROGRESS,
    SOURCE_DONE,
    DB_DONE,
    CLEANUP_DONE,
    VERIFIED,
    FINALIZING,
]


class PrivacyLockedError(RuntimeError):
    """A privacy operation is active or unresolved; serving is blocked."""


class PrivacyOperationError(RuntimeError):
    """The operation failed and left the application locked. Message is
    generic on purpose: it must never carry personal data."""


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, fsync, then replace, so
    a crash leaves either the old file or the new one, never a torn mix."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates the file 0600. Source files are ordinary app data and
    # keep their normal mode; the plan and lock hold personal data and stay 0600.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        if path.suffix != ".json":
            os.chmod(tmp, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def is_locked(ops_dir: Path) -> bool:
    return (ops_dir / LOCK_NAME).exists()


def assert_unlocked(ops_dir: Path) -> None:
    if is_locked(ops_dir):
        raise PrivacyLockedError("a privacy operation is in progress or needs review")


def acquire(ops_dir: Path, op_id: str) -> None:
    ops_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ops_dir, 0o700)  # the plan is temporary protected personal data
    try:
        fd = os.open(ops_dir / LOCK_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise PrivacyLockedError("a privacy operation is already in progress") from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"op_id": op_id, "state": PLANNING}))
        handle.flush()
        os.fsync(handle.fileno())


def read_lock(ops_dir: Path) -> dict | None:
    path = ops_dir / LOCK_NAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "CORRUPT"}
    return data if isinstance(data, dict) else {"state": "CORRUPT"}


def set_state(ops_dir: Path, state: str) -> None:
    lock = read_lock(ops_dir) or {}
    lock["state"] = state
    atomic_write(ops_dir / LOCK_NAME, json.dumps(lock))


def write_plan(ops_dir: Path, plan: dict) -> None:
    atomic_write(ops_dir / PLAN_NAME, json.dumps(plan))


def read_plan(ops_dir: Path) -> dict | None:
    path = ops_dir / PLAN_NAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def remove_plan(ops_dir: Path) -> None:
    (ops_dir / PLAN_NAME).unlink(missing_ok=True)


def release(ops_dir: Path) -> None:
    (ops_dir / LOCK_NAME).unlink(missing_ok=True)
