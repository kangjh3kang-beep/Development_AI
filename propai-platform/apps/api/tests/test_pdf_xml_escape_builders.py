"""전 reportlab PDF 빌더의 XML 미이스케이프 크래시 회귀(전역 전파방지·exhaustive).

[왜 이 테스트인가 — 쉬운 설명]
reportlab 의 Paragraph 는 텍스트를 작은 HTML/XML 로 본다. 그래서 사용자·엔진이 만든 동적
문자열(주소·상호·근거·법령 URL 등)에 '<', '&', '</para>' 같은 글자/태그가 섞이면 reportlab 이
"태그가 깨졌다"며 ValueError 를 던지고, 그게 그대로 HTTP 500 으로 새어 나간다. 빌더들은
docstring 에서 'graceful(크래시 없음)'을 약속하므로 이는 약속 위반이다.

[무엇을 검증하나]
decision_brief_pdf 의 회귀 패턴(test_decision_brief_pdf.py)을 전 라이브 빌더로 복제한다.
각 빌더에 ★bare '&' 가 아니라 '<x>'/'</para>' 같은 '실제 크래시 케이스'를 주입하고:
  (1) ValueError 없이 유효 %PDF(b'%PDF…') 를 만든다(은폐 아님·정상 렌더).
  (2) Paragraph 에 들어가는 원문이 XML 엔티티(&lt; &gt; &amp;)로 치환됐다('</para>' 부분문자열 부재).

[방법]
생산 코드에 테스트 전용 seam 을 넣지 않고, reportlab.platypus.Paragraph/Table 만 일시 래핑해
'렌더 전 원문'을 캡처한다(한글 CID 폰트는 글리프 코드라 PDF 바이트에서 한국어 substring 검색
불가 → 원문 캡처가 결정론적). 캡처 종료 시 원복한다. DB·공공API·LLM 불요(샌드박스 가능).
"""

from __future__ import annotations

import reportlab.platypus as _platypus

from app.services.design_ingest import design_proposal_pdf
from app.services.land_intelligence import desk_appraisal_pdf, land_analysis_report_pdf
from app.services.market.market_report_service import MarketReportService
from app.services.report import design_audit_pdf, pipeline_report_pdf
from app.services.sales.cert import termination_cert_pdf

# reportlab 이 미이스케이프 시 ValueError 를 던지는 '진짜 크래시' 문자열(bare '&' 아님).
XML_BOMB = "값 <x> & </para> 1<2"


def _is_pdf(b: bytes) -> bool:
    return isinstance(b, bytes) and b.startswith(b"%PDF") and len(b) > 800


def _render_and_capture(fn) -> tuple[bytes, str, str]:
    """fn() 호출 중 텍스트를 캡처해 (pdf_bytes, paragraph_text, table_cell_text) 반환.

    ★Paragraph 원문과 Table 셀 원문을 분리 캡처한다. reportlab 은 ★Paragraph flowable 만 XML
    파싱한다(거기 '<','&','</para>' 가 있으면 ValueError→500). Table 의 bare str 셀은 XML
    파싱하지 않고 글자 그대로 그리므로 크래시 벡터가 아니고 이스케이프 대상도 아니다. 따라서
    '이스케이프됐는지' 검증은 paragraph_text 에만 적용해야 한다(bare 셀의 원문 '</para>' 는 정상).
    fn 은 인자 없이 호출 가능한 클로저. 생산 코드 무변경 — platypus 만 일시 래핑(종료 시 원복).
    """
    para_text: list[str] = []
    cell_text: list[str] = []
    orig_para = _platypus.Paragraph
    orig_table = _platypus.Table

    class _CapParagraph(orig_para):  # type: ignore[misc, valid-type]
        def __init__(self, text, *args, **kwargs):  # type: ignore[no-untyped-def]
            para_text.append(str(text))
            super().__init__(text, *args, **kwargs)

    class _CapTable(orig_table):  # type: ignore[misc, valid-type]
        def __init__(self, data, *args, **kwargs):  # type: ignore[no-untyped-def]
            for row in data or []:
                for cell in row:
                    # Paragraph 셀(중첩 flowable)은 위 _CapParagraph 가 이미 para_text 에 잡았다.
                    # 나머지 bare str 셀만 cell_text 로(이스케이프 비대상·크래시 비대상).
                    if not isinstance(cell, orig_para):
                        cell_text.append(str(cell))
            super().__init__(data, *args, **kwargs)

    _platypus.Paragraph = _CapParagraph
    _platypus.Table = _CapTable
    try:
        pdf = fn()
    finally:
        _platypus.Paragraph = orig_para
        _platypus.Table = orig_table
    return pdf, "|".join(para_text), "|".join(cell_text)


