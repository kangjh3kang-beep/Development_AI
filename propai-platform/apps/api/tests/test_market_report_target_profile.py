"""시장조사보고서 보강 단위테스트 — 타겟 프로파일(K-Atlas 대체)·시니어 정밀분석·보고서 스토리라인.

검증 축:
  A. target_profile 5축 조립(주력연령·주력가구·소득분위·상권·입지) + 각 축 data_source 정직 강등.
  B. Executive Summary(등급·KPI·투자의견) 결정론 산출.
  C. 시니어 정밀분석 배선 — MarketInterpreter market_data 매핑(실거래·공시지가·적정분양가·실효FAR)
     + prior_context 근거 조립, 무키({}) 시 None 폴백(정직).
  D. _attach_senior 다전문가(appraisal·urban·finance) 라우팅 + 실값 inputs 주입.
  E. 상권(SEMAS) 신규 배선 — analyze_commercial_area 재사용·미확보 정직 강등.
  F. 보고서 스토리라인 — Exec Summary 두괄식 + 표준 목차 순서(적정분양가 < 사업타당성) + 무목업.

python-pptx/docx 미설치 환경은 importorskip 으로 skip 허용. reportlab PDF는 생성 스모크.
"""
from __future__ import annotations

import io

import pytest

from app.services.market.market_report_service import (
    MarketReportService,
    _build_target_profile,
    _exec_summary,
    _income_tier_label,
    _insight_text,
    _investment_opinion,
    _market_strength,
    _roi_grade,
)


# ── 픽스처: 라이브(전 축 실데이터) / 미확보(전 축 강등) rep ──────────────────

def _live_demographics() -> dict:
    """DemographicProfile.model_dump() 구조 — migration/population/macro_income 최상위(실제 계약)."""
    return {
        "source_phase": 1,
        "migration": {"data_source": "live", "net_migration": 1300,
                      "total_inflow": 12500, "total_outflow": 11200},
        "population": {
            "data_source": "live",
            "total_population": 45000, "household_count": 18000, "avg_household_size": 2.5,
            "age_distribution": {"20-29": 100, "30-39": 320, "40-49": 210},
            "household_types": {"1_person": 45.0, "2_person": 30.0, "3_person": 15.0, "4_over": 10.0},
        },
        "macro_income": {"data_source": "live", "avg_income_10k": 4800, "median_income_10k": 4080},
    }


def _commercial_live() -> dict:
    return {
        "total_stores": 820,
        "category_distribution": [{"category": "음식", "count": 300}, {"category": "소매", "count": 220}],
        "vitality_score": 72,
        "grade": "B",
    }


def _infra_live() -> dict:
    return {"nearest_subway": {"name": "역삼역", "distance_m": 320},
            "schools": [{"name": "A초"}, {"name": "B중"}]}


