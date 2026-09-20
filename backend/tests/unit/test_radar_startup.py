from pathlib import Path

from app.core.config import Settings
from app.radar import startup


def test_startup_refresh_runs_only_for_a_configured_existing_instance(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    settings = Settings(
        _env_file=None,
        database_path=str(db_path),
        source_data_dir=str(source_dir),
        gpt_api_key="test-key",
        gpt_base_url="https://example.test/v1",
        gpt_model="test-model",
    )
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        startup,
        "_refresh_locked",
        lambda _settings, path, source: calls.append((path, source)),
    )

    startup.refresh_if_needed(settings)

    assert calls == [(db_path, source_dir)]


def test_startup_refresh_skips_when_reasoning_is_not_configured(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    settings = Settings(
        _env_file=None,
        database_path=str(db_path),
        source_data_dir=str(source_dir),
    )
    called = False

    def fail_if_called(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr(startup, "_refresh_locked", fail_if_called)

    startup.refresh_if_needed(settings)

    assert called is False


def test_startup_refresh_retries_below_target(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    settings = Settings(
        _env_file=None,
        database_path=str(db_path),
        source_data_dir=str(source_dir),
        gpt_api_key="test-key",
        gpt_base_url="https://example.test/v1",
        gpt_model="test-model",
        radar_startup_target=5,
        radar_startup_maximum=10,
    )
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(startup.service, "load_findings", lambda *_args: [object()])
    monkeypatch.setattr(
        startup,
        "_refresh_locked",
        lambda _settings, path, source: calls.append((path, source)),
    )

    startup.refresh_if_needed(settings)

    assert calls == [(db_path, source_dir)]


def test_startup_refresh_skips_at_target(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    settings = Settings(
        _env_file=None,
        database_path=str(db_path),
        source_data_dir=str(source_dir),
        gpt_api_key="test-key",
        gpt_base_url="https://example.test/v1",
        gpt_model="test-model",
        radar_startup_target=5,
    )
    called = False

    monkeypatch.setattr(startup.service, "load_findings", lambda *_args: [object()] * 5)

    def fail_if_called(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr(startup, "_refresh_locked", fail_if_called)

    startup.refresh_if_needed(settings)

    assert called is False