def _assert_escaped(para_text: str) -> None:
    """Paragraph 원문(XML 파싱 경로)에서 위험 문자가 엔티티로 치환됐는지 확인(은폐 아님·정상 렌더).

    Table 의 bare 셀은 reportlab 이 XML 파싱하지 않아 검증 대상이 아니다(여기 인자로 안 받는다).
    """
    # 깨진 닫는 태그 '</para>' 가 Paragraph 원문에 그대로 남아 있으면(=미이스케이프) reportlab 이 깨진다.
    assert "</para>" not in para_text
    # '<x>' → '&lt;x&gt;', '&' → '&amp;' 로 최소 1회 이상 치환돼 있어야 한다.
    assert "&lt;" in para_text and "&gt;" in para_text and "&amp;" in para_text


# ──────────────────────────────────────────────────────────────────────────
# 1) pipeline_report_pdf — 요약·섹션·리스크·AI해석 동적 텍스트(+주소·제목)
# ──────────────────────────────────────────────────────────────────────────

def _pipeline_report() -> dict:
    return {
        "project_address": XML_BOMB,
        "generated_at": "2026-06-25 <t> & x",
        "executive_summary": {"결론<요약>": "추진 <검토> & 보류 </para>"},
        "sections": [
            {"section_no": "1<b>", "title": "부지 <분석> & 입지",
             "content": {"용도<지역>": "일반상업 & <상한>"}},
            {"section_no": "2", "title": "단순 섹션", "content": "본문 <텍스트> & 종합 </para>"},
        ],
        "risk_assessment": {"리스크<항목>": "도로 <접함> & 후퇴"},
    }


def test_pipeline_report_pdf_xml_no_crash_and_escaped():
    pdf, para, _cells = _render_and_capture(
        lambda: pipeline_report_pdf.build_pipeline_report_pdf(
            _pipeline_report(),
            narratives={"site_analysis": {"핵심<요지>": "양호 <전망> & 안정 </para>"}},
        )
    )
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 2) design_audit_pdf — finding/overall/metrics/링크/근거·신뢰도 동적 텍스트
# ──────────────────────────────────────────────────────────────────────────

def _design_audit() -> dict:
    return {
        "project_id": "p<1> & x",
        "id": "a<id>",
        "created_at": "2026 <t> & x",
        "overall": {"종합<판정>": "조건부 <검토> & 보류 </para>"},
        "findings": [
            {"check_id": "CMP<1>", "title": "사례 <편차> & 과다",
             "detail": "북측 <이격> 부족 </para>", "severity": "high",
             "category": "comparison"},
            {"check_id": "LAW<1>", "title": "법규 <인센티브> & 적용",
             "category": "legal", "legal_ref_key": "kglp_78"},
            {"check_id": "ENG<1>", "title": "구조 <룰> & 점검", "category": "engineering"},
            {"category": "strength", "title": "장점 <항목> & 우수"},
        ],
        "blindspot": {"items": [{"claim": "쟁점 <추정> & 검토 </para>",
                                 "basis": "근거 <자료> & x", "confidence": "low"}],
                      "summary": "요약 <쟁점> & x"},
        "inputs": {"derived_signals": {"comparables": [
            {"title": "표본<A>", "면적<㎡>": "100 & <상한>"}]}},
    }


def test_design_audit_pdf_xml_no_crash_and_escaped():
    pdf, para, _cells = _render_and_capture(
        lambda: design_audit_pdf.build_design_audit_pdf(_design_audit())
    )
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 3) market_report_service.to_pdf — 주소·내러티브·출처·적정분양가 동적 텍스트
# ──────────────────────────────────────────────────────────────────────────