def _full_rep() -> dict:
    """전 축 라이브 rep(렌더러/Exec Summary용)."""
    return {
        "address": "서울 <강남> 역삼", "generated_at": "2026-07-09 09:00",
        "months": ["202604", "202605", "202606"], "coordinates": {},
        "zone_type": "일반상업지역", "official_price_per_sqm": 25000000,
        "trade": {"아파트": {"count": 120, "avg": 92000, "min": 60000, "max": 150000,
                            "avg_area_m2": 84.9, "per_pyeong": {"avg": 3200}}},
        "rent": {"아파트": {"count": 40, "avg": 45000, "min": 20000, "max": 90000}},
        "apt_trend": [{"ym": "202604", "avg_per_pyeong": 3100}, {"ym": "202605", "avg_per_pyeong": 3150},
                      {"ym": "202606", "avg_per_pyeong": 3200}],
        "narrative": {"summary": "인라인 요약", "opportunities": ["기회 1"], "risks": ["리스크 1"],
                      "price_trend": "상승", "target_persona": "30대"},
        "senior_insight": {"market_overview": "전용 시장개요.", "price_trend_analysis": "가격추이.",
                           "comparable_analysis": "비교.", "investment_insight": "투자 시사점.",
                           "risk_factors": "리스크 정밀.", "timing_recommendation": "매수 적기."},
        "feasibility_analysis": {"financials": {"roi_percent": 14.5, "total_cost_10k": 5000000,
                                                "total_revenue_10k": 6200000, "net_profit_10k": 1200000,
                                                "npv_10k": 800000},
                                 "massing": {"land_area_sqm": 1000, "gfa_sqm": 2500, "gfa_pyeong": 756,
                                             "estimated_far": 250, "estimated_bca": 60},
                                 "assumptions": {"note": "개략"}},
        "pricing_band": {"data_source": "live", "fair_price_10k": 92000,
                         "affordability_verdict": "within_optimistic", "note": "적정"},
        "unit_mix_recommendation": {"data_source": "live", "recommended_mix": {"59㎡": 40, "84㎡": 60},
                                    "dominant_band": "84㎡", "rationale": "수요"},
        "target_profile": _build_target_profile(_live_demographics(), _commercial_live(), "live", _infra_live()),
        "raw_data": {
            "real_estate": {"source": "국토교통부 실거래가", "data_source": "live",
                            "trend_series": [{"per_pyeong_manwon": 3200, "mom_pct": 1.6, "ym": "202606"}],
                            "trade_table": [{"type": "아파트", "count": 120, "per_pyeong_manwon": 3200,
                                             "avg_10k": 92000, "avg_area_m2": 84.9}],
                            "rent_table": [{"type": "아파트", "count": 40, "avg_10k": 45000,
                                            "min_10k": 20000, "max_10k": 90000}]},
            "population": {"data_source": "live",
                           # ★migration_data_source: _build_population_block이 생산하는 실제 계약 필드.
                           #   exec_summary는 이 출처를 게이트해 미확보('0명') 가짜표기를 막는다(무목업).
                           "migration_data_source": "live",
                           "summary": {"total_population": 45000, "household_count": 18000, "avg_household_size": 2.5},
                           "age_distribution": [{"label": "30-39", "count": 320}],
                           "household_types": [{"label": "1인", "ratio": 45.0}],
                           "migration": {"net_migration": 1300, "total_inflow": 12500, "total_outflow": 11200},
                           "source": "통계청"},
            "income": {"data_source": "live", "avg_income_10k": 4800, "median_income_10k": 4080,
                       "median_estimated": True, "source": "국세청"}},
    }


def _degraded_rep() -> dict:
    """전 축 미확보 rep(use_llm=False·무키). 무목업 정직 강등 검증용."""
    return {
        "address": "서울 강남", "generated_at": "2026-07-09", "months": ["202606"], "coordinates": {},
        "zone_type": None, "official_price_per_sqm": None,
        "trade": {}, "rent": {}, "apt_trend": [],
        "narrative": {"summary": "(AI 분석 미포함)", "opportunities": [], "risks": [],
                      "price_trend": "", "target_persona": "AI 분석 미포함"},
        "senior_insight": None,
        "feasibility_analysis": {"error": "용도지역 미확인"},
        "pricing_band": {"data_source": "unavailable", "note": "비교 데이터 없음"},
        "unit_mix_recommendation": {"data_source": "unavailable"},
        "target_profile": _build_target_profile({}, None, "unavailable", {}),
        "raw_data": {"real_estate": {"source": "국토교통부 실거래가", "data_source": "live", "trend_series": []}},
    }


# ── A. target_profile 5축 ────────────────────────────────────────────────

