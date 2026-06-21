"""도시계획 페르소나 오케스트레이션 단위테스트(R9).

permit/regulation/development/special_parcel/expert_panel을 monkeypatch로 대체해,
서비스 폴백 조립·게이트(PASS/TENTATIVE/BLOCK)·잠정 강등(R12)·한도 분리(R12)·PDF 생성을
DB·외부API 없이 검증한다.
"""

from __future__ import annotations

from app.services.persona import cache, urban_report
from app.services.persona.runner import run_persona


class _FakeDB:
    async def execute(self, *a, **k):  # pragma: no cover
        raise AssertionError("DB 접근이 없어야 한다(address 직접 전달)")


def _patch_urban(monkeypatch, *, special=None, panel=None):
    """공통: permit/regulation/development 서비스를 가벼운 가짜로 대체."""
    class _FakePermit:
        async def analyze(self, address, parcels=None, use_llm=True):
            return {
                "summary": "강남 일반상업 — 주거·업무 가능",
                "site": {"zone_type": "일반상업지역", "max_far": 800, "legal_max_far": 800,
                         "max_bcr": 60, "land_area_sqm": 1000,
                         "special_parcel": special},
                "methods": [{"method": "주상복합", "score": 80,
                             "issues": ["용도용적제"], "solutions": ["지구단위계획"]}],
                "recommendation": "주상복합 권고",
            }

    class _FakeReg:
        async def analyze(self, address, pnu=None, use_llm=True):
            return {
                "zone_type": "일반상업지역", "land_area_sqm": 1000,
                "limits": {"far": {"legal": 800, "ordinance": 700, "effective": 700},
                           "bcr": {"legal": 60, "ordinance": 60, "effective": 60}},
                "hierarchy": [], "districts": [],
                "ai": {"strategies": ["지구단위계획 활용"], "opportunities": ["역세권 고밀"]},
            }

    monkeypatch.setattr(
        "app.services.permit.permit_analysis_service.PermitAnalysisService", _FakePermit)
    monkeypatch.setattr(
        "app.services.regulation.regulation_analysis_service.RegulationAnalysisService", _FakeReg)
    if panel is not None:
        monkeypatch.setattr(
            "app.services.expert_panel.expert_panel_service.ExpertPanelService", panel)
    cache._STORE.clear()


async def test_urban_single_pass(monkeypatch):
    _patch_urban(monkeypatch)  # special=None → 일상부지
    out = await run_persona("urban_planner", _FakeDB(),
                            {"address": "서울특별시 강남구 역삼동 123"}, use_llm=False)
    assert out["persona_key"] == "urban_planner"
    assert out["status"] == "confirmed"
    art = out["artifacts"]
    # interpreter 부재 정직 고지(R2)
    assert art["interpreter_available"] is False
    assert "interpreter" in art["interpreter_note"]
    # 한도 법정/조례/실효 분리(R12)
    assert art["zone_limits"]["far"] == {"legal": 800, "ordinance": 700, "effective": 700}
    # 개발방식 AHP 산출
    assert art["dev_methods"] and art["dev_methods"][0]["rank"] == 1
    # 인센티브 추출(규칙기반): '지구단위계획','역세권' 키워드
    assert any("지구단위" in i for i in art["incentives"])
    # 무과금
    assert out["billing"]["estimated_fee_krw"] == 0


async def test_urban_special_parcel_tentative(monkeypatch):
    # 게이트 강등: CONDITIONAL 해결가능성 → TENTATIVE
    special = {"developability": "CONDITIONAL", "resolvable": "CONDITIONAL",
               "honest_disclosure": "선행 협의 전제 잠정치"}
    _patch_urban(monkeypatch, special=special)
    out = await run_persona("urban_planner", _FakeDB(),
                            {"address": "어딘가"}, use_llm=False)
    assert out["status"] == "tentative"          # R12 잠정 강등
    zone = next(c for c in out["checklist"] if c["step"] == "zone")
    assert zone["status"] == "tentative"
    assert any("잠정" in n or "선행절차" in n for n in out["honesty_notes"])


async def test_urban_no_address_partial(monkeypatch):
    out = await run_persona("urban_planner", _FakeDB(), {}, use_llm=False)
    assert out["status"] == "partial"
    assert out["artifacts"]["interpreter_available"] is False
    assert any("주소" in n for n in out["honesty_notes"])


async def test_urban_pdf_renders(monkeypatch):
    _patch_urban(monkeypatch)
    out = await run_persona("urban_planner", _FakeDB(),
                            {"address": "서울특별시 강남구 역삼동 123"}, use_llm=False)
    pdf = urban_report.to_pdf(out)
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF"


async def test_urban_expert_panel_permit_lens(monkeypatch):
    seen = {"atype": None}

    class _FakePanel:
        async def analyze(self, atype, ctx, address="", mode="single"):
            seen["atype"] = atype
            return {"consensus": "permit-ok", "experts": [], "roster": [], "mode": mode}

    _patch_urban(monkeypatch, panel=_FakePanel)
    out = await run_persona("urban_planner", _FakeDB(),
                            {"address": "서울특별시 강남구 역삼동 123"}, use_llm=True)
    assert seen["atype"] == "permit"             # permit lens(R2)
    assert out["verification"]["expert_panel"]["consensus"] == "permit-ok"
