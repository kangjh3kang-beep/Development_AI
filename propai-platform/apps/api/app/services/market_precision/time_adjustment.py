"""TimeAdjustment — 거래 시점 → 현재 시점 보정(R-ONE 실데이터 opt-in, 외삽 금지).

★스파이크 확정: ``app.services.land_intelligence.reb_statistics_service.housing_time_adjust``가
이미 R-ONE 주택매매가격지수 실데이터 경로를 보유한다(``RONE_HOUSING_STATBL_ID`` 환경변수
설정 시에만 조회 — 미설정/조회실패는 None). 이 모듈은 그 함수를 재구현하지 않고 그대로
호출하며, None을 받으면 임의 계수를 만들지 않고 UNKNOWN + "미보정" 정직 표기로 반환한다
(``app.services.cost.unit_price_repository``의 opt-in escalate_to_current와 동일 관례 —
보정은 부착만 하고 원본 가격을 자동으로 변형하지 않는다).

★R1 M-3 봉합(OBSERVED 경로 정직성 비대칭 해소): R-ONE 실계수가 가용해도(``status=OBSERVED``)
이 모듈은 그 계수를 표시 가격(ComparableCase/PriceSuggestion)에 실제로 적용하지 않는다 —
근거로만 부착한다. 종전엔 이 사실이 UNKNOWN 경로의 assumption에만 있고 OBSERVED 경로에는
없어, "실계수가 있으니 이미 반영됐다"는 오인 소지가 있었다. 두 경로 모두 동일하게
"계수는 근거 표기용, 표시 가격은 미보정 원본"임을 assumption에 명시한다.
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
        assumption=(
            "이 계수는 근거 표기용입니다 — 표시 가격(비교사례·분양가 제안)은 이 계수를 "
            "적용하지 않은 미보정 원본 그대로입니다(자동 시점보정 미실시)."
        ),
        limitation="R-ONE 통계는 광역시도 단위 대표치입니다 — 개별 단지 변동과 다를 수 있습니다(외삽 한계).",
    )


__all__ = ["resolve_time_adjustment"]
