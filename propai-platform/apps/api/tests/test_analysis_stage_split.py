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
    """★3상태가 서로 다른 문자열이어야 프론트가 구분할 수 있다.

    deferred는 analyze()의 게이트에, ok/unavailable은 공용 생성 메서드에 있다(리팩터 후 위치).
    """
    analyze_src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    gen_src = inspect.getsource(ComprehensiveAnalysisService.generate_interpretations)
    assert '"status": "deferred"' in analyze_src
    assert '"status": "unavailable"' in gen_src
    assert '"status": "ok"' in gen_src


def test_success_path_also_sets_ai_interpretation_status():
    """성공 경로에도 status를 부여한다 — 없으면 '해석 있음'을 상태로 확인할 수 없다."""
    src = inspect.getsource(ComprehensiveAnalysisService.generate_interpretations)
    assert 'out["ai_interpretation_status"] = {"status": "ok"}' in src


# ── 해석 생성이 게이트 **안**에서만 일어나는가(밖에 남으면 deferred가 덮인다) ───────

def test_interpretation_is_generated_only_inside_the_gate():
    """★핵심 배선 불변식: 해석 생성이 게이트 밖에 남으면 deferred 값을 곧바로 덮어써서
    '건너뛰기'가 실제로는 동작하지 않는다(구현 중 실제로 밟은 함정 — market 블록이 밖에 있었다).

    리팩터 후 생성은 generate_interpretations() 1회 호출로 단일화됐다. 그 호출이 else 블록
    안에만 있어야 한다.
    """
    src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    # ★주석 언급이 아니라 **실제 호출 형태**로 센다(주석까지 세면 항상 통과하는 공허한 가드).
    call = "await self.generate_interpretations("
    assert src.count(call) == 1, f"해석 생성 호출이 1곳이 아니다({src.count(call)}곳)"

    after_gate = src.split("if not include_interpretation:")[1]
    else_body = after_gate.split("else:", 1)[1].split("# Phase 1 성장루프")[0]
    assert call in else_body, (
        "해석 생성이 게이트 밖(건너뛰기가 무효화되고 deferred가 덮인다)"
    )


def test_no_interpreter_is_instantiated_outside_the_shared_method():
    """★분기 방지: analyze()가 인터프리터를 직접 만들면 공용 메서드와 구현이 갈라진다."""
    src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    assert "SiteAnalysisInterpreter(" not in src
    assert "MarketInterpreter(" not in src


# ── W2-b: 해석 전용 엔드포인트(2단계) ───────────────────────────────────────

def test_interpretation_endpoint_is_registered():
    """★2단계 경로가 실제로 라우터에 등록돼 있어야 한다(배선층)."""
    import app.routers.comprehensive_analysis as mod

    paths = [getattr(r, "path", "") for r in mod.router.routes]
    assert "/interpretation" in paths, f"해석 엔드포인트 미등록: {paths}"


def test_interpretation_endpoint_inherits_llm_quota_gate():
    """★LLM을 쓰는 엔드포인트가 쿼터 게이트를 우회하면 안 된다.

    쿼터는 라우터 레벨 dependencies에 붙어 있으므로 신규 엔드포인트도 자동 적용된다 —
    이 테스트는 그 부착이 사라지는 회귀를 잡는다(무료 LLM 우회 경로 생성 방지).
    """
    import app.routers.comprehensive_analysis as mod

    src = inspect.getsource(mod)
    assert "Depends(enforce_llm_quota)" in src, "라우터 레벨 LLM 쿼터 게이트 소실"


def test_both_paths_share_one_interpretation_implementation():
    """★SSOT: 통합 경로와 독립 엔드포인트가 **같은** generate_interpretations()를 탄다.

    별도 구현하면 프롬프트·폴백·상태표기가 갈라져 "어느 경로로 받았는지"에 따라 해석 품질이
    달라진다 — 단계분할이 만들 수 있는 가장 조용한 결함이라 구조로 막는다.
    """
    import app.routers.comprehensive_analysis as mod

    analyze_src = inspect.getsource(ComprehensiveAnalysisService.analyze)
    endpoint_src = inspect.getsource(mod.run_interpretation)

    assert "generate_interpretations(" in analyze_src, "통합 경로가 공용 메서드를 안 쓴다"
    assert "generate_interpretations(" in endpoint_src, "독립 경로가 공용 메서드를 안 쓴다"
    # 인터프리터를 엔드포인트가 직접 인스턴스화하면 구현이 갈라진 것이다.
    assert "SiteAnalysisInterpreter(" not in endpoint_src, "엔드포인트가 해석을 자체 구현(분기)"
    assert "MarketInterpreter(" not in endpoint_src, "엔드포인트가 해석을 자체 구현(분기)"


@pytest.mark.asyncio
async def test_generate_interpretations_degrades_honestly_without_raising():
    """해석 실패는 raise하지 않고 status='unavailable'+사유로 내려온다.

    ★1단계에서 이미 받은 분석 본문을 잃지 않는 것이 단계분할의 핵심 이득이다
    (종전엔 524 하나로 분석 전체가 사라졌다).
    """
    svc = ComprehensiveAnalysisService()
    # LLM 키·네트워크 없이 호출 → 두 인터프리터 모두 실패 경로를 탄다.
    out = await svc.generate_interpretations({"zone_type": "보전관리지역"})

    assert set(out) == {
        "ai_interpretation", "ai_interpretation_status",
        "market_interpretation", "market_interpretation_status",
    }
    for key in ("ai_interpretation_status", "market_interpretation_status"):
        assert out[key]["status"] in ("ok", "unavailable"), out[key]
        if out[key]["status"] == "unavailable":
            assert out[key].get("reason"), "실패인데 사유가 없다(정직 degrade 위반)"


@pytest.mark.asyncio
async def test_generate_interpretations_does_not_mutate_input():
    """입력 result를 변형하지 않는다 — 호출부가 병합을 통제한다."""
    svc = ComprehensiveAnalysisService()
    src = {"zone_type": "보전관리지역"}
    before = dict(src)
    await svc.generate_interpretations(src)
    assert src == before, "입력 result가 변형됐다"
