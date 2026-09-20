"""Vercel entrypoint for the full FastAPI application.

The local project keeps the backend in ``backend/``. Vercel's Python runtime
needs a root-level function entrypoint, so this adapter imports the same app
without creating a second API implementation.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.main import app  # noqa: E402

__all__ = ["app"]
