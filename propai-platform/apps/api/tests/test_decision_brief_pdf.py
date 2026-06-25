"""Stage1 통합 의사결정 브리프 PDF 빌더(decision_brief_pdf.to_pdf) 단위테스트.

실 reportlab으로 유효 PDF를 생성한다(라이브검증 겸·DB/공공API/LLM 불요·샌드박스). 검증:
  - PDF bytes 생성·%PDF 헤더·유효 크기.
  - 종합판정(GO/CONDITIONAL/HOLD)·핵심 KPI·5(=3 통합)파트 섹션 텍스트 포함.
  - unavailable part·deploy_pending 정직표기.
  - 빈 브리프(엣지)도 크래시 없이 graceful.

★텍스트 포함 검증: 한글폰트(HYSMyeongJo-Medium=CID)로 렌더된 PDF 바이트스트림은 글리프 코드라
  한국어를 substring 으로 찾을 수 없고, pypdf 도 미설치다. 따라서 reportlab Paragraph/Table 에
  '들어가는' 텍스트(렌더 전 원문)를 캡처해 섹션·KPI·정직표기 포함을 결정론적으로 확인한다(생산
  코드에 테스트 전용 seam 추가 없이, platypus 클래스만 일시 래핑). 동시에 to_pdf 가 실제로 유효
  %PDF 바이트를 만드는지도 같은 호출에서 확인한다.
"""

from __future__ import annotations

import reportlab.platypus as _platypus

from app.services.land_intelligence import decision_brief_pdf


def _brief_ok(*, deploy_pending: bool = True) -> dict:
    """실엔진형 정상 브리프(부지 ok·인허가 ok·법규 unavailable 혼재)."""
    return {
        "address": "서울특별시 강남구 역삼동 123",
        "project_id": "p1",
        "parcel_count": 2,
        "parts": [
            {
                "part": "site_market", "title": "부지·입지·시장",
                "summary_oneliner": "일반상업지역 · 실효 용적률 700% · 계획 GFA 11970㎡",
                "status": "ok",
                "key_metrics": [
                    {"key": "land_area", "label": "대지면적", "value": 1710.0, "unit": "㎡"},
                    {"key": "effective_far", "label": "실효 용적률", "value": 700, "unit": "%"},
                    {"key": "gfa", "label": "계획 연면적(GFA)", "value": 11970.0, "unit": "㎡"},
                    {"key": "presale_price", "label": "예상 분양가", "value": 5000, "unit": "만원/평"},
                ],
                "evidence": [{"label": "용적률 한도", "value": "700%", "basis": "조례"}],
                "legal_links": [
                    {"label": "국토계획법 제78조", "url": "https://law.go.kr/x"},
                    {"label": "url 없는 항목", "url": None},
                ],
                "confidence": "high", "detail_route": "/projects/{id}/canvas",
            },
            {
                "part": "permit_design", "title": "인허가·사업모델 Top3",
                "summary_oneliner": "추천 주상복합 · ROI 12% · 3개 Top 모델 · 잠정(선행절차 전제)",
                "status": "ok", "scenario_status": "tentative",
                "honest_disclosure": "site_id 미확보 — 분양가는 지역 통계 기반 추정",
                "key_metrics": [
                    {"key": "top1_model", "label": "추천 1순위 모델", "value": "주상복합", "unit": ""},
                    {"key": "roi", "label": "1순위 ROI(사업수익률)", "value": 12, "unit": "%"},
                ],
                "evidence": [], "legal_links": [],
                "confidence": "medium", "detail_route": "/projects/{id}/feasibility",
            },
            {
                "part": "regulation", "title": "법규 계층",
                "summary_oneliner": "법규 계층 미확보 — 주소 미확보(정직 고지).",
                "status": "unavailable", "reason": "주소 미확보(정직 고지).",
                "key_metrics": [], "evidence": [], "legal_links": [],
                "confidence": "low", "detail_route": "/projects/{id}/legal",
            },
        ],
        "verdict": {
            "decision": "CONDITIONAL", "confidence": "medium", "gate": "TENTATIVE",
            "reasons": ["디벨로퍼 Go/No-Go: 조건부"],
            "blockers": ["특이부지/도로·인허가 선행절차 전제 — 확정 GO 강등(잠정)."],
            "go_nogo": {"decision": "조건부", "top1": "주상복합", "grade": "B",
                        "roi_pct": 12, "status": "conditional"},
        },
        "billing": {"use_llm": False, "billing_key": "decision_brief", "estimated_fee_krw": 0.0},
        "meta": {
            "use_llm": False,
            "deploy_pending": deploy_pending,
            "deploy_pending_note": "라이브 DB·공공데이터 API·LLM 실호출은 배포 환경에서만 동작합니다.",
            "area_override": {"override_area_sqm": 1710.0, "engine_area_sqm": 236.0,
                              "ratio": 7.25, "warning": "입력 통합면적이 엔진 대표면적과 5배 이상 차이납니다."},
        },
    }


