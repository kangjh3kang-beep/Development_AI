"""AbsorptionEstimate — 흡수율(분양률) 추정. 데이터 소스 부재 확정 → 항상 UNKNOWN(모델 날조 금지).

★스파이크 확정(반드시 읽을 것): 청약홈(``app.services.land_intelligence.presale_service.
PresaleService``, ApplyhomeInfoDetailSvc)은 분양 공고정보(단지·주택형별 분양가·접수기간 등)만
제공하고 청약경쟁률·계약률(=실제 흡수 실적)은 별도 미연동이다. ``app.services.persona.
checklist.judge_sales_subscription``도 이미 동일 결론에 도달해 "주변 실거래 표본수를 수요
활성도 대리지표로 사용(직접 청약경쟁률 아님)"이라고 명시 디스클레이머를 달고 있다. R-ONE
부동산통계(``reb_statistics_service``)에도 흡수율 직접 지표가 없다. 따라서 이 함수는
휴리스틱으로 흡수율 수치를 만들지 않고 항상 UNKNOWN을 반환한다(RDM/RFI 연계는 W3-6
``emit_rfi()``로 "흡수율 데이터 소스 없음"을 구조화 방출할 수 있으나, 배선 여부는 호출부
선택 — 이번 1차 범위는 계약 + 정직 표기까지).
"""
from __future__ import annotations

from app.services.market_precision.contracts import AbsorptionEstimate
from app.services.provenance.fact_status import FactStatus

_BASIS = (
    "흡수율(분양률) 직접 데이터 소스 부재 — 청약홈(ApplyhomeInfoDetailSvc)은 분양 공고정보만 "
    "제공하며 청약경쟁률·계약률(실제 흡수 실적)은 별도 미연동. R-ONE 통계에도 흡수율 지표 없음."
)
_LIMITATIONS: tuple[str, ...] = (
    "흡수율(분양률) 수치를 산출/추정하지 않습니다 — 실데이터 없이 모델링하면 날조입니다.",
    "청약홈 경쟁률·계약률 API 연동 또는 시행사 실적 데이터 확보 시 재구현이 필요합니다.",
)


def estimate_absorption(demand_proxy_note: str | None = None) -> AbsorptionEstimate:
    """흡수율 추정 — 항상 UNKNOWN(실데이터 부재, 모델 날조 금지).

    demand_proxy_note: ``judge_sales_subscription``류의 "수요 활성도 대리지표" 서술(예: 주변
    실거래 표본수)을 전달하면 참고 문맥으로만 assumptions에 남긴다(흡수율 수치로 오인되지 않게
    "참고(흡수율 아님)" 접두를 강제한다).
    """
    assumptions: tuple[str, ...] = ()
    if demand_proxy_note:
        assumptions = (f"참고(흡수율 아님): {demand_proxy_note}",)
    return AbsorptionEstimate(
        status=FactStatus.UNKNOWN,
        absorption_rate_pct=None,
        basis=_BASIS,
        assumptions=assumptions,
        limitations=_LIMITATIONS,
        note="흡수율 UNKNOWN — 전문가 분양 전략 검토 필수(가짜 수치로 대체하지 않음).",
    )


__all__ = ["estimate_absorption"]
