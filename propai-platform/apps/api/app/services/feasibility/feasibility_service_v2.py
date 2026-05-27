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

        # Step 3: 각 유형별 입력값 자동 생성 + 수지분석 계산
        max_far = zone_limits.get("max_far_pct", 250)
        max_bcr = zone_limits.get("max_bcr_pct", 60)

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
                    avg_sale_price_per_pyeong=self._get_regional_price(dev_type, region),
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

                # Composite score: 70% profitability + 30% permit ease
                profit_score = min(100, max(0, output.profit_rate_pct * 5))  # 20% -> 100점
                permit_score = (6 - permit["permit_complexity"]) * 20  # 1->100, 5->20
                composite = profit_score * 0.7 + permit_score * 0.3

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

    def _get_regional_price(self, dev_type: str, region: str) -> int:
        """지역x개발유형별 평균 분양가 (만원/평)."""
        base = {"서울": 4000, "경기": 2500, "인천": 2200, "부산": 2300}.get(region, 2000)
        multiplier = {
            "M01": 1.0, "M02": 1.0, "M06": 1.0, "M07": 1.1, "M08": 0.85,
            "M09": 0.7, "M10": 1.2, "M11": 0.8, "M12": 1.1, "M13": 0.75,
        }.get(dev_type, 1.0)
        return int(base * multiplier)

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
