import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.api import deps
from app.db import migrations
from app.db.connection import connect
from app.main import app


def test_a_connection_can_be_used_from_another_thread(tmp_path):
    """FastAPI opens a request's connection in one worker thread and may run the
    endpoint in another. That used to raise sqlite3.ProgrammingError."""
    conn = connect(str(tmp_path / "t.db"))
    result = {}

    def use():
        result["n"] = conn.execute("SELECT 1").fetchone()[0]

    worker = threading.Thread(target=use)
    worker.start()
    worker.join()
    assert result == {"n": 1}
    conn.close()


def test_many_parallel_requests_all_succeed(tmp_path):
    db_path = tmp_path / "app.db"
    boot = connect(str(db_path))
    migrations.initialize(boot)
    boot.close()

    def get_conn():
        conn = connect(str(db_path))
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[deps.get_conn] = get_conn
    try:

        def call(_):
            return TestClient(app).get("/api/stats").status_code

        with ThreadPoolExecutor(max_workers=16) as pool:
            statuses = list(pool.map(call, range(64)))
        assert statuses == [200] * 64
    finally:
        app.dependency_overrides.clear()
