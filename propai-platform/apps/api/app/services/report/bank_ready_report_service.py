"""
은행제출용 사업성 보고서 자동 생성 서비스.
Feasibly 벤치마크 — 전 모듈 데이터를 통합하여 PF 대출 심사용 보고서 생성.
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class BankReadyReportService:
    """PF 대출 심사용 통합 보고서 생성."""

    REPORT_SECTIONS = [
        {"id": "summary", "title": "1. 사업개요", "required": True},
        {"id": "market", "title": "2. 시장분석", "required": True},
        {"id": "legal", "title": "3. 법규검토", "required": True},
        {"id": "design", "title": "4. 설계개요", "required": False},
        {"id": "unit_mix", "title": "5. 유닛믹스 분석", "required": False},
        {"id": "feasibility", "title": "6. 사업수지분석", "required": True},
        {"id": "finance", "title": "7. 자금조달계획", "required": True},
        {"id": "risk", "title": "8. 리스크분석", "required": True},
        {"id": "esg", "title": "9. ESG 분석", "required": False},
        {"id": "appendix", "title": "10. 부록", "required": False},
    ]

    def generate_report(
        self,
        project_data: dict,
        selected_sections: Optional[list] = None,
        template: str = "bank",  # "bank" | "internal"
    ) -> dict:
        """통합 보고서 데이터 생성."""
        sections = selected_sections or [s["id"] for s in self.REPORT_SECTIONS]

        report = {
            "meta": {
                "title": f"사업성 분석 보고서 — {project_data.get('project_name', '무제')}",
                "template": template,
                "generated_at": datetime.now().isoformat(),
                "generated_by": "PropAI v30.0",
                "legal_disclaimer": "본 보고서는 AI 기반 자동 분석 결과이며, 최종 투자 의사결정 시 전문가 검토를 권장합니다.",
                "data_basis_date": datetime.now().strftime("%Y-%m-%d"),
            },
            "sections": [],
            "completeness": {"total": len(sections), "filled": 0, "empty": 0},
        }

        for section_id in sections:
            section_data = self._build_section(section_id, project_data, template)
            report["sections"].append(section_data)
            if section_data.get("has_data"):
                report["completeness"]["filled"] += 1
            else:
                report["completeness"]["empty"] += 1

        report["completeness"]["pct"] = round(
            report["completeness"]["filled"] / max(report["completeness"]["total"], 1) * 100
        )

        return report

    def _build_section(self, section_id: str, data: dict, template: str) -> dict:
        builders = {
            "summary": self._build_summary,
            "market": self._build_market,
            "legal": self._build_legal,
            "design": self._build_design,
            "unit_mix": self._build_unit_mix,
            "feasibility": self._build_feasibility,
            "finance": self._build_finance,
            "risk": self._build_risk,
            "esg": self._build_esg,
            "appendix": self._build_appendix,
        }
        builder = builders.get(section_id, self._build_empty)
        return builder(data, template)

    def _build_summary(self, data: dict, template: str) -> dict:
        site = data.get("site_analysis") or {}
        zoning = data.get("zoning") or {}
        return {
            "id": "summary",
            "title": "1. 사업개요",
            "has_data": bool(site.get("address")),
            "content": {
                "project_name": data.get("project_name", ""),
                "address": site.get("address", ""),
                "pnu": site.get("pnu", ""),
                "land_area_sqm": site.get("land_area_sqm"),
                "zone_type": zoning.get("zone_type", ""),
                "zone_limits": zoning.get("zone_limits"),
                "estimated_value": site.get("estimated_value"),
                "development_type": data.get("development_type", ""),
                "total_gfa_sqm": data.get("design", {}).get("total_gfa_sqm"),
                "total_households": data.get("design", {}).get("total_households"),
            },
        }

    def _build_market(self, data: dict, template: str) -> dict:
        market = data.get("market_analysis") or {}
        return {
            "id": "market",
            "title": "2. 시장분석",
            "has_data": bool(market.get("statistics")),
            "content": {
                "region": market.get("region", ""),
                "analysis_period": market.get("period", ""),
                "statistics": market.get("statistics"),
                "chart_data": market.get("chart_data"),
                "comparable_transactions": market.get("comparables", [])[:10],
                "supply_demand": market.get("supply_demand"),
            },
        }

    def _build_legal(self, data: dict, template: str) -> dict:
        compliance = data.get("compliance") or {}
        return {
            "id": "legal",
            "title": "3. 법규검토",
            "has_data": bool(compliance.get("bcr_compliant") is not None),
            "content": {
                "bcr_check": {"compliant": compliance.get("bcr_compliant"), "planned": compliance.get("planned_bcr"), "limit": compliance.get("max_bcr")},
                "far_check": {"compliant": compliance.get("far_compliant"), "planned": compliance.get("planned_far"), "limit": compliance.get("max_far")},
                "height_check": {"compliant": compliance.get("height_compliant"), "planned": compliance.get("planned_height"), "limit": compliance.get("max_height")},
                "violations": compliance.get("violations", []),
                "special_districts": compliance.get("special_districts", []),
            },
        }

    def _build_design(self, data: dict, template: str) -> dict:
        design = data.get("design") or {}
        return {
            "id": "design",
            "title": "4. 설계개요",
            "has_data": bool(design.get("total_gfa_sqm")),
            "content": {
                "total_gfa_sqm": design.get("total_gfa_sqm"),
                "floor_count": design.get("floor_count"),
                "building_type": design.get("building_type"),
                "bcr_pct": design.get("bcr"),
                "far_pct": design.get("far"),
                "parking_spaces": design.get("parking_spaces"),
            },
        }

    def _build_unit_mix(self, data: dict, template: str) -> dict:
        unit_mix = data.get("unit_mix") or {}
        return {
            "id": "unit_mix",
            "title": "5. 유닛믹스 분석",
            "has_data": bool(unit_mix.get("units")),
            "content": {
                "total_units": unit_mix.get("total_units"),
                "total_revenue_won": unit_mix.get("total_revenue_won"),
                "gfa_efficiency_pct": unit_mix.get("gfa_efficiency_pct"),
                "units": unit_mix.get("units", []),
                "optimization_method": unit_mix.get("method"),
            },
        }

    def _build_feasibility(self, data: dict, template: str) -> dict:
        feas = data.get("feasibility") or {}
        return {
            "id": "feasibility",
            "title": "6. 사업수지분석",
            "has_data": bool(feas.get("profit_rate_pct") is not None),
            "content": {
                "total_revenue_won": feas.get("total_revenue_won"),
                "total_cost_won": feas.get("total_cost_won"),
                "net_profit_won": feas.get("net_profit_won"),
                "profit_rate_pct": feas.get("profit_rate_pct"),
                "roi_pct": feas.get("roi_pct"),
                "npv_won": feas.get("npv_won"),
                "grade": feas.get("grade"),
                "cost_breakdown": feas.get("cost_breakdown"),
            },
        }

    def _build_finance(self, data: dict, template: str) -> dict:
        finance = data.get("finance") or {}
        return {
            "id": "finance",
            "title": "7. 자금조달계획",
            "has_data": bool(finance.get("total_finance_cost")),
            "content": {
                "equity_won": finance.get("equity_won"),
                "bridge_loan": finance.get("bridge_loan"),
                "pf_loan": finance.get("pf_loan"),
                "midpay_loan": finance.get("midpay_loan"),
                "total_finance_cost": finance.get("total_finance_cost"),
                "weighted_avg_rate": finance.get("weighted_avg_rate"),
            },
        }

    def _build_risk(self, data: dict, template: str) -> dict:
        mc = data.get("monte_carlo") or {}
        return {
            "id": "risk",
            "title": "8. 리스크분석",
            "has_data": bool(mc.get("mean")),
            "content": {
                "simulation_count": mc.get("n_simulations"),
                "npv_mean": mc.get("mean"),
                "npv_std": mc.get("std"),
                "npv_p5": mc.get("p5"),
                "npv_p95": mc.get("p95"),
                "probability_positive": mc.get("probability_positive"),
                "convergence": mc.get("convergence_ratio"),
                "risk_grade": "낮음" if (mc.get("probability_positive", 0) or 0) > 0.8 else "중간" if (mc.get("probability_positive", 0) or 0) > 0.5 else "높음",
            },
        }

    def _build_esg(self, data: dict, template: str) -> dict:
        esg = data.get("esg") or {}
        gresb = data.get("gresb") or {}
        return {
            "id": "esg",
            "title": "9. ESG 분석",
            "has_data": bool(esg.get("embodied_carbon_kg") or gresb.get("total_score")),
            "content": {
                "embodied_carbon_kg": esg.get("embodied_carbon_kg"),
                "operational_carbon_kg": esg.get("operational_carbon_kg"),
                "total_carbon_per_sqm": esg.get("total_carbon_per_sqm"),
                "gresb_score": gresb.get("total_score"),
                "gresb_grade": gresb.get("grade"),
                "recommendations": gresb.get("recommendations", []),
            },
        }

    def _build_appendix(self, data: dict, template: str) -> dict:
        return {
            "id": "appendix",
            "title": "10. 부록",
            "has_data": True,
            "content": {
                "comparable_transactions": data.get("site_analysis", {}).get("comparables", []),
                "tax_detail": data.get("tax_detail"),
                "data_sources": data.get("_metadata", {}).get("data_sources", []),
                "calculation_basis": data.get("_metadata", {}).get("legal_basis_date"),
            },
        }

    def _build_empty(self, data: dict, template: str) -> dict:
        return {"id": "unknown", "title": "알 수 없는 섹션", "has_data": False, "content": {}}
