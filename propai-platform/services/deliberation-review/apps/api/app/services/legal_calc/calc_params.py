"""R1.5 — 산정 파라미터 소스(INV-11). 제외규정 임계는 versioned 데이터/룰셋/override에서 주입.

우선순위: 명시 override > 룰셋(기준일 유효) 버전 params > 기본 데이터파일(app/data/calc_params.json).
코드 내 법정 임계 리터럴 0건 유지.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

_DATA_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "calc_params.json"

_defaults_cache: dict[str, float] | None = None
_meta_cache: dict[str, dict] | None = None


def _defaults() -> dict[str, float]:
    global _defaults_cache
    if _defaults_cache is None:
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        _defaults_cache = {k: v["value"] for k, v in raw.items()}
    return _defaults_cache


def _all_meta() -> dict[str, dict]:
    global _meta_cache
    if _meta_cache is None:
        _meta_cache = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return _meta_cache


class CalcParamSource:
    def __init__(
        self,
        overrides: dict[str, Any] | None = None,
        base: dict[str, Any] | None = None,
    ) -> None:
        self._overrides = overrides or {}
        self._base = base or {}

    def get(self, name: str) -> float:
        if name in self._overrides:
            return float(self._overrides[name])
        if name in self._base:
            return float(self._base[name])
        defaults = _defaults()
        if name in defaults:
            return float(defaults[name])
        raise KeyError(f"unknown calc param: {name}")

    def meta(self, name: str) -> dict:
        """파라미터 근거 메타 {value(적용값)·unit·basis_article·description}. 설명가능성 전파용.

        value는 get()(override 우선) 적용값, 나머지 근거는 데이터파일(calc_params.json)에서.
        """
        base_meta = _all_meta().get(name, {})
        return {**base_meta, "value": self.get(name)}
