"""P3+ — 용도지역 국가 규제 상한 제공자(INV-3). 코드 하드코딩 금지 → 버전 데이터파일 로드.

값은 app/data/national_zone_limits.json(시행령 §84/§85 상한·national 베이스라인)에서 로드(parameters.py 패턴).
DB override(set_override) 가능 — 조례 강화/개정을 코드 변경 없이 주입. 코드 내 법정 수치 리터럴 0건(INV-3 통과).
엔진이 입력 limit를 echo하지 않고 용도지역에서 **독립** 한도를 해소(reg_graph 수치 한도) → 플랫폼 한도와 divergence(P5).
"""
from __future__ import annotations

import json
import math
import pathlib
from typing import Any

_DATA_PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "national_zone_limits.json"

# 산정 변수 → 데이터파일 한도 키(값은 문자열 — INV-3 스캐너 numeric 면제). 비대상 변수(building_height 등)는 미수록.
_VAR_TO_KEY: dict[str, str] = {
    "building_area": "bcr_pct",
    "far_floor_area": "far_pct",
    "gross_floor_area": "far_pct",
}

_cache: dict[str, Any] | None = None
_override: dict[str, dict[str, Any]] = {}


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return _cache


def reload() -> None:
    """캐시 무효화(테스트/재적재용)."""
    global _cache
    _cache = None


def set_zone_override(zone: str, limits: dict[str, Any]) -> None:
    """DB/런타임 주입값으로 특정 용도지역 한도 override(조례 강화 등). 데이터파일 우선순위 < override."""
    _override[zone] = limits


def _merged_entry(z: str, zones: dict[str, Any]) -> dict[str, Any]:
    """zone 한도 = 데이터파일 base ∪ override(키 단위 병합 — 부분 override는 나머지 지표 base 보존).
    resolve_zone_limit·all_zone_limits **공유 SSOT** — 두 경로 override 의미 일치(read 표면=실 계산값).
    ⚠️ 전체교체가 아닌 병합인 이유: 조례가 일부 지표(예 far)만 강화해도 나머지 한도(bcr)를 지우면 안 됨."""
    return {**(zones.get(z) or {}), **(_override.get(z) or {})}


def _limit_num(v: Any) -> float | None:
    """유한 수치 한도만(bool·None·nan·inf 거부) — override의 잘못된 타입이 거짓 한도(True→1.0 등)로 통과 방지."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _norm_zone(use_zone: str | None, zones: dict[str, Any]) -> str | None:
    """용도지역 명칭 정규화 — 공백 제거 + '지역' 접미 보정. 데이터 키와 매칭되는 정규명 반환(미매칭 None)."""
    if not use_zone:
        return None
    z = str(use_zone).replace(" ", "").strip()
    if not z:
        return None
    if z in zones or z in _override:
        return z
    if (z + "지역") in zones or (z + "지역") in _override:
        return z + "지역"
    return None


def all_zone_limits() -> dict[str, Any]:
    """전 용도지역 × 산정변수 한도 + provenance 일괄 노출(엔진 규제 SSOT read 표면).

    플랫폼이 자신의 ZONE_LIMITS를 이 1차출처와 대조(reg-source divergence·P5)하는 read-only 소비원.
    데이터파일 zone ∪ override zone, 변수별 한도(override 우선). 결정론(동일 데이터파일 동일 출력)."""
    data = _load()
    meta = dict(data.get("_meta") or {})
    zones_in = data.get("zones") or {}
    src = meta.get("source") or "national_zone_limits"
    out: dict[str, Any] = {}
    for z in sorted(set(zones_in) | set(_override)):
        entry = _merged_entry(z, zones_in)  # 공유 SSOT — resolve_zone_limit와 동일 override 의미
        vars_out: dict[str, Any] = {}
        for var, key in _VAR_TO_KEY.items():
            v = _limit_num(entry.get(key))
            if v is not None:
                vars_out[var] = {"value": v, "unit": "%", "source": f"{src}:{z}"}
        if vars_out:
            out[z] = vars_out
    return {"meta": meta, "zones": out}


def resolve_zone_limit(use_zone: str | None, target_variable: str | None) -> tuple[float, str] | None:
    """(용도지역, 산정변수) → (한도%, 출처). 미상 zone/비대상 변수/미수록 → None(날조 금지·표면화)."""
    key = _VAR_TO_KEY.get(target_variable or "")
    if not key:
        return None
    data = _load()
    zones = data.get("zones") or {}
    z = _norm_zone(use_zone, zones)
    if z is None:
        return None
    val = _limit_num(_merged_entry(z, zones).get(key))  # 공유 SSOT — all_zone_limits와 동일 override 병합
    if val is None:
        return None
    src = (data.get("_meta") or {}).get("source") or "national_zone_limits"
    return val, f"{src}:{z}"
