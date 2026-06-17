"""R0 — 관할 해석 외부 어댑터(인터페이스 + mock). 라이브 호출은 임계경로 인라인 금지(A5).

USE_MOCK_ADAPTERS=true(dev)에서는 versioned 로컬 미러(app/data/mock_jurisdiction.json)를 사용.
실제 외부(토지이음/VWORLD) 연동은 동일 인터페이스로 후속 페이즈에서 주입.
"""
from __future__ import annotations

import json
import pathlib
from typing import Protocol

from app.contracts.enums import JurisdictionSource

_MOCK_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "mock_jurisdiction.json"


class AdapterTimeout(Exception):
    """외부 어댑터 타임아웃/장애. 호출자는 fallback chain으로 흡수한다."""


class JurisdictionAdapter(Protocol):
    source: JurisdictionSource

    def lookup(self, pnu: str) -> dict: ...


def _load_mock() -> dict:
    return json.loads(_MOCK_PATH.read_text(encoding="utf-8"))


class ExternalJurisdictionAdapter:
    """외부 API 미러(mock). 미등록 PNU는 장애로 간주(AdapterTimeout)."""

    source = JurisdictionSource.EXTERNAL

    def lookup(self, pnu: str) -> dict:
        data = _load_mock()
        if pnu not in data:
            raise AdapterTimeout(f"external lookup miss/timeout: {pnu}")
        return data[pnu]


class CadastralAdapter:
    """공부(대지면적/지목) 기반 fallback. 용도지역 단일 추정(assumed)."""

    source = JurisdictionSource.CADASTRAL

    def lookup(self, pnu: str) -> dict:
        # 공부에는 용도지역 상세가 없으므로 단일 미확정 zone으로 반환(assumed 처리는 resolver가).
        return {
            "sido_code": None,
            "sigungu_code": None,
            "zones": [{"zone_code": "UNRESOLVED_FROM_CADASTRE", "area_ratio": None}],
        }
