"""AI 비서 잘림·커버리지 수정 회귀 테스트 (2026-07-17).

배경(tracer 확정 근본원인):
- 잘림: ai_assistant.py(_plain_chat_text/_plain_chat_stream) · assistant_agent.py
  (run_agent_events) 세 곳이 max_tokens=1024를 하드코딩해 플랫폼 기본
  (llm_provider.py get_llm 기본값=4096)보다 낮았다. ainvoke 완성-후-송출 구조라 상한
  도달 시 문장 중간 절단이 에러 표시 없이 조용히 전송됐다.
- 커버리지: _READ_TOOLS가 3개(analyze_site·feasibility_precheck·estimate_land_price)뿐이고
  analyze_site는 조례·실효FAR를 전혀 참조하지 않는 구조적 결함이었다(auto_zoning_service.
  ZONE_LIMITS 법정상한만 참조).

봉합 계약(이 파일이 고정하는 값 — 무회귀):
1. 3개 get_llm() 호출부 모두 max_tokens 하드코딩 제거(플랫폼 기본 4096 상속).
2. stop_reason/finish_reason이 max_tokens/length면 정직 절단 고지(_TRUNCATION_NOTICE)를
   응답 말미에 덧붙인다.
3. analyze_site가 precheck_service._legal_limits(SSOT — OrdinanceService·calc_effective_far)를
   재사용해 legal_far(법정)·effective_far(실효)·far_source를 분리 표기한다(재계산 금지).
   zone_type이 주소 키워드 추론(inferred)이면 신뢰불가로 생략한다.
4. _READ_TOOLS에 rough_feasibility·permit_top3·nearby_transactions 3종을 얇은 래퍼로 추가한다.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.ai import assistant_agent as agent_module
from apps.api.routers import ai_assistant as router_module

# asyncio_mode=auto(pyproject.toml)라 async def 테스트는 마킹 없이 자동 인식된다.
# 동기 테스트(예: test_is_truncated_detection)도 이 파일에 섞여 있어 모듈 전역
# pytestmark(pytest.mark.asyncio)는 적용하지 않는다(붙이면 동기 테스트에 경고 발생).


async def _noop_billing(*args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def _stub_billing(monkeypatch):
    """실제 DB/과금 부수효과 차단(best-effort라 실패해도 무해하지만 테스트를 hermetic화)."""
    monkeypatch.setattr(
        "app.services.ai.base_interpreter.record_llm_response_billing", _noop_billing,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 페이크 LLM — 실제 네트워크/SDK 없이 get_llm() 호출부만 검증
# ─────────────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, content="ok", stop_reason=None, tool_calls=None):
        self.content = content
        self.response_metadata = {"stop_reason": stop_reason} if stop_reason else {}
        self.tool_calls = tool_calls or []
        self.usage_metadata = {}


class _FakePlainLLM:
    """단발 ainvoke/astream용 페이크(assistant_chat/_stream 폴백 경로가 소비)."""

    def __init__(self, resp):
        self._resp = resp

    async def ainvoke(self, msgs):
        return self._resp

    async def astream(self, msgs):
        yield self._resp


class _FakeToolLLM:
    """bind_tools() 이후 반환되는 페이크 — 도구 호출 없이 바로 최종응답."""

    def __init__(self, resp):
        self._resp = resp

    async def ainvoke(self, convo):
        return self._resp


class _FakeBaseLLM:
    def __init__(self, resp):
        self._resp = resp

    def bind_tools(self, tools):
        return _FakeToolLLM(self._resp)

    async def ainvoke(self, convo):
        return self._resp


# ─────────────────────────────────────────────────────────────────────────────
# 1) max_tokens 하드코딩 제거 회귀 핀 — 플랫폼 기본(4096) 상속 확인
# ─────────────────────────────────────────────────────────────────────────────

async def test_plain_chat_text_no_hardcoded_max_tokens(monkeypatch):
    captured: dict = {}

    def fake_get_llm(**kwargs):
        captured.update(kwargs)
        return _FakePlainLLM(_FakeResp("안녕하세요"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    text = await router_module._plain_chat_text([HumanMessage(content="hi")])
    assert "max_tokens" not in captured
    assert text == "안녕하세요"


async def test_plain_chat_stream_no_hardcoded_max_tokens(monkeypatch):
    captured: dict = {}

    def fake_get_llm(**kwargs):
        captured.update(kwargs)
        return _FakePlainLLM(_FakeResp("스트림 응답"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    chunks = [c async for c in router_module._plain_chat_stream([HumanMessage(content="hi")])]
    assert "max_tokens" not in captured
    assert "".join(chunks) == "스트림 응답"


async def test_run_agent_events_no_hardcoded_max_tokens(monkeypatch):
    captured: dict = {}

    def fake_get_llm(**kwargs):
        captured.update(kwargs)
        return _FakeBaseLLM(_FakeResp("도구없이 응답"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    events = [
        ev
        async for ev in agent_module.run_agent_events(
            [SystemMessage(content="sys"), HumanMessage(content="hi")]
        )
    ]
    assert "max_tokens" not in captured
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert deltas == ["도구없이 응답"]


# ─────────────────────────────────────────────────────────────────────────────
# 2) stop_reason 절단 정직 고지 유닛
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "meta,expected",
    [
        ({"stop_reason": "max_tokens"}, True),
        ({"finish_reason": "length"}, True),
        ({"stop_reason": "end_turn"}, False),
        ({}, False),
    ],
)
def test_is_truncated_detection(meta, expected):
    class _R:
        response_metadata = meta

    assert agent_module._is_truncated(_R()) is expected


def test_is_truncated_missing_metadata():
    class _R:
        pass

    assert agent_module._is_truncated(_R()) is False


async def test_plain_chat_text_appends_truncation_notice(monkeypatch):
    def fake_get_llm(**kwargs):
        return _FakePlainLLM(_FakeResp("잘린 문장", stop_reason="max_tokens"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    text = await router_module._plain_chat_text([HumanMessage(content="hi")])
    assert text.startswith("잘린 문장")
    assert agent_module._TRUNCATION_NOTICE in text


async def test_plain_chat_text_no_notice_when_complete(monkeypatch):
    def fake_get_llm(**kwargs):
        return _FakePlainLLM(_FakeResp("완결된 문장", stop_reason="end_turn"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    text = await router_module._plain_chat_text([HumanMessage(content="hi")])
    assert text == "완결된 문장"
    assert agent_module._TRUNCATION_NOTICE not in text


async def test_plain_chat_stream_appends_truncation_notice(monkeypatch):
    def fake_get_llm(**kwargs):
        return _FakePlainLLM(_FakeResp("스트림 잘림", stop_reason="max_tokens"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    chunks = [c async for c in router_module._plain_chat_stream([HumanMessage(content="hi")])]
    assert "".join(chunks) == "스트림 잘림" + agent_module._TRUNCATION_NOTICE


async def test_run_agent_events_appends_truncation_notice(monkeypatch):
    def fake_get_llm(**kwargs):
        return _FakeBaseLLM(_FakeResp("에이전트 절단", stop_reason="max_tokens"))

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", fake_get_llm)
    events = [
        ev
        async for ev in agent_module.run_agent_events(
            [SystemMessage(content="sys"), HumanMessage(content="hi")]
        )
    ]
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert len(deltas) == 1
    assert agent_module._TRUNCATION_NOTICE in deltas[0]


# ─────────────────────────────────────────────────────────────────────────────
# 3) 도구 커버리지 확장 — 스모크(임포트·시그니처·등록)
# ─────────────────────────────────────────────────────────────────────────────

def test_read_tools_registered():
    names = {t.name for t in agent_module._READ_TOOLS}
    assert names == {
        "analyze_site", "feasibility_precheck", "estimate_land_price",
        "rough_feasibility", "permit_top3", "nearby_transactions",
    }
    assert set(agent_module._TOOL_LABELS) == names
    assert set(agent_module._TOOLS_BY_NAME) == names


@pytest.mark.parametrize(
    "tool_name,expected_args",
    [
        ("rough_feasibility", {"address", "dev_type"}),
        ("permit_top3", {"address", "area_sqm"}),
        ("nearby_transactions", {"address", "months"}),
    ],
)
def test_new_tool_signatures(tool_name, expected_args):
    t = agent_module._TOOLS_BY_NAME[tool_name]
    assert set(t.args) == expected_args
    assert t.description
    assert "읽기 전용" in t.description


# ─────────────────────────────────────────────────────────────────────────────
# 4) analyze_site — legal_far/effective_far/far_source 분리 표기(SSOT 재사용)
# ─────────────────────────────────────────────────────────────────────────────

async def test_analyze_site_includes_legal_and_effective_far(monkeypatch):
    from app.services.precheck import precheck_service as precheck_module
    from app.services.zoning import auto_zoning_service as zoning_module

    async def _fake_analyze(self, address):
        return {
            "address": address, "pnu": "1111010100100010000",
            "zone_type": "제2종일반주거지역", "zone_source": "vworld",
            "land_area_sqm": 500.0, "land_category": "대",
            "official_price_per_sqm": 3_000_000,
        }

    async def _fake_legal_limits(zone_type, address=None, pnu=None, **_kwargs):
        return {
            "far_pct": 250, "applied_far_pct": 200.0,
            "far_source": "구조상한(건폐율×4층) 적용", "far_reliable": True,
        }

    monkeypatch.setattr(zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(precheck_module, "_legal_limits", _fake_legal_limits)

    out = await agent_module._TOOLS_BY_NAME["analyze_site"].ainvoke(
        {"address": "서울 강남구 역삼동 1"}
    )
    assert "법정 용적률(legal_far): 250%" in out
    assert "실효 용적률(effective_far): 200%" in out
    assert "구조상한(건폐율×4층) 적용" in out
    assert "SSOT 확정" in out


async def test_analyze_site_skips_far_lookup_when_inferred(monkeypatch):
    from app.services.precheck import precheck_service as precheck_module
    from app.services.zoning import auto_zoning_service as zoning_module

    called = {"n": 0}

    async def _fake_analyze(self, address):
        return {
            "address": address, "zone_type": "제2종일반주거지역",
            "zone_source": "keyword_inference", "land_area_sqm": 500.0,
        }

    async def _fake_legal_limits(zone_type, address=None, pnu=None, **_kwargs):
        called["n"] += 1
        return {"far_pct": 250, "applied_far_pct": 200.0}

    monkeypatch.setattr(zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(precheck_module, "_legal_limits", _fake_legal_limits)

    out = await agent_module._TOOLS_BY_NAME["analyze_site"].ainvoke(
        {"address": "서울 강남구 역삼동 1"}
    )
    assert called["n"] == 0
    assert "effective_far" not in out
    assert "legal_far" not in out


# ─────────────────────────────────────────────────────────────────────────────
# 5) 신규 도구 3종 — 얇은 래퍼 포맷팅 유닛(하위 서비스는 스텁으로 격리)
# ─────────────────────────────────────────────────────────────────────────────

async def test_rough_feasibility_tool_formats_summary(monkeypatch):
    import app.services.feasibility.rough_feasibility_orchestrator as orch_module

    async def _fake_build(*, address, parcels=None, project_id=None, dev_type=None,
                           region="", equity_won=None, overrides=None, db=None, site_id=None):
        return {
            "scenario_status": "actual",
            "inputs": {
                "zone_type": "제2종일반주거지역", "dev_type_name": "도시형생활주택",
                "effective_far_pct": 200.0, "gfa_sqm": 1000.0,
            },
            "summary": {
                "total_cost_won": 1_000_000_000, "total_revenue_won": 1_300_000_000,
                "net_profit_won": 300_000_000, "roi_pct": 30.0, "grade": "B",
            },
            "degraded_notes": [],
        }

    monkeypatch.setattr(orch_module, "build_rough_scenario", _fake_build)
    out = await agent_module._TOOLS_BY_NAME["rough_feasibility"].ainvoke(
        {"address": "서울 강남구 역삼동 1"}
    )
    assert "용도지역: 제2종일반주거지역" in out
    assert "순이익: 300,000,000원" in out
    assert "ROI: 30.0%" in out
    assert "등급: B" in out


async def test_rough_feasibility_tool_reports_unavailable_honestly(monkeypatch):
    import app.services.feasibility.rough_feasibility_orchestrator as orch_module

    async def _fake_build(**kwargs):
        return {
            "scenario_status": "unavailable",
            "degraded_notes": ["개발 가능한 사업모델이 없어 개략수지를 산출하지 않습니다(무목업)."],
        }

    monkeypatch.setattr(orch_module, "build_rough_scenario", _fake_build)
    out = await agent_module._TOOLS_BY_NAME["rough_feasibility"].ainvoke(
        {"address": "서울 강남구 역삼동 1"}
    )
    assert "산출 불가" in out


async def test_permit_top3_tool_formats_recommendations(monkeypatch):
    import app.services.feasibility.feasibility_service_v2 as feas_module

    async def _fake_top3(self, address, land_area_sqm=None, region="",
                          equity_won=10_000_000_000, use_llm=True, with_senior=True,
                          parcels=None):
        assert use_llm is False
        assert with_senior is False
        return {
            "zone_type": "제3종일반주거지역", "effective_far_pct": 250.0,
            "land_price_reliable": True, "far_reliable": True,
            "recommendations": [
                {
                    "type_name": "오피스텔", "development_type": "M04",
                    "feasibility": {
                        "profit_rate_pct": 15.2, "net_profit_won": 500_000_000, "grade": "A",
                    },
                },
            ],
        }

    monkeypatch.setattr(feas_module.FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)
    out = await agent_module._TOOLS_BY_NAME["permit_top3"].ainvoke(
        {"address": "서울 강남구 역삼동 1"}
    )
    assert "1. 오피스텔" in out
    assert "등급 A" in out


async def test_permit_top3_tool_no_heavy_llm_subcall_flags(monkeypatch):
    """도구가 use_llm=False·with_senior=False로 호출하는지(무거운 하위호출 제외) 확인."""
    import app.services.feasibility.feasibility_service_v2 as feas_module

    captured: dict = {}

    async def _fake_top3(self, address, land_area_sqm=None, region="",
                          equity_won=10_000_000_000, use_llm=True, with_senior=True,
                          parcels=None):
        captured["use_llm"] = use_llm
        captured["with_senior"] = with_senior
        return {"recommendations": []}

    monkeypatch.setattr(feas_module.FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)
    await agent_module._TOOLS_BY_NAME["permit_top3"].ainvoke({"address": "서울 강남구 역삼동 1"})
    assert captured == {"use_llm": False, "with_senior": False}


async def test_nearby_transactions_tool_formats_summary(monkeypatch):
    import app.services.land_intelligence.nearby_map_service as nearby_module
    from app.services.zoning import auto_zoning_service as zoning_module

    async def _fake_analyze(self, address):
        return {"pnu": "1168010100100010000"}

    async def _fake_build(self, *, address, lawd_cd, months=3, radius_m=1000,
                           sigungu_hint="", center_hint=None):
        assert lawd_cd == "11680"
        return {
            "data_source": "molit_live",
            "categories": {
                "apt_trade": {
                    "label": "아파트 매매", "kind": "trade", "count": 5,
                    "groups": [
                        {"name": "역삼자이", "count": 5, "avg_price_10k": 150000,
                         "avg_area_m2": 84.9},
                    ],
                },
            },
        }

    monkeypatch.setattr(zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(nearby_module.NearbyMapService, "build", _fake_build)
    out = await agent_module._TOOLS_BY_NAME["nearby_transactions"].ainvoke(
        {"address": "서울 강남구 역삼동 1"}
    )
    assert "아파트 매매" in out
    assert "역삼자이" in out


async def test_nearby_transactions_tool_no_pnu_is_honest(monkeypatch):
    from app.services.zoning import auto_zoning_service as zoning_module

    async def _fake_analyze(self, address):
        return {"pnu": None}

    monkeypatch.setattr(zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    out = await agent_module._TOOLS_BY_NAME["nearby_transactions"].ainvoke(
        {"address": "존재하지않는주소"}
    )
    assert "데이터 없음" in out
