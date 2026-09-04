"""P2 페르소나(디벨로퍼·설계·시공) 오케스트레이션 단위테스트(R9).

전담 interpreter·외부 서비스(feasibility_v2/compute_design_mass/unit_mix/estimate_overview/
expert_panel)는 monkeypatch로 대체해 DB·외부API 없이 파이프라인 조립·체크리스트 판정·
검증루프(전문가패널 캐시·잠정 강등 R12·정직 고지 R1)·핸드오프 스키마·무과금·PDF 생성을 검증한다.
"""

from __future__ import annotations

from app.services.persona import cache
from app.services.persona.registry import PERSONA_REGISTRY, get_persona, list_personas
from app.services.persona.runner import run_persona
from app.services.report.render import build_report_model_from_persona, render_report


class _FakeDB:
    """address 직접 전달 경로만 쓰므로 DB 미접촉(execute 호출되면 실패시킴)."""

    async def execute(self, *a, **k):  # pragma: no cover — 호출되면 안 됨
        raise AssertionError("DB 접근이 없어야 한다(address 직접 전달)")


# ── 레지스트리(선언) ──

def test_registry_has_five_personas():
    # superset 비교(==5 아님) — P3 페르소나 추가 시에도 P2 핵심 5종 존재만 보장(회귀 방지).
    assert {
        "sales_agent", "urban_planner", "developer", "designer", "constructor",
    } <= set(PERSONA_REGISTRY)
    meta = list_personas()
    assert len(meta) >= 5
    for key in ("developer", "designer", "constructor"):
        spec = get_persona(key)
        assert spec is not None
        assert len(spec.checklist) == 4
        assert spec.dispatch_key == key
        m = next(x for x in meta if x["key"] == key)
        assert len(m["checklist"]) == 4
    # ExpertPanel ROSTERS 보유 키로 매핑(business/developer/construction 강등 방지).
    assert get_persona("developer").expert_lens == "feasibility"
    assert get_persona("designer").expert_lens == "design"
    assert get_persona("constructor").expert_lens == "cost"


# ── 디벨로퍼 ──

_RECOMMEND_LIVE = {
    "address": "서울특별시 강남구 역삼동 123",
    "zone_type": "일반상업지역",
    "effective_far_pct": 700,
    "land_price_reliable": True,
    "scenario_status": "actual",
    "total_types_analyzed": 5,
    "recommendations": [
        {"type_name": "주상복합", "composite_score": 88,
         "feasibility": {"total_revenue_won": 500_00000000, "total_cost_won": 400_00000000,
                         "net_profit_won": 100_00000000, "roi_pct": 12.5, "roe_pct": 25.0,
                         "npv_won": 80_00000000, "grade": "A"},
         "permit": {"is_permitted": True, "permit_complexity": 2}},
        {"type_name": "오피스텔", "composite_score": 70,
         "feasibility": {"net_profit_won": 60_00000000, "roi_pct": 8.0, "grade": "B",
                         "npv_won": 40_00000000},
         "permit": {"permit_complexity": 3}},
    ],
    "all_results": [{}, {}, {}],
    "ai_interpretation": None,
}


def _patch_feasibility(monkeypatch, result):
    class _FakeFeas:
        async def auto_recommend_top3(self, address, use_llm=False, **k):
            return dict(result)

    monkeypatch.setattr(
        "app.services.feasibility.feasibility_service_v2.FeasibilityServiceV2", _FakeFeas)
    cache._STORE.clear()


async def test_developer_live_confirmed_no_llm(monkeypatch):
    _patch_feasibility(monkeypatch, _RECOMMEND_LIVE)
    out = await run_persona("developer", _FakeDB(),
                            {"address": "서울특별시 강남구 역삼동 123"}, use_llm=False)
    assert out["persona_key"] == "developer"
    art = out["artifacts"]
    assert art["interpreter_available"] is True          # R2: 전담 interpreter 실재
    # 체크리스트: viability pass, go_nogo Go
    by_step = {c["step"]: c for c in out["checklist"]}
    assert by_step["viability"]["status"] == "pass"
    assert "Go" in by_step["go_nogo"]["value"]["decision"]
    # DSCR 미산출 정직 고지(R1)
    assert any("DSCR" in n for n in out["honesty_notes"])
    assert by_step["irr_npv"]["value"]["dscr"] is None
    # 무과금
    assert out["billing"]["estimated_fee_krw"] == 0
    assert "expert_panel" not in out["verification"]