def _market_rep() -> dict:
    return {
        "address": XML_BOMB,
        "generated_at": "2026-06-25 <t> & x",
        "months": ["202604", "202605", "202606"],
        "coordinates": {},
        "narrative": {
            "summary": "시장 <요약> & 분석 </para>",
            "opportunities": ["기회 <요인> & 1", "기회 </para> 2"],
            "risks": ["리스크 <요인> & 1"],
            "price_trend": "동향 <상승> & 보합 </para>",
        },
        "zone_type": "일반상업 <지역> & x",
        "trade": {"아파트<A>": {"count": 10, "avg": 50000,
                                "per_pyeong": {"avg": 3000}, "avg_area_m2": 84.0}},
        "rent": {},
        "apt_trend": [],
        "raw_data": {
            "population": {"summary": {"total_population": 1000},
                           "source": "KOSIS <인구> & x", "data_source": "DT_<1> & x"},
            "income": {"avg_income_10k": 5000, "source": "국세청 <소득> & x",
                       "data_source": "DT_<2> & x"},
        },
        "pricing_band": {"data_source": "comparable", "fair_price_10k": 60000,
                         "affordability_verdict": "적정 <범위> & x",
                         "note": "산정 <근거> & 비교 </para>"},
    }


def test_market_report_pdf_xml_no_crash_and_escaped():
    svc = MarketReportService()  # MolitClient 생성만(네트워크 호출 없음)
    pdf, para, _cells = _render_and_capture(lambda: svc.to_pdf(_market_rep()))
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 4) termination_cert_pdf — 증명서번호·발급법인/대표·무결성해시 동적 텍스트
# ──────────────────────────────────────────────────────────────────────────

def _cert() -> dict:
    return {
        "certificate_no": "CERT <2026> & 0001",
        "freelancer_name": "홍길동 <상담> & x",
        "freelancer_rrn": "9001011234567",
        "site_name": "현장 <A> & B",
        "period_start": "2025-01-01", "period_end": "2025-12-31",
        "payee_name": "수령 <자> & x", "payee_account": "은행 1234",
        "income_total": 10000000, "withholding_total": 330000, "net_total": 9670000,
        "issuer_company_name": "주식회사 <AT&T> & 부동산</para>",
        "issuer_biz_no": "123-45-67890",
        "issuer_ceo_name": "대표 <김&이> 사장",
        "issued_at": "2026-01-15",
        "ledger_hash": "abc123<deadbeef>&x",
    }


def test_termination_cert_pdf_xml_no_crash_and_escaped():
    # fetch_stamp=False — 외부 직인 다운로드(네트워크) 비활성(샌드박스·결정론).
    pdf, para, _cells = _render_and_capture(
        lambda: termination_cert_pdf.build_termination_cert_pdf(_cert(), fetch_stamp=False)
    )
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 5) land_analysis_report_pdf — 프로젝트명·지번·건물명 동적 텍스트
# ──────────────────────────────────────────────────────────────────────────

def _land_data() -> dict:
    return {
        "project_name": "프로젝트 <A> & B </para>",
        "parcels": [
            {"jibun": "역삼동 <123> & 4", "area_sqm": 500.0, "zone_type": "일반상업",
             "bcr_pct": 60, "far_pct": 700, "jimok": "대", "parcel_case": "aggregate",
             "official_price_per_sqm": 1000000, "status": "ok",
             "building": {"building_name": "타워 <A&B>", "unit_count": 50}},
        ],
        "units_by_parcel": {
            "역삼동 <123> & 4": {
                "plat_area_sqm": 500.0, "unit_count": 2, "reliable": True,
                "units": [
                    {"dong": "101<x>", "ho": "1<2>", "exclusive_area_sqm": 84.0,
                     "land_share_sqm": 10.0, "land_share_pyeong": 3.0},
                ],
            }
        },
    }


def test_land_analysis_report_pdf_xml_no_crash_and_escaped():
    pdf, para, _cells = _render_and_capture(
        lambda: land_analysis_report_pdf.build_land_analysis_report(_land_data())
    )
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 6) desk_appraisal_pdf — 근거(rationale)·교차검증·시점수정·AI해석·면책 동적 텍스트
# ──────────────────────────────────────────────────────────────────────────

def _appraisal() -> dict:
    return {
        "area_sqm": 500,
        "appraised_price_per_sqm": 1000000,
        "appraised_total_won": 500000000,
        "confidence": 0.8,
        "range_per_sqm": {"low": 900000, "high": 1100000},
        "methods": [{"method": "거래사례비교", "unit_price": 1000000,
                     "rationale": "사례 <비교> & 보정 </para>"}],
        "weight_note": "가중 <근거> & x",
        "cross_check": {"firms": [950000, 1050000], "mean": 1000000, "cv_pct": 5,
                        "note": "교차 <검증> & 안정 </para>"},
        "building": {"rationale": "원가 <법> & 복합"},
        "income": {"rationale": "수익 <환원> & x"},
        "complex_total_won": 700000000, "income_total_won": 650000000,
        "complex_note": "복합 <참고> & x </para>",
        "market_stats": {"cap_rate": {"source": "R-ONE", "pct": 4.5, "basis": "근거 <자료> & x"},
                         "rone_available": True},
        "time_adjust_basis": "시점 <수정> & 근거 </para>",
        "disclaimer": "면책 <고지> & 참고용 </para>",
    }