def _is_pdf(b: bytes) -> bool:
    return isinstance(b, bytes) and b.startswith(b"%PDF") and len(b) > 1500


def _render_and_capture(brief: dict) -> str:
    """to_pdf 를 호출하되 Paragraph/Table 에 들어가는 원문 텍스트를 캡처해 '|'로 합쳐 반환.

    렌더 전 원문을 캡처하므로 CID 폰트(글리프 코드)에도 한국어 substring 검증이 결정론적이다.
    동시에 to_pdf 반환값이 유효 %PDF 바이트인지도 확인한다(렌더 자체가 성공해야 캡처가 의미).
    생산 코드엔 손대지 않고 platypus.Paragraph/Table 만 일시 래핑한다(테스트 종료 시 원복).
    """
    captured: list[str] = []
    orig_para = _platypus.Paragraph
    orig_table = _platypus.Table

    class _CapParagraph(orig_para):  # type: ignore[misc, valid-type]
        def __init__(self, text, *args, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(text)
            super().__init__(text, *args, **kwargs)

    class _CapTable(orig_table):  # type: ignore[misc, valid-type]
        def __init__(self, data, *args, **kwargs):  # type: ignore[no-untyped-def]
            for row in data:
                for cell in row:
                    captured.append(str(cell))
            super().__init__(data, *args, **kwargs)

    _platypus.Paragraph = _CapParagraph
    _platypus.Table = _CapTable
    try:
        pdf = decision_brief_pdf.to_pdf(brief)
    finally:
        _platypus.Paragraph = orig_para
        _platypus.Table = orig_table
    assert _is_pdf(pdf)
    return "|".join(captured)


# ── 1) PDF bytes 생성·%PDF 헤더(기본 CID 폰트 경로) ──

def test_to_pdf_default_font_valid_pdf():
    pdf = decision_brief_pdf.to_pdf(_brief_ok())
    assert _is_pdf(pdf)


# ── 2) 종합판정(GO/CONDITIONAL/HOLD) 섹션 포함 ──

def test_to_pdf_contains_verdict_section():
    text = _render_and_capture(_brief_ok())
    assert "종합 판정" in text
    assert "CONDITIONAL" in text  # 판정 라벨에 결정값 노출
    assert "조건부" in text         # 디벨로퍼 Go/No-Go 패스스루
    assert "판정 근거" in text


# ── 3) 핵심 KPI 섹션 포함(통합면적·실효용적률·GFA·분양가·ROI) ──

def test_to_pdf_contains_kpi_section():
    text = _render_and_capture(_brief_ok())
    assert "핵심 KPI" in text
    assert "통합 대지면적" in text
    assert "실효 용적률" in text
    assert "예상 연면적(GFA)" in text
    assert "사업수익률(ROI)" in text


# ── 4) 5(=3 통합)파트 요약 섹션 포함(파트 제목·oneliner) ──

def test_to_pdf_contains_part_summaries():
    text = _render_and_capture(_brief_ok())
    assert "통합 분석 파트 요약" in text
    assert "부지·입지·시장" in text
    assert "인허가·사업모델 Top3" in text
    assert "법규 계층" in text
    # 근거·법령 섹션 + verified url 만 노출(죽은링크 금지: url None 항목은 링크 미노출)
    assert "근거·법령" in text
    assert "https://law.go.kr/x" in text


# ── 5) unavailable part 정직표기 ──

def test_to_pdf_unavailable_part_honest():
    text = _render_and_capture(_brief_ok())
    # 법규 part unavailable 사유가 oneliner(warn)로 노출
    assert "법규 계층 미확보" in text


# ── 6) 잠정 시나리오·정직 고지(honest_disclosure) 포함 ──

def test_to_pdf_tentative_and_honest_disclosure():
    text = _render_and_capture(_brief_ok())
    assert "잠정 시나리오" in text
    assert "site_id" in text  # 인허가 part honest_disclosure


# ── 7) deploy_pending 정직표기 ──

def test_to_pdf_deploy_pending_note():
    text = _render_and_capture(_brief_ok(deploy_pending=True))
    assert "정직 고지" in text
    assert "배포 환경" in text  # deploy_pending_note
    # 면적 override 괴리 warning 도 정직 고지에 합류
    assert "5배 이상 차이" in text


def test_to_pdf_no_deploy_pending_note_when_live():
    # deploy_pending=False(라이브)면 그 고지 문구는 빠진다(가짜 deploy-pending 위장 금지).
    text = _render_and_capture(_brief_ok(deploy_pending=False))
    assert "배포 환경에서만 동작" not in text


# ── 8) 빈 브리프(엣지)도 graceful(크래시 없이 유효 PDF) ──

def test_to_pdf_empty_brief_graceful():
    empty = {
        "address": None, "project_id": None, "parcel_count": 0, "parts": [],
        "verdict": {"decision": "HOLD", "confidence": "low",
                    "reasons": ["주소 또는 프로젝트 ID가 필요합니다(무목업)."],
                    "blockers": ["주소 또는 프로젝트 ID가 필요합니다(무목업)."],
                    "go_nogo": None, "gate": "PASS"},
        "billing": {"use_llm": False, "estimated_fee_krw": 0.0},
        "meta": {"use_llm": False, "deploy_pending": True,
                 "reason": "주소 또는 프로젝트 ID가 필요합니다(무목업)."},
    }
    pdf = decision_brief_pdf.to_pdf(empty)
    assert _is_pdf(pdf)


def test_to_pdf_bare_dict_no_keyerror():
    # 완전 빈 dict(키 전무)도 .get 안전접근으로 크래시 없이 유효 PDF.
    pdf = decision_brief_pdf.to_pdf({})
    assert _is_pdf(pdf)


def test_to_pdf_empty_brief_shows_honest_part_notice():
    text = _render_and_capture({"parts": [], "verdict": {}, "meta": {}})
    assert "분석 파트 미확보" in text  # 빈 parts 정직 고지


# ── 9) XML 미이스케이프 크래시 회귀(HIGH) — '<'/'&'/'</para>' 가 섞여도 graceful ──

def _brief_with_xml_chars() -> dict:
    """동적 도메인 문자열(주소·근거·법령 라벨/URL·판정 근거)에 reportlab 을 깨뜨리던
    '<', '>', '&', '</para>' 를 의도적으로 심은 브리프(과거 to_pdf 가 ValueError→HTTP500)."""
    return {
        "address": "서울 <강남> & 역삼 </para> 1<2",
        "parcel_count": 1,
        "parts": [
            {
                "part": "site_market", "title": "부지<&>입지", "status": "ok",
                "summary_oneliner": "용적률 <700%> & 계획 GFA</para>",
                "key_metrics": [
                    {"key": "land_area", "label": "대지<면적>", "value": 1710.0, "unit": "㎡"},
                    {"key": "effective_far", "label": "실효&용적률", "value": 700, "unit": "%"},
                ],
                "evidence": [{"label": "근거<라벨>", "value": "a < b & c", "basis": "조례</para>"}],
                "legal_links": [
                    {"label": "국토계획법<제78조>",
                     "url": "https://law.go.kr/x?a=1&b=2<c>"},
                ],
                "confidence": "high",
            },
        ],
        "verdict": {
            "decision": "CONDITIONAL", "confidence": "medium", "gate": "TENTATIVE",
            "reasons": ["근거 <중요> & 검토 </para>"],
            "blockers": ["차단 <요인> & 제약"],
            "go_nogo": {"decision": "조건부<>", "top1": "주상복합&타워",
                        "grade": "B", "roi_pct": 12},
        },
        "meta": {"deploy_pending": True,
                 "deploy_pending_note": "배포 환경 <전용> & 한정"},
    }


def test_to_pdf_xml_chars_no_crash_valid_pdf():
    # 과거: reportlab Paragraph 가 '<'/'&'/'</para>' 를 깨진 태그로 보고 ValueError→500.
    # 기대: 이스케이프해 ValueError 없이 유효 %PDF 를 만든다(try/except 은폐 아님·정상 렌더).
    pdf = decision_brief_pdf.to_pdf(_brief_with_xml_chars())
    assert _is_pdf(pdf)


def test_to_pdf_xml_chars_are_escaped_in_render():
    # 캡처된 원문에는 위험 문자가 XML 엔티티(&lt; &gt; &amp;)로 치환돼 들어가야 한다.
    text = _render_and_capture(_brief_with_xml_chars())
    # 주소의 '<강남>' → '&lt;강남&gt;', '&' → '&amp;'
    assert "&lt;강남&gt;" in text
    assert "&amp;" in text
    # 닫는 태그 '</para>' 도 그대로가 아니라 이스케이프돼야 한다(원문 '</para>' 부분문자열 부재).
    assert "</para>" not in text
    # 법령 URL 의 '&'(쿼리스트링)·'<' 도 이스케이프(죽은링크 아님·verified url 노출 유지)
    assert "law.go.kr/x?a=1&amp;b=2&lt;c&gt;" in text


def test_to_pdf_bool_metric_not_rendered_as_one():
    # _fmt_value 의 bool 선차단 — True 가 '1'(잠복)이 아니라 'True' 로 표기돼야 한다.
    brief = {
        "parts": [
            {
                "part": "site_market", "title": "부지", "status": "ok",
                "summary_oneliner": "-",
                "key_metrics": [
                    {"key": "flag", "label": "플래그", "value": True, "unit": ""},
                ],
                "evidence": [], "legal_links": [],
            },
        ],
        "verdict": {}, "meta": {},
    }
    text = _render_and_capture(brief)
    assert "True" in text
    # 라벨 '플래그' 행에서 값이 '1'로 잠복 변환되지 않았음을 함께 확인(셀 '|플래그|True|' 형태).
    assert "|플래그|True" in text or "플래그|True" in text
