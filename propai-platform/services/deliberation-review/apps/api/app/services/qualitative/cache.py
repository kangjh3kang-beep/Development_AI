"""L3-C — 정성 결과 캐시(INV-32 재현성). (입력해시+snapshot+모델버전) 키로 결과 캐싱."""
from __future__ import annotations

from app.contracts.qualitative import QualAssessment


class QualCache:
    def __init__(self) -> None:
        self._store: dict[str, QualAssessment] = {}

    def get(self, key: str) -> QualAssessment | None:
        return self._store.get(key)

    def put(self, key: str, value: QualAssessment) -> None:
        self._store[key] = value


_DEFAULT_CACHE = QualCache()


def default_cache() -> QualCache:
    return _DEFAULT_CACHE
