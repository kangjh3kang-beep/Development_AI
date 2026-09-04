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
    # 보호구역 규제 없음 → G1(P0) 무발동 → is_valid=True(gating behavior 불변). 보호구역 경로의
    #   flip은 test_golden_baseline·test_protection_zone_severity가 고정한다.
    assert fa["is_valid"] is True
    # ★W3-2 라이브 seam 확증: analyze()가 제2종주거(지역기준가 미매칭 폴백)에서 bare 분양가
    #   (sale_prices — 신뢰구간·시나리오 미동반)를 산출하므로 estimate_dispersion.SALE_PRICE_POINT_ESTIMATE
    #   (계층C·P2 비차단) 배지가 이 주경로에 상시 실린다. 이는 재확증한 _calc_sale_prices bare-point
    #   shape가 라이브 analyze() 산출과 일치함을 실경로로 증명한다(합성 fixture 넘어선 그라운드 트루스).
    codes = [f["code"] for f in fa["findings"]]
    assert "SALE_PRICE_POINT_ESTIMATE" in codes, (
        "analyze()가 산출한 bare 분양가에 W3-2 배지가 실린다(seam 통과·라이브 shape 확증)"
    )
    # ★핵심 seam 계약 = P0 부재(모든 finding 비차단) → analyze() gating behavior 불변. 이후 Wave가
    #   비차단 배지를 더 실어도 이 계약은 유지된다(P0 배지가 여기서 발동하면 그건 검토 대상 회귀).
    assert all(f["severity"] != "P0" for f in fa["findings"])
    # runner 배선 메타(경로 비의존 계약 — enabled 플래그가 실제 실행경로였음을 확인).
    assert fa["metadata"].get("enabled") is True
    # 참고: analyze()-레벨 additive-only(키 1개만 추가) behavior 불변은 runner-레벨
    #   test_runner_noop::test_runner_noop_empty_report_and_additive가 저비용으로 커버한다
    #   (analyze() 이중 호출 회피). 이 seam 테스트는 '배선 실재'만 고정한다(변이-킬 대상).