def test_target_profile_five_axes_live():
    tp = _build_target_profile(_live_demographics(), _commercial_live(), "live", _infra_live())
    assert tp["primary_age"]["band"] == "30-39"           # 최빈 연령대
    assert tp["primary_household"]["type"] == "1인 가구"   # 최빈 가구
    assert tp["primary_household"]["estimated"] is True    # SGIS 미제공 추정 명시
    assert tp["income_tier"]["tier_label"] == "중상위 소득권(추정)"
    assert tp["commercial"]["data_source"] == "live" and tp["commercial"]["grade"] == "B"
    assert tp["location"]["nearest_subway"] == "역삼역" and tp["location"]["school_count"] == 2
    # K-Atlas 신용·카드소비는 PREMIUM 제휴 예정으로 정직 강등
    assert tp["premium"]["credit_score"]["status"] == "PREMIUM 제휴 예정"
    assert tp["premium"]["card_spending"]["data_source"] == "unavailable"


def test_target_profile_degrade_when_unavailable():
    tp = _build_target_profile({}, None, "unavailable", {})
    for axis in ("primary_age", "primary_household", "income_tier", "commercial", "location"):
        assert tp[axis]["data_source"] == "unavailable", axis
    # 상권 미확보는 note 로 사유 정직 표기
    assert "상권" in tp["commercial"]["note"]


def test_income_tier_label_bands():
    assert _income_tier_label(2500) == "중하위 소득권(추정)"
    assert _income_tier_label(3500) == "중위 소득권(추정)"
    assert _income_tier_label(4800) == "중상위 소득권(추정)"
    assert _income_tier_label(7000) == "상위 소득권(추정)"
    assert _income_tier_label(None) is None
    assert _income_tier_label(0) is None


# ── B. Executive Summary ─────────────────────────────────────────────────

def test_exec_summary_grades_and_opinion():
    es = _exec_summary(_full_rep())
    assert es["business_grade"]["grade"] == "B"          # ROI 14.5 → 양호(B)
    assert es["market_strength"]["grade"] == "강세"       # 순유입>0 + 상승추세
    assert es["kpi"]["apt_per_pyeong_manwon"] == 3200
    assert es["kpi"]["net_migration"] == 1300
    assert es["kpi"]["fair_price_10k"] == 92000
    assert es["kpi"]["roi_percent"] == 14.5
    assert es["opinion"].startswith("Go")
    assert es["expert_opinion"] == "투자 시사점."          # senior_insight 병기


def test_exec_summary_degraded_honest():
    es = _exec_summary(_degraded_rep())
    assert es["business_grade"]["grade"] == "-"           # 수지 없음
    assert es["kpi"]["fair_price_10k"] is None            # 적정분양가 미확보
    assert "재검토" in es["opinion"]
    assert es["expert_opinion"] is None


# ── 무목업 회귀 방어(적대리뷰 CRITICAL·HIGH) ──

def test_has_source_rejects_mock():
    """★무목업: 'mock'(무키 시 반환되는 가짜값)은 미확보로 취급해야 한다."""
    from app.services.market.market_report_service import _has_source
    assert _has_source("mock") is False
    assert _has_source("unavailable") is False
    assert _has_source("") is False
    assert _has_source("live") is True
    assert _has_source("fallback") is True   # 전국 평균 근사(공개 고지)는 유지


def test_target_profile_drops_mock_income():
    """KOSIS 무키(mock 소득)면 income_tier 축은 노출 안 되고 unavailable(가짜 4,620만원 차단)."""
    from app.services.market.market_report_service import _build_target_profile
    tp = _build_target_profile(
        {"macro_income": {"data_source": "mock", "avg_income_10k": 4620}}, None, "unavailable", {})
    it = tp["income_tier"]
    assert it.get("value") is None and it["data_source"] == "unavailable"


def test_exec_summary_net_migration_unavailable_gated():
    """순이동 미확보(0/unavailable)면 KPI에 가짜 '0명'·근거없는 시장강도 등급이 안 나와야 한다."""
    rep = {
        "raw_data": {"population": {
            "migration_data_source": "unavailable",
            "migration": {"net_migration": 0},  # unavailable이 0으로 채운 값
        }},
    }
    es = _exec_summary(rep)
    assert es["kpi"]["net_migration"] is None          # 가짜 0 미표시
    assert es["market_strength"]["grade"] == "-"       # 근거 없으면 등급 억제


