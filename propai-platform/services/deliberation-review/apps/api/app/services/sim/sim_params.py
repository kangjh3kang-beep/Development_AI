"""L3-B — 시뮬 파라미터 소스(INV-20). 모델 상수/임계는 versioned 데이터/override 주입.

코드 내 모델 상수 리터럴 0건 유지(일조 축경사·기준시간, 피난 보행속도 등 전부 JSON).
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

_DATA_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "sim_params.json"

_cache: dict[str, float] | None = None


def _defaults() -> dict[str, float]:
    global _cache
    if _cache is None:
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        _cache = {k: v["value"] for k, v in raw.items()}
    return _cache


class SimParamSource:
    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self._overrides = overrides or {}

    def get(self, name: str) -> float:
        if name in self._overrides:
            return float(self._overrides[name])
        defaults = _defaults()
        if name in defaults:
            return float(defaults[name])
        raise KeyError(f"unknown sim param: {name}")
