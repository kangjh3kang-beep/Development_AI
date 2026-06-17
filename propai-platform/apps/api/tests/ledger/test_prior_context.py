"""Phase 1: prior_context 근거블록 포맷·수치추출 단위테스트(순수)."""
from app.services.ledger.prior_context import build_prior_block, prior_numbers


def _prior():
    return {
        "analysis_type": "design_audit",
        "version": 3,
        "content_hash": "abc123",
        "created_at": "2026-06-10 09:00:00",
        "payload": {
            "kind": "design_audit", "schema_version": "design_audit/v1",
            "verdict": "conditional", "counts": {"fail": 1, "warn": 2},
            "findings_brief": [
                {"check_id": "FAR-01", "status": "fail", "current": 250.0, "limit": 200.0},
                {"check_id": "BCR-02", "status": "pass", "current": 55.0, "limit": 60.0},
            ],
        },
    }


def test_build_prior_block_includes_version_and_contradiction_rule():
    block = build_prior_block(_prior())
    assert "이전 분석" in block
    assert "v3" in block  # 버전 표면화
    assert "design_audit" in block
    assert "FAR-01" in block and "250" in block  # 비교 핵심(findings_brief)
    # 모순명시 규칙(spec: 이전결론 모순 시 명시)
    assert "모순" in block


def test_build_prior_block_none_returns_empty():
    assert build_prior_block(None) == ""
    assert build_prior_block({}) == ""


def test_prior_numbers_extracts_findings_values():
    nums = prior_numbers(_prior())
    assert 250.0 in nums and 200.0 in nums and 55.0 in nums and 60.0 in nums