def test_roi_grade_and_market_strength_and_opinion():
    assert _roi_grade(25)[0] == "A"
    assert _roi_grade(-3)[0] == "D"
    assert _roi_grade(None) == ("-", "데이터 없음")
    assert _market_strength(-500, [{"mom_pct": -1.0}])[0] == "약세"
    assert _market_strength(None, None)[0] == "-"
    assert _investment_opinion(15, "within_conservative").startswith("Go")
    assert "지불여력 초과" in _investment_opinion(5, "over_band")
    assert _investment_opinion(None, None).startswith("재검토")


def test_insight_text_fallback_precedence():
    rep = {"narrative": {"summary": "인라인"}}
    assert _insight_text(rep, "market_overview", "summary") == "인라인"     # senior 없음 → 인라인
    rep["senior_insight"] = {"market_overview": "전용"}
    assert _insight_text(rep, "market_overview", "summary") == "전용"       # senior 우선
    assert _insight_text({}, "market_overview") is None                     # 둘 다 없음 → None


# ── C. 시니어 정밀분석(MarketInterpreter) 배선 ─────────────────────────────

async def test_senior_market_insight_maps_market_data(monkeypatch):
    captured: dict = {}

    async def fake_gen(self, market_data, *, prior_context=None):
        captured["market_data"] = market_data
        captured["prior_context"] = prior_context
        return {"market_overview": "o", "price_trend_analysis": "p", "comparable_analysis": "c",
                "investment_insight": "i", "risk_factors": "r", "timing_recommendation": "t"}

    monkeypatch.setattr(
        "app.services.ai.market_interpreter.MarketInterpreter.generate_interpretation", fake_gen)

    svc = MarketReportService.__new__(MarketReportService)
    insight = await svc._senior_market_insight(
        address="서울 강남", zone_type="일반상업지역", land_area_sqm=1000.0,
        stats_trade={"아파트": {"count": 120, "avg": 92000, "min": 60000, "max": 150000}},
        official_price=25000000,
        pricing_band={"data_source": "live", "fair_price_10k": 92000, "affordability_verdict": "within_optimistic"},
        unit_mix={"data_source": "live", "recommended_mix": {"84㎡": 60}, "dominant_band": "84㎡"},
        demographics=_live_demographics(),
        feasibility={"financials": {"roi_percent": 14.5, "total_cost_10k": 5000000, "npv_10k": 800000},
                     "massing": {"estimated_far": 250, "estimated_bca": 60}},
    )
    assert insight and insight["investment_insight"] == "i"
    md = captured["market_data"]
    # 실거래 → transaction_prices(avg/max/min = 만원)
    assert md["transaction_prices"]["아파트"]["avg_price_10k"] == 92000
    assert md["transaction_prices"]["아파트"]["max_price_10k"] == 150000
    # 공시지가 → land_prices
    assert md["land_prices"]["official_price_per_sqm"] == 25000000
    # 적정분양가(84㎡ 총액) → sale_prices(평당 환산)
    assert md["sale_prices"] and md["sale_prices"][0]["sale_price_per_pyeong_man"] > 0
    # 실효 용적률 → effective_far
    assert md["effective_far"]["effective_far_pct"] == 250
    # prior_context 에 인구·수급·사업성 근거 주입
    assert "순유입" in captured["prior_context"]
    assert "적정 분양가" in captured["prior_context"]
    assert "ROI" in captured["prior_context"]


async def test_senior_market_insight_none_when_no_key(monkeypatch):
    """무키/파싱실패 시 인터프리터가 {} 반환 → None(정직 폴백)."""
    async def fake_empty(self, market_data, *, prior_context=None):
        return {}

    monkeypatch.setattr(
        "app.services.ai.market_interpreter.MarketInterpreter.generate_interpretation", fake_empty)
    svc = MarketReportService.__new__(MarketReportService)
    insight = await svc._senior_market_insight(
        address="a", zone_type="z", land_area_sqm=1000.0, stats_trade={},
        official_price=None, pricing_band=None, unit_mix=None, demographics=None, feasibility=None)
    assert insight is None


