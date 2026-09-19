import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(database_path: str) -> sqlite3.Connection:
    db_file = Path(database_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    # A request's connection is created by the dependency in one worker thread and
    # used by the endpoint in another. It is never shared between requests and is
    # used sequentially, so cross-thread use is safe; SQLite's default check would
    # turn any two parallel page requests into a 500.
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
