"""R0 — 해소 파라미터 제공자(INV-3). 허용오차 밴드 등은 코드 하드코딩 금지 → 데이터 주입.

값은 versioned 데이터파일(app/data/resolution_parameters.json)에서 로드. DB 주입(resolution_parameter
테이블)으로 override 가능하도록 set_override 제공. 코드 내 법정/도메인 수치 리터럴 0건 유지.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

_DATA_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "resolution_parameters.json"

_cache: dict[str, Any] | None = None
_overrides: dict[str, Any] = {}


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return _cache


def reload() -> None:
    """캐시 무효화(테스트/재적재용)."""
    global _cache
    _cache = None


def set_override(name: str, value: Any) -> None:
    """DB/런타임 주입값으로 파라미터 override."""
    _overrides[name] = value


def param_meta(name: str) -> dict[str, Any]:
    data = _load()
    if name not in data:
        raise KeyError(f"unknown resolution parameter: {name}")
    return data[name]


def param(name: str) -> Any:
    """파라미터 값 반환. override 우선, 없으면 데이터파일."""
    if name in _overrides:
        return _overrides[name]
    return param_meta(name)["value"]
