"""기하 SSOT(design_geometry) 단위테스트 — 순수 로직(DB/네트워크/LLM 무관).

검증:
- 평면 브리지(build_unit_plans): 평형 분해 → generate_unit_plan 실폴리곤(rooms/boundaries/openings) 적재.
- DesignGeometry SSOT 어셈블(build_design_geometry): 매스+동+층+코어+평형 평면.
- LLM 검증게이트(verify_adjusted_plan): 무중첩·음수·과대·빈 → 폐기·원안 폴백(가짜 통과 금지).
- allowed_uses(별표): 확인분만·미확정 None.
- orientation_from_polygon: 최장변 방위→향. None 입력 None.
- core_type_for_units: 세대수→코어형 매핑(UNIT_CORE_TYPES 계약).
"""

import asyncio

import pytest

from app.services.design_ingest.composition import compute_unit_breakdown
from app.services.design_ingest.design_geometry import (
    DesignGeometry,
    allowed_uses,
    build_design_geometry,
    build_unit_plans,
    core_type_for_units,
    llm_adjust_unit_plan,
    orientation_from_polygon,
    verify_adjusted_plan,
)

# 서울 인근 동서로 긴 직사각형 필지(향 산출 안정 — 남향 기대).
_GEO_EW_LONG = {
    "type": "Polygon",
    "coordinates": [[[127.0, 37.5], [127.0012, 37.5], [127.0012, 37.5004],
                     [127.0, 37.5004], [127.0, 37.5]]],
}


def _breakdown(types=("59A", "84A"), per_floor_net=300.0, floors=10):
    ub = compute_unit_breakdown(per_floor_net, floors, list(types))
    assert ub is not None
    return ub["units"]


# ── allowed_uses(국토계획법 별표) ──

def test_allowed_uses_known_zone_korean():
    uses = allowed_uses("제2종일반주거지역")
    assert uses is not None and "공동주택" in uses


def test_allowed_uses_zone_code_alias():
    # 코드(2R) → 한글명 별칭으로 해석.
    assert allowed_uses("2R") == allowed_uses("제2종일반주거지역")


def test_allowed_uses_commercial_includes_office():
    uses = allowed_uses("일반상업지역")
    assert uses is not None and "업무시설" in uses and "판매시설" in uses


def test_allowed_uses_unknown_is_none():
    # 미확정 용도지역은 무근거 폴백 금지 — None(정직).
    assert allowed_uses("무슨이상한지역") is None
    assert allowed_uses(None) is None


# ── core_type_for_units ──

def test_core_type_small_is_stair():
    assert core_type_for_units(2) == "계단실형"


def test_core_type_mid_is_corridor():
    assert core_type_for_units(4) == "복도형"


def test_core_type_high_density_is_tower():
    assert core_type_for_units(8) == "타워형"


def test_core_type_none_defaults_stair():
    assert core_type_for_units(None) == "계단실형"


# ── orientation_from_polygon ──

def test_orientation_ew_long_is_south_facing():
    o = orientation_from_polygon(_GEO_EW_LONG)
    assert o is not None
    # 동서로 긴 필지 → 최장변 동서 → 주 입면 법선 남/북 → 남향 채택(facing≈0).
    assert abs(o["facing_deg"]) < 1.0
    assert o["facing_label"] == "남"
    assert o["longest_edge_m"] > 0


def test_orientation_none_input():
    assert orientation_from_polygon(None) is None
    assert orientation_from_polygon({}) is None


# ── 평면 브리지(D3 해소) ──

def test_build_unit_plans_produces_real_polygons():
    plans = build_unit_plans(_breakdown(), core_type="복도형")
    assert len(plans) == 2
    for p in plans:
        assert p["plan"] is not None
        assert p["plan_error"] is None
        # generate_unit_plan 반환 형식 그대로 — rooms/boundaries/openings 실폴리곤 보유.
        assert len(p["plan"]["rooms"]) > 0
        assert len(p["plan"]["boundaries"]) > 0
        assert len(p["plan"]["openings"]) > 0


def test_build_unit_plans_out_of_range_area_is_honest_none():
    # 지원범위(20~250㎡) 밖 평형은 가짜 평면 금지 — plan=None + 사유.
    plans = build_unit_plans([{"type": "XL", "area_sqm": 9999.0, "total_count": 1}])
    assert len(plans) == 1
    assert plans[0]["plan"] is None
    assert "범위밖" in (plans[0]["plan_error"] or "")


def test_build_unit_plans_empty_input():
    assert build_unit_plans(None) == []
    assert build_unit_plans([]) == []


# ── DesignGeometry SSOT 어셈블 ──

def test_build_design_geometry_full():
    mass = {"building_width_m": 30.0, "building_depth_m": 15.0, "num_floors": 12,
            "floor_height_m": 3.0, "total_floor_area_sqm": 5400.0}
    candidate = {
        "unit_breakdown": _breakdown(),
        "estimated_units": 80, "estimated_floors": 12, "estimated_gfa_sqm": 5400.0,
        "placement": {"building": {"x": 0, "y": 0, "w": 30.0, "d": 15.0},
                      "blocks": [{"x": 0, "y": 0, "w": 30.0, "d": 15.0}]},
    }
    geo = build_design_geometry(
        candidate, {"area_sqm": 2000.0, "zone_code": "2R"},
        mass=mass, site_geometry=_GEO_EW_LONG, building_use="공동주택",
    )
    assert isinstance(geo, DesignGeometry)
    d = geo.to_dict()
    assert d["site"]["orientation"]["facing_label"] == "남"
    assert len(d["floors"]) == 12
    assert len(d["dongs"]) == 1
    assert len(d["cores"]) == 1 and d["cores"][0]["num_cores"]
    # units[].plan은 generate_unit_plan 실폴리곤(평면 브리지 적재).
    assert all(u["plan"] for u in d["units"])
    assert d["provenance"]["unit"] == "m"
    assert "generate_unit_plan" in d["provenance"]["reused"]


