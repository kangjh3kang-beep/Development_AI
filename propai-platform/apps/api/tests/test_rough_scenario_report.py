"""개략수지 → 시니어 최종 사업성분석 보고서(요구 ⑨) 테스트.

검증:
 ① 개략수지 → FeasibilityInterpreter 입력 매핑(단일 추천·profit_rate 재구성·BLOCK 반영)
 ② 전문 IM 목차 순서(표지→Executive Summary→①~⑧)
 ③ use_llm=False 정직 폴백('AI 분석 미포함'·서술 섹션 생략)
 ④ use_llm=True 서술 포함(인터프리터 stub) · LLM 실패 시 정직 강등
 ⑤ degraded_notes 정직 노출(⑦ 리스크 섹션 체크리스트)
 ⑥ 투자의견 규칙(Go/조건부/보류/재검토)
 ⑦ ⑤개략수지 섹션 = bank_ready _build_feasibility 재사용
 ⑧ 금융·감정평가 시니어 자문 부착(자기자본비율 verdict)
 ⑨ PDF/DOCX 스모크 + 미지원 포맷 PDF 폴백
 라우터 스모크(scenario 직접·address 재생성·필수입력 422)

LLM·네트워크는 호출하지 않는다(use_llm=False 또는 인터프리터 stub). 시니어 자문은
결정론 코어(senior_orchestrator)라 실제로 돌려 검증한다. python-docx 미설치면 해당만 skip.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.feasibility import rough_scenario_report as rsr
from app.services.feasibility.rough_scenario_report import (
    build_rough_scenario_report_model,
    generate_rough_scenario_report,
    scenario_to_interpreter_input,
)
from app.services.report.render.model import ChecklistBlock, DataTableBlock


# ─────────────────────────────────────────────────────────────────────────────
# 공용 시나리오 픽스처
# ─────────────────────────────────────────────────────────────────────────────
def _scenario(**over) -> dict:
    """정상(actual) 개략수지 결과 표본(build_rough_scenario 계약)."""
    sc = {
        "address": "서울특별시 강남구 역삼동 736",
        "project_id": "abcd1234-ef56-7890",
        "scenario_status": "actual",
        "inputs": {
            "land_area_sqm": 1000.0, "zone_type": "제2종일반주거지역",
            "effective_far_pct": 200.0, "dev_type": "M06", "dev_type_name": "일반분양",
            "gfa_sqm": 2000.0, "saleable_area_pyeong": 423.5, "parcel_count": 1,
            "project_months": 30,
        },
        "land_cost": {
            "total_won": 5_000_000_000, "per_sqm_won": 5_000_000,
            "basis": "탁상감정 적정단가 5,000,000원/㎡ × 1,000㎡ + 취득세 등",
            "evidence": {"evidence": [{"label": "채택 단가", "value": "5,000,000원/㎡"}]},
            "source": "desk_appraisal(탁상감정)",
        },
        "construction_cost": {
            "total_won": 5_000_000_000, "unit_per_sqm_won": 2_500_000,
            "basis": "국토부 기본형건축비 직접공사비 + 간접비 15%", "source": "construction_cost_engine(국토부 SSOT)",
        },
        "revenue": {
            "total_won": 16_000_000_000, "sale_price_per_pyeong": 40_000_000,
            "saleable_area_pyeong": 423.5, "basis": "지역×유형 시장표준 시세 × 분양가능면적", "source": "지역 시세 테이블",
        },
        "cost_breakdown": {
            "land_won": 5_000_000_000, "construction_won": 5_000_000_000,
            "finance_won": 800_000_000, "other_won": 400_000_000,
        },
        "margin": {"developer_profit_won": 2_440_000_000, "rate_pct": 20.0, "target_revenue_won": 14_640_000_000},
        "summary": {
            "total_cost_won": 12_200_000_000, "total_revenue_won": 16_000_000_000,
            "net_profit_won": 3_800_000_000, "roi_pct": 31.1, "npv_won": 3_000_000_000,
            "irr_pct": 25.0, "payback_month": 28, "grade": "A",
        },
        "cashflow": {
            "monthly_rows": [
                {"month": m, "inflow": 0, "outflow": 100, "net": -100, "cumulative": -100 * (m + 1)}
                for m in range(30)
            ],
            "summary": {"peak_negative_cashflow": -3_000_000_000, "discount_rate_annual_pct": 6.0, "irr_annual_pct": 25.0},
        },
        "overrides_applied": [],
        "degraded_notes": [],
    }
    sc.update(over)
    return sc


def _unavailable_scenario() -> dict:
    """핵심 축 결측(산출 불가) 정직 강등 결과."""
    return {
        "address": "강원도 어딘가 산 1",
        "project_id": None,
        "scenario_status": "unavailable",
        "inputs": {
            "land_area_sqm": None, "zone_type": None, "effective_far_pct": None,
            "dev_type": None, "dev_type_name": None, "gfa_sqm": None,
            "saleable_area_pyeong": None, "parcel_count": 1, "project_months": None,
        },
        "land_cost": {"total_won": None, "per_sqm_won": None, "basis": None, "evidence": None, "source": None},
        "construction_cost": {"total_won": None, "unit_per_sqm_won": None, "basis": None, "source": None},
        "revenue": {"total_won": None, "sale_price_per_pyeong": None, "saleable_area_pyeong": None, "basis": None, "source": None},
        "cost_breakdown": {"land_won": None, "construction_won": None, "finance_won": None, "other_won": None},
        "margin": {"developer_profit_won": None, "rate_pct": 20.0, "target_revenue_won": None},
        "summary": {
            "total_cost_won": None, "total_revenue_won": None, "net_profit_won": None,
            "roi_pct": None, "npv_won": None, "irr_pct": None, "payback_month": None, "grade": None,
        },
        "cashflow": None,
        "overrides_applied": [],
        "degraded_notes": ["개발 가능한 사업모델이 없어 개략수지를 산출하지 않습니다(무목업)."],
    }


class _FakeInterp:
    """FeasibilityInterpreter stub — 실제 LLM 대신 8키 서술을 반환(네트워크 0)."""

    RESULT = {
        "overall_recommendation": "AI종합: 우수한 사업지로 추진 권고.",
        "top1_analysis": "AI1위: 일반분양 수익구조 견고.",
        "top2_analysis": "AI2위: 데이터 없음.",
        "top3_analysis": "AI3위: 데이터 없음.",
        "risk_assessment": "AI리스크: 분양률·금리 상승 주의.",
        "profit_optimization": "AI수익최적화: 유닛믹스 조정 검토.",
        "market_timing": "AI타이밍: 현 시장 진입 적정.",
        "financing_advice": "AI자금조달: 브릿지→본PF 전환 권장.",
    }

    async def generate_interpretation(self, recommend_data: dict) -> dict:
        return dict(self.RESULT)


def _sections_by_no(model) -> dict:
    return {s.section_no: s for s in model.sections}


# ─────────────────────────────────────────────────────────────────────────────
# ① 인터프리터 입력 매핑
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_to_interpreter_input_mapping():
    ii = scenario_to_interpreter_input(_scenario())
    assert ii["address"] == "서울특별시 강남구 역삼동 736"
    assert ii["zone_type"] == "제2종일반주거지역"
    assert ii["land_area_sqm"] == 1000.0
    assert ii["total_types_analyzed"] == 1  # 단일 확정안
    recs = ii["recommendations"]
    assert len(recs) == 1
    feas = recs[0]["feasibility"]
    assert recs[0]["development_type"] == "M06"
    assert feas["roi_pct"] == 31.1
    assert feas["grade"] == "A"
    # 수입기준 이익률(÷총분양수입)을 결정적으로 재구성(3,800/16,000 = 23.75 → 23.8)
    assert feas["profit_rate_pct"] == 23.8
    assert recs[0]["unit_summary"]["total_gfa_sqm"] == 2000.0


def test_interpreter_input_marks_block_when_unavailable():
    ii = scenario_to_interpreter_input(_unavailable_scenario())
    # 산출 불가(unavailable)면 인허가 불가(False)로 정직 표기 → 인터프리터가 낙관 금지.
    assert ii["recommendations"][0]["permit"]["is_permitted"] is False


# ─────────────────────────────────────────────────────────────────────────────
# ② 목차 순서
# ─────────────────────────────────────────────────────────────────────────────
def test_toc_order_and_section_titles():
    model = build_rough_scenario_report_model(_scenario())
    assert model.exec_summary is not None
    assert "Executive Summary" in model.exec_summary.title
    nos = [s.section_no for s in model.sections]
    assert nos == [1, 2, 3, 4, 5, 6, 7, 8]  # ①~⑧ 순서 고정
    titles = [s.title for s in model.sections]
    assert "사업 개요" in titles[0]
    assert "토지비" in titles[1]
    assert "공사비" in titles[2]
    assert "분양수입" in titles[3]
    assert "개략 사업수지" in titles[4]
    assert "현금흐름" in titles[5]
    assert "시니어 자문" in titles[6]
    assert "결론" in titles[7]


# ─────────────────────────────────────────────────────────────────────────────
# ③ use_llm=False 정직 폴백
# ─────────────────────────────────────────────────────────────────────────────
async def test_use_llm_false_honest_fallback():
    j = await generate_rough_scenario_report(_scenario(), use_llm=False, format="json")
    assert j["honesty"]["use_llm"] is False
    assert j["honesty"]["ai_included"] is False
    assert "AI 시니어 서술 미포함" in j["honesty"]["ai_note"]
    assert j["narrative"] == {}
    # AI 서술 섹션(시니어 종합의견·시장 타이밍 등)은 없어야 함 — exec 요약에 정직 고지 문구.
    exec_texts = [
        p for b in j["exec_summary"]["blocks"] if b.get("kind") == "narrative" for p in b.get("paragraphs", [])
    ]
    assert any("AI 시니어 서술 미포함" in t for t in exec_texts)


# ─────────────────────────────────────────────────────────────────────────────
# ④ use_llm=True 서술 포함 / LLM 실패 정직 강등
# ─────────────────────────────────────────────────────────────────────────────
async def test_use_llm_true_includes_senior_narrative(monkeypatch):
    monkeypatch.setattr(rsr, "FeasibilityInterpreter", _FakeInterp)
    j = await generate_rough_scenario_report(_scenario(), use_llm=True, format="json")
    assert j["honesty"]["ai_included"] is True
    assert j["honesty"]["ai_note"] == ""
    assert j["narrative"]["overall_recommendation"].startswith("AI종합")
    # Executive Summary에 '시니어 종합의견' 서술 포함
    exec_titles = [b.get("title") for b in j["exec_summary"]["blocks"] if b.get("kind") == "narrative"]
    assert "시니어 종합의견" in exec_titles
    # ⑦ 리스크 섹션에 AI 리스크 서술, ⑧ 결론에 타이밍/자금조달/수익최적화
    sec7 = next(s for s in j["sections"] if s["section_no"] == 7)
    assert any("AI리스크" in p for b in sec7["blocks"] if b.get("kind") == "narrative" for p in b.get("paragraphs", []))
    sec8 = next(s for s in j["sections"] if s["section_no"] == 8)
    sec8_titles = [b.get("title") for b in sec8["blocks"] if b.get("kind") == "narrative"]
    assert "시장 타이밍 · 진입 전략" in sec8_titles
    assert "자금조달(PF) 구조 제안" in sec8_titles


async def test_use_llm_true_llm_failure_degrades(monkeypatch):
    class _Boom:
        async def generate_interpretation(self, data):
            raise RuntimeError("LLM 연결 실패")

    monkeypatch.setattr(rsr, "FeasibilityInterpreter", _Boom)
    j = await generate_rough_scenario_report(_scenario(), use_llm=True, format="json")
    # 실패해도 보고서는 생성되고, 정직하게 미포함 표기
    assert j["honesty"]["ai_included"] is False
    assert "실패" in j["honesty"]["ai_note"]
    assert j["narrative"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ degraded_notes 정직 노출
# ─────────────────────────────────────────────────────────────────────────────
def test_degraded_notes_surfaced_in_risk_section():
    note = "분양단가: 주변 실거래 미연동 — 전국 기본값 폴백(참고용)."
    model = build_rough_scenario_report_model(_scenario(degraded_notes=[note]))
    sec7 = _sections_by_no(model)[7]
    checklists = [b for b in sec7.blocks if isinstance(b, ChecklistBlock)]
    assert checklists, "degraded_notes가 ⑦ 리스크 섹션에 체크리스트로 노출돼야 함"
    labels = [lbl for cl in checklists for (lbl, _st) in cl.items]
    assert note in labels


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ 투자의견 규칙
# ─────────────────────────────────────────────────────────────────────────────
def test_investment_opinion_go_when_clean_grade_a():
    # 등급 A + 결측 없음 + 시니어 PASS(자기자본비율) → Go
    label, _ = rsr._investment_opinion(_scenario(), {"verdict": "PASS"})
    assert label == "Go(추진 권고)"


def test_investment_opinion_conditional_when_degraded():
    label, _ = rsr._investment_opinion(_scenario(degraded_notes=["폴백"]), {"verdict": "PASS"})
    assert label == "조건부 Go"


def test_investment_opinion_block_verdict_holds():
    label, _ = rsr._investment_opinion(_scenario(), {"verdict": "BLOCK"})
    assert label == "보류"


def test_investment_opinion_review_when_core_missing():
    label, _ = rsr._investment_opinion(_unavailable_scenario(), {"verdict": "unavailable"})
    assert label == "재검토"


def test_investment_opinion_hold_when_grade_f():
    sc = _scenario()
    sc["summary"]["grade"] = "F"
    sc["summary"]["roi_pct"] = -5.0
    label, _ = rsr._investment_opinion(sc, {"verdict": "PASS"})
    assert label == "보류"


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ ⑤개략수지 섹션 = bank_ready _build_feasibility 재사용
# ─────────────────────────────────────────────────────────────────────────────
def test_feasibility_section_reuses_bank_builder():
    model = build_rough_scenario_report_model(_scenario())
    sec5 = _sections_by_no(model)[5]
    # KV표에 bank _build_feasibility content(한글 라벨)와 마진 필드가 있어야 함(★HIGH-3).
    kv = next(b for b in sec5.blocks if getattr(b, "kind", None) == "kv")
    labels = [r[0] for r in kv.rows]
    # ★HIGH-3: 영문 dict 키가 사용자 라벨로 그대로 노출되면 안 됨 → 한글 라벨로 변환.
    assert "ROI(총사업비 대비, %)" in labels
    assert "사업성 등급" in labels
    assert "수입기준 이익률(%)" in labels
    assert "roi_pct" not in labels and "grade" not in labels and "profit_rate_pct" not in labels
    assert any("개발이익" in lbl for lbl in labels)
    # 총사업비 구성 표(토지/공사/금융/제경비+합계)
    tables = [b for b in sec5.blocks if isinstance(b, DataTableBlock)]
    assert tables and tables[0].total_row is True
    assert len(tables[0].rows) == 5


# ─────────────────────────────────────────────────────────────────────────────
# ⑧ 금융·감정평가 시니어 자문 부착(결정론 코어 실행)
# ─────────────────────────────────────────────────────────────────────────────
async def test_senior_consultation_attached_with_equity():
    j = await generate_rough_scenario_report(
        _scenario(), use_llm=False, format="json", equity_won=10_000_000_000
    )
    consult = j["senior_consultation"]
    # 금융·감정평가 두 도메인 자문이 붙는다.
    names = [c.get("name_ko") for c in consult.get("consultations", [])]
    assert any("금융" in (n or "") for n in names)
    assert any("감정평가" in (n or "") for n in names)
    # 자기자본 100억/총사업비 122억 = 82% → 자기자본비율 PASS(어떤 연도 기준에도 충족)
    assert consult["verdict"] == "PASS"
    fin = next(c for c in consult["consultations"] if "금융" in (c.get("name_ko") or ""))
    fin_labels = [e.get("label") for e in fin.get("evaluations", [])]
    assert any("자기자본비율" in (lbl or "") for lbl in fin_labels)


# ─────────────────────────────────────────────────────────────────────────────
# ⑨ 렌더 스모크(PDF/DOCX) + 폴백
# ─────────────────────────────────────────────────────────────────────────────
async def test_pdf_render_smoke():
    data, mime, ext = await generate_rough_scenario_report(_scenario(), use_llm=False, format="pdf")
    assert ext == "pdf" and mime == "application/pdf"
    assert data[:4] == b"%PDF" and len(data) > 2000


async def test_unavailable_scenario_still_renders_pdf():
    data, mime, ext = await generate_rough_scenario_report(_unavailable_scenario(), use_llm=False, format="pdf")
    assert data[:4] == b"%PDF" and len(data) > 1000  # 산출 불가여도 정직 보고서 생성


async def test_docx_render_smoke():
    pytest.importorskip("docx")  # python-docx 미설치면 skip
    data, mime, ext = await generate_rough_scenario_report(_scenario(), use_llm=False, format="docx")
    assert ext == "docx" and data[:4] == b"PK\x03\x04"


async def test_unknown_format_falls_back_to_pdf():
    data, mime, ext = await generate_rough_scenario_report(_scenario(), use_llm=False, format="xlsx")
    assert ext == "pdf" and data[:4] == b"%PDF"


# ─────────────────────────────────────────────────────────────────────────────
# 라우터 스모크
# ─────────────────────────────────────────────────────────────────────────────
def _client(monkeypatch, fake_scenario=None):
    from app.core.database import get_db
    from app.routers import v2_feasibility

    if fake_scenario is not None:
        async def _fake_build(**kwargs):
            fake_scenario["_regen_kwargs"] = kwargs
            return fake_scenario

        monkeypatch.setattr(v2_feasibility, "build_rough_scenario", _fake_build)

    app = FastAPI()
    app.include_router(v2_feasibility.router)

    async def _odb():
        yield None

    app.dependency_overrides[get_db] = _odb
    return TestClient(app)


def test_router_report_json_with_scenario(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/v2/feasibility/rough-scenario/report", json={
        "scenario": _scenario(), "use_llm": False, "format": "json", "equity_won": 10_000_000_000,
    })
    assert resp.status_code == 200
    d = resp.json()
    assert d["toc"][0].startswith("Executive Summary")
    assert d["investment_opinion"]["label"] == "Go(추진 권고)"
    assert d["honesty"]["ai_included"] is False


def test_router_report_pdf_with_scenario(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/v2/feasibility/rough-scenario/report", json={
        "scenario": _scenario(), "use_llm": False, "format": "pdf",
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
    assert "rough_scenario_report.pdf" in resp.headers.get("content-disposition", "")


def test_router_report_regenerates_from_address(monkeypatch):
    client = _client(monkeypatch, fake_scenario=_scenario())
    resp = client.post("/api/v2/feasibility/rough-scenario/report", json={
        "address": "서울특별시 강남구 역삼동 736", "region": "서울", "use_llm": False, "format": "json",
    })
    assert resp.status_code == 200
    assert resp.json()["toc"][0].startswith("Executive Summary")


def test_router_report_requires_scenario_or_address(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/api/v2/feasibility/rough-scenario/report", json={
        "use_llm": False, "format": "json",
    })
    assert resp.status_code == 422
    assert "scenario 또는 address" in resp.json()["detail"]