def test_senior_prior_context_builds_and_none():
    ctx = MarketReportService._senior_prior_context(
        _live_demographics(),
        {"financials": {"roi_percent": 14.5, "total_cost_10k": 5000000, "npv_10k": 800000}},
        {"data_source": "live", "fair_price_10k": 92000, "affordability_verdict": "within_optimistic"},
        {"data_source": "live", "recommended_mix": {"84㎡": 60}, "dominant_band": "84㎡"})
    assert ctx is not None
    assert "순유입" in ctx and "주력 연령대" in ctx and "적정 분양가" in ctx
    # 근거 전무 → None(정직)
    assert MarketReportService._senior_prior_context(None, None, None, None) is None


# ── D. _attach_senior 다전문가 라우팅 + 실값 주입 ──────────────────────────

def test_attach_senior_multi_domains_and_inputs(monkeypatch):
    captured: dict = {}

    def fake_multi(domains, inputs=None, result=None):
        captured["domains"] = domains
        captured["inputs"] = inputs
        return {"verdict": None, "evaluations": [], "consultations": []}

    monkeypatch.setattr(
        "app.services.senior_agents.consultation_hook.attach_senior_consultation_multi", fake_multi)

    rep: dict = {}
    MarketReportService._attach_senior(
        rep, {"financials": {"total_cost_10k": 5000000}},
        official_price=25000000, land_area_sqm=1000.0, zone_type="일반상업지역", real_pp=3200.0)
    assert captured["domains"] == ["appraisal", "urban", "finance"]
    inp = captured["inputs"]
    assert inp["total_cost"] == 5000000 * 10000.0             # 만원→원
    assert inp["land_appraised_total"] == 25000000 * 1000.0   # 공시지가×면적(원)
    assert inp["zone_type"] == "일반상업지역"
    assert inp["land_area_sqm"] == 1000.0
    assert inp["comparable_price_per_pyeong_10k"] == 3200.0
    assert "senior_consultation" in rep


def test_attach_senior_graceful_when_hook_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("engine down")

    monkeypatch.setattr(
        "app.services.senior_agents.consultation_hook.attach_senior_consultation_multi", boom)
    rep: dict = {}
    # 절대 raise 안 함(무회귀). senior_consultation 키는 미부착(graceful).
    MarketReportService._attach_senior(rep, None, official_price=None, land_area_sqm=None)
    assert "senior_consultation" not in rep


# ── E. 상권(SEMAS) 신규 배선 ──────────────────────────────────────────────

async def test_commercial_area_live_and_unavailable(monkeypatch):
    async def fake_analyze(self, lat, lon, radius_m=500):
        assert radius_m == 500
        return _commercial_live()

    monkeypatch.setattr(
        "app.services.external_api.commercial_area_service.CommercialAreaService.analyze_commercial_area",
        fake_analyze)
    svc = MarketReportService.__new__(MarketReportService)
    res, src = await svc._commercial_area({"lat": 37.5, "lon": 127.0})
    assert src == "live" and res["grade"] == "B"
    # 좌표 부재 → 정직 미확보(호출 자체 안 함)
    res2, src2 = await svc._commercial_area({})
    assert res2 is None and src2 == "unavailable"


async def test_commercial_area_graceful_on_error(monkeypatch):
    async def boom(self, lat, lon, radius_m=500):
        raise RuntimeError("SEMAS down")

    monkeypatch.setattr(
        "app.services.external_api.commercial_area_service.CommercialAreaService.analyze_commercial_area", boom)
    svc = MarketReportService.__new__(MarketReportService)
    res, src = await svc._commercial_area({"lat": 37.5, "lon": 127.0})
    assert res is None and src == "unavailable"


