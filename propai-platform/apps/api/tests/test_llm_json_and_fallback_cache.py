"""LLM JSON 공용 파서(llm_json)·폴백 캐시오염 방지 술어(analysis_cache) 검증.

2026-07-22 라이브 실측 결함 2건의 회귀를 잠근다:
- 규제분석 LLM이 프리앰블("다음은 JSON입니다:")·후행 설명을 붙이면 자체 파서(선행 펜스만
  처리)가 json.loads에 실패해 "AI 해석 일시 미제공" 폴백으로 강등(간헐·실측 2/3 빈도).
- 그 폴백 결과가 영속 캐시(cache_put)에 박제되어 refresh 전까지 모든 조회가 영원히
  폴백을 반환(자가치유 불가). regulation·permits·market_report 3개 라우터 공통 클래스.
- 부수 결함: get_llm의 키 미설정 ValueError가 coarse 분류에서 'parse'로 오분류(진단 오도).
"""
import json
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.llm_json import coerce_llm_text, extract_json_text, parse_llm_json
from app.services.common.analysis_cache import llm_fallback_present, llm_fallback_stale

_OBJ = {"summary": "요약", "risks": ["리스크1"]}
_OBJ_TXT = json.dumps(_OBJ, ensure_ascii=False)


# ── parse_llm_json: 관대 추출 ──────────────────────────────────────────────

def test_parse_plain_object():
    assert parse_llm_json(_OBJ_TXT) == _OBJ


def test_parse_fenced_with_lang_tag():
    assert parse_llm_json(f"```json\n{_OBJ_TXT}\n```") == _OBJ


def test_parse_fenced_without_lang_tag():
    assert parse_llm_json(f"```\n{_OBJ_TXT}\n```") == _OBJ


def test_parse_preamble_before_fence():
    """★라이브 결함 재현 — 프리앰블 뒤 펜스는 기존 startswith 파서가 전부 실패하던 케이스."""
    raw = f"다음은 요청하신 규제 해석 JSON입니다:\n\n```json\n{_OBJ_TXT}\n```"
    assert parse_llm_json(raw) == _OBJ


def test_parse_bare_json_with_trailing_prose():
    raw = f"{_OBJ_TXT}\n\n위 JSON은 제공된 데이터만 근거로 작성했습니다."
    assert parse_llm_json(raw) == _OBJ


def test_parse_preamble_and_bare_json():
    raw = f"규제 해석 결과:\n{_OBJ_TXT}"
    assert parse_llm_json(raw) == _OBJ


def test_parse_array_not_swallowed_by_inner_object():
    """리스트 응답에서 내부 dict만 건져 리스트를 잃지 않는다(legal_discovery 계약)."""
    arr = [{"law": "국토계획법"}, {"law": "건축법"}]
    raw = "탐색 결과:\n" + json.dumps(arr, ensure_ascii=False) + "\n이상입니다."
    assert parse_llm_json(raw) == arr


def test_parse_anthropic_content_blocks():
    blocks = [{"type": "text", "text": f"```json\n{_OBJ_TXT}\n```"}]
    assert parse_llm_json(blocks) == _OBJ


def test_parse_unparseable_raises_jsondecodeerror():
    try:
        parse_llm_json("죄송합니다. 분석에 필요한 데이터가 부족합니다.")
        raise AssertionError("JSONDecodeError가 나야 한다")
    except json.JSONDecodeError:
        pass


def test_coerce_and_extract_helpers():
    assert coerce_llm_text("abc") == "abc"
    assert coerce_llm_text([{"type": "text", "text": "a"}, "b"]) == "a\nb"
    assert extract_json_text(f"서문\n```json\n{_OBJ_TXT}\n```\n후문") == _OBJ_TXT


# ── llm_fallback_present: 3개 서비스 폴백 마커 ────────────────────────────

