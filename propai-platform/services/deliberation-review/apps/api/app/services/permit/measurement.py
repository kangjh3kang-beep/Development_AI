"""INC-PD2 — 심의 계측: 정량(엔진 산출 면적 → 대지면적 대비 비율 vs reg SSOT 한도) 부합도 + 정성 등급 밴드.

★단위 정합: reg SSOT 한도(bcr_pct/far_pct)는 비율(%)이고 엔진 산출(building_area/far_floor_area)은 절대면적(m²)
이므로, 비율(면적/대지면적×100)로 환산해 차원 일치 비교한다. 대지면적(plot_area) 부재/0이면 비율 형성 불가 →
HELD(무음/날조 금지). 정성 등급은 등급별 부합도 밴드로 매핑(등급 존재≠부합). margin/share는 계산식(리터럴 아님,
INV-3). 측정값 존재 시 calc_trace 항상 부착(설명가능성).
"""
from __future__ import annotations

from app.contracts.analysis import AnalysisResult
from app.contracts.permit_process import CriterionKind, CriterionRef
from app.contracts.permit_result import CriterionResult
from app.contracts.rationale import LegalRef
from app.services.explain.legal_refs import resolve_text
from app.services.legal_calc.zone_limit_provider import resolve_zone_limit

_CONFORMANCE_RANK = {"부합": 0, "조건부": 1, "미흡": 2, "HELD": 3}
# L3-C 등급 → 부합도 밴드(등급 존재≠부합; LOW/NONE은 미흡, MEDIUM 조건부). 문자열 맵(INV-3 무관).
_GRADE_CONFORMANCE = {"HIGH": "부합", "MEDIUM": "조건부", "LOW": "미흡", "NONE": "미흡"}


def _legal_basis(basis_article: str | None) -> list[LegalRef]:
    """근거조문(자유텍스트) → LegalRef(법령명·조항·요지·시행일·1차출처 링크). 미해소 시 [](무음 금지·식별자만)."""
    d = resolve_text(basis_article)
    if not d:
        return []
    return [LegalRef(**{k: v for k, v in d.items() if k != "match"})]


def _measured_for(result: AnalysisResult, variable_id: str) -> float | None:
    """엔진 산출 legal_quantities에서 변수값 조회(소비 read-only). 없으면 None."""
    for q in result.legal_quantities:
        if q.variable_id == variable_id and q.value is not None:
            return float(q.value)
    return None


def measure_quantitative(result: AnalysisResult, ref: CriterionRef,
                         use_zone: str | None) -> CriterionResult:
    """정량 부합도 — 면적(엔진) → 대지면적 대비 비율(%) vs 한도(reg SSOT %). 비율 형성 불가면 HELD."""
    area = _measured_for(result, ref.ssot_ref or "")
    plot_area = _measured_for(result, "plot_area")
    resolved = resolve_zone_limit(use_zone, ref.ssot_ref) if use_zone else None
    limit_pct = resolved[0] if resolved else None
    source = resolved[1] if resolved else None
    cr = CriterionResult(criterion_id=ref.criterion_id, kind=ref.kind.value,
                         measured=area, limit=limit_pct, basis_article=ref.basis_article,
                         legal_basis=_legal_basis(ref.basis_article))   # 근거+링크 기본 동반
    if area is None:
        return cr   # 측정값 부재 → HELD(무음 금지)
    trace = {"measured_area": area, "plot_area": plot_area, "limit_pct": limit_pct,
             "source": source, "basis_article": ref.basis_article, "measure": ref.measure}
    cr.calc_trace = trace
    if limit_pct is None or plot_area is None or plot_area <= 0 or area < 0:
        trace["note"] = "ratio_unresolved(한도·대지면적 부재/비양수 또는 음수 면적)"
        cr.conformance = "HELD"   # 비율 형성 불가/비정상 입력 → 보류(무음 '부합' 날조 금지)
        return cr
    share = area / plot_area * 100.0          # 비율(%) = 면적/대지면적×100 (식 — 리터럴 할당 아님)
    trace["computed_pct"] = share
    cr.margin = (limit_pct - share) / limit_pct if limit_pct else None
    cr.conformance = "부합" if share <= limit_pct else "미흡"
    if source:
        cr.legal_refs = [source]
    return cr


def measure_qualitative(result: AnalysisResult, ref: CriterionRef) -> CriterionResult:
    """정성 등급 밴드 — L3-C QualAssessment(item 매칭)의 등급을 부합도로 매핑(등급 존재≠부합). 없으면 HELD."""
    cr = CriterionResult(criterion_id=ref.criterion_id, kind=ref.kind.value,
                         basis_article=ref.basis_article,
                         legal_basis=_legal_basis(ref.basis_article))   # 근거+링크 기본 동반
    keys = [k for k in (ref.criterion_id, ref.ssot_ref) if k]
    for qa in result.qualitative:
        item = qa.item or ""
        if any(k in item for k in keys):
            grade = qa.grade.value if qa.grade is not None else None
            cr.grade = grade
            cr.conformance = _GRADE_CONFORMANCE.get(grade or "", "HELD")  # 등급 밴드; 미상→HELD
            if qa.citation is not None and qa.citation.source:
                cr.legal_refs = [qa.citation.source]
            return cr
    cr.conformance = "HELD"
    return cr


def measure(result: AnalysisResult, ref: CriterionRef, use_zone: str | None) -> CriterionResult:
    if ref.kind == CriterionKind.QUANTITATIVE:
        return measure_quantitative(result, ref, use_zone)
    return measure_qualitative(result, ref)


def worst_conformance(values: list[str]) -> str:
    """단계/종합 종합 = worst-of(보수)."""
    if not values:
        return "HELD"
    return max(values, key=lambda v: _CONFORMANCE_RANK.get(v, 3))
