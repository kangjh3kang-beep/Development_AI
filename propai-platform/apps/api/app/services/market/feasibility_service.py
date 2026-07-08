"""시장조사 보고서용 개략 사업타당성 추정 서비스 (Quick Massing Estimate).

[역할 구분 — 중요]
- 본 서비스(market/FeasibilityService): 시장조사 보고서에 싣는 "빠른 개략 추정"이다.
  주소 1건에 대해 용도지역·주변 평당시세만으로 가설계 규모·개략 ROI를 즉시 계산한다.
  단일 호출·무의존(외부 모듈 없음)으로 보고서 생성 흐름을 막지 않는 것이 목적이다.
- 정밀 수지분석은 FeasibilityServiceV2
  (apps/api/app/services/feasibility/feasibility_service_v2.py)를 사용한다.
  V2는 15개 개발유형 모듈·지역시세 테이블·NPV·등급판정 등 정밀 엔진이다.
  실제 사업 의사결정 수치는 반드시 V2를 사용하고, 본 서비스 수치는 "참고용 개략값"이다.

반환 단위: 만원 (10k won).
아래 상수는 모두 개략 추정용 가정값이며, 정밀값이 아니다(근거는 각 주석 참조).
"""
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785  # 1평 = 3.305785㎡

# ── 개략 추정 가정 상수(매직넘버 제거) ──
# 평당 건축비(만원/평): 도급공사 기준 중간값 가정. 정밀 단가는 V2 cost 엔진이 산출.
CONSTRUCTION_COST_PER_PYEONG_10K = 750
# 토지 매입비 추정: 공시지가에 곱하는 실거래 배수(공시지가는 통상 실거래의 약 40~60% 수준 → 2.5배 환산)
LAND_COST_OFFICIAL_PRICE_MULTIPLIER = 2.5
# 공시지가 정보가 없을 때 토지비 기본 단가(만원/평)
LAND_COST_DEFAULT_PER_PYEONG_10K = 2000
# 부대비용율: (건축비+토지비) 대비 설계·인허가·금융 등 소프트코스트 비율
SOFT_COST_RATIO = 0.10
# 전용률(분양 가능 면적/연면적): 공용면적 제외한 분양 가능 비율 가정
SALEABLE_AREA_RATIO = 0.75
# NPV(순현재가치) 개략 가정: 개발사업 자본비용(할인율) 연 8%, 개발기간 3년.
#   토지비는 t0 선투입, 건축·부대비는 t1~N 균등 분산, 분양수입은 완공시점(tN) 일시 실현으로 단순화.
#   정밀 현금흐름·세후 IRR/NPV 는 FeasibilityServiceV2 가 산출(본 값은 참고용 개략).
NPV_DISCOUNT_RATE = 0.08
NPV_DEV_PERIOD_YEARS = 3

