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


# ── Phase 3.2 잔여: cost·market 도메인 ──

def test_cost_and_market_domains_registered():
    assert {"cost", "market"} <= set(AVAILABLE_DOMAINS)
    assert get_specialist("cost").analysis_type == "domain_agent_cost"
    assert get_specialist("market").analysis_type == "domain_agent_market"


def test_cost_tool_deterministic():
    # ★P3: 상수(CONSTRUCTION_COST_PER_SQM)×면적 개산 폐기 — standard_quantity_estimator
    #   (표준물량 추정)+origin_cost_calculator(12단계 법정요율) 실계산으로 교체.
    from app.services.agents.registry import _cost_tool
    o = _cost_tool({"dev_type": "M06", "gfa_sqm": 1000})
    assert o["findings"][0]["check_id"] == "COST"
    assert o["findings"][0]["current"] == o["summary"]["total_construction_cost"]
    assert o["summary"]["total_construction_cost"] > 0
    assert o["summary"]["building_type"] == "공동주택"  # M06(일반분양) → estimator 기본 폴백
    assert o["summary"]["cost_per_sqm"] == round(o["summary"]["total_construction_cost"] / 1000)
    assert o == _cost_tool({"dev_type": "M06", "gfa_sqm": 1000})         # 결정론


def test_cost_tool_dev_type_maps_building_type():
    from app.services.agents.registry import _cost_tool
    # M09(지식산업센터) → 근린생활시설(_DEV_TYPE_TO_BUILDING_TYPE 매핑)
    o = _cost_tool({"dev_type": "M09", "gfa_sqm": 1000})
    assert o["summary"]["building_type"] == "근린생활시설"


def test_cost_tool_zero_gfa_no_division_error():
    from app.services.agents.registry import _cost_tool
    o = _cost_tool({"dev_type": "M06", "gfa_sqm": 0})
    assert o["summary"]["total_construction_cost"] == 0
    assert o["summary"]["cost_per_sqm"] == 0


def test_market_tool_surfaces_signals_no_fabrication():
    from app.services.agents.registry import _market_tool
    o = _market_tool({"official_price_per_sqm": 5_000_000})
    assert o["findings"][0]["check_id"] == "MARKET_PRICE" and o["findings"][0]["current"] == 5_000_000.0
    assert _market_tool({})["findings"] == []        # 신호 없으면 빈 findings(가짜 생성 X)
