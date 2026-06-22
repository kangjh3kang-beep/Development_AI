"""INC-17 — 도면 업로드 인테이크: base64 → drawings(data-uri) 구성 + POST /analyze/upload 위임.

이미지=data-uri 1시트, PDF=PyMuPDF 분할(미설치 graceful degrade), 비지원/빈/거대/잘못된 base64 거부.
"""
import base64

import pytest

from app.adapters.vision import upload_intake as ui
from app.adapters.vision.upload_intake import UploadError, build_drawings
from app.api import deps

# 1x1 투명 PNG.
_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def test_build_drawings_image_to_datauri():
    out = build_drawings([{"filename": "site.png", "content_base64": _PNG, "sheet_role": "SITE"}])
    assert len(out) == 1
    d = out[0]
    assert d["sheet_id"] == "site.png" and d["sheet_role"] == "SITE"
    assert d["image_ref"].startswith("data:image/png;base64,")


def test_build_drawings_media_from_magic_not_extension():
    # ★확장자(.jpg)와 실제 바이트(PNG) 불일치 시 매직바이트가 우선 — 선언/페이로드 일치 보장(비전 API 거부 방지).
    out = build_drawings([{"filename": "p.jpg", "content_base64": f"data:image/jpeg;base64,{_PNG}"}])
    assert out[0]["image_ref"].startswith("data:image/png;base64,")  # 매직=PNG


def test_build_drawings_accepts_urlsafe_base64():
    urlsafe = base64.urlsafe_b64encode(base64.b64decode(_PNG)).decode("ascii")
    out = build_drawings([{"filename": "u.png", "content_base64": urlsafe}])
    assert out[0]["image_ref"].startswith("data:image/png;base64,")


def test_build_drawings_unique_sheet_ids_for_same_filename():
    # 동일 파일명 다중 업로드 → sheet_id 고유화(합의 단계 무음 병합 방지).
    out = build_drawings([{"filename": "a.png", "content_base64": _PNG},
                          {"filename": "a.png", "content_base64": _PNG}])
    assert out[0]["sheet_id"] != out[1]["sheet_id"]


def test_build_drawings_dos_guards(monkeypatch):
    # 파일 수 상한.
    monkeypatch.setattr(ui, "_MAX_FILES", 1)
    with pytest.raises(UploadError, match="too_many_files"):
        build_drawings([{"filename": "a.png", "content_base64": _PNG},
                        {"filename": "b.png", "content_base64": _PNG}])
    monkeypatch.setattr(ui, "_MAX_FILES", 50)
    # 요청 누적 총량 상한.
    monkeypatch.setattr(ui, "_MAX_TOTAL_BYTES", 4)
    with pytest.raises(UploadError, match="total_too_large"):
        build_drawings([{"filename": "a.png", "content_base64": _PNG}])


def test_build_drawings_rejects_unsupported_and_empty():
    with pytest.raises(UploadError, match="no_files"):
        build_drawings([])
    with pytest.raises(UploadError, match="content_base64_missing"):
        build_drawings([{"filename": "x.png"}])
    # ★비이미지 콘텐츠(매직 미인식) → unsupported. (.png 위장이어도 매직 우선이라 거부.)
    _txt = base64.b64encode(b"plain text content, definitely not an image").decode("ascii")
    with pytest.raises(UploadError, match="unsupported_type"):
        build_drawings([{"filename": "x.png", "content_base64": _txt}])
    with pytest.raises(UploadError, match="invalid_base64"):
        build_drawings([{"filename": "x.png", "content_base64": "!!notbase64!!"}])


def test_build_drawings_size_guard(monkeypatch):
    monkeypatch.setattr(ui, "_MAX_BYTES", 4)  # 4바이트 상한 — 1x1 PNG는 초과
    with pytest.raises(UploadError, match="file_too_large"):
        build_drawings([{"filename": "x.png", "content_base64": _PNG}])


def test_build_drawings_pdf_graceful_degrade_when_no_pymupdf():
    # PyMuPDF 미설치 환경 → PDF는 pdf_split_unavailable(graceful degrade, 무음 통과 금지). 매직바이트 판별.
    pdf_b64 = base64.b64encode(b"%PDF-1.4\n%fake minimal").decode("ascii")
    try:
        import fitz  # noqa: F401
    except ImportError:
        with pytest.raises(UploadError, match="pdf_split_unavailable"):
            build_drawings([{"filename": "plan.pdf", "content_base64": pdf_b64}])
    else:
        pytest.skip("PyMuPDF 설치됨 — degrade 경로 비해당(분할 성공 케이스는 통합테스트)")


def test_upload_endpoint_builds_drawings_and_analyzes(client):
    resp = client.post("/api/v1/analyze/upload", json={
        "pnu": "1111010100100000002", "application_date": "2026-01-01",
        "files": [{"filename": "site.png", "content_base64": _PNG, "sheet_role": "SITE"}],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("report") is not None  # 정상 AnalysisResult(파이프라인 위임 성공)
    # 업로드가 drawings로 합류돼 도면 자동해석 경로 진입(mock 모드면 graceful).
    assert body.get("drawing_source") in ("VLLM_VISION", "HINTS", "none", None)


def test_upload_endpoint_rejects_bad_file(client):
    _txt = base64.b64encode(b"not an image at all").decode("ascii")
    resp = client.post("/api/v1/analyze/upload", json={
        "files": [{"filename": "x.png", "content_base64": _txt}]})
    assert resp.status_code == 422 and "upload_error" in resp.text


def test_upload_endpoint_requires_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    r = client.post("/api/v1/analyze/upload", json={
        "files": [{"filename": "s.png", "content_base64": _PNG}]})
    assert r.status_code == 401
