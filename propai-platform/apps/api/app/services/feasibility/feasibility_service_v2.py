"""FeasibilityServiceV2 — 수지분석 고도화 통합 서비스.

전체 파이프라인 오케스트레이션:
입력 → 모듈 선택 → 계산 → 등급 판정 → 결과 반환.
"""

from __future__ import annotations

from typing import Any

from app.services.feasibility.modules.base_module import ModuleInput, ModuleOutput
from app.services.feasibility.modules.module_assembler import get_module, list_modules, ALL_MODULE_CODES
from app.services.feasibility.aggregation_engine import compare_scenarios


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
