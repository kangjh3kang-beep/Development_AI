"""AI 권고 엔진 — 6규칙 진단 (R001~R006).

수지분석 결과 기반 자동 진단 + 개선 제안.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass


@dataclass
class Recommendation:
    """단일 권고."""
    rule_code: str
    rule_name: str
    severity: str  # info / warning / critical
    message: str
    suggestion: str
    current_value: float | None = None
    threshold_value: float | None = None


def diagnose(
    *,
    profit_rate_pct: float,
    roi_pct: float,
    finance_cost_ratio_pct: float = 0,
    construction_cost_ratio_pct: float = 0,
    tax_cost_ratio_pct: float = 0,
    grade: str = "F",
) -> list[Recommendation]:
    """6규칙 진단 실행.

    R001: 수익률 < 10% → 사업성 경고
    R002: ROI < 15% → 투자수익 경고
    R003: 금융비 비중 > 15% → 자금구조 개선
    R004: 공사비 비중 > 60% → VE 검토
    R005: 세금비중 > 10% → 절세 전략
    R006: 등급 D 이하 → 사업 재검토
    """
    recs: list[Recommendation] = []

    # R001: 수익률 경고
    if profit_rate_pct < 10.0:
        severity = "critical" if profit_rate_pct < 5.0 else "warning"
        recs.append(Recommendation(
            rule_code="R001",
            rule_name="수익률 경고",
            severity=severity,
            message=f"수익률 {profit_rate_pct:.1f}%로 기준(10%) 미달",
            suggestion="분양가 인상, 공사비 절감, 또는 개발유형 변경을 검토하세요",
            current_value=profit_rate_pct,
            threshold_value=10.0,
        ))

    # R002: ROI 경고
    if roi_pct < 15.0:
        severity = "critical" if roi_pct < 8.0 else "warning"
        recs.append(Recommendation(
            rule_code="R002",
            rule_name="투자수익률 경고",
            severity=severity,
            message=f"ROI {roi_pct:.1f}%로 기준(15%) 미달",
            suggestion="자기자본 비율 조정 또는 레버리지 구조 개선을 검토하세요",
            current_value=roi_pct,
            threshold_value=15.0,
        ))

    # R003: 금융비 비중
    if finance_cost_ratio_pct > 15.0:
        recs.append(Recommendation(
            rule_code="R003",
            rule_name="금융비 과다",
            severity="warning",
            message=f"금융비 비중 {finance_cost_ratio_pct:.1f}%로 기준(15%) 초과",
            suggestion="브릿지 기간 단축, PF 금리 협상, 또는 자기자본 확충을 검토하세요",
            current_value=finance_cost_ratio_pct,
            threshold_value=15.0,
        ))

    # R004: 공사비 비중
    if construction_cost_ratio_pct > 60.0:
        recs.append(Recommendation(
            rule_code="R004",
            rule_name="공사비 과다",
            severity="warning",
            message=f"공사비 비중 {construction_cost_ratio_pct:.1f}%로 기준(60%) 초과",
            suggestion="VE(가치공학) 검토, 공법 변경, 또는 설계 최적화를 검토하세요",
            current_value=construction_cost_ratio_pct,
            threshold_value=60.0,
        ))

    # R005: 세금 비중
    if tax_cost_ratio_pct > 10.0:
        recs.append(Recommendation(
            rule_code="R005",
            rule_name="세금 비중 과다",
            severity="info",
            message=f"세금 비중 {tax_cost_ratio_pct:.1f}%로 기준(10%) 초과",
            suggestion="세금 감면 혜택 확인, 개발유형 변경, 또는 분양시기 조정을 검토하세요",
            current_value=tax_cost_ratio_pct,
            threshold_value=10.0,
        ))

    # R006: 등급 경고
    if grade in ("D", "E", "F"):
        severity = "critical" if grade == "F" else "warning"
        recs.append(Recommendation(
            rule_code="R006",
            rule_name="사업 등급 경고",
            severity=severity,
            message=f"사업 등급 {grade}로 사업성 재검토 필요",
            suggestion="토지비 절감, 분양가 현실화, 또는 사업 구조 전면 재검토를 권고합니다",
        ))

    return recs
