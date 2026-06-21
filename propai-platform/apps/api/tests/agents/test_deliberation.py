"""INC-PD5 — 심의 SpecialistAgent: 등록 + 엔진 응답 매핑 + URL 미설정 graceful(네트워크 없음)."""
import types

from app.services.agents.registry import (
    AVAILABLE_DOMAINS,
    _deliberation_tool,
    _map_permit_response,
    get_specialist,
)


def test_deliberation_domain_registered():
    assert "심의" in AVAILABLE_DOMAINS
    a = get_specialist("심의")
    assert a.domain == "심의" and a.analysis_type == "domain_agent_심의"


def test_map_permit_response_maps_stages():
    res = {"spec_id": "permit-default", "run_id": "r1",
           "overall_conformance": "미흡", "overall_verification": "NEEDS_REVIEW",
           "stages": [{"stage_id": "building_review", "name": "건축심의",
                       "conformance": "미흡", "verification_status": "NEEDS_REVIEW"}]}
    out = _map_permit_response(res)
    assert out["summary"]["available"] is True
    assert out["summary"]["overall_conformance"] == "미흡"
    assert out["summary"]["spec_id"] == "permit-default"
    assert out["findings"][0]["check_id"] == "building_review"
    assert out["findings"][0]["status"] == "미흡"
    assert out["findings"][0]["note"] == "건축심의"


def test_map_permit_response_empty_stages():
    out = _map_permit_response({"spec_id": "x"})
    assert out["findings"] == [] and out["summary"]["available"] is True


async def test_deliberation_tool_graceful_when_url_unset(monkeypatch):
    # 엔진 URL 미설정 → 미연동 graceful(네트워크 호출 없음)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: types.SimpleNamespace(DELIBERATION_ENGINE_URL="", DELIBERATION_ENGINE_TOKEN=""),
    )
    out = await _deliberation_tool({"pnu": "1111010100100000001"})
    assert out["findings"] == []
    assert out["summary"]["available"] is False
    assert out["summary"]["reason"] == "engine_url_unset"
