"""렌더 디스패치 — 정본 ReportModel + 포맷 → (bytes, MIME, 확장자).

지연 임포트: 포맷별 렌더러가 무거운 라이브러리를 쓰므로 요청 포맷만 로드.
알 수 없는 포맷은 PDF 로 정직 폴백(에러 대신 안전).
"""

from __future__ import annotations

from .model import ReportModel

_MIME = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

SUPPORTED_FORMATS = tuple(_MIME.keys())


def render_report(model: ReportModel, fmt: str = "pdf") -> tuple[bytes, str, str]:
    """정본 모델을 원하는 포맷으로 렌더. 반환=(파일 bytes, MIME, 확장자).

    ★W1-C 발행 게이트: publish_gate.check_publishable 위반(APPROVED 라벨 사칭·미승인 확정
    표현·가정의 사실화)이 있으면 예외로 차단한다. 위반이 없으면(대다수 기존 DRAFT 보고서)
    기존과 동일하게 통과한다(무회귀).
    """
    from .publish_gate import ReportPublishGateError, check_publishable

    gate = check_publishable(model)
    if not gate.ok:
        raise ReportPublishGateError(gate)

    f = (fmt or "pdf").strip().lower()
    if f not in _MIME:
        f = "pdf"  # 미지원 포맷은 PDF 폴백

    if f == "pdf":
        from .pdf_renderer import render_pdf

        data = render_pdf(model)
    elif f == "pptx":
        from .pptx_renderer import render_pptx

        data = render_pptx(model)
    else:  # docx
        from .docx_renderer import render_docx

        data = render_docx(model)

    return data, _MIME[f], f
