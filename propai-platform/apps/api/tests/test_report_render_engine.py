"""통합 보고서 생성엔진 테스트 — 하나의 정본 모델을 PDF/PPTX/DOCX 로 렌더.

검증: (1) 세 포맷 모두 유효 파일 시그니처, (2) 정직표기(None→'—'·XML 주입 안전),
(3) 핵심 데이터 존재, (4) 산식 복제 0(렌더 패키지가 도메인 산식 서비스를 임포트하지 않음).
PPTX/DOCX 라이브러리 미설치 환경에서는 해당 포맷만 skip(무결성 유지).
"""

from __future__ import annotations

import zipfile

import pytest

from app.services.report.render import render_report
from app.services.report.render.model import (
    ChartBlock,
    DataTableBlock,
    Evidence,
    EvidenceBlock,
    GradeBadgeBlock,
    KPITile,
    KPITileBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    Series,
)


def _sample_model() -> ReportModel:
    """모든 Block 타입 + 정직 경계값(None·0·XML '<>')을 담은 표본."""
    exec_sum = Section(title="심사 요약", blocks=[
        GradeBadgeBlock(grade="normal", label="사업성 등급"),
        KPITileBlock(tiles=[
            KPITile(label="LTV", value="65%", basis="≤ 70%"),
            KPITile(label="사업이익률", value="16.4%"),
        ]),
        NarrativeBlock(paragraphs=["결론: 조건부 추진 가능."]),
    ])
    secs = [
        Section(section_no=1, title="사업 개요", blocks=[
            KVTableBlock(rows=[("소재지", "용인 <예시> & 처인"), ("대지면적", 11465),
                               ("연면적", None), ("공시지가(㎡)", 0)]),
        ]),
        Section(section_no=2, title="사업 수지", blocks=[
            DataTableBlock(headers=["항목", "금액(억원)"], rows=[["토지비", 420], ["합계", 1032]],
                           numeric_cols=[1], total_row=True),
            ChartBlock(chart_type="bar", title="총사업비", categories=["토지", "공사"],
                       series=[Series(name="억원", values=[420, 480])]),
            ChartBlock(chart_type="tornado", title="민감도", categories=["분양가", "분양률"],
                       series=[Series(name="영향", values=[120, 95])]),
        ]),
        Section(section_no=3, title="근거", blocks=[
            EvidenceBlock(items=[Evidence(value="용적률 250%", basis="조례", source="zoning", confidence="low")]),
        ]),
    ]
    return ReportModel(
        meta=ReportMeta(title="프로젝트 통합 분석 보고서", project_address="용인 <예시>",
                        generated_at="2026-07-03", doc_no="PROPAI-TEST"),
        sections=secs, exec_summary=exec_sum)


def _zip_text(data: bytes) -> str:
    """OOXML(zip) 안의 모든 xml 텍스트를 이어붙여 반환(내용 검증용)."""
    import io

    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.endswith(".xml"):
                out.append(z.read(name).decode("utf-8", "ignore"))
    return "\n".join(out)


def test_pdf_render_signature_and_honesty():
    data, mime, ext = render_report(_sample_model(), "pdf")
    assert ext == "pdf" and mime == "application/pdf"
    assert data[:4] == b"%PDF"
    assert len(data) > 2000


@pytest.mark.parametrize("fmt,sig", [("pptx", b"PK\x03\x04"), ("docx", b"PK\x03\x04")])
def test_ooxml_render_signature_content_and_xml_safety(fmt, sig):
    pytest.importorskip(fmt)  # 라이브러리 미설치 환경은 skip
    data, mime, ext = render_report(_sample_model(), fmt)
    assert ext == fmt
    assert data[:4] == sig, f"{fmt} 유효 OOXML 시그니처 아님"
    text = _zip_text(data)
    # 핵심 데이터 존재
    assert "11,465" in text, f"{fmt} 통합 대지면적 누락"
    assert "사업이익률" in text
    # 정직표기: None 은 '—', XML 특수문자는 이스케이프되어 리터럴 보존(문서 안깨짐)
    assert "—" in text, f"{fmt} 빈값 정직표기(—) 누락"
    assert "예시" in text  # '<예시>' 가 살아있음(주입으로 문서 안깨짐)


def test_unknown_format_falls_back_to_pdf():
    data, mime, ext = render_report(_sample_model(), "xlsx")
    assert ext == "pdf" and data[:4] == b"%PDF"


def test_no_formula_duplication_in_render_package():
    """렌더 패키지는 '표현'만 — 도메인 산식 서비스를 임포트하지 않는다(어댑터 제외)."""
    import pathlib

    render_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "report" / "render"
    forbidden = ("feasibility_service", "monte_carlo", "gresb_scoring", "kr_tax", "avm_service")
    for py in render_dir.glob("*.py"):
        if py.name == "adapters.py":  # 어댑터만 도메인 서비스(PipelineReportService) 재사용 허용
            continue
        src = py.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in src, f"{py.name} 이 도메인 산식 {token} 을 임포트/재구현(산식 복제 금지)"


@pytest.mark.parametrize("fmt", ["pdf", "pptx", "docx"])
def test_bank_adapter_renders_all_formats(fmt):
    """은행제출용 보고서(bank dict) → 3포맷 렌더 + 미확보 섹션·완성도 정직 표기."""
    if fmt != "pdf":
        pytest.importorskip(fmt)
    from app.services.report.render import build_report_model_from_bank

    bank = {
        "meta": {"title": "사업성 분석 보고서 — <샘플>", "generated_at": "2026-07-03",
                 "legal_disclaimer": "AI 기반 자동 분석 결과."},
        "sections": [
            {"id": "summary", "title": "1. 사업개요", "has_data": True,
             "content": {"address": "용인 <샘플> & 처인", "land_area_sqm": 11465, "estimated_value": 0}},
            {"id": "esg", "title": "9. ESG 분석", "has_data": False, "content": {}},
        ],
        "completeness": {"total": 2, "filled": 1, "empty": 1, "pct": 50},
    }
    model = build_report_model_from_bank(bank)
    data, _mime, ext = render_report(model, fmt)
    assert ext == fmt and len(data) > 500
    sig = b"%PDF" if fmt == "pdf" else b"PK\x03\x04"
    assert data[:4] == sig
    if fmt != "pdf":
        text = _zip_text(data)
        assert "11,465" in text  # 통합 대지면적
        assert "미확보" in text  # ESG 미확보 섹션 정직 표기
