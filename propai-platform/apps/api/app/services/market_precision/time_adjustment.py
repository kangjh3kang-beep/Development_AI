"""TimeAdjustment — 거래 시점 → 현재 시점 보정(R-ONE 실데이터 opt-in, 외삽 금지).

★스파이크 확정: ``app.services.land_intelligence.reb_statistics_service.housing_time_adjust``가
이미 R-ONE 주택매매가격지수 실데이터 경로를 보유한다(``RONE_HOUSING_STATBL_ID`` 환경변수
설정 시에만 조회 — 미설정/조회실패는 None). 이 모듈은 그 함수를 재구현하지 않고 그대로
호출하며, None을 받으면 임의 계수를 만들지 않고 UNKNOWN + "미보정" 정직 표기로 반환한다
(``app.services.cost.unit_price_repository``의 opt-in escalate_to_current와 동일 관례 —
보정은 부착만 하고 원본 가격을 자동으로 변형하지 않는다).
"""
from __future__ import annotations

from app.services.land_intelligence.reb_statistics_service import housing_time_adjust
from app.services.market_precision.contracts import TimeAdjustment
from app.services.provenance.fact_status import FactStatus

_UNCONFIGURED_LIMITATION = (
    "R-ONE 주택매매가격지수 통계표ID(RONE_HOUSING_STATBL_ID) 미설정 또는 조회 실패 — "
    "시점보정 계수를 산출/외삽하지 않고 미보정 원본 그대로 사용합니다(정직 표기, 가짜 계수 금지)."
)


async def resolve_time_adjustment(address: str = "") -> TimeAdjustment:
    """주소 기준 시점보정계수를 조회한다. 미가용 시 UNKNOWN(임의 계수 금지)."""
    result = await housing_time_adjust(address)
    if not result:
        return TimeAdjustment(
            status=FactStatus.UNKNOWN,
            factor=None,
            source="미보정",
            basis="시점보정 실데이터 미가용(R-ONE 통계표 미설정 또는 조회 실패).",
            assumption="비교사례 거래가는 시점보정 없이 원본(거래 시점 가격) 그대로 사용됩니다.",
            limitation=_UNCONFIGURED_LIMITATION,
        )
    return TimeAdjustment(
        status=FactStatus.OBSERVED,
        factor=result.get("factor"),
        source=result.get("source") or "R-ONE",
        basis=result.get("basis") or "주택매매가격지수 누적 변동",
        assumption=None,
        limitation="R-ONE 통계는 광역시도 단위 대표치입니다 — 개별 단지 변동과 다를 수 있습니다(외삽 한계).",
    )


__all__ = ["resolve_time_adjustment"]
