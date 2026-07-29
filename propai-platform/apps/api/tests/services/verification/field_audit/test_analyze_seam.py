"""analyze() 주경로 seam 통합테스트 — field_audit runner 삽입 배선을 고정(R1 MEDIUM 봉합).

W0 산출물의 핵심 = field_audit runner를 comprehensive analyze() **주경로**에 배선. 이 seam을
고정하는 테스트가 없으면, W1이 실 findings를 이 seam으로 실어나를 때 배선이 조용히 빠져도
미검출된다. 이 테스트는 실제 analyze()를 (collect_comprehensive만 mock한) 최소 의존으로
호출해 result에 'field_audit' 키 + AuditReport 계약(is_valid 등)이 실림을 assert한다.

★변이증명(R2 수동 확인): analyze()의 `_field_audit_runner.run(...)` 삽입을 제거하면 이 테스트가
FAIL한다(배선 실재를 테스트가 고정) → 확인 후 원복.

DB 비의존: analyze()는 DB/LLM/외부API 미가용에도 graceful degrade하며 seam(return 직전)까지
도달한다. 따라서 이 seam 테스트는 sibling growth-loop 테스트의 DB skip-guard와 달리 **항상 실행**
된다(더 강한 배선 가드).
"""

import pytest

import app.services.growth.capture_service as cap

pytestmark = pytest.mark.asyncio


def _fake_base():
    """analyze()가 소비하는 최소 base(단일필지·제2종주거·실효값 포함). growth-loop 테스트와 동형."""
    return {
        "pnu": "1115010300102240000",
        "zone_type": "제2종일반주거지역",
        "land_register": {"area_sqm": 300.0},
        "effective_far": {"effective_far_pct": 200.0, "effective_bcr_pct": 60.0},
        "warnings": [],
    }


async def test_analyze_wires_field_audit_seam(monkeypatch):
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return _fake_base()

    # 기존 growth-loop 테스트 패턴 재사용(type-level monkeypatch).
    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)
    # growth 관측 emit 무음화(테스트 격리 — 전역 in-memory 큐 오염 방지). seam 배선과 무관.
    monkeypatch.setattr(cap, "record_event", lambda *a, **k: None)

    result = await svc.analyze("의정부동 224-seam", tenant_id="t-seam", project_id=None)

    # ★seam 고정: analyze() 주경로가 field_audit runner를 호출해 result에 'field_audit'를 실었다.
    #   이 assert가 배선 제거 시 FAIL(변이-킬) → 배선 실재를 테스트가 고정.
    assert "field_audit" in result, "analyze() 삽입 배선이 빠졌다(seam 미배선)"

    fa = result["field_audit"]
    assert isinstance(fa, dict)
    # AuditReport 계약 필드 존재(is_valid·findings·metadata·coverage) — W1 findings가 실릴 통로.
    for key in ("is_valid", "findings", "metadata", "coverage"):
        assert key in fa, f"AuditReport 계약 필드 누락: {key}"
    # W0(등록 규칙 0건): is_valid=True·findings=[] — behavior 불변.
    assert fa["is_valid"] is True
    assert fa["findings"] == []
    # runner 배선 메타(경로 비의존 계약 — enabled 플래그가 실제 실행경로였음을 확인).
    assert fa["metadata"].get("enabled") is True
    # 참고: analyze()-레벨 additive-only(키 1개만 추가) behavior 불변은 runner-레벨
    #   test_runner_noop::test_runner_noop_empty_report_and_additive가 저비용으로 커버한다
    #   (analyze() 이중 호출 회피). 이 seam 테스트는 '배선 실재'만 고정한다(변이-킬 대상).