class FeasibilityService:
    def __init__(self) -> None:
        pass

    def _estimate_zoning_parameters(self, zone_type: str) -> dict[str, Any] | None:
        """용도지역의 건폐율(BCA)·용적률(FAR) 한도를 공용 SSOT에서 산정.

        ★종전 자체 하드코딩 표(상업600·녹지80·미분류 150 기본값)는 공용 산식(legal_zone_limits)
        우회 + 미분류 용도지역에 근거 없는 150% 적용 위험이라 제거(완성도 감사 P0). 이제
        applicable_limits_for(법정범위→조례→계획 계층)에 위임하고, 못 찾으면 None을 반환해
        호출부가 정직하게 '산출 불가'로 처리한다(무날조).
        """
        from app.services.zoning.legal_zone_limits import applicable_limits_for

        limits = applicable_limits_for(zone_type or None)
        if not limits:
            return None
        far = limits.get("applied_far_pct") or limits.get("legal_max_far_pct")
        bca = limits.get("applied_bcr_pct") or limits.get("legal_max_bcr_pct")
        if not far:
            return None
        basis = str(limits.get("far_source") or "법정범위")
        if not limits.get("ordinance_confirmed"):
            basis += " (조례 미확인 — 법정상한 기준)"
        return {"far": float(far), "bca": float(bca or 0), "basis": basis}

    def analyze_feasibility(
        self,
        land_area_sqm: float,
        zone_type: str,
        avg_pyeong_price_manwon: float,
        official_price_per_sqm: float = 0,
        far_pct_override: float | None = None,
        bcr_pct_override: float | None = None,
        far_basis_override: str | None = None,
    ) -> dict[str, Any]:
        """보고서용 개략 사업타당성 계산(참고용). 반환 단위: 만원(10k won).

        정밀 수지는 FeasibilityServiceV2 를 사용한다(상단 docstring 참조).
        far_pct_override: 상위(다필지 통합분석 blended_far_eff_pct 등)가 이미 확보한 실효
          용적률이 있으면 주입 — 자체 추정 대신 공용 산식 값을 그대로 사용(SSOT 단일경유).
        """
        try:
            if not land_area_sqm or land_area_sqm <= 0:
                # 면적 미상 — 종전 기본 100평(330㎡) 임의 대입 제거(무날조).
                return {
                    "method": "quick_estimate",
                    "available": False,
                    "reason": "대지면적 미확보 — 개략 수지 산출 불가(면적 확인 후 재시도)",
                }
            if far_pct_override and far_pct_override > 0:
                params: dict[str, Any] | None = {
                    "far": float(far_pct_override),
                    "bca": float(bcr_pct_override or 0),
                    "basis": far_basis_override or "다필지 통합분석 실효용적률(면적가중)",
                }
            else:
                params = self._estimate_zoning_parameters(zone_type)
            if not params:
                # 용도지역 미확인 — 근거 없는 기본값(구 150%)으로 날조하지 않고 정직 반환.
                return {
                    "method": "quick_estimate",
                    "available": False,
                    "reason": f"용도지역 미확인('{zone_type}') — 용적률 근거 부재로 개략 수지 산출 불가",
                }
            far_ratio = params["far"] / 100.0

            # 1. 건축 가능 연면적(개략): 토지면적 × 용적률
            total_gfa_sqm = land_area_sqm * far_ratio
            total_gfa_pyeong = total_gfa_sqm / PYEONG_SQM

            # 2. 예상 건축비: 연면적(평) × 평당 건축비
            total_construction_cost = total_gfa_pyeong * CONSTRUCTION_COST_PER_PYEONG_10K

            # 3. 예상 토지 매입비: 공시지가가 있으면 실거래 환산배수 적용, 없으면 기본 평단가
            if official_price_per_sqm > 0:
                land_cost = (
                    land_area_sqm * official_price_per_sqm * LAND_COST_OFFICIAL_PRICE_MULTIPLIER
                ) / 10000
            else:
                land_cost = (land_area_sqm / PYEONG_SQM) * LAND_COST_DEFAULT_PER_PYEONG_10K

            # 부대비용: (건축비+토지비)의 일정 비율
            soft_cost = (total_construction_cost + land_cost) * SOFT_COST_RATIO
            total_cost = total_construction_cost + land_cost + soft_cost

            # 4. 예상 분양 수익: 분양 가능 면적(연면적×전용률) × 평당 시세
            saleable_pyeong = total_gfa_pyeong * SALEABLE_AREA_RATIO
            expected_revenue = saleable_pyeong * avg_pyeong_price_manwon

            # 5. ROI(개략) 산출
            profit = expected_revenue - total_cost
            roi_percent = (profit / total_cost) * 100 if total_cost > 0 else 0

            # 6. NPV(개략): 토지비 t0 선투입, 건축·부대비 t1~N 균등 분산, 분양수입 tN 일시 실현 후 할인.
            r = NPV_DISCOUNT_RATE
            n = NPV_DEV_PERIOD_YEARS
            annual_build_cost = (total_construction_cost + soft_cost) / n if n > 0 else 0
            npv = -land_cost
            for t in range(1, n + 1):
                npv += (-annual_build_cost) / ((1 + r) ** t)
            npv += expected_revenue / ((1 + r) ** n)

            return {
                "method": "quick_estimate",  # 본 결과는 보고서용 개략 추정임을 명시(정밀=V2)
                "massing": {
                    "land_area_sqm": round(land_area_sqm, 2),
                    "gfa_sqm": round(total_gfa_sqm, 2),
                    "gfa_pyeong": round(total_gfa_pyeong, 2),
                    "estimated_far": params["far"],
                    "estimated_bca": params["bca"],
                    # 용적률 출처(공용 산식/blended 주입/법정폴백) — 실무자 근거 추적용(무날조).
                    "far_basis": params.get("basis") or "",
                },
                "financials": {
                    "total_revenue_10k": int(expected_revenue),
                    "land_cost_10k": int(land_cost),
                    "construction_cost_10k": int(total_construction_cost),
                    "soft_cost_10k": int(soft_cost),
                    "total_cost_10k": int(total_cost),
                    "net_profit_10k": int(profit),
                    "roi_percent": round(roi_percent, 2),
                    "npv_10k": int(npv),  # 순현재가치(개략·할인 반영). 양수면 자본비용 초과 수익.
                },
                "assumptions": {
                    "avg_pyeong_price_10k": int(avg_pyeong_price_manwon),
                    "construction_cost_per_pyeong_10k": CONSTRUCTION_COST_PER_PYEONG_10K,
                    "land_cost_official_price_multiplier": LAND_COST_OFFICIAL_PRICE_MULTIPLIER,
                    "soft_cost_ratio": SOFT_COST_RATIO,
                    "saleable_area_ratio": SALEABLE_AREA_RATIO,
                    "npv_discount_rate": NPV_DISCOUNT_RATE,
                    "npv_dev_period_years": NPV_DEV_PERIOD_YEARS,
                    "note": "보고서용 개략 추정값(참고용). NPV는 할인율 8%·개발 3년 단순가정. 정밀 수지·세후 IRR은 FeasibilityServiceV2 사용.",
                }
            }
        except Exception as e:
            logger.error("Feasibility analysis failed", error=str(e))
            return {
                "error": "사업 타당성 분석 중 오류가 발생했습니다.",
                "details": str(e)
            }
