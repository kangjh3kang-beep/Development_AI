"""코드리뷰 iter5 — ConfidenceComposer/FindingGate 배선(gated_status 박제 해소·충돌 패널티)."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis

_PNU = "1111010100100000002"


def _rule(conflicts=None):
    return {"rule": {"rule_id": "far", "comparator": "<=", "basis_article": "국토계획법시행령§85"},
            "measured": 250, "limit": 300, "confidence": 0.9, "conflicts": conflicts or []}


def test_finding_gate_wired_sets_gated_status():
    # FindingGate 배선 — gated_status가 기본 NEEDS_REVIEW 박제가 아니라 실제 게이트 결과로 채워짐.
    r = run_analysis(AnalysisInput(pnu=_PNU, application_date=date(2026, 1, 1), rules=[_rule()]))
    assert len(r.findings) == 1
    f = r.findings[0]
    # composite 0.9 ≥ 임계(0.7) + 충돌 없음 → CONFIRMED(박제 NEEDS_REVIEW 아님).
    assert f.gated_status.value == "CONFIRMED"


def test_conflict_penalty_downgrades_composite():
    # ConfidenceComposer 배선 — 충돌 시 composite 강등(원시 통과 해소) → NEEDS_REVIEW.
    r = run_analysis(AnalysisInput(pnu=_PNU, application_date=date(2026, 1, 1),
                                   rules=[_rule(conflicts=["dup"])]))
    f = r.findings[0]
    assert f.composite_confidence < 0.9          # 충돌 패널티 반영
    assert f.gated_status.value == "NEEDS_REVIEW"  # 충돌 → 확인 필요