def test_desk_appraisal_pdf_xml_no_crash_and_escaped():
    pdf, para, _cells = _render_and_capture(
        lambda: desk_appraisal_pdf.build_desk_appraisal_pdf(
            _appraisal(),
            address=XML_BOMB,
            ai_sections={"valuation_narrative": "추정 <근거> & x </para>",
                         "추가<섹션>": "라벨 미정의 <항목> & x"},
        )
    )
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 7) design_proposal_pdf — 다필지 노트·특이부지 노트·경고·법령링크 동적 텍스트
# ──────────────────────────────────────────────────────────────────────────

def _design_result() -> dict:
    return {
        "site": {
            "zone_code": "UQA110", "area_sqm": 500.0, "buildable_footprint_sqm": 300.0,
            "max_gfa_sqm": 3500.0, "max_floors_est": 12, "far_source": "ordinance",
            "evidence": [{"claim": "용적률 <근거> & x",
                          "link": "https://law.go.kr/x?a=1&b=2<c>"}],
            "warnings": ["부지 <경고> & 1 </para>"],
        },
        "permit": {"is_permitted": True, "permit_complexity": 3,
                   "reason": "허가 <가능> & x"},
        "multi_parcel": {"aggregation": {
            "parcel_count": 2, "total_area_sqm": 1000.0, "dominant_zone": "일반상업 <지역> & x",
            "blended_far_eff_pct": 650, "integrated_gfa_sqm": 6500.0,
            "far_basis_note": "면적가중 <근거> & 통합 </para>"}},
        "special_parcel": {"is_special": True, "gate": "TENTATIVE",
                           "severity_label": "학교용지 <중> & x", "developability": "조건부",
                           "resolvable": "COND", "note": "특이 <고지> & x </para>"},
        "proposals": [{
            "candidate": {
                "estimated_gfa_sqm": 6000.0, "max_envelope_gfa_sqm": 6500.0,
                "estimated_floors": 12, "estimated_units": 60,
                "disciplines_covered": ["건축<a>", "구조"], "missing_disciplines": ["전기<b>"],
                "parking_required": 50,
                "warnings": ["설계 <경고> & 1 </para>"],
                "score_breakdown": {"explanation": "선정 <근거> & x"},
                "sources": [{"drawing_type": "평면<도>", "score": 0.9}],
            },
            "verdict": {"verdict": "conditional", "notes": ["판정 <노트> & 1 </para>"]},
            "evidence": [{"claim": "추천 <근거> & x", "link": "https://law.go.kr/y?p=1&q=2"}],
        }],
        "recommendation": {"index": 0},
    }


def test_design_proposal_pdf_xml_no_crash_and_escaped():
    pdf, para, _cells = _render_and_capture(
        lambda: design_proposal_pdf.build_design_proposal_pdf(_design_result())
    )
    assert _is_pdf(pdf)
    _assert_escaped(para)


# ──────────────────────────────────────────────────────────────────────────
# 8) 무회귀 — 위험 문자 없는 정상 입력은 그대로(과대 이스케이프로 정적 마크업 깨지지 않음)
# ──────────────────────────────────────────────────────────────────────────

def test_clean_inputs_no_spurious_entities_pipeline():
    clean = {
        "project_address": "서울특별시 강남구 역삼동 123",
        "generated_at": "2026-06-25",
        "executive_summary": {"결론": "추진 검토"},
        "sections": [{"section_no": "1", "title": "부지 분석", "content": "본문 종합"}],
        "risk_assessment": {"리스크": "도로 접함"},
    }
    pdf, para, _cells = _render_and_capture(
        lambda: pipeline_report_pdf.build_pipeline_report_pdf(clean)
    )
    assert _is_pdf(pdf)
    # 위험 문자가 없으면 엔티티가 생기지 않는다(과대 이스케이프·이중 이스케이프 회귀 방지).
    assert "&amp;" not in para and "&lt;" not in para and "&gt;" not in para
