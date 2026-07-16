"""시장조사보고서 어댑터(build_report_model_from_market) 단위테스트.

생성허브 로드맵① — 시장 리포트 렌더 스택 통합(market_report_service.to_pdf/to_pptx/to_docx 가
reportlab/python-pptx/python-docx 를 직접 재구현하던 이원화를 해소하고 통합 ReportModel 로 일원화).

검증 축(어댑터 단위 — MarketReportService.build_report 실호출은 목킹하지 않고 결과 dict 픽스처 주입):
  (a) 섹션 구성 — 구 to_pdf 의 핵심 섹션(Executive Summary·1~8)이 모델에 그대로 존재 + 순서 보존
      (적정 분양가가 사업 타당성보다 먼저 — 인과 정합)
  (b) 경쟁 단지 비교(competitor_complexes, #338) — 있으면 섹션 노출, 없으면 생략(정직·무목업)
  (c) 결측 정직 — 미확보/미선택 축은 fmt_value('—') 또는 원본 안내 문구 그대로("데이터 없음"·
      "AI 분석 미포함"·"상권(SEMAS) 데이터 미확보"·"개략 수지 산출 불가")
  (d) senior_insight 우선순위 — 전용 인터프리터 텍스트가 인라인 narrative 보다 우선 노출
  (e) 실렌더(PDF) — pytest.importorskip("reportlab") 가드(로컬 venv 미설치 — CI 검증,
      기존 test_desk_appraisal_multi_report.py 컨벤션 미러)
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.report.render import (
    build_report_model_from_market,
    render_report,
)
from app.services.report.render.model import (
    DataTableBlock,
    KVTableBlock,
    NarrativeBlock,
    Section,
    fmt_value,
)

_EMPTY = fmt_value(None)  # '—' 통일 표기(토큰 상수 비의존)


def _full_rep() -> dict[str, Any]:
    """전 축 라이브 rep — 8섹션 + Executive Summary + 경쟁단지 비교 전부 채워진 픽스처."""
    return {
        "address": "서울 강남 역삼",
        "generated_at": "2026-07-17 09:00",
        "months": ["202605", "202606", "202607"],
        "coordinates": {"lat": 37.5, "lon": 127.0},
        "zone_type": "일반상업지역",
        "official_price_per_sqm": 25000000,
        "trade": {"아파트": {"count": 120, "per_pyeong": {"avg": 3200}}},
        "narrative": {
            "summary": "인라인 시장 요약", "opportunities": ["기회 1"], "risks": ["리스크 1"],
            "price_trend": "상승", "target_persona": "30대 실수요",
        },
        "senior_insight": {
            "market_overview": "전용 시장개요.", "price_trend_analysis": "가격추이 전용해석.",
            "comparable_analysis": "비교분석 전용해석.", "investment_insight": "투자 시사점.",
            "risk_factors": "리스크 정밀.", "timing_recommendation": "매수 적기.",
        },
        "feasibility_analysis": {
            "financials": {"roi_percent": 14.5, "total_cost_10k": 5000000,
                           "total_revenue_10k": 6200000, "net_profit_10k": 1200000, "npv_10k": 800000},
            "massing": {"land_area_sqm": 1000, "gfa_sqm": 2500, "gfa_pyeong": 756},
            "assumptions": {"note": "개략 가정"},
        },
        "pricing_band": {"data_source": "live", "fair_price_10k": 92000,
                         "affordability_verdict": "within_optimistic", "note": "적정 범위"},
        "unit_mix_recommendation": {"data_source": "live", "recommended_mix": {"59㎡": 40, "84㎡": 60},
                                    "rationale": "수요기반"},
        "target_profile": {
            "primary_age": {"band": "30-39", "value": "30대"},
            "primary_household": {"type": "1인 가구"},
            "income_tier": {"tier_label": "중상위 소득권(추정)"},
            "commercial": {"data_source": "live", "total_stores": 820, "grade": "B",
                          "vitality_score": 72, "category_distribution": [{"category": "음식", "count": 300}]},
            "location": {"nearest_subway": "역삼역", "subway_distance_m": 300, "school_count": 2},
            "premium": {"note": "신용평점·카드소비는 PREMIUM 제휴 예정"},
        },
        "raw_data": {
            "real_estate": {
                "source": "국토교통부 실거래가", "data_source": "live",
                "trade_table": [{"type": "아파트", "count": 120, "per_pyeong_manwon": 3200,
                                 "avg_10k": 92000, "avg_area_m2": 84.9}],
                "rent_table": [{"type": "아파트", "count": 40, "avg_10k": 45000,
                                "min_10k": 20000, "max_10k": 90000}],
                "trend_series": [{"ym": "202606", "per_pyeong_manwon": 3200, "mom_pct": 1.6},
                                  {"ym": "202607", "per_pyeong_manwon": 3250, "mom_pct": 1.6}],
                "competitor_complexes": [
                    {"name": "역삼래미안", "deal_count": 12, "avg_per_pyeong_manwon": 3300,
                     "price_basis": "전용", "recent_deal_ym": "202607", "build_year": 2015},
                ],
            },
            "population": {
                "data_source": "live", "migration_data_source": "live",
                "summary": {"total_population": 45000, "household_count": 18000, "avg_household_size": 2.5},
                "age_distribution": [{"label": "30-39", "count": 320}],
                "household_types": [{"label": "1인", "ratio": 45.0}],
                "migration": {"net_migration": 1300, "total_inflow": 12500, "total_outflow": 11200},
                "source": "통계청",
            },
            "income": {"data_source": "live", "avg_income_10k": 4800, "median_income_10k": 4080,
                       "median_estimated": True, "source": "국세청"},
        },
    }


def _degraded_rep() -> dict[str, Any]:
    """전 축 미확보 rep — 무목업 정직 강등 검증용(인구/소득/상권/수지 전부 미확보)."""
    return {
        "address": "서울 강남", "generated_at": "2026-07-17", "months": ["202607"], "coordinates": {},
        "zone_type": None, "official_price_per_sqm": None,
        "trade": {}, "narrative": {"summary": "", "opportunities": [], "risks": [], "price_trend": ""},
        "senior_insight": None,
        "feasibility_analysis": {"error": "용도지역 미확인"},
        "pricing_band": {"data_source": "unavailable", "note": "비교 데이터 없음"},
        "unit_mix_recommendation": {"data_source": "unavailable"},
        "target_profile": {"commercial": {"data_source": "unavailable"}, "location": {}},
        "raw_data": {"real_estate": {"source": "국토교통부 실거래가", "data_source": "live", "trend_series": []}},
    }


def _sections_by_title(model) -> dict[str, Section]:
    out: dict[str, Section] = {}
    if model.exec_summary:
        out[model.exec_summary.title] = model.exec_summary
    for s in model.sections:
        out[s.title] = s
    return out


def _joined_text(model) -> str:
    """모델 전체(제목·문단·표 셀)를 한 문자열로 평탄화 — 순서·문구 검증용."""
    parts: list[str] = []

    def _walk(sec: Section) -> None:
        parts.append(sec.title)
        for b in sec.blocks:
            if getattr(b, "title", None):
                parts.append(b.title)
            paragraphs = getattr(b, "paragraphs", None)
            if paragraphs:
                parts.extend(str(p) for p in paragraphs)
            rows = getattr(b, "rows", None)
            if rows:
                for row in rows:
                    parts.extend(str(x) for x in row)

    if model.exec_summary:
        _walk(model.exec_summary)
    for sec in model.sections:
        _walk(sec)
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# (a) 섹션 구성 + 순서
# ─────────────────────────────────────────────────────────────────────────

def test_adapter_sections_present_and_ordered():
    model = build_report_model_from_market(_full_rep())
    assert model.meta.title == "시장조사보고서"
    assert model.meta.project_address == "서울 강남 역삼"
    assert model.meta.confidential is False

    joined = _joined_text(model)
    order = ["핵심 요약 (Executive Summary)", "1. 시장 개요", "2. 수요 분석", "3. 가격·실거래",
             "4. 입지 분석", "5. 사업 타당성", "6. 리스크 요인", "7. 결론 및 권고", "8. 부록"]
    idxs = [joined.index(s) for s in order]
    assert idxs == sorted(idxs), f"목차 순서 어긋남: {idxs}"

    # ★인과 정합: 적정 분양가(매출 입력)가 사업 타당성보다 먼저 등장(수지 산정의 전제)
    assert joined.index("적정 분양가") < joined.index("5. 사업 타당성")

    # senior_insight 전용 해석이 인라인 narrative 보다 우선 노출
    assert "전용 시장개요." in joined


def test_adapter_exec_summary_kpi_rows():
    model = build_report_model_from_market(_full_rep())
    secs = _sections_by_title(model)
    kpi_table = next(b for b in secs["핵심 요약 (Executive Summary)"].blocks if isinstance(b, DataTableBlock))
    by_label = {row[0]: row[1] for row in kpi_table.rows}
    assert by_label["아파트 평당시세"] == "3,200만원/평"
    assert by_label["개략 ROI"] == "14.5%"
    assert "투자 시사점." in "\n".join(
        "\n".join(p.paragraphs) for p in secs["핵심 요약 (Executive Summary)"].blocks
        if isinstance(p, NarrativeBlock)
    )


# ─────────────────────────────────────────────────────────────────────────
# (b) 경쟁 단지 비교(competitor_complexes) — 있으면 노출, 없으면 생략
# ─────────────────────────────────────────────────────────────────────────

def test_competitor_complexes_section_present_when_data():
    model = build_report_model_from_market(_full_rep())
    secs = _sections_by_title(model)
    comp_table = next(
        (b for b in secs["3. 가격·실거래"].blocks
         if isinstance(b, DataTableBlock) and b.title == "경쟁 단지 비교 (실거래 상위)"),
        None,
    )
    assert comp_table is not None, "경쟁 단지 비교 섹션이 없음"
    assert comp_table.rows == [["역삼래미안", "12건", "3,300만원/평", "202607", "2015"]]


def test_competitor_complexes_section_omitted_when_absent():
    rep = _full_rep()
    rep["raw_data"]["real_estate"]["competitor_complexes"] = []
    model = build_report_model_from_market(rep)
    secs = _sections_by_title(model)
    comp_table = next(
        (b for b in secs["3. 가격·실거래"].blocks
         if isinstance(b, DataTableBlock) and b.title == "경쟁 단지 비교 (실거래 상위)"),
        None,
    )
    assert comp_table is None, "데이터 없을 때는 섹션 자체가 생략돼야 함(가짜 빈 표 금지)"


# ─────────────────────────────────────────────────────────────────────────
# (c) 결측 정직 — 미확보/미선택 축은 원본 안내 문구 또는 fmt_value('—') 그대로
# ─────────────────────────────────────────────────────────────────────────

def test_degraded_honest_no_mockup():
    model = build_report_model_from_market(_degraded_rep())
    joined = _joined_text(model)
    assert "인구 데이터 없음" in joined
    assert "소득 데이터 없음" in joined
    assert "상권(SEMAS) 데이터 미확보" in joined
    assert "개략 수지 산출 불가" in joined
    assert "AI 분석 미포함" in joined


def test_degraded_pricing_band_unavailable_shows_note_not_fake_price():
    model = build_report_model_from_market(_degraded_rep())
    secs = _sections_by_title(model)
    narr = next(
        b for b in secs["3. 가격·실거래"].blocks
        if isinstance(b, NarrativeBlock) and b.title == "적정 분양가 (거래사례비교)"
    )
    assert "비교 데이터 없음" in narr.paragraphs[0]


def test_degraded_kv_missing_values_use_empty_mark():
    model = build_report_model_from_market(_full_rep())
    rep = _full_rep()
    rep["feasibility_analysis"] = {
        "financials": {"roi_percent": None, "total_cost_10k": None, "total_revenue_10k": None,
                       "net_profit_10k": None, "npv_10k": None},
        "massing": {},
    }
    model = build_report_model_from_market(rep)
    secs = _sections_by_title(model)
    kv = next(b for b in secs["5. 사업 타당성 (Feasibility · 개략 추정)"].blocks if isinstance(b, KVTableBlock))
    by_label = dict(kv.rows)
    assert by_label["ROI(투자수익률)"] == _EMPTY
    assert by_label["총사업비"] == _EMPTY
    assert by_label["대지면적"] == _EMPTY


# ─────────────────────────────────────────────────────────────────────────
# (e) 실렌더(PDF) — reportlab 미설치 환경(로컬 venv)은 skip, CI 는 실제 검증
# ─────────────────────────────────────────────────────────────────────────

def test_full_and_degraded_render_pdf_smoke():
    pytest.importorskip("reportlab")
    for rep in (_full_rep(), _degraded_rep()):
        model = build_report_model_from_market(rep)
        data, media_type, ext = render_report(model, "pdf")
        assert ext == "pdf" and media_type == "application/pdf"
        assert data[:4] == b"%PDF" and len(data) > 800


def test_service_to_pdf_delegates_to_adapter():
    """MarketReportService.to_pdf 가 어댑터+엔진으로 위임되는지(하위호환 진입점 무회귀)."""
    pytest.importorskip("reportlab")
    from app.services.market.market_report_service import MarketReportService

    svc = MarketReportService.__new__(MarketReportService)
    pdf = svc.to_pdf(_full_rep())
    assert pdf[:4] == b"%PDF"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