def test_fallback_present_regulation_shape():
    assert llm_fallback_present({"ai": {"generated": False, "fallback_reason": "parse"}}) is True
    assert llm_fallback_present({"ai": {"generated": True}}) is False
    assert llm_fallback_present({"ai": None}) is False  # use_llm=False 경로


def test_fallback_present_permits_shape():
    assert llm_fallback_present({"ai": False, "methods": []}) is True
    assert llm_fallback_present({"ai": True, "methods": []}) is False


def test_fallback_present_market_report_shape():
    assert llm_fallback_present({"narrative": {"generated": False}}) is True
    assert llm_fallback_present({"narrative": {"generated": True}}) is False
    # use_llm=False 리터럴(마커 없음)은 폴백으로 보지 않는다
    assert llm_fallback_present({"narrative": {"summary": "AI 분석 미포함"}}) is False


def test_fallback_present_non_dict():
    assert llm_fallback_present(None) is False
    assert llm_fallback_present([1, 2]) is False


# ── llm_fallback_stale: 유예 기반 자가치유 판정 ───────────────────────────

def _fb(created_at=None) -> dict:
    out = {"ai": {"generated": False, "fallback_reason": "parse"}}
    if created_at is not None:
        out["_cache"] = {"cached": True, "created_at": created_at}
    return out


def test_stale_success_payload_never_stale():
    assert llm_fallback_stale({"ai": {"generated": True}, "_cache": {"created_at": "2020-01-01 00:00:00+00:00"}}) is False


def test_stale_fresh_fallback_within_grace_returns_cached():
    from datetime import datetime
    now = str(datetime.now(UTC))
    assert llm_fallback_stale(_fb(now)) is False


def test_stale_old_fallback_triggers_retry():
    assert llm_fallback_stale(_fb("2020-01-01 00:00:00+00:00")) is True


def test_stale_missing_meta_defaults_to_retry():
    # created_at 결손이면 치유 우선(재시도 허용)
    assert llm_fallback_stale(_fb(None)) is True


# ── regulation _llm: 폴백 사유 정직 분류 ─────────────────────────────────

_LIMITS = {"bcr": {"legal": 20, "ordinance": None, "effective": 20},
           "far": {"legal": 100, "ordinance": None, "effective": 80}}
_DISTRICTS = [{"name": "토지거래계약허가구역", "impact": "상"}]


async def _run_llm(mock_llm=None, get_llm_side_effect=None):
    from app.services.regulation.regulation_analysis_service import RegulationAnalysisService
    kwargs = {"side_effect": get_llm_side_effect} if get_llm_side_effect else {"return_value": mock_llm}
    with patch("app.services.ai.llm_provider.get_llm", **kwargs):
        return await RegulationAnalysisService()._llm(
            "서울 강남구 역삼동 736-1", "일반상업지역", "", 4172.0, _LIMITS, _DISTRICTS,
        )


async def test_llm_provider_init_failure_classified_provider_not_parse():
    """★오분류 회귀 잠금 — 키 미설정 ValueError는 'provider'다('parse' 아님)."""
    out = await _run_llm(get_llm_side_effect=ValueError("anthropic API key not configured"))
    assert out["generated"] is False
    assert out["fallback_reason"] == "provider"


async def test_llm_preamble_fenced_response_parses_ok():
    """★라이브 결함 재현 — 프리앰블+펜스 응답도 이제 성공한다."""
    resp = MagicMock()
    resp.content = f"다음은 통합 해석입니다:\n```json\n{_OBJ_TXT}\n```"
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=resp)
    out = await _run_llm(mock_llm=llm)
    assert out["generated"] is True
    assert out["summary"] == "요약"


async def test_llm_garbage_response_classified_parse():
    resp = MagicMock()
    resp.content = "죄송합니다. JSON을 생성할 수 없습니다."
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=resp)
    out = await _run_llm(mock_llm=llm)
    assert out["generated"] is False
    assert out["fallback_reason"] == "parse"
