"""중심엔진 수렴 — 규제 출처 정합 대조(reg-source divergence·P5).

플랫폼 권위 ZONE_LIMITS(auto_zoning_service)와 엔진 1차출처(GET /api/v1/reg/zone-limits, 시행령 §84/§85)를
용도지역×지표(FAR/BCR)로 전수 대조해 drift를 표면화한다. 두 테이블은 같은 시행령 상한의 별도 사본이라
한쪽만 개정되면 분석이 어긋난다 — 이 대조가 authoritative 승격(엔진 SSOT 일원화) 전 drift 게이트다.

순수함수(부수효과·라이브 발화 0·결정론). 엔진 호출/degrade는 BFF 라우터가 담당, 여기선 두 dict만 비교.
"""
from __future__ import annotations

import math
from typing import Any

# (플랫폼 키, 엔진 변수명, 표시 라벨) — FAR/BCR만 국가 상한 대조 대상(height는 엔진 national 미수록).
_METRICS = (("max_far", "far_floor_area", "FAR"), ("max_bcr", "building_area", "BCR"))

# 엔진 national 용도지역 표(시행령 §84/§85)가 **의도적으로** 미수록하는 플랫폼 특별구역(별도 법령 규율).
# 이 집합의 platform_only는 정상 coverage gap. 그 외 platform_only는 unexpected(엔진 규제 누락 회귀 의심)로 표면화
# → drift==0·match_rate=1.0만 보면 묻히는 '엔진이 기존 zone/지표를 잃은' 회귀를 별도 신호로 노출.
ENGINE_UNSUPPORTED_ZONES = frozenset({"역세권개발구역", "도시재생활성화구역"})


def _num(v: Any) -> float | None:
    """유한 수치만(bool·None·nan·inf 거부) — 잘못된 한도값이 거짓 일치/발산을 만들지 않도록."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _engine_value(metric: Any) -> float | None:
    """엔진 지표 항목({value:...}) → 유한 수치. 구조 비정상(list 등)이면 None — 한 지표의 변형이
    예외로 전체 대조를 reconcile_failed로 뭉개지 않도록 격리(해당 지표만 engine 결손=정직 표면화)."""
    return _num(metric.get("value")) if isinstance(metric, dict) else None


def _classify(pv: float | None, ev: float | None, tol: float) -> tuple[str, float | None]:
    """한 쌍(platform, engine) → (상태, rel_err). 한쪽 결손=coverage gap(platform_only/engine_only),
    양측 존재 시 상대오차 tol 이내=matched, 초과=drift(개정 비동기화 의심)."""
    if pv is None:
        return "engine_only", None
    if ev is None:
        return "platform_only", None
    if ev == 0:
        return ("matched" if pv == 0 else "drift"), None
    rel = abs(pv - ev) / abs(ev)
    return ("matched" if rel <= tol else "drift"), round(rel, 6)


def compare_zone_limits(platform: dict[str, Any], engine_zones: dict[str, Any], *, tol: float = 0.0,
                        expected_engine_unsupported: frozenset[str] = ENGINE_UNSUPPORTED_ZONES) -> dict[str, Any]:
    """플랫폼 ZONE_LIMITS vs 엔진 1차출처(zone→var→{value}) 정합 대조.

    platform: {zone: {max_far, max_bcr, ...}}. engine_zones: {zone: {far_floor_area: {value}, ...}}.
    반환: rows(zone·metric·platform·engine·rel_err·status) + 요약(matched/drift·coverage gap·match_rate)
    + unexpected_platform_only(엔진이 기존 규제 zone/지표를 잃은 **회귀 신호** — drift==0에 묻히지 않게 별도 표면화).
    tol=0이면 완전일치만 matched(시행령 상한은 정확값이라 기본 엄격). 결정론·순수."""
    rows: list[dict[str, Any]] = []
    matched = drift = platform_only = engine_only = 0
    platform_only_zones: set[str] = set()
    engine_only_zones: set[str] = set()
    for zone in sorted(set(platform) | set(engine_zones)):
        p = platform.get(zone) or {}
        e = engine_zones.get(zone) or {}
        for pkey, ekey, label in _METRICS:
            pv = _num(p.get(pkey))
            ev = _engine_value(e.get(ekey))  # 구조 비정상 격리(전체 대조 보호)
            if pv is None and ev is None:
                continue  # 양측 미수록 — 대조 대상 아님(noise 배제)
            status, rel = _classify(pv, ev, tol)
            if status == "matched":
                matched += 1
            elif status == "drift":
                drift += 1
            elif status == "platform_only":
                platform_only += 1
                platform_only_zones.add(zone)
            else:
                engine_only += 1
                engine_only_zones.add(zone)
            rows.append({"zone": zone, "metric": label, "platform": pv, "engine": ev,
                         "rel_err": rel, "status": status})
    compared = matched + drift  # 양측 모두 값 존재(진짜 대조 가능) 건수
    # ★엔진이 잃은 규제(기대 미수록 특별구역 외 platform_only) = 회귀 신호. 비어야 정상.
    unexpected = sorted(z for z in platform_only_zones if z not in expected_engine_unsupported)
    return {
        "rows": rows,
        "matched": matched,
        "drift": drift,
        "platform_only": platform_only,  # 엔진 national 미수록(특별구역 등) — 정상 coverage gap일 수 있음
        "engine_only": engine_only,
        "platform_only_zones": sorted(platform_only_zones),
        "engine_only_zones": sorted(engine_only_zones),
        "unexpected_platform_only": unexpected,  # 비어있지 않으면 엔진 규제 누락 회귀 의심(감시 신호)
        "compared": compared,
        "match_rate": (matched / compared) if compared else None,
        "platform_zones": len(platform),
        "engine_zones": len(engine_zones),
    }


def platform_zone_limits() -> dict[str, Any]:
    """플랫폼 권위 용도지역 한도(auto_zoning_service.ZONE_LIMITS) — reg-source 대조 좌변.
    lazy import(VWorldService 체인 격리) — 호출 시점에만 적재."""
    from app.services.zoning.auto_zoning_service import ZONE_LIMITS
    return ZONE_LIMITS