async def test_developer_missing_is_partial(monkeypatch):
    out = await run_persona("developer", _FakeDB(), {}, use_llm=False)  # 주소 없음
    assert out["status"] == "partial"
    assert any("주소" in n for n in out["honesty_notes"])
    v = next(c for c in out["checklist"] if c["step"] == "viability")
    assert v["status"] == "missing"


async def test_developer_unreliable_land_tentative(monkeypatch):
    result = dict(_RECOMMEND_LIVE)
    result["land_price_reliable"] = False
    _patch_feasibility(monkeypatch, result)
    out = await run_persona("developer", _FakeDB(),
                            {"address": "어딘가"}, use_llm=False)
    assert out["status"] == "tentative"                  # R12 잠정 강등
    assert any("공시지가" in n for n in out["honesty_notes"])


async def test_developer_handoff_consumed(monkeypatch):
    _patch_feasibility(monkeypatch, _RECOMMEND_LIVE)
    ctx = {"address": "서울특별시 강남구 역삼동 123",
           "report_contracts": {
               "designer": {"status": "confirmed",
                            "checklist": [{"step": "layout", "status": "pass"}]}}}
    out = await run_persona("developer", _FakeDB(), ctx, use_llm=False)
    assert out["artifacts"]["handoff"]["designer"]["status"] == "confirmed"  # R11


async def test_developer_pdf_renders(monkeypatch):
    _patch_feasibility(monkeypatch, _RECOMMEND_LIVE)
    out = await run_persona("developer", _FakeDB(),
                            {"address": "서울특별시 강남구 역삼동 123"}, use_llm=False)
    pdf, _mime, _ext = render_report(build_report_model_from_persona(out, "developer"), "pdf")
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF"


# ── 설계 ──

# 매스 — "3R"(법정 bcr 50%·far 300%) 한도 내 값(실제 한도 비교가 pass 되도록).
_MASS = {
    "building_width_m": 24.0, "building_depth_m": 16.0, "num_floors": 20,
    "floor_height_m": 3.0, "building_height_m": 60.0,
    "bcr_pct": 48, "far_pct": 290, "total_units": 110,
}
# 매스 — "3R" 한도 초과(bcr 55>50·far 700>300) — 법규 no-op 해소 검증용(compliance warn).
_MASS_OVER = {
    "building_width_m": 24.0, "building_depth_m": 16.0, "num_floors": 20,
    "floor_height_m": 3.0, "building_height_m": 60.0,
    "bcr_pct": 55, "far_pct": 700, "total_units": 120,
}
_UNIT_MIX = {
    "method": "SLSQP", "total_units": 120, "efficiency_ratio": 0.75,
    "total_revenue_100m": 900, "gfa_efficiency_pct": 92.0, "total_parking_required": 120,
    "units": [
        {"code": "S59", "count": 60, "ratio_pct": 50.0, "area_sqm": 59, "price_per_pyeong_10k": 3200},
        {"code": "S84", "count": 60, "ratio_pct": 50.0, "area_sqm": 84, "price_per_pyeong_10k": 3500},
    ],
}


def _patch_design(monkeypatch, *, mass=_MASS, unit_mix=_UNIT_MIX, panel=None):
    async def _fake_mass(project_id, req):
        return dict(mass) if mass is not None else {}

    class _FakeOptimizer:
        def optimize(self, inp):
            return dict(unit_mix) if unit_mix is not None else {"error": "no", "units": []}

    monkeypatch.setattr("app.routers.design_v61.compute_design_mass", _fake_mass)
    monkeypatch.setattr(
        "app.services.feasibility.unit_mix_optimizer.UnitMixOptimizer", _FakeOptimizer)
    if panel is not None:
        monkeypatch.setattr(
            "app.services.expert_panel.expert_panel_service.ExpertPanelService", panel)
    cache._STORE.clear()


