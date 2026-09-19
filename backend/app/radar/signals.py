"""Curated external signals.

A small, app-owned, human-curated file. The Radar never scrapes the web
and never invents an outside development: with no file (or an empty one)
it simply has only internal evidence to work with. Signals live under the
source directory so deletion verification scans them like any other
application-owned surface.
"""

import json
from pathlib import Path

from app.radar.schemas import ExternalSignal

SIGNALS_FILENAME = "external_signals.json"


def load_signals(source_dir: Path) -> list[ExternalSignal]:
    path = source_dir / SIGNALS_FILENAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ExternalSignal.model_validate(item) for item in data.get("signals", [])]
    except (OSError, ValueError) as exc:
        # A malformed curated file must fail loudly, not silently drop signals.
        raise ValueError(f"{SIGNALS_FILENAME} is not a valid signal list") from exc
