"""시장·분양 정밀화 계약 패키지 (v4.0 Wave3 W3-8 — 스펙 P [시장·분양 정밀화]).

분양가·흡수율(분양률) 추정을 "감"이 아니라 비교사례 명시·보정 근거·불확실성 정직의
계약으로 표준화한다. 5개 계약:
  - ``ComparableCase``/``ComparableSet``  : 비교 실거래 사례 1건/묶음(선정·제외 사유 명시).
  - ``TimeAdjustment``                    : 거래시점→현재 시점보정(지수·출처·정직 마커).
  - ``PriceSuggestion``                   : 분양가 제안(범위 + 지불여력크로스체크, 점추정 단독 금지).
  - ``AbsorptionEstimate``                : 흡수율 추정(데이터 없으면 UNKNOWN, 날조 금지).

★스파이크 결론(그린필드 금지 — 재확증, 반드시 읽을 것):
1) 적정분양가 SSOT는 이미 존재한다 — ``app.services.sales.pricing.suggest.suggest_base_price``
   (MOLIT 실거래 동/시군구 교차검증 + 신축프리미엄 3안 tiers + 원가회수 2차 가드)와
   ``app.services.market.pricing_band_service.compute_fair_price``(거래사례+지불여력
   PIR/DSR/LTV). 이 패키지는 그 계산을 재구현하지 않고 계약으로 재포장한다(``price_suggestion``
   모듈이 ``suggest_base_price`` 결과를 소비 — 이중 MOLIT 호출 없음).
2) 개별 비교사례(단지·거래·근접범위·선정/제외 사유)는 종전엔 존재하지 않았다 — 기존
   ``_trade_per_pyeong``은 중앙값+표본수만 집계하고 원시 사례를 버렸다. 이번에 그 함수에
   opt-in ``collect_cases`` 파라미터를 추가해(기본 False — 무회귀) 같은 MOLIT 수집 루프에서
   사례를 함께 확보한다(새 MOLIT 호출 추가 없음).
3) 시점보정 실데이터 경로는 존재한다 — ``app.services.land_intelligence.reb_statistics_service.
   housing_time_adjust``(R-ONE 주택매매가격지수, ``RONE_HOUSING_STATBL_ID`` 설정 시 실계수,
   미설정 시 None). ``time_adjustment`` 모듈은 이를 그대로 호출하고 None이면 UNKNOWN+미보정
   정직 표기만 한다(임의 계수 외삽 금지).
4) 흡수율(분양률) 직접 데이터 소스는 부재를 확정했다 — 청약홈(PresaleService,
   ApplyhomeInfoDetailSvc)은 분양 공고정보만 제공하고 청약경쟁률·계약률은 미포함
   (``app.services.persona.checklist.judge_sales_subscription``가 이미 동일 결론으로
   실거래 표본수를 "수요 활성도 대리지표(직접 청약경쟁률 아님)"로만 쓰고 있음). R-ONE에도
   흡수율 지표 없음. 따라서 ``absorption`` 모듈은 항상 UNKNOWN을 반환한다(모델 날조 금지).
"""
from __future__ import annotations

from app.services.market_precision.absorption import estimate_absorption
from app.services.market_precision.comparables import build_comparable_set
from app.services.market_precision.contracts import (
    AbsorptionEstimate,
    ComparableCase,
    ComparableSet,
    PriceSuggestion,
    TimeAdjustment,
)
from app.services.market_precision.price_suggestion import (
    assemble_market_precision,
    build_price_suggestion,
    price_suggestion_from_result,
)
from app.services.market_precision.time_adjustment import resolve_time_adjustment

__all__ = [
    "AbsorptionEstimate",
    "ComparableCase",
    "ComparableSet",
    "PriceSuggestion",
    "TimeAdjustment",
    "assemble_market_precision",
    "build_comparable_set",
    "build_price_suggestion",
    "estimate_absorption",
    "price_suggestion_from_result",
    "resolve_time_adjustment",
]
