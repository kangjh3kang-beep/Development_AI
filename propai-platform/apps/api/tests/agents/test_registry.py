"""Phase 3 T3 — registry + permit 구체 specialist 단위테스트(결정론 도구, 무 LLM).

check_permit_feasibility(dev_type 코드, zone_type) 실측: dev_type은 'M06'(일반분양) 등 코드.
제2종일반주거지역 허용=[M01,M02,M04,M06,M10,M11,M12,M13].
"""
import pytest

from app.services.agents.registry import AVAILABLE_DOMAINS, get_specialist


def test_permit_domain_registered():
    assert "permit" in AVAILABLE_DOMAINS
    a = get_specialist("permit")
    assert a.domain == "permit" and a.analysis_type == "domain_agent_permit"


def test_unknown_domain_raises():
    with pytest.raises(KeyError):
        get_specialist("nonexistent")


def test_permit_tool_is_deterministic_no_llm():
    # permit 도구는 check_permit_feasibility 기반 — 동일 입력 동일 findings(LLM 비개입)
    from app.services.agents.registry import _permit_tool
    o1 = _permit_tool({"dev_type": "M06", "zone_type": "제2종일반주거지역"})
    o2 = _permit_tool({"dev_type": "M06", "zone_type": "제2종일반주거지역"})
    assert o1 == o2 and o1["findings"][0]["check_id"] == "PERMIT"
    assert o1["findings"][0]["status"] == "pass"        # M06(일반분양) 허용 → pass


def test_permit_tool_disallowed_is_fail():
    from app.services.agents.registry import _permit_tool
    o = _permit_tool({"dev_type": "M09", "zone_type": "제2종일반주거지역"})
    assert o["findings"][0]["status"] == "fail"         # M09(지식산업센터) 불허 → fail
    assert o["summary"]["is_permitted"] is False


# ── Phase 3.2: 다도메인 specialist(zoning·far) ──

def test_multi_domain_registry():
    assert set(AVAILABLE_DOMAINS) >= {"permit", "zoning", "far"}
    for d in ("permit", "zoning", "far"):
        assert get_specialist(d).analysis_type == f"domain_agent_{d}"


def test_zoning_tool_lists_permitted_types_deterministic():
    from app.services.agents.registry import _zoning_tool
    o = _zoning_tool({"zone_type": "제2종일반주거지역"})
    assert o["findings"][0]["check_id"] == "ZONING"
    assert o["summary"]["permitted_count"] == 8          # [M01,M02,M04,M06,M10,M11,M12,M13]
    assert o == _zoning_tool({"zone_type": "제2종일반주거지역"})   # 결정론


def test_far_tool_effective_far_deterministic():
    from app.services.agents.registry import _far_tool
    o = _far_tool({"zone_type": "제2종일반주거지역"})
    assert o["findings"][0]["check_id"] == "FAR"
    assert o["findings"][0]["current"] == 250.0 and o["findings"][0]["status"] == "pass"
    assert o["summary"]["effective_far_pct"] == 250.0