# ── F. 보고서 스토리라인·목차 정합 ──────────────────────────────────────────

def test_pdf_smoke_full_and_degraded():
    pytest.importorskip("reportlab")
    svc = MarketReportService.__new__(MarketReportService)
    for rep in (_full_rep(), _degraded_rep()):
        pdf = svc.to_pdf(rep)
        assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_docx_section_order_and_exec_summary():
    docx = pytest.importorskip("docx")
    svc = MarketReportService.__new__(MarketReportService)
    b = svc.to_docx(_full_rep())
    assert b[:2] == b"PK"
    d = docx.Document(io.BytesIO(b))
    texts = [p.text for p in d.paragraphs]
    joined = "\n".join(texts)
    # Exec Summary 두괄식(첫 콘텐츠 섹션)
    assert "핵심 요약 (Executive Summary)" in joined
    # 표준 목차 8개 메인 섹션이 순서대로 등장
    order = ["핵심 요약 (Executive Summary)", "1. 시장 개요", "2. 수요 분석", "3. 가격·실거래",
             "4. 입지 분석", "5. 사업 타당성", "6. 리스크", "7. 결론", "8. 부록"]
    idxs = [joined.index(s) for s in order]
    assert idxs == sorted(idxs), f"목차 순서 어긋남: {idxs}"
    # ★인과 정합: 적정 분양가(매출)가 사업 타당성 앞
    assert joined.index("적정 분양가") < joined.index("사업 타당성")
    # 시니어 정밀 내러티브가 섹션에 주입됨(표만→해석)
    assert "전용 시장개요." in joined


def test_docx_degraded_honest_no_mockup():
    docx = pytest.importorskip("docx")
    svc = MarketReportService.__new__(MarketReportService)
    b = svc.to_docx(_degraded_rep())
    d = docx.Document(io.BytesIO(b))
    joined = "\n".join(p.text for p in d.paragraphs)
    # 무목업: 미확보 축은 정직 표기(가짜 수치 없음)
    assert "인구 데이터 없음" in joined
    assert "상권(SEMAS) 데이터 미확보" in joined
    assert "개략 수지 산출 불가" in joined
    # AI 미포함 시 정직 안내(senior_insight None·narrative 빈값)
    assert "AI 분석 미포함" in joined


# ── G. build_report 엔드투엔드 배선(외부 협력자 monkeypatch) ─────────────────

