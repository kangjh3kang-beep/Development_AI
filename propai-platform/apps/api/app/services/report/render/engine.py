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
    """정본 모델을 원하는 포맷으로 렌더. 반환=(파일 bytes, MIME, 확장자)."""
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
