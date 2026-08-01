"""W2-a 단계분할 계약 잠금 — AI 해석 분리와 '건너뜀 ≠ 실패' 정직 표기.

★배경: 종합분석은 오리진 실측 190초인데 Cloudflare 엣지가 ~125초에서 끊는다(실사용자 524).
LLM 해석 2종이 소요의 대부분이므로, 결정론 분석만 먼저 받아 화면을 채우고 해석을 후속
호출로 이어붙일 수 있게 한다. 이때 **건너뛴 것을 실패로 보이게 하면 안 된다** — 프론트가
"정상인데 비어있음"/"생성 실패"/"이번 호출에서 요청 안 함" 3상태를 구분해야 한다.
"""

from __future__ import annotations

import inspect

import pytest

from app.routers.comprehensive_analysis import ComprehensiveAnalysisRequest
from app.services.land_intelligence.comprehensive_analysis_service import (
    ComprehensiveAnalysisService,
)

# ── 계약: 파라미터 존재와 기본값(기존 호출부 무회귀) ────────────────────────

def test_analyze_accepts_include_interpretation_defaulting_to_true():
    sig = inspect.signature(ComprehensiveAnalysisService.analyze)
    assert "include_interpretation" in sig.parameters, "단계분할 파라미터 부재"
    assert sig.parameters["include_interpretation"].default is True, (
        "기본값이 True가 아니면 기존 호출부가 조용히 해석을 잃는다"
    )


def test_request_schema_defaults_to_full_analysis():
    """★스키마 기본값도 True — 구버전 프론트가 보내지 않아도 동작 불변."""
    req = ComprehensiveAnalysisRequest(address="서울시 강남구 역삼동 1-1")
    assert req.include_interpretation is True


def test_request_schema_accepts_false():
    req = ComprehensiveAnalysisRequest(address="주소", include_interpretation=False)
    assert req.include_interpretation is False


# ── ★배선 잠금: 라우터가 실제로 서비스에 전달하는가 ─────────────────────────

def test_router_forwards_include_interpretation_to_service():
    """★파라미터만 있고 배선이 없으면 조용히 무시된다(로직·배선 2층 중 배선층).

    라우터 소스에서 analyze() 호출에 인자가 실제로 실려 있는지 확인한다.
    """
    import app.routers.comprehensive_analysis as mod

    src = inspect.getsource(mod.run_comprehensive_analysis)
    assert "include_interpretation=req.include_interpretation" in src, (
        "라우터가 include_interpretation을 서비스로 전달하지 않는다(배선 누락)"
    )


# ── ★정직 표기: 건너뜀은 실패가 아니다 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_skipped_interpretation_is_marked_deferred_not_failed(monkeypatch):
    """include_interpretation=False → status='deferred'(실패 아님)."""
    svc = ComprehensiveAnalysisService()

    # 무거운 수집을 타지 않도록 analyze의 상류를 최소 stub으로 대체할 수 없으므로,
    # 게이트 분기 자체를 순수하게 검증한다(아래 소스 계약 테스트와 쌍).
    src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    assert 'if not include_interpretation:' in src
    # deferred 분기가 두 해석 필드를 **모두** 덮는다.
    gate = src.split("if not include_interpretation:")[1].split("else:")[0]
    assert '"status": "deferred"' in gate
    assert 'result["ai_interpretation"]' in gate
    assert 'result["market_interpretation"]' in gate
    assert 'result["ai_interpretation_status"]' in gate
    assert 'result["market_interpretation_status"]' in gate
    assert svc is not None


def test_deferred_is_distinguishable_from_unavailable():
    """★3상태가 서로 다른 문자열이어야 프론트가 구분할 수 있다."""
    src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    assert '"status": "deferred"' in src
    assert '"status": "unavailable"' in src
    assert '"status": "ok"' in src


def test_success_path_also_sets_ai_interpretation_status():
    """성공 경로에도 status를 부여한다 — 없으면 '해석 있음'을 상태로 확인할 수 없다."""
    src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    ok_block = src.split("include_interpretation")[-1]
    assert 'result["ai_interpretation_status"] = {"status": "ok"}' in ok_block


# ── 해석 블록이 게이트 **안**에 있는가(밖에 남으면 deferred가 덮인다) ───────

def test_both_llm_phases_are_inside_the_gate():
    """★핵심 배선 불변식: market 해석이 게이트 밖에 남으면 deferred 값을 덮어써서
    '건너뛰기'가 실제로는 동작하지 않는다(구현 중 실제로 밟은 함정)."""
    src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    after_gate = src.split("if not include_interpretation:")[1]
    else_body = after_gate.split("else:", 1)[1]
    # else 블록 안에서 두 인터프리터가 모두 호출돼야 한다.
    head = else_body.split("# Phase 1 성장루프")[0]
    assert "site_analysis_interpreter" in head, "부지 해석이 게이트 밖"
    assert "market_interpreter" in head, "시장 해석이 게이트 밖(deferred가 덮인다)"