async def test_designer_live_confirmed_no_llm(monkeypatch):
    _patch_design(monkeypatch)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울특별시 강남구 역삼동 123",
                             "land_area_sqm": 1000, "zone_code": "3R"}, use_llm=False)
    assert out["persona_key"] == "designer"
    art = out["artifacts"]
    assert art["interpreter_available"] is True
    assert art["mass"]["far_pct"] == 290        # "3R" 한도(300) 내
    by_step = {c["step"]: c["status"] for c in out["checklist"]}
    assert by_step["layout"] == "pass"
    assert by_step["unit_mix"] == "pass"        # GFA 효율 92% ≥ 80
    assert by_step["compliance"] == "pass"      # bcr 48≤50·far 290≤300 — 실제 한도 비교(초과 없음)
    # 법정 한도가 zone_code 로 실제 산출돼 compliance value 에 노출(no-op 아님).
    comp = next(c for c in out["checklist"] if c["step"] == "compliance")
    assert comp["value"]["max_bcr_pct"] == 50.0 and comp["value"]["max_far_pct"] == 300.0
    assert out["billing"]["estimated_fee_krw"] == 0
    assert out["artifacts"]["unit_mix"]["total_units"] == 120


async def test_designer_compliance_flags_over_limit(monkeypatch):
    # [HIGH] 법규 no-op 해소 — 한도 초과 매스(bcr 55>50·far 700>300)는 warn + 위반 목록.
    _patch_design(monkeypatch, mass=_MASS_OVER)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000, "zone_code": "3R"},
                            use_llm=False)
    comp = next(c for c in out["checklist"] if c["step"] == "compliance")
    assert comp["status"] == "warn"
    assert "건폐율 초과" in comp["value"]["violations"]
    assert "용적률 초과" in comp["value"]["violations"]


# 매스 — "2R"(법정 bcr 60%·far 250%, 국토계획법 시행령 §85 SSOT) 한도 내 값
# (한글 zone_code 정규화 후 실제 비교 pass 검증용).
_MASS_2R = {
    "building_width_m": 24.0, "building_depth_m": 16.0, "num_floors": 12,
    "floor_height_m": 3.0, "building_height_m": 36.0,
    "bcr_pct": 55, "far_pct": 190, "total_units": 80,
}


async def test_designer_korean_zone_code_normalized_compliance_fires(monkeypatch):
    # [HIGH] 프론트 SSOT가 보내는 '한글명'(제2종일반주거지역)이 단축코드(2R)로 정규화돼
    # 법규준수가 'missing'이 아니라 실제 한도비교(pass)로 발화하는지 검증(no-op/강등 해소).
    _patch_design(monkeypatch, mass=_MASS_2R)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000,
                             "zone_code": "제2종일반주거지역"}, use_llm=False)
    comp = next(c for c in out["checklist"] if c["step"] == "compliance")
    # 한글명이 2R 로 정규화돼 법정 한도(bcr 60·far 250, 국토계획법 시행령 §85 SSOT)가
    # 실제 산출됨 → missing 아님. (★§85 정본 정합: 종전 far 200%는 결함 고정값이었음.)
    assert comp["status"] == "pass"
    assert comp["value"]["max_bcr_pct"] == 60.0 and comp["value"]["max_far_pct"] == 250.0
    assert comp["value"]["zone_code"] == "2R"
    # 'zone_code 미확보' 정직 고지가 붙지 않아야 한다(정규화 성공 경로).
    assert not any("미확보" in n for n in out["honesty_notes"])


async def test_designer_korean_zone_code_over_limit_warns(monkeypatch):
    # 한글 zone_code 정규화 후 한도 초과(far 290>250, §85 SSOT)면 missing 이 아니라 warn + 위반 목록.
    _patch_design(monkeypatch, mass=_MASS)  # far_pct 290 > 2R 한도 250
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000,
                             "zone_code": "제2종일반주거지역"}, use_llm=False)
    comp = next(c for c in out["checklist"] if c["step"] == "compliance")
    assert comp["status"] == "warn"
    assert comp["value"]["zone_code"] == "2R"
    assert "용적률 초과" in comp["value"]["violations"]


async def test_designer_unsupported_korean_zone_honest_missing(monkeypatch):
    # 단축코드가 없는 용도(자연녹지지역 등)는 None→missing 정직 고지(가짜 코드 금지·무목업).
    _patch_design(monkeypatch)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000,
                             "zone_code": "자연녹지지역"}, use_llm=False)
    comp = next(c for c in out["checklist"] if c["step"] == "compliance")
    assert comp["status"] == "missing"
    assert any("zone_code" in n or "용도지역" in n for n in out["honesty_notes"])


