"""Phase 0 — 픽스처 로더(페이즈별 하위 디렉터리 탐색). tests/fixtures/<phase>/<name>.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent


def load_fixture(phase: str, name: str) -> Any | None:
    """tests/fixtures/<phase>/<name>.json 로드. 없으면 None(정직)."""
    path = _FIXTURES / phase / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
