"""종합 보고서 PDF 생성 태스크.

프로젝트의 모든 분석 결과를 종합하여 PDF 보고서를 생성한다.
ReportLab으로 생성 후 MinIO에 저장.
"""

import io
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


async def run_generate_report_pdf(
    ctx: dict[str, Any],
    project_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """종합 보고서 PDF 생성.

    1. 프로젝트 관련 전체 데이터 DB 조회
    2. ReportLab Canvas로 커버페이지/목차/본문 렌더링
    3. 나눔고딕 한글 폰트 등록
    4. MinIO 업로드
    """
    from miniopy_async import Minio
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    logger.info("PDF 보고서 생성 시작", project_id=project_id)

    settings = ctx["settings"]
    db = ctx["db"]

    # 1. 프로젝트 데이터 수집
    project_data = await _fetch_project_data(db, project_id)

    # 2. 한글 폰트 등록 (나눔고딕)
    try:
        pdfmetrics.registerFont(TTFont("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"))
        font_name = "NanumGothic"
    except Exception:
        font_name = "Helvetica"
        logger.debug("나눔고딕 폰트 없음 — Helvetica 폴백")

    # 3. PDF 생성
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "KoreanTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=24,
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "KoreanHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        spaceBefore=15,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "KoreanBody",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=14,
    )

    elements: list[Any] = []
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    # ── 커버페이지 ──
    elements.append(Spacer(1, 5 * cm))
    elements.append(Paragraph("PropAI", title_style))
    elements.append(Paragraph("부동산 개발 분석 종합 보고서", heading_style))
    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(f"프로젝트: {project_data.get('name', project_id)}", body_style))
    elements.append(Paragraph(f"생성일: {now}", body_style))
    elements.append(Spacer(1, 3 * cm))

    # ── AVM 시세 분석 ──
    avm = project_data.get("avm", {})
    if avm:
        elements.append(Paragraph("1. AVM 시세 분석", heading_style))
        avm_data = [
            ["항목", "값"],
            ["추정가격", f"{avm.get('estimated_price', 0):,.0f}원"],
            ["㎡당 단가", f"{avm.get('price_per_sqm', 0):,.0f}원"],
            ["신뢰도", f"{avm.get('confidence_score', 0):.1%}"],
            ["비교사례 수", f"{avm.get('comparable_count', 0)}건"],
            ["모델 버전", str(avm.get("model_version", "-"))],
        ]
        table = Table(avm_data, colWidths=[6 * cm, 10 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5 * cm))

    # ── 세금 분석 ──
    tax = project_data.get("tax", {})
    if tax:
        elements.append(Paragraph("2. 세금 분석", heading_style))
        tax_data = [
            ["세금 유형", str(tax.get("tax_type", "-"))],
            ["과세표준", f"{tax.get('taxable_value', 0):,.0f}원"],
            ["산출세액", f"{tax.get('amount', 0):,.0f}원"],
            ["적용세율", f"{tax.get('tax_rate', 0):.2%}"],
        ]
        table = Table([["항목", "값"]] + tax_data, colWidths=[6 * cm, 10 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5 * cm))

    # ── 법규 검토 ──
    regulation = project_data.get("regulation", {})
    if regulation:
        elements.append(Paragraph("3. 법규 검토", heading_style))
        compliant = "적합" if regulation.get("is_compliant") else "부적합"
        elements.append(Paragraph(f"적합 여부: {compliant}", body_style))
        violations = regulation.get("violations", [])
        if violations:
            elements.append(Paragraph(f"위반사항: {len(violations)}건", body_style))
        elements.append(Spacer(1, 0.5 * cm))

    # ── 면책 조항 ──
    elements.append(Spacer(1, 2 * cm))
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=body_style,
        fontSize=8,
        textColor=colors.grey,
    )
    elements.append(Paragraph(
        "※ 본 보고서는 AI 기반 자동 분석 결과이며, 투자 의사결정의 최종 근거로 사용할 수 없습니다. "
        "실제 투자 시 전문가 상담을 권장합니다. PropAI v30.0",
        disclaimer_style,
    ))

    doc.build(elements)

    # 4. MinIO 업로드
    pdf_bytes = buffer.getvalue()
    file_name = f"reports/{project_id}/{uuid4().hex}.pdf"

    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )

    bucket = "propai-reports"
    if not await minio_client.bucket_exists(bucket):
        await minio_client.make_bucket(bucket)

    await minio_client.put_object(
        bucket,
        file_name,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )

    pdf_url = f"{settings.minio_endpoint}/{bucket}/{file_name}"

    logger.info("PDF 보고서 생성 완료", project_id=project_id, url=pdf_url)
    return {
        "status": "completed",
        "project_id": project_id,
        "pdf_url": pdf_url,
        "pages": doc.page,
    }


async def _fetch_project_data(db: Any, project_id: str) -> dict[str, Any]:
    """프로젝트 관련 전체 데이터를 DB에서 조회한다."""
    from sqlalchemy import text

    result: dict[str, Any] = {"project_id": project_id}

    # 프로젝트 기본 정보
    row = await db.execute(
        text("SELECT name, status FROM projects WHERE id = :pid"),
        {"pid": project_id},
    )
    proj = row.fetchone()
    if proj:
        result["name"] = proj.name
        result["status"] = proj.status

    # AVM 최신 결과
    row = await db.execute(
        text(
            "SELECT estimated_price, price_per_sqm, confidence_score, "
            "comparable_count, model_version "
            "FROM avm_valuations WHERE project_id = :pid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"pid": project_id},
    )
    avm = row.fetchone()
    if avm:
        result["avm"] = {
            "estimated_price": avm.estimated_price,
            "price_per_sqm": avm.price_per_sqm,
            "confidence_score": avm.confidence_score,
            "comparable_count": avm.comparable_count,
            "model_version": avm.model_version,
        }

    # 세금 최신 결과
    row = await db.execute(
        text(
            "SELECT tax_type, amount, taxable_value, tax_rate "
            "FROM tax_calculations WHERE project_id = :pid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"pid": project_id},
    )
    tax = row.fetchone()
    if tax:
        result["tax"] = {
            "tax_type": tax.tax_type,
            "amount": tax.amount,
            "taxable_value": tax.taxable_value,
            "tax_rate": tax.tax_rate,
        }

    # 법규 검토 최신 결과
    row = await db.execute(
        text(
            "SELECT is_compliant, violations "
            "FROM regulation_checks WHERE project_id = :pid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"pid": project_id},
    )
    reg = row.fetchone()
    if reg:
        result["regulation"] = {
            "is_compliant": reg.is_compliant,
            "violations": reg.violations or [],
        }

    return result