async def test_designer_compliance_missing_zone_honest(monkeypatch):
    # zone_code 미확보 → 법정 한도 비교 불가 → missing 정직 고지(과거: 무조건 pass 오판).
    _patch_design(monkeypatch)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000}, use_llm=False)
    comp = next(c for c in out["checklist"] if c["step"] == "compliance")
    assert comp["status"] == "missing"
    assert any("zone_code" in n or "용도지역" in n for n in out["honesty_notes"])


async def test_designer_threads_land_area_and_zone(monkeypatch):
    # [HIGH] 설계 퇴화 해소 — ctx.land_area_sqm/zone_code 가 compute_design_mass 요청에 전달되는지.
    captured: dict = {}

    async def _fake_mass(project_id, req):
        captured["land_area_sqm"] = req.land_area_sqm
        captured["zone_code"] = req.zone_code
        return dict(_MASS)

    class _FakeOptimizer:
        def optimize(self, inp):
            return dict(_UNIT_MIX)

    monkeypatch.setattr("app.routers.design_v61.compute_design_mass", _fake_mass)
    monkeypatch.setattr(
        "app.services.feasibility.unit_mix_optimizer.UnitMixOptimizer", _FakeOptimizer)
    cache._STORE.clear()
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1200, "zone_code": "2R"},
                            use_llm=False)
    assert captured["land_area_sqm"] == 1200.0
    assert captured["zone_code"] == "2R"
    # 폴백 매스 정직 고지가 없어야 한다(실치수 입력 경로).
    assert not any("폴백" in n for n in out["honesty_notes"])


async def test_designer_no_area_fallback_mass(monkeypatch):
    # land_area 없음 → 폴백 매스(정직 고지). 유닛믹스는 GFA 미산출로 missing.
    _patch_design(monkeypatch)
    out = await run_persona("designer", _FakeDB(), {"address": "어딘가"}, use_llm=False)
    assert any("폴백" in n or "GFA" in n for n in out["honesty_notes"])
    um = next(c for c in out["checklist"] if c["step"] == "unit_mix")
    assert um["status"] == "missing"            # 연면적 미산출 → 유닛믹스 보류


async def test_designer_pdf_renders(monkeypatch):
    _patch_design(monkeypatch)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000, "zone_code": "3R"},
                            use_llm=False)
    pdf, _mime, _ext = render_report(build_report_model_from_persona(out, "designer"), "pdf")
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF"


async def test_designer_expert_panel_design_lens(monkeypatch):
    seen = {"atype": None}

    class _FakePanel:
        async def analyze(self, atype, ctx, address="", mode="single"):
            seen["atype"] = atype
            return {"consensus": "design-ok", "experts": [], "roster": [], "mode": mode}

    _patch_design(monkeypatch, panel=_FakePanel)
    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000, "zone_code": "3R"},
                            use_llm=True)
    assert seen["atype"] == "design"            # design lens(강등 방지)
    assert out["verification"]["expert_panel"]["consensus"] == "design-ok"


class _FakeTruncatedResp:
    """DesignInterpreter의 fallback_key(design_overview) 하나에만 원문이 뭉치는 절단 JSON."""
    content = '{"design_overview": "설계 개요를 서술하던 중 max_tokens에 걸려 문장이 중간에서 짤'
    response_metadata = {"stop_reason": "max_tokens"}
    usage_metadata: dict = {}


class _FakeTruncatedLLM:
    model = "fake"

    async def ainvoke(self, messages, config=None):  # noqa: ARG002
        return _FakeTruncatedResp()


async def test_designer_llm_fallback_only_not_exposed(monkeypatch):
    """★재발 방지 앵커(R1 R2): design 인터프리터가 절단(fallback-only)으로 응답해도
    BaseInterpreter._invoke가 {}로 강등 → persona/runner.py의 "if isinstance(interp, dict)
    and interp:" 가드가 무수정으로 raw 원문을 artifacts에 노출하지 않는다(persona/runner.py:774
    소비처, R1이 무가드로 지적한 지점)."""
    from app.services.ai.design_interpreter import DesignInterpreter

    _patch_design(monkeypatch)
    monkeypatch.setattr(DesignInterpreter, "_get_llm", lambda self: _FakeTruncatedLLM(), raising=True)
    monkeypatch.setenv("INTERP_REDIS_CACHE", "0")

    out = await run_persona("designer", _FakeDB(),
                            {"address": "서울 강남", "land_area_sqm": 1000, "zone_code": "3R"},
                            use_llm=True)
    art = out["artifacts"]
    # 절단 응답이라도 raw 원문("짤"로 끝나는 미완성 문장)이 artifacts 어디에도 노출되지 않는다.
    assert "ai_interpretation" not in art or not art.get("ai_interpretation")
    assert "짤" not in str(art)


