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
from typing import Any, Dict
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

# 용도지역별 기본 건폐율(BCA, %)·용적률(FAR, %) 추정표.
# 국토계획법 시행령 상한 부근의 대표값이며, 조례 실효값은 V2/조례 엔진이 반영한다.
ZONING_PARAMS = {
    "제1종주거": {"bca": 60, "far": 150},
    "제2종주거": {"bca": 60, "far": 200},
    "제3종주거": {"bca": 50, "far": 250},
    "상업": {"bca": 70, "far": 600},
    "준주거": {"bca": 60, "far": 400},
    "공업": {"bca": 70, "far": 300},
    "녹지": {"bca": 20, "far": 80},
}
ZONING_PARAMS_DEFAULT = {"bca": 50, "far": 150}  # 미분류 용도지역 기본값


class FeasibilityService:
    def __init__(self) -> None:
        pass

    def _estimate_zoning_parameters(self, zone_type: str) -> Dict[str, Any]:
        """용도지역 이름에서 기본 건폐율(BCA)·용적률(FAR) 추정(개략값)."""
        zone = zone_type or ""
        # 준주거는 "주거"를 포함하므로 먼저 판정해야 제2종주거로 오분류되지 않는다.
        if "준주거" in zone:
            return dict(ZONING_PARAMS["준주거"])
        if "제1종" in zone and "주거" in zone:
            return dict(ZONING_PARAMS["제1종주거"])
        if "제2종" in zone and "주거" in zone:
            return dict(ZONING_PARAMS["제2종주거"])
        if "제3종" in zone and "주거" in zone:
            return dict(ZONING_PARAMS["제3종주거"])
        if "상업" in zone:
            return dict(ZONING_PARAMS["상업"])
        if "공업" in zone:
            return dict(ZONING_PARAMS["공업"])
        if "녹지" in zone:
            return dict(ZONING_PARAMS["녹지"])
        return dict(ZONING_PARAMS_DEFAULT)

    def analyze_feasibility(
        self,
        land_area_sqm: float,
        zone_type: str,
        avg_pyeong_price_manwon: float,
        official_price_per_sqm: float = 0
    ) -> Dict[str, Any]:
        """보고서용 개략 사업타당성 계산(참고용). 반환 단위: 만원(10k won).

        정밀 수지는 FeasibilityServiceV2 를 사용한다(상단 docstring 참조).
        """
        try:
            params = self._estimate_zoning_parameters(zone_type)
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

            return {
                "method": "quick_estimate",  # 본 결과는 보고서용 개략 추정임을 명시(정밀=V2)
                "massing": {
                    "land_area_sqm": round(land_area_sqm, 2),
                    "gfa_sqm": round(total_gfa_sqm, 2),
                    "gfa_pyeong": round(total_gfa_pyeong, 2),
                    "estimated_far": params["far"],
                    "estimated_bca": params["bca"]
                },
                "financials": {
                    "total_revenue_10k": int(expected_revenue),
                    "land_cost_10k": int(land_cost),
                    "construction_cost_10k": int(total_construction_cost),
                    "soft_cost_10k": int(soft_cost),
                    "total_cost_10k": int(total_cost),
                    "net_profit_10k": int(profit),
                    "roi_percent": round(roi_percent, 2)
                },
                "assumptions": {
                    "avg_pyeong_price_10k": int(avg_pyeong_price_manwon),
                    "construction_cost_per_pyeong_10k": CONSTRUCTION_COST_PER_PYEONG_10K,
                    "land_cost_official_price_multiplier": LAND_COST_OFFICIAL_PRICE_MULTIPLIER,
                    "soft_cost_ratio": SOFT_COST_RATIO,
                    "saleable_area_ratio": SALEABLE_AREA_RATIO,
                    "note": "보고서용 개략 추정값(참고용). 정밀 수지는 FeasibilityServiceV2 사용.",
                }
            }
        except Exception as e:
            logger.error("Feasibility analysis failed", error=str(e))
            return {
                "error": "사업 타당성 분석 중 오류가 발생했습니다.",
                "details": str(e)
            }
