"""FeasibilityServiceV2 — 수지분석 고도화 통합 서비스.

전체 파이프라인 오케스트레이션:
입력 → 모듈 선택 → 계산 → 등급 판정 → 결과 반환.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.feasibility.modules.base_module import ModuleInput, ModuleOutput
from app.services.feasibility.modules.module_assembler import get_module, list_modules, ALL_MODULE_CODES
from app.services.feasibility.aggregation_engine import compare_scenarios

logger = logging.getLogger(__name__)


class FeasibilityServiceV2:
    """수지분석 고도화 v2 통합 서비스."""

    def calculate(self, inp: ModuleInput) -> ModuleOutput:
        """단일 개발유형 수지분석 실행.

        Args:
            inp: ModuleInput (development_type 필수)

        Returns:
            ModuleOutput
        """
        module = get_module(inp.development_type)

        errors = module.validate_input(inp)
        if errors:
            raise ValueError(f"입력 검증 실패: {', '.join(errors)}")

        return module.calculate(inp)

    def calculate_multi(self, inputs: list[ModuleInput]) -> dict[str, Any]:
        """복수 개발유형 비교 분석.

        Args:
            inputs: 여러 ModuleInput 리스트

        Returns:
            {'results': [...ModuleOutput...], 'comparison': {...}}
        """
        results = []
        for inp in inputs:
            output = self.calculate(inp)
            results.append(output)

        # 비교 분석용 dict 변환
        scenarios = []
        for r in results:
            scenarios.append({
                "name": f"{r.module_name} ({r.development_type})",
                "profit_rate_pct": r.profit_rate_pct,
                "roi_pct": r.roi_pct,
                "grade": r.grade,
                "net_profit_won": r.net_profit_won,
                "total_revenue_won": r.total_revenue_won,
                "total_cost_won": r.total_cost_won,
            })

        comparison = compare_scenarios(scenarios)

        return {
            "results": results,
            "comparison": comparison,
        }

    def list_available_modules(self) -> list[dict[str, str]]:
        """사용 가능한 개발유형 모듈 목록."""
        return list_modules()

    def get_module_info(self, development_type: str) -> dict[str, str]:
        """특정 모듈 정보."""
        module = get_module(development_type)
        return {
            "code": module.code,
            "name": module.name,
        }

    # ------------------------------------------------------------------
    # Auto-Recommend Top 3
    # ------------------------------------------------------------------

    async def auto_recommend_top3(
        self,
        address: str,
        land_area_sqm: float | None = None,
        region: str = "서울",
        equity_won: int = 10_000_000_000,  # 자기자본 100억 기본
    ) -> dict:
        """부지 주소로부터 최적 사업모델 Top 3 자동 추천."""

        # Step 1: 용도지역 자동 감지
        from ..zoning.auto_zoning_service import AutoZoningService
        zoning_service = AutoZoningService()
        zoning = await zoning_service.analyze_by_address(address)

        zone_type = zoning.get("zone_type", "")
        zone_limits = zoning.get("zone_limits") or {}
        site_area = land_area_sqm or zoning.get("land_area_sqm") or 1000

        # Step 2: 인허가 가능 유형 필터
        from .permit_validator import (
            get_permitted_types,
            check_permit_feasibility,
            DEVELOPMENT_TYPE_NAMES,
        )
        permitted_types = get_permitted_types(zone_type)

        if not permitted_types:
            return {
                "error": f"'{zone_type}' 용도지역에서 개발 가능한 사업모델이 없습니다.",
                "recommendations": [],
            }

        # Step 2.5: 조례 기반 유효 용적률/건폐율 적용
        # 조례값이 있으면 법정 상한보다 낮은 값이 실효값
        ordinance_far = zone_limits.get("ordinance_far_pct")
        ordinance_bcr = zone_limits.get("ordinance_bcr_pct")
        max_far = ordinance_far or zone_limits.get("max_far_pct", 250)
        max_bcr = ordinance_bcr or zone_limits.get("max_bcr_pct", 60)

        results: list[dict[str, Any]] = []
        for dev_type in permitted_types:
            try:
                # Auto-generate input based on zone constraints
                effective_far = min(max_far, self._get_type_typical_far(dev_type))
                total_gfa = site_area * effective_far / 100
                total_hh = max(1, int(total_gfa / self._get_type_avg_unit_area(dev_type)))

                inp = ModuleInput(
                    development_type=dev_type,
                    total_land_area_sqm=site_area,
                    total_gfa_sqm=total_gfa,
                    total_households=total_hh,
                    avg_sale_price_per_pyeong=self._get_regional_price(dev_type, region, address),
                    avg_area_pyeong=self._get_type_avg_unit_area(dev_type) / 3.305785,
                    sale_ratio=0.95 if dev_type not in ("M14", "M15") else 0.0,
                    official_price_per_sqm=zoning.get("official_price_per_sqm") or 1_500_000,
                    price_multiplier=1.1,
                    building_type=self._get_building_type(dev_type),
                    sido_name=region,
                    sigungu_name="",
                    project_months=self._get_type_project_months(dev_type),
                    discount_rate=0.08,
                    equity_won=equity_won,
                )

                output = self.calculate(inp)
                permit = check_permit_feasibility(dev_type, zone_type)

                # 종합 점수: 순이익(50%) + 수익률(30%) + 인허가용이성(20%)
                # 순이익 기준: 100억 이상이면 만점
                profit_amount_score = min(100, max(0, output.net_profit_won / 1e8))  # 100억→100점
                profit_rate_score = min(100, max(0, output.profit_rate_pct * 2))     # 50%→100점
                permit_score = (6 - permit["permit_complexity"]) * 20                # 1→100, 5→20
                composite = profit_amount_score * 0.5 + profit_rate_score * 0.3 + permit_score * 0.2

                results.append({
                    "development_type": dev_type,
                    "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
                    "feasibility": {
                        "total_revenue_won": output.total_revenue_won,
                        "total_cost_won": output.total_cost_won,
                        "net_profit_won": output.net_profit_won,
                        "profit_rate_pct": output.profit_rate_pct,
                        "roi_pct": output.roi_pct,
                        "npv_won": output.npv_won,
                        "grade": output.grade,
                    },
                    "permit": permit,
                    "unit_summary": {
                        "total_gfa_sqm": round(total_gfa, 1),
                        "total_households": total_hh,
                        "avg_area_pyeong": round(inp.avg_area_pyeong, 1),
                    },
                    "composite_score": round(composite, 1),
                    "input_used": inp,  # For user refinement
                })
            except Exception as e:
                logger.warning(f"{dev_type} 계산 실패: {e}")

        # Step 4: 정렬 + Top 3
        results.sort(key=lambda r: r["composite_score"], reverse=True)
        top3 = results[:3]

        return {
            "address": address,
            "zone_type": zone_type,
            "zone_limits": zone_limits,
            "land_area_sqm": site_area,
            "total_types_analyzed": len(results),
            "permitted_types": len(permitted_types),
            "recommendations": top3,
            "all_results": results,  # Full ranking for reference
        }

    # ------------------------------------------------------------------
    # Helper methods for auto-generation
    # ------------------------------------------------------------------

    def _get_type_typical_far(self, dev_type: str) -> float:
        """개발유형별 일반적 용적률."""
        typical = {
            "M01": 250, "M02": 300, "M03": 400, "M04": 250, "M05": 200,
            "M06": 250, "M07": 400, "M08": 500, "M09": 400, "M10": 100,
            "M11": 80, "M12": 150, "M13": 300, "M14": 250, "M15": 300,
        }
        return typical.get(dev_type, 250)

    def _get_type_avg_unit_area(self, dev_type: str) -> float:
        """개발유형별 평균 세대면적 (m2)."""
        areas = {
            "M01": 84, "M02": 84, "M03": 59, "M04": 84, "M05": 49,
            "M06": 84, "M07": 102, "M08": 39, "M09": 50, "M10": 165,
            "M11": 200, "M12": 130, "M13": 30, "M14": 59, "M15": 84,
        }
        return areas.get(dev_type, 84)

    def _get_regional_price(self, dev_type: str, region: str, address: str = "") -> int:
        """지역x개발유형별 평균 분양가 (원/평).

        주소에서 시군구를 추출하여 세분화된 단가 적용.
        향후 실거래가 API 연동으로 교체 예정.

        2026년 기준 평균 분양가 (만원/평, 보수적):
        - 서울 강남권: 5000~7000, 강북권: 2500~3500
        - 경기 판교/분당: 3500~4500, 수원/용인: 1800~2500, 의정부/파주: 1200~1800
        """
        # 시군구 세분화 (경기도 내 격차 반영)
        sigungu_prices: dict[str, int] = {
            # 서울 구별
            "강남구": 5500, "서초구": 5000, "송파구": 4500, "용산구": 4000,
            "마포구": 3500, "성동구": 3200, "영등포구": 3000,
            "강동구": 3000, "동작구": 2800, "광진구": 2800,
            "노원구": 2200, "도봉구": 2000, "중랑구": 2200, "강북구": 2000,
            # 경기 시별
            "성남시": 3500, "분당": 4000, "판교": 4500,
            "수원시": 2200, "용인시": 2000, "화성시": 1800,
            "고양시": 2000, "일산": 2200,
            "의정부시": 1400, "남양주시": 1600, "구리시": 2200,
            "파주시": 1200, "양주시": 1100, "동두천시": 900,
            "안양시": 2500, "안산시": 1500, "시흥시": 1400,
            "김포시": 1600, "광명시": 2800, "하남시": 3000,
            "평택시": 1300, "오산시": 1200, "이천시": 1100,
            "부천시": 2000, "광주시": 1500,
            # 인천 구별
            "연수구": 2500, "송도": 2800, "부평구": 1600, "남동구": 1800,
            # 부산
            "해운대구": 2800, "수영구": 2500, "부산진구": 2000,
        }

        # 주소에서 시군구 매칭
        base_man_won = None
        for sg, price in sigungu_prices.items():
            if sg in address:
                base_man_won = price
                break

        # 시군구 매칭 실패 시 시도 기본값
        if base_man_won is None:
            base_man_won = {
                "서울특별시": 3000, "서울": 3000,
                "경기도": 1800, "경기": 1800,
                "인천광역시": 1800, "인천": 1800,
                "부산광역시": 2000, "부산": 2000,
                "대구광역시": 1800, "대구": 1800,
                "대전광역시": 1700, "대전": 1700,
                "광주광역시": 1500, "광주": 1500,
                "울산광역시": 1600, "울산": 1600,
                "세종특별자치시": 1800, "세종": 1800,
                "제주특별자치도": 1500, "제주": 1500,
                "강원도": 1100, "충청북도": 1200, "충청남도": 1300,
                "전라북도": 1000, "전라남도": 900,
                "경상북도": 1100, "경상남도": 1200,
            }.get(region, 1500)

        # 개발유형별 보정
        multiplier = {
            "M01": 1.0, "M02": 1.0, "M04": 0.95, "M06": 1.0,
            "M07": 1.1, "M08": 0.8, "M09": 0.65,
            "M10": 1.1, "M11": 0.75, "M12": 1.05, "M13": 0.7,
        }.get(dev_type, 1.0)
        return int(base_man_won * multiplier * 10000)  # 만원 → 원 변환

    def _get_building_type(self, dev_type: str) -> str:
        """개발유형별 건축 유형."""
        types = {
            "M01": "apartment", "M02": "apartment", "M06": "apartment",
            "M07": "apartment", "M08": "officetel", "M09": "office",
            "M10": "house", "M11": "house", "M12": "townhouse",
            "M13": "apartment", "M14": "apartment", "M15": "apartment",
        }
        return types.get(dev_type, "apartment")

    def _get_type_project_months(self, dev_type: str) -> int:
        """개발유형별 예상 사업기간 (개월)."""
        months = {
            "M01": 60, "M02": 60, "M03": 48, "M04": 48, "M05": 36,
            "M06": 36, "M07": 42, "M08": 30, "M09": 36, "M10": 12,
            "M11": 12, "M12": 24, "M13": 24, "M14": 36, "M15": 48,
        }
        return months.get(dev_type, 36)