def test_build_design_geometry_mass_only_no_candidate():
    # 후보 없음(도면·평형 미상) — 매스 기반 기하만, units=[](정직·가짜 금지).
    mass = {"building_width_m": 20.0, "building_depth_m": 12.0, "num_floors": 5,
            "floor_height_m": 3.0, "total_floor_area_sqm": 1200.0}
    geo = build_design_geometry(None, {"area_sqm": 800.0}, mass=mass).to_dict()
    assert len(geo["floors"]) == 5
    assert geo["units"] == []
    assert geo["site"]["orientation"] is None  # 폴리곤 미제공 → 향 None


# ── LLM 검증게이트(RLVR: LLM proposes / rules verify) ──

def _ref_plan():
    return build_unit_plans(_breakdown(types=("59A",)), core_type="계단실형")[0]["plan"]


def test_verify_gate_accepts_original_rooms():
    plan = _ref_plan()
    res = verify_adjusted_plan(plan, plan["rooms"], area_sqm=59.0)
    assert res["ok"] is True and res["fell_back"] is False


def test_verify_gate_rejects_overlap():
    plan = _ref_plan()
    bad = [{"name": "a", "x": 0, "y": 0, "w": 5, "h": 5},
           {"name": "b", "x": 1, "y": 1, "w": 5, "h": 5}]
    res = verify_adjusted_plan(plan, bad, area_sqm=59.0)
    assert res["ok"] is False and res["fell_back"] is True
    assert res["rooms"] == plan["rooms"]  # 원안 폴백
    assert any("중첩" in v for v in res["violations"])


def test_verify_gate_rejects_negative_dim():
    plan = _ref_plan()
    res = verify_adjusted_plan(plan, [{"name": "a", "x": 0, "y": 0, "w": -1, "h": 5}], area_sqm=59.0)
    assert res["ok"] is False


def test_verify_gate_rejects_area_inflation():
    plan = _ref_plan()
    # 본체 envelope 크게 초과하는 거대 실 → 면적 부풀리기 거부.
    huge = [{"name": "a", "x": 0, "y": 0, "w": 100, "h": 100}]
    res = verify_adjusted_plan(plan, huge, area_sqm=59.0)
    assert res["ok"] is False


def test_verify_gate_empty_falls_back():
    plan = _ref_plan()
    res = verify_adjusted_plan(plan, [], area_sqm=59.0)
    assert res["ok"] is False and res["rooms"] == plan["rooms"]


# ── LLM 조정층 폴백(무LLM 환경에서도 정직 동작) ──

def test_llm_adjust_no_plan_returns_none():
    # plan 없는 유닛은 조정 대상 부재 → None.
    assert asyncio.run(llm_adjust_unit_plan({"plan": None}, site_context={})) is None


def test_llm_adjust_falls_back_when_llm_unavailable(monkeypatch):
    # _llm_propose_rooms를 강제 실패시키면 결정론 원안 유지(applied=False·정직표기).
    import app.services.design_ingest.design_geometry as dg

    async def _boom(*_a, **_k):
        raise RuntimeError("no llm key")

    monkeypatch.setattr(dg, "_llm_propose_rooms", _boom)
    plan = _ref_plan()
    res = asyncio.run(dg.llm_adjust_unit_plan({"plan": plan}, site_context={}))
    assert res is not None
    assert res["applied"] is False
    assert res["rooms"] == plan["rooms"]


def test_llm_adjust_applies_when_proposal_valid(monkeypatch):
    # 유효(무중첩·envelope 내) 조정안이면 검증 통과 → applied=True.
    import app.services.design_ingest.design_geometry as dg

    plan = _ref_plan()

    async def _good(*_a, **_k):
        # 원안 rooms를 살짝만 변형(여전히 무중첩·envelope 내) — 통과 기대.
        return [dict(r) for r in plan["rooms"]]

    monkeypatch.setattr(dg, "_llm_propose_rooms", _good)
    res = asyncio.run(dg.llm_adjust_unit_plan({"plan": plan}, site_context={}))
    assert res is not None and res["applied"] is True
    assert res["verification"]["passed"] is True


def test_llm_adjust_rejects_bad_proposal(monkeypatch):
    # 검증 실패(중첩) 조정안이면 폐기 → applied=False·원안 폴백.
    import app.services.design_ingest.design_geometry as dg

    plan = _ref_plan()

    async def _bad(*_a, **_k):
        return [{"name": "a", "x": 0, "y": 0, "w": 5, "h": 5},
                {"name": "b", "x": 1, "y": 1, "w": 5, "h": 5}]

    monkeypatch.setattr(dg, "_llm_propose_rooms", _bad)
    res = asyncio.run(dg.llm_adjust_unit_plan({"plan": plan}, site_context={}))
    assert res is not None and res["applied"] is False
    assert res["verification"]["fell_back"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
