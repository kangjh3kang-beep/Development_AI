"""Phase 0 — 재현성 입력해시(INV-7). 정규화(키 정렬) → 안정 sha256."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(data: Any) -> str:
    """결정적 직렬화 — 키 순서 무관 동일 문자열."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def input_hash(data: Any) -> str:
    """정규화 입력 → 안정 해시(재현성 키). 동일 입력(키 순서 무관) → 동일 해시."""
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()