# ── 시공 ──

_EST = {
    "building_type": "apartment", "structure_type": "RC",
    "total_gfa_sqm": 30000, "gfa_above_sqm": 25000, "gfa_below_sqm": 5000,
    "unit_cost_per_sqm": 2_300_000, "total_won": 90_00000000, "per_pyeong_won": 7_600_000,
    "range": {"min_won": 82_00000000, "expected_won": 90_00000000, "max_won": 100_00000000},
    "items": [
        {"name": "레미콘", "quantity": 12000, "unit": "㎥", "cost_won": 15_00000000,
         "unit_cost_won": 125000, "price_source": "db"},
        {"name": "철근", "quantity": 3000, "unit": "ton", "cost_won": 18_00000000,
         "unit_cost_won": 600000, "price_source": "db"},
    ],
    "qto_source": "derived", "unit_price_source": "db",
    "note": "건축개요 기반 표준 추정",
}


def _patch_cost(monkeypatch, est=_EST):
    async def _fake_est(req, db):
        return dict(est)

    monkeypatch.setattr("app.routers.cost.estimate_overview", _fake_est)
    cache._STORE.clear()


async def test_constructor_live_confirmed_no_llm(monkeypatch):
    _patch_cost(monkeypatch)
    out = await run_persona("constructor", _FakeDB(),
                            {"address": "서울 강남", "total_gfa_sqm": 30000}, use_llm=False)
    assert out["persona_key"] == "constructor"
    art = out["artifacts"]
    assert art["interpreter_available"] is True
    by_step = {c["step"]: c["status"] for c in out["checklist"]}
    assert by_step["unit_cost"] == "pass"
    assert by_step["qto"] == "pass"             # unit_price_source == "db"
    # 레인지 폭 = (100-82)/90 = 20% ≤ 25 → pass
    assert by_step["cost_safety"] == "pass"
    assert out["billing"]["estimated_fee_krw"] == 0
    assert art["estimate"]["total_won"] == 90_00000000


async def test_constructor_threads_gfa_and_building_type(monkeypatch):
    # [CRITICAL] E2E 가능화 — ctx.total_gfa_sqm/building_type 가 estimate_overview 요청에 전달되는지.
    captured: dict = {}

    async def _fake_est(req, db):
        captured["total_gfa_sqm"] = req.total_gfa_sqm
        captured["building_type"] = req.building_type
        return dict(_EST)

    monkeypatch.setattr("app.routers.cost.estimate_overview", _fake_est)
    cache._STORE.clear()
    out = await run_persona("constructor", _FakeDB(),
                            {"address": "서울 강남", "total_gfa_sqm": 30000,
                             "building_type": "officetel"}, use_llm=False)
    assert captured["total_gfa_sqm"] == 30000.0
    assert captured["building_type"] == "officetel"
    assert out["status"] != "partial"            # GFA 확보 → partial 강등 없음


async def test_constructor_no_gfa_partial(monkeypatch):
    out = await run_persona("constructor", _FakeDB(), {"address": "어딘가"}, use_llm=False)
    assert out["status"] == "partial"
    assert any("연면적" in n for n in out["honesty_notes"])
    uc = next(c for c in out["checklist"] if c["step"] == "unit_cost")
    assert uc["status"] == "missing"


async def test_constructor_fallback_price_honesty(monkeypatch):
    est = dict(_EST)
    est["unit_price_source"] = "fallback"
    _patch_cost(monkeypatch, est)
    out = await run_persona("constructor", _FakeDB(),
                            {"address": "서울 강남", "total_gfa_sqm": 30000}, use_llm=False)
    assert any("fallback" in n for n in out["honesty_notes"])
    qto = next(c for c in out["checklist"] if c["step"] == "qto")
    assert qto["status"] == "warn"


async def test_constructor_pdf_renders(monkeypatch):
    _patch_cost(monkeypatch)
    out = await run_persona("constructor", _FakeDB(),
                            {"address": "서울 강남", "total_gfa_sqm": 30000}, use_llm=False)
    pdf, _mime, _ext = render_report(build_report_model_from_persona(out, "constructor"), "pdf")
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF"
