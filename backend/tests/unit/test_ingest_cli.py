import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_INGEST_SCRIPT = _REPO_ROOT / "scripts" / "ingest.py"


def test_ingest_cli_rejects_a_partial_embedding_configuration() -> None:
    env = os.environ.copy()
    # Environment variables override the local .env file. The values below are
    # deliberately synthetic so the test proves only the validation branch and
    # never reads or reports a developer's real credentials.
    env.update(
        {
            "GPT_API_KEY": "test-key",
            "GPT_BASE_URL": "https://example.invalid",
            "GPT_EMBEDDING_MODEL": "",
        }
    )

    result = subprocess.run(
        [sys.executable, str(_INGEST_SCRIPT)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Incomplete GPT embedding configuration" in result.stderr
    assert "GPT_EMBEDDING_MODEL" in result.stderr
    assert "test-key" not in result.stderr