async def test_build_report_end_to_end_wiring(monkeypatch):
    """build_report 가 target_profile·senior_insight·senior_consultation 를 실제로 조립하고
    렌더러가 동작하는지(호출부 배선 무결) 검증. 외부 네트워크는 결정론 stub."""
    svc = MarketReportService()

    async def fake_cat(self, lawd_cd):
        return {"months": ["202606"],
                "trade": {"아파트": {"count": 120, "avg": 92000, "min": 60000, "max": 150000,
                                    "avg_area_m2": 84.9, "per_pyeong": {"avg": 3200}}},
                "rent": {}, "apt_trend": [{"ym": "202606", "avg_per_pyeong": 3200, "avg": 92000, "count": 120}]}

    async def fake_comp(self, address, pnu=None):
        return {"coordinates": {"lat": 37.5, "lon": 127.0},
                "land_register": {"land_area": 1000},
                "local_ordinance": {"zone_type": "일반상업지역"},
                "official_prices": [{"price_per_sqm": 25000000}],
                "infrastructure": {"nearest_subway": {"name": "역삼역", "distance_m": 300},
                                   "schools": [{"name": "A초"}]}}

    async def fake_comm(self, coords):
        return (_commercial_live(), "live")

    async def fake_presale(self, lawd_cd, coords):
        return (None, "unavailable")

    async def fake_narr(self, ctx):
        # ctx 보강 검증: 적정분양가·수요MD·타겟프로파일이 인라인 내러티브에도 흐르는지.
        assert "pricing_band" in ctx and "unit_mix_recommendation" in ctx and "target_profile" in ctx
        return {"summary": "요약", "opportunities": ["o"], "risks": ["r"],
                "price_trend": "t", "target_persona": "p"}

    async def fake_senior(self, **kw):
        return {"market_overview": "SI개요", "price_trend_analysis": "p", "comparable_analysis": "c",
                "investment_insight": "i", "risk_factors": "r", "timing_recommendation": "t"}

    monkeypatch.setattr(MarketReportService, "_category_stats", fake_cat)
    monkeypatch.setattr(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive", fake_comp)
    monkeypatch.setattr(MarketReportService, "_commercial_area", fake_comm)
    monkeypatch.setattr(MarketReportService, "_nearby_presale_84_price", fake_presale)
    monkeypatch.setattr(MarketReportService, "_narrative", fake_narr)
    monkeypatch.setattr(MarketReportService, "_senior_market_insight", fake_senior)

    rep = await svc.build_report("서울 강남구 역삼동", "11680", use_llm=True)

    # 과제1: target_profile 5축(상권·입지 라이브·데모그래픽 미선택은 강등)
    tp = rep["target_profile"]
    assert tp["commercial"]["data_source"] == "live" and tp["commercial"]["grade"] == "B"
    assert tp["location"]["nearest_subway"] == "역삼역"
    assert tp["primary_age"]["data_source"] == "unavailable"   # 인구 미선택 → 정직 강등
    assert tp["premium"]["credit_score"]["status"] == "PREMIUM 제휴 예정"
    # 과제2: 시니어 정밀 내러티브 + 다전문가 자문 첨부
    assert rep["senior_insight"]["investment_insight"] == "i"
    assert "senior_consultation" in rep                        # appraisal·urban·finance 자문
    # feasibility·pricing_band 은 실제 산출(재사용)
    assert rep["feasibility_analysis"]["financials"]["roi_percent"] is not None
    # 렌더러 스모크(배선 무결)
    assert svc.to_pdf(rep)[:4] == b"%PDF"


async def test_build_report_no_llm_senior_insight_none(monkeypatch):
    """use_llm=False면 senior_insight=None(정직)·target_profile 은 여전히 조립(실데이터 축)."""
    svc = MarketReportService()

    async def fake_cat(self, lawd_cd):
        return {"months": ["202606"], "trade": {}, "rent": {}, "apt_trend": []}

    async def fake_comp(self, address, pnu=None):
        return {"coordinates": {"lat": 37.5, "lon": 127.0}, "land_register": {"land_area": 1000},
                "local_ordinance": {"zone_type": "일반상업지역"}, "official_prices": [{"price_per_sqm": 25000000}],
                "infrastructure": {}}

    async def fake_comm(self, coords):
        return (_commercial_live(), "live")

    async def fake_presale(self, lawd_cd, coords):
        return (None, "unavailable")

    def _boom_senior(*a, **k):  # senior_insight 는 use_llm=False 경로에서 호출되면 안 됨
        raise AssertionError("use_llm=False 인데 _senior_market_insight 호출됨")

    monkeypatch.setattr(MarketReportService, "_category_stats", fake_cat)
    monkeypatch.setattr(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive", fake_comp)
    monkeypatch.setattr(MarketReportService, "_commercial_area", fake_comm)
    monkeypatch.setattr(MarketReportService, "_nearby_presale_84_price", fake_presale)
    monkeypatch.setattr(MarketReportService, "_senior_market_insight", _boom_senior)

    rep = await svc.build_report("서울 강남구 역삼동", "11680", use_llm=False)
    assert rep["senior_insight"] is None                       # 정직 폴백
    assert rep["target_profile"]["commercial"]["data_source"] == "live"  # 실데이터 축은 유지
    assert svc.to_pdf(rep)[:4] == b"%PDF"
