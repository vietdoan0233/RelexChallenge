import sqlite3

import pytest

from app.db import migrations


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(connection)
    yield connection
    connection.close()
