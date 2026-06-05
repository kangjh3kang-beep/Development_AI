"""R-ONE 부동산통계정보 인제스션 레이어 — 다종 통계 단일 출처화.

지가변동률(reb_client) 외 주택가격지수 변동률·상업용 투자수익률(cap rate)·전월세전환율을
통계표(STATBL_ID)별로 조회해 시점수정·수익환원법에 실데이터를 주입한다.

설계 원칙(할루시네이션 방지):
 - STATBL_ID는 env(RONE_*_STATBL_ID)로 명시 설정하거나 키워드 자동탐색(rone-status).
 - 값은 sane-range 검증을 통과할 때만 채택, 아니면 기존 근사값으로 graceful 폴백.
 - 모든 반환값에 source('R-ONE' | '근사')를 명시해 출처 투명성 보장.

각 모듈이 각자 추정/하드코딩하던 시세·수익률·시점보정을 본 레이어로 단일화한다.
"""

from __future__ import annotations

import os
from typing import Any


def _sido_of(address: str) -> str:
    from app.services.land_intelligence.land_price_index import _sido_of as _s
    return _s(address)


# 통계표 레지스트리: env STATBL_ID 키 + 수록주기 + 탐색 키워드 + 합리적 값 범위
_STAT_REGISTRY = {
    "housing": {
        "env": "RONE_HOUSING_STATBL_ID", "cycle": "MM",
        "keyword": "주택종합 매매가격지수", "kind": "rate",  # 월 변동률 누적
    },
    "commercial_yield": {
        "env": "RONE_COMMYIELD_STATBL_ID", "cycle": "QQ",
        "keyword": "상업용부동산 투자수익률", "kind": "level",  # 최신 수익률(%)
        "sane": (1.0, 12.0),
    },
    "jeonse_conv": {
        "env": "RONE_JEONSE_CONV_STATBL_ID", "cycle": "MM",
        "keyword": "전월세전환율", "kind": "level",
        "sane": (2.0, 12.0),
    },
}


def _statbl(kind: str) -> str:
    reg = _STAT_REGISTRY.get(kind, {})
    return (os.getenv(reg.get("env", "")) or "").strip()


async def housing_time_adjust(address: str = "") -> dict[str, Any] | None:
    """주택매매가격지수 월 변동률 누적 → 건물/주택 시점수정계수. 미설정/비정상 시 None."""
    statbl = _statbl("housing")
    if not statbl:
        return None
    try:
        from app.services.external_api.reb_client import (
            fetch_statbl_rows, cumulative_factor_from_rows,
        )
        rows = await fetch_statbl_rows(statbl, "MM", size=480)
        if not rows:
            return None
        f = cumulative_factor_from_rows(rows, _sido_of(address))
        if f and 0.5 < f < 2.0:  # sane: 24개월 누적이 ±100% 이내
            return {"factor": f, "source": "R-ONE", "basis": "주택매매가격지수 누적 변동"}
    except Exception:  # noqa: BLE001
        pass
    return None


async def commercial_cap_rate(address: str = "") -> dict[str, Any] | None:
    """상업용부동산 투자수익률(소득수익률) 최신값 → 자본환원율(cap rate). 비정상 시 None."""
    statbl = _statbl("commercial_yield")
    if not statbl:
        return None
    try:
        from app.services.external_api.reb_client import (
            fetch_statbl_rows, latest_value_from_rows,
        )
        rows = await fetch_statbl_rows(statbl, "QQ", size=120)
        if not rows:
            return None
        res = latest_value_from_rows(rows, _sido_of(address))
        if not res:
            return None
        val, wrttime = res
        lo, hi = _STAT_REGISTRY["commercial_yield"]["sane"]
        if lo <= val <= hi:
            return {"cap_rate": round(val / 100.0, 4), "pct": val,
                    "wrttime": wrttime, "source": "R-ONE",
                    "basis": "상업용부동산 투자수익률(소득수익률) 실측"}
    except Exception:  # noqa: BLE001
        pass
    return None


async def jeonse_conversion_rate(address: str = "") -> dict[str, Any] | None:
    """전월세전환율 최신값(연 %) → 보증금↔월세 환산율. 비정상 시 None."""
    statbl = _statbl("jeonse_conv")
    if not statbl:
        return None
    try:
        from app.services.external_api.reb_client import (
            fetch_statbl_rows, latest_value_from_rows,
        )
        rows = await fetch_statbl_rows(statbl, "MM", size=120)
        if not rows:
            return None
        res = latest_value_from_rows(rows, _sido_of(address))
        if not res:
            return None
        val, wrttime = res
        lo, hi = _STAT_REGISTRY["jeonse_conv"]["sane"]
        if lo <= val <= hi:
            return {"rate": round(val / 100.0, 4), "pct": val,
                    "wrttime": wrttime, "source": "R-ONE",
                    "basis": "전월세전환율 실측"}
    except Exception:  # noqa: BLE001
        pass
    return None


async def land_price_trend(address: str = "") -> dict[str, Any] | None:
    """월별·연도별 지가변동률 통계 시계열(최근 24개월 + 연도별). 미가용 시 None."""
    from app.services.external_api.reb_client import fetch_land_price_changes, trend_from_rows
    rows = await fetch_land_price_changes(months=36)
    if not rows:
        return None
    t = trend_from_rows(rows, _sido_of(address), months=24)
    return t or None


async def get_market_stats(address: str = "") -> dict[str, Any]:
    """지역 부동산 시장 통계 묶음(시점수정·cap rate·전환율) — 모세혈관 주입용 단일 출처.

    각 항목은 R-ONE 실데이터 가용 시 채택, 아니면 None(호출측이 근사 폴백).
    """
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async

    land_ta = await time_adjust_factor_async(address)
    housing = await housing_time_adjust(address)
    cap = await commercial_cap_rate(address)
    jeonse = await jeonse_conversion_rate(address)
    trend = await land_price_trend(address)          # 월별·연도별 지가변동률 추이
    return {
        "region": _sido_of(address) or "전국",
        "land_time_adjust": land_ta,                 # 토지 시점수정(지가변동률)
        "land_price_trend": trend,                   # 월별/연도별 통계분석(시계열)
        "housing_time_adjust": housing,              # 건물/주택 시점수정(주택가격지수)
        "cap_rate": cap,                             # 상업용 투자수익률(자본환원율)
        "jeonse_conversion_rate": jeonse,            # 전월세전환율
        "rone_available": any([
            (land_ta or {}).get("source") == "R-ONE", housing, cap, jeonse, trend,
        ]),
    }
