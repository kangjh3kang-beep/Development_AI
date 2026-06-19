"""INC-17 — 도면 업로드 인테이크: 업로드 콘텐츠(base64) → AnalysisInput.drawings[].image_ref(data-uri) 자동 구성.

멀티파트 의존(python-multipart) 없이 JSON base64 수신(프런트 FileReader.readAsDataURL 호환, URL-safe도 허용).
이미지는 ★매직바이트로 실제 포맷 판별(확장자 위조/불일치 방어) 후 data-uri 인라인 — 파일시스템 쓰기·경로탈출 표면이
없어 image_source.build_image_block의 data: 경로가 그대로 소비. PDF는 PyMuPDF(fitz, 선택 의존)로 페이지→시트 분할;
미설치 시 graceful degrade. DoS 방어: 파일당/요청 누적/PDF 페이지·렌더 출력 상한(작은 입력의 증폭 차단).
목적: 사용자가 시트별 image_ref를 손으로 JSON에 적던 진입장벽 제거(멀티모달 설계도면 자동분석 편의성 최대 갭 해소).
"""
from __future__ import annotations

import base64
import binascii

# 운영 상수(법정 파라미터 아님 — INV-3 무관). DoS 증폭 차단의 다층 상한.
_MAX_BYTES = 20 * 1024 * 1024        # 파일 1건 입력 상한
_MAX_FILES = 50                       # 요청당 파일 수 상한
_MAX_TOTAL_BYTES = 80 * 1024 * 1024   # 요청 누적 입력·출력 합 상한(증폭 방어)
_MAX_PDF_PAGES = 200                  # PDF 페이지 상한(PDF 폭탄 방어)
_PDF_DPI = 150                        # PDF 페이지 렌더 해상도
_MAX_PIXELS = 40_000_000              # 페이지 렌더 픽셀 면적 상한(거대 MediaBox OOM 차단; A0@150DPI≈35M 허용)


class UploadError(ValueError):
    """업로드 인테이크 거부(빈/비지원/거대/잘못된 base64/PDF미지원/상한초과) — 라우터가 422로 표면화."""


def _image_media_from_magic(raw: bytes) -> str | None:
    """매직바이트로 실제 이미지 media type 판별(확장자 불신). 미지 포맷은 None."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def _decode(content_b64: str) -> bytes:
    """base64(data-uri/표준/URL-safe) → bytes. 잘못된 인코딩·빈·상한초과는 UploadError(무음 통과 금지)."""
    s = (content_b64.split(",", 1)[-1] if content_b64.startswith("data:") else content_b64).strip()
    try:
        raw = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        try:  # URL-safe base64 폴백(프런트 인코딩 차이 흡수). 패딩 보정.
            raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        except (binascii.Error, ValueError) as exc:
            raise UploadError("invalid_base64") from exc
    if not raw:
        raise UploadError("empty_content")
    if len(raw) > _MAX_BYTES:
        raise UploadError("file_too_large")
    return raw


def _pdf_to_data_uris(raw: bytes, out_budget: int) -> list[str]:
    """PDF bytes → 페이지별 PNG data-uri. PyMuPDF 미설치 시 UploadError(graceful degrade).
    ★PDF 폭탄(작은 입력→멀티GB 증폭) 다층 차단: 페이지 수 상한 + **렌더 전 픽셀 면적 상한**(거대 MediaBox OOM
    방지) + 출력 누적이 out_budget(요청 공유 잔여예산) 초과 시 거부."""
    try:
        import fitz  # PyMuPDF (선택 의존)
    except ImportError as exc:
        raise UploadError("pdf_split_unavailable") from exc
    uris: list[str] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        if doc.page_count > _MAX_PDF_PAGES:
            raise UploadError("pdf_too_many_pages")
        used = 0
        for page in doc:
            r = page.rect  # 렌더 전 예상 픽셀 면적 검사(get_pixmap의 거대 할당 차단)
            if (r.width * _PDF_DPI / 72.0) * (r.height * _PDF_DPI / 72.0) > _MAX_PIXELS:
                raise UploadError("pdf_page_too_large")
            uri = "data:image/png;base64," + base64.b64encode(
                page.get_pixmap(dpi=_PDF_DPI).tobytes("png")).decode("ascii")
            used += len(uri)
            if used > out_budget:  # 요청 공유 출력 예산(다중 PDF 합산 증폭 차단)
                raise UploadError("pdf_render_too_large")
            uris.append(uri)
    finally:
        doc.close()
    if not uris:
        raise UploadError("pdf_no_pages")
    return uris


def build_drawings(files: list[dict]) -> list[dict]:
    """업로드 파일 목록 → AnalysisInput.drawings 항목. files=[{filename, content_base64, sheet_role?}].

    이미지=1 시트(매직 판별 media의 data-uri), PDF=페이지별 시트 자동 분할. sheet_id 고유 보장(합의 단계 무음 병합 방지).
    결정론(동일 입력 동일 출력). 빈/비지원/거대/잘못된 base64/PDF미지원/상한초과는 UploadError."""
    if not files:
        raise UploadError("no_files")
    if len(files) > _MAX_FILES:
        raise UploadError("too_many_files")
    drawings: list[dict] = []
    seen: set[str] = set()
    total_in = 0   # 누적 입력 raw(디코드 메모리 방어)
    total_out = 0  # 누적 출력 data-uri(다운스트림/영속 증폭 방어) — 입력·출력 모두 _MAX_TOTAL_BYTES 공유

    def _uid(base: str) -> str:
        sid, n = base, 1
        while sid in seen:
            sid, n = f"{base}#{n}", n + 1
        seen.add(sid)
        return sid

    for i, f in enumerate(files):
        if not isinstance(f, dict) or not f.get("content_base64"):
            raise UploadError(f"files[{i}].content_base64_missing")
        filename = str(f.get("filename") or f"upload{i}")
        role = f.get("sheet_role")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        raw = _decode(str(f["content_base64"]))
        total_in += len(raw)
        if total_in > _MAX_TOTAL_BYTES:
            raise UploadError("total_too_large")
        if ext == "pdf" or raw[:5] == b"%PDF-":
            for p, uri in enumerate(_pdf_to_data_uris(raw, _MAX_TOTAL_BYTES - total_out)):
                total_out += len(uri)  # PDF 출력도 공유 예산에 정산(다중 PDF 합산 증폭 차단)
                drawings.append({"sheet_id": _uid(f"{filename}#p{p + 1}"), "image_ref": uri, "sheet_role": role})
        elif (media := _image_media_from_magic(raw)) is not None:  # 확장자 아닌 실제 매직으로 media 결정
            uri = f"data:{media};base64," + base64.b64encode(raw).decode("ascii")
            total_out += len(uri)
            if total_out > _MAX_TOTAL_BYTES:
                raise UploadError("total_too_large")
            drawings.append({"sheet_id": _uid(filename), "image_ref": uri, "sheet_role": role})
        else:
            raise UploadError(f"files[{i}].unsupported_type:{ext or 'unknown'}")
    return drawings
