"""파이프라인 결과 기반 통합 보고서 생성 서비스.

은행 PF 대출 심사용 10섹션 보고서 + GRESB ESG 요약을 자동 생성한다.
파이프라인 7단계(site_analysis → design → cost → feasibility → tax → esg → report)
결과를 종합하여 구조화된 보고서 데이터를 반환한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── 보고서 모델 ──────────────────────────────────────────────


class ReportSection(BaseModel):
    """보고서 개별 섹션."""

    section_no: int
    title: str
    content: dict[str, Any] = Field(default_factory=dict)


class PipelineReport(BaseModel):
    """통합 분석 보고서."""

    report_id: str
    project_address: str
    generated_at: str
    sections: list[ReportSection] = Field(default_factory=list)
    executive_summary: dict[str, Any] = Field(default_factory=dict)
    risk_assessment: dict[str, Any] = Field(default_factory=dict)


# ── 보고서 생성 서비스 ──────────────────────────────────────


class PipelineReportService:
    """파이프라인 결과 → 10섹션 통합 보고서 생성.

    각 섹션은 ``pipeline_result["stages"]`` 에서 해당 단계의 ``data``를
    추출하여 은행 PF 심사 양식에 맞게 구조화한다.
    """

    # ── public ──

    def generate(self, pipeline_result: dict) -> PipelineReport:
        """파이프라인 전체 결과로 보고서 생성."""
        stages = pipeline_result.get("stages", {})
        address = pipeline_result.get("address", "")

        # 단계별 data 추출 (StageResult 형태 또는 flat dict 모두 대응)
        site = self._extract_data(stages.get("site_analysis"))
        design = self._extract_data(stages.get("design"))
        cost = self._extract_data(stages.get("cost"))
        feasibility = self._extract_data(stages.get("feasibility"))
        tax = self._extract_data(stages.get("tax"))
        esg = self._extract_data(stages.get("esg"))

        sections = [
            self._section_project_overview(site, design, address),
            self._section_site_analysis(site),
            self._section_architecture_plan(design),
            self._section_compliance(design),
            self._section_cost(cost),
            self._section_sales_plan(feasibility, design),
            self._section_feasibility(feasibility),
            self._section_risk(feasibility),
            self._section_tax(tax),
            self._section_esg(esg),
        ]

        executive_summary = self._build_executive_summary(
            site, design, cost, feasibility, esg,
        )
        risk_assessment = self._build_risk_assessment(feasibility)

        return PipelineReport(
            report_id=str(uuid.uuid4()),
            project_address=address,
            generated_at=datetime.now().isoformat(),
            sections=sections,
            executive_summary=executive_summary,
            risk_assessment=risk_assessment,
        )

    # ── private helpers ──

    @staticmethod
    def _extract_data(stage_entry: dict | None) -> dict[str, Any]:
        """StageResult dict 또는 이미 flat한 dict에서 data를 추출."""
        if not stage_entry:
            return {}
        # StageResult 직렬화 구조: {"stage": ..., "data": {...}, ...}
        if "data" in stage_entry and isinstance(stage_entry["data"], dict):
            return stage_entry["data"]
        return stage_entry

    # ── 10 섹션 빌더 ──

    def _section_project_overview(
        self, site: dict, design: dict, address: str,
    ) -> ReportSection:
        """섹션 1: 사업 개요."""
        return ReportSection(
            section_no=1,
            title="사업 개요",
            content={
                "address": address,
                "land_area_sqm": site.get("land_area_sqm"),
                "zone_type": site.get("zone_type"),
                "pnu_codes": site.get("pnu_codes", []),
                "official_land_price": site.get("official_land_price"),
                "building_type": design.get("building_type"),
                "total_gfa_sqm": design.get("total_gfa_sqm"),
            },
        )

    def _section_site_analysis(self, site: dict) -> ReportSection:
        """섹션 2: 입지 분석."""
        return ReportSection(
            section_no=2,
            title="입지 분석",
            content={
                "zone_type": site.get("zone_type"),
                "max_bcr": site.get("max_bcr"),
                "max_far": site.get("max_far"),
                "nearby_transactions": site.get("nearby_transactions"),
                "infrastructure": site.get("infrastructure"),
                "building_info": site.get("building_info"),
                "local_ordinance": site.get("local_ordinance"),
                "warnings": site.get("warnings", []),
            },
        )

    def _section_architecture_plan(self, design: dict) -> ReportSection:
        """섹션 3: 건축 계획."""
        return ReportSection(
            section_no=3,
            title="건축 계획",
            content={
                "building_type": design.get("building_type"),
                "total_gfa_sqm": design.get("total_gfa_sqm"),
                "building_area_sqm": design.get("building_area_sqm"),
                "floor_count_above": design.get("floor_count_above"),
                "floor_count_below": design.get("floor_count_below"),
                "unit_count": design.get("unit_count"),
                "bcr_used_pct": design.get("bcr_used_pct"),
                "far_used_pct": design.get("far_used_pct"),
            },
        )

    def _section_compliance(self, design: dict) -> ReportSection:
        """섹션 4: 법규 검토."""
        compliance = design.get("compliance", {})
        return ReportSection(
            section_no=4,
            title="법규 검토",
            content={
                "check_summary": compliance.get("summary", {}),
                "check_results": compliance.get("results", []),
                "error": compliance.get("error"),
            },
        )

    def _section_cost(self, cost: dict) -> ReportSection:
        """섹션 5: 공사비 분석."""
        return ReportSection(
            section_no=5,
            title="공사비 분석",
            content={
                "total_construction_cost": cost.get("total_construction_cost"),
                "direct_cost": cost.get("direct_cost"),
                "cost_per_pyeong": cost.get("cost_per_pyeong"),
                "total_gfa_pyeong": cost.get("total_gfa_pyeong"),
                "construction_months": cost.get("construction_months"),
                "cost_breakdown": cost.get("cost_breakdown", {}),
                "material_item_count": cost.get("material_item_count"),
            },
        )

    def _section_sales_plan(
        self, feasibility: dict, design: dict,
    ) -> ReportSection:
        """섹션 6: 분양/임대 계획."""
        return ReportSection(
            section_no=6,
            title="분양/임대 계획",
            content={
                "avg_sale_price_per_pyeong": feasibility.get("avg_sale_price_per_pyeong"),
                "total_revenue": feasibility.get("total_revenue"),
                "unit_count": design.get("unit_count"),
                "building_type": design.get("building_type"),
            },
        )

    def _section_feasibility(self, feasibility: dict) -> ReportSection:
        """섹션 7: 사업 수지 분석."""
        cashflow = feasibility.get("cashflow", {})
        return ReportSection(
            section_no=7,
            title="사업 수지 분석",
            content={
                "land_cost": feasibility.get("land_cost"),
                "construction_cost": feasibility.get("construction_cost"),
                "total_project_cost": feasibility.get("total_project_cost"),
                "total_revenue": feasibility.get("total_revenue"),
                "net_profit": feasibility.get("net_profit"),
                "profit_rate_pct": feasibility.get("profit_rate_pct"),
                "grade": feasibility.get("grade"),
                "cashflow_summary": cashflow.get("summary", {}),
                "cashflow_phases": cashflow.get("phases", {}),
            },
        )

    def _section_risk(self, feasibility: dict) -> ReportSection:
        """섹션 8: 리스크 분석."""
        mc = feasibility.get("monte_carlo", {})
        sensitivity = feasibility.get("sensitivity", {})
        return ReportSection(
            section_no=8,
            title="리스크 분석",
            content={
                "monte_carlo": {
                    "n_simulations": mc.get("n_simulations"),
                    "profit_mean": mc.get("profit_mean"),
                    "profit_std": mc.get("profit_std"),
                    "p10": mc.get("p10"),
                    "p50": mc.get("p50"),
                    "p90": mc.get("p90"),
                    "probability_positive": mc.get("probability_positive"),
                    "var_95_won": mc.get("var_95_won"),
                },
                "sensitivity": {
                    "base_result": sensitivity.get("base_result", {}),
                    "tornado": sensitivity.get("tornado", []),
                },
            },
        )

    def _section_tax(self, tax: dict) -> ReportSection:
        """섹션 9: 세금 분석."""
        return ReportSection(
            section_no=9,
            title="세금 분석",
            content={
                "acquisition_tax": tax.get("acquisition_tax"),
                "property_tax_annual": tax.get("property_tax_annual"),
                "transfer_tax": tax.get("transfer_tax"),
                "vat": tax.get("vat"),
                "total_tax": tax.get("total_tax"),
            },
        )

    def _section_esg(self, esg: dict) -> ReportSection:
        """섹션 10: ESG/탄소 평가."""
        embodied = esg.get("embodied_carbon", {})
        operational = esg.get("operational_carbon", {})
        lifecycle = esg.get("lifecycle_total", {})
        gresb = esg.get("gresb", {})
        gseed = esg.get("gseed_prediction", {})
        low_carbon = esg.get("low_carbon_scenario", {})

        return ReportSection(
            section_no=10,
            title="ESG/탄소 평가",
            content={
                "embodied_carbon_kgCO2eq": embodied.get("total_kgCO2eq")
                    or esg.get("embodied_carbon_kg"),
                "embodied_per_sqm": embodied.get("per_sqm_kgCO2eq"),
                "operational_carbon_30yr_kgCO2eq": operational.get("total_30yr_kgCO2eq")
                    or esg.get("operational_carbon_30yr_kg"),
                "lifecycle_total_kgCO2eq": lifecycle.get("total_kgCO2eq")
                    or esg.get("total_lifecycle_carbon_kg"),
                "carbon_per_sqm": lifecycle.get("per_sqm_kgCO2eq")
                    or esg.get("carbon_per_sqm_kg"),
                "gresb_score": gresb.get("total_score") or gresb.get("estimated_score"),
                "gresb_grade": gresb.get("grade"),
                "gseed_predicted_grade": gseed.get("predicted_grade"),
                "low_carbon_scenario": {
                    "reduction_pct": low_carbon.get("reduction_pct"),
                    "alternative_materials": low_carbon.get("alternatives", []),
                } if low_carbon else None,
            },
        )

    # ── Executive Summary & Risk Assessment ──

    def _build_executive_summary(
        self,
        site: dict,
        design: dict,
        cost: dict,
        feasibility: dict,
        esg: dict,
    ) -> dict[str, Any]:
        """핵심 지표 요약 (보고서 첫 페이지)."""
        return {
            "address": site.get("zone_type", ""),
            "land_area_sqm": site.get("land_area_sqm"),
            "building_type": design.get("building_type"),
            "total_gfa_sqm": design.get("total_gfa_sqm"),
            "unit_count": design.get("unit_count"),
            "total_construction_cost": cost.get("total_construction_cost"),
            "total_project_cost": feasibility.get("total_project_cost"),
            "total_revenue": feasibility.get("total_revenue"),
            "net_profit": feasibility.get("net_profit"),
            "profit_rate_pct": feasibility.get("profit_rate_pct"),
            "grade": feasibility.get("grade"),
            "gresb_score": (esg.get("gresb") or {}).get("total_score")
                or (esg.get("gresb") or {}).get("estimated_score"),
            "embodied_carbon_kg": esg.get("embodied_carbon_kg"),
        }

    @staticmethod
    def _build_risk_assessment(feasibility: dict) -> dict[str, Any]:
        """종합 리스크 등급 판정."""
        mc = feasibility.get("monte_carlo", {})
        prob_positive = mc.get("probability_positive", 0) or 0
        profit_rate = feasibility.get("profit_rate_pct", 0) or 0

        # 리스크 등급: 수익확률 + 수익률 기반 복합 판정
        if prob_positive >= 0.85 and profit_rate >= 15:
            risk_grade = "LOW"
            risk_label = "낮음"
        elif prob_positive >= 0.65 and profit_rate >= 5:
            risk_grade = "MEDIUM"
            risk_label = "중간"
        elif prob_positive >= 0.40:
            risk_grade = "HIGH"
            risk_label = "높음"
        else:
            risk_grade = "VERY_HIGH"
            risk_label = "매우 높음"

        return {
            "risk_grade": risk_grade,
            "risk_label": risk_label,
            "probability_positive": prob_positive,
            "profit_rate_pct": profit_rate,
            "var_95_won": mc.get("var_95_won"),
            "recommendation": (
                "사업 추진 적합" if risk_grade == "LOW"
                else "조건부 추진 가능" if risk_grade == "MEDIUM"
                else "추가 검토 필요" if risk_grade == "HIGH"
                else "사업 재검토 권고"
            ),
        }
