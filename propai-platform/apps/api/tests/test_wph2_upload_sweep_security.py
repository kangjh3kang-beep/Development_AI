"""WP-H 세션2 게이트 — 업로드 표면 전역 결선 + 안전추출 + P16 학습게이트.

세션1(SEC 52)이 봉합한 것 위에, 세션2가 추가한 3가지를 검증한다(★우회 0·무회귀):
  1) 잔여 업로드 표면 결선: 각 경로가 쓰는 expected_kinds 계약이 위장/폭탄을 거부하고 정상은 통과.
     - storage_service.upload_image: 서비스 계층에서 ContentRejectedError(4xx) 로 명시 거부.
     - excel/csv·xlsx·dxf·pdf·ifc 표면별 inspect_upload 설정의 거부/통과.
  2) 안전추출(safe_extract_archive): zip slip(../)·압축폭탄·손상 차단, 정상 zip 은 추출·확장자 선별.
  3) P16 학습게이트(keep_train_allowed): 권리불명·미등록 자산은 학습 0(default-deny).

DB/네트워크 무관(순수 단위). 인메모리 바이트 + tmp_path 로 fixture 를 만든다.
"""

from __future__ import annotations

import io
import struct
import zipfile

import pytest

from app.services.security.asset_rights import (
    AssetRight,
    is_train_allowed,
    keep_train_allowed,
    resolve_asset_right,
)
from app.services.security.content_inspection import (
    ArchiveLimits,
    http_status_for,
    inspect_upload,
    safe_extract_archive,
)
from apps.api.services.storage_service import (
    _IMAGE_UPLOAD_KINDS,
    ContentRejectedError,
    upload_image,
)

# ── 정상/위장 fixture ────────────────────────────────────────────────────
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
_WEBP = b"RIFF" + struct.pack("<I", 64) + b"WEBP" + b"\x00" * 56
_PDF = b"%PDF-1.7\n" + b"%stuff\n" * 8 + b"%%EOF"
_DXF_ASCII = (b"  0\r\nSECTION\r\n  2\r\nHEADER\r\n  0\r\nENDSEC\r\n"
              b"  0\r\nSECTION\r\n  2\r\nENTITIES\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n")
_IFC = b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(());\nENDSEC;\n"
_EXE = b"MZ\x90\x00" + b"\x00" * 64  # Windows PE 위장
_CSV = b"name,phone\n\xed\x99\x8d\xea\xb8\xb8\xeb\x8f\x99,010-1234-5678\n"  # 정상 CSV(매직 없음)


def _zip_bytes(entries, compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def _xlsx_like() -> bytes:
    """정상 xlsx(zip 기반) 최소형."""
    return _zip_bytes([
        ("[Content_Types].xml", b"<xml/>" * 10),
        ("xl/workbook.xml", b"<workbook/>" * 20),
    ])


# ══════════════════════════════════════════════════════════════════════
# 1) storage_service.upload_image — 서비스 계층 결선(ContentRejectedError, 4xx)
# ══════════════════════════════════════════════════════════════════════
async def test_upload_image_rejects_executable_disguised_as_png():
    """png 로 선언한 실행파일(MZ) → 네트워크 도달 전 ContentRejectedError(4xx)."""
    with pytest.raises(ContentRejectedError) as ei:
        await upload_image(_EXE, "image/png")
    assert ei.value.http_status < 500  # 클라이언트 귀책(4xx) — 인프라 502 아님
    assert ei.value.code == "executable"


async def test_upload_image_rejects_active_content_svg_mime():
    """무해한 바이트라도 content_type=svg(활성 콘텐츠) 선언이면 거부(저장형 XSS 차단)."""
    with pytest.raises(ContentRejectedError):
        await upload_image(_PNG, "image/svg+xml")


async def test_upload_image_rejects_mime_spoof_png_declared_jpeg_bytes():
    """png 선언인데 실제 jpeg 바이트 → 위장(mime_mismatch) 거부."""
    with pytest.raises(ContentRejectedError) as ei:
        await upload_image(_JPEG, "image/png")
    assert ei.value.code == "mime_mismatch"


def test_upload_image_kinds_whitelist_matches_allowed_types():
    """_IMAGE_UPLOAD_KINDS 는 이미지 4종만(문서·아카이브 불포함)."""
    assert frozenset({"png", "jpeg", "gif", "webp"}) == _IMAGE_UPLOAD_KINDS
    # 실측 계열이 이미지가 아니면 거부(예: pdf 를 이미지 업로드로).
    v = inspect_upload(_PDF, "x.pdf", "application/pdf", expected_kinds=_IMAGE_UPLOAD_KINDS)
    assert not v.allowed and v.code == "unsupported_type"


# ══════════════════════════════════════════════════════════════════════
# 2) 표면별 inspect_upload 설정 계약(각 라우터가 쓰는 expected_kinds)
# ══════════════════════════════════════════════════════════════════════
def test_excel_csv_surface_no_whitelist_allows_csv_blocks_bomb_and_exe():
    """auto_zoning parse_parcels·auction watchlist(엑셀+CSV): expected_kinds 없음.
    정상 CSV·xlsx 통과 / 실행위장·압축폭탄(폴리글랏 포함) 거부."""
    assert inspect_upload(_CSV, "list.csv", "text/csv").allowed
    assert inspect_upload(_xlsx_like(), "list.xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet").allowed
    assert not inspect_upload(_EXE, "list.csv", "text/csv").allowed
    # 압축폭탄(비율) — expected_kinds 무관하게 아카이브 검사가 동작.
    bomb = _zip_bytes([("big.bin", b"\x00" * 5_000_000)])
    vb = inspect_upload(bomb, "list.xlsx", None)
    assert not vb.allowed and vb.code == "archive_bomb"


def test_xlsx_only_surface_zip_whitelist_blocks_exe_and_csv():
    """registry land_schedule·sales draw_import(xlsx 전용): expected_kinds={"zip"}.
    정상 xlsx 통과 / 실행위장 거부 / 매직없는 CSV 는 미인식(unsupported)."""
    assert inspect_upload(_xlsx_like(), "a.xlsx", None, expected_kinds={"zip"}).allowed
    assert not inspect_upload(_EXE, "a.xlsx", None, expected_kinds={"zip"}).allowed
    v = inspect_upload(_CSV, "a.csv", "text/csv", expected_kinds={"zip"})
    assert not v.allowed and v.code == "unsupported_type"


def test_dxf_surface_whitelist():
    """design_v61 import-dxf·design_references geometry·design_audit dxf: expected_kinds={"dxf"}."""
    assert inspect_upload(_DXF_ASCII, "plan.dxf", "application/dxf", expected_kinds={"dxf"}).allowed
    assert not inspect_upload(_PNG, "plan.dxf", "image/png", expected_kinds={"dxf"}).allowed
    assert not inspect_upload(_EXE, "plan.dxf", None, expected_kinds={"dxf"}).allowed


def test_pdf_surface_whitelist():
    """design_audit extract-brief: expected_kinds={"pdf"}. pdf 통과 / zip 거부."""
    assert inspect_upload(_PDF, "brief.pdf", "application/pdf", expected_kinds={"pdf"}).allowed
    assert not inspect_upload(_xlsx_like(), "brief.pdf", None, expected_kinds={"pdf"}).allowed


def test_ifc_surface_whitelist():
    """design_audit run-upload IFC: expected_kinds={"ifc"}. ifc 통과 / 실행위장 거부."""
    assert inspect_upload(_IFC, "m.ifc", "application/octet-stream", expected_kinds={"ifc"}).allowed
    assert not inspect_upload(_EXE, "m.ifc", None, expected_kinds={"ifc"}).allowed


def test_rejection_codes_map_to_4xx():
    """거부 코드는 모두 4xx(클라이언트 귀책) — 인프라 502 오분류 방지."""
    for code in ("executable", "mime_mismatch", "unsupported_type",
                 "archive_bomb", "path_traversal", "too_large"):
        assert 400 <= http_status_for(code) < 500


# ══════════════════════════════════════════════════════════════════════
# 3) safe_extract_archive — zip slip·bomb·손상 차단, 정상 추출·확장자 선별
# ══════════════════════════════════════════════════════════════════════
def test_safe_extract_normal_zip_writes_all(tmp_path):
    data = _zip_bytes([("a.txt", b"hello"), ("sub/b.txt", b"world")])
    res = safe_extract_archive(data, tmp_path / "out")
    assert res.ok and res.extracted == 2
    assert (tmp_path / "out" / "a.txt").read_bytes() == b"hello"
    assert (tmp_path / "out" / "sub" / "b.txt").read_bytes() == b"world"


def test_safe_extract_blocks_zip_slip(tmp_path):
    """../ 엔트리(zip slip) → path_traversal 거부, 대상 밖에 파일 미생성."""
    data = _zip_bytes([("ok.txt", b"ok"), ("../evil.txt", b"pwned")])
    res = safe_extract_archive(data, tmp_path / "out")
    assert not res.ok and res.code == "path_traversal"
    # 대상 폴더의 부모에 evil.txt 가 생기지 않아야 한다(정리됨).
    assert not (tmp_path / "evil.txt").exists()


def test_safe_extract_blocks_absolute_path_entry(tmp_path):
    data = _zip_bytes([("/etc/pwned", b"x")])
    res = safe_extract_archive(data, tmp_path / "out")
    assert not res.ok and res.code == "path_traversal"


def test_safe_extract_blocks_bomb_by_total(tmp_path):
    """전개 총량 상한 초과 → archive_bomb(부분 추출물 정리)."""
    data = _zip_bytes([("big.bin", b"\x00" * 100_000)])
    limits = ArchiveLimits(max_total_uncompressed=10_000)
    res = safe_extract_archive(data, tmp_path / "out", limits=limits)
    assert not res.ok and res.code == "archive_bomb"


def test_safe_extract_blocks_bomb_by_ratio(tmp_path):
    """압축비 초과 → archive_bomb."""
    data = _zip_bytes([("z.bin", b"\x00" * 5_000_000)])  # 5MB zeros → 비율 수백~수천
    res = safe_extract_archive(data, tmp_path / "out")
    assert not res.ok and res.code == "archive_bomb"


def test_safe_extract_corrupt_zip(tmp_path):
    res = safe_extract_archive(b"PK\x03\x04not-a-real-zip", tmp_path / "out")
    assert not res.ok and res.code in ("archive_corrupt", "extract_error")


def test_safe_extract_allowed_exts_filter(tmp_path):
    """allowed_exts 지정 시 해당 확장자만 추출(그 외는 건너뜀 — 거부 아님)."""
    data = _zip_bytes([("plan.dxf", b"0\nSECTION"), ("readme.txt", b"x"), ("logo.png", b"y")])
    res = safe_extract_archive(data, tmp_path / "out", allowed_exts=frozenset({"dxf"}))
    assert res.ok and res.extracted == 1
    assert (tmp_path / "out" / "plan.dxf").exists()
    assert not (tmp_path / "out" / "readme.txt").exists()


# ══════════════════════════════════════════════════════════════════════
# 4) P16 학습게이트 — keep_train_allowed (권리불명=학습 0)
# ══════════════════════════════════════════════════════════════════════
def test_keep_train_allowed_default_deny_unknown_and_unregistered():
    """미등록(None)·불명(unknown) 자산은 제외, 명시 train_ok 만 통과."""
    rows = [
        ("in1", "out1", "hashA"),  # train_ok
        ("in2", "out2", "hashB"),  # 미등록(None)
        ("in3", "out3", "hashC"),  # unknown(명시 등록됐지만 권리불명)
        ("in4", "out4", "hashD"),  # 명시 train_allowed=False
        ("in5", "out5", None),     # content_hash 없음 → 키 불가 → 제외
    ]
    rights = {
        "hashA": resolve_asset_right("hashA", scope="train_ok"),
        # hashB: 없음(None)
        "hashC": resolve_asset_right("hashC"),  # 기본 unknown → train False
        "hashD": AssetRight(asset_key="hashD", scope="internal_only", train_allowed=False),
    }
    kept, excluded = keep_train_allowed(rows, rights, key_index=2)
    kept_hashes = [r[2] for r in kept]
    assert kept_hashes == ["hashA"]
    assert excluded == 4


def test_is_train_allowed_none_is_false():
    """게이트 기본: right 없음(불명)=False(default-deny)."""
    assert is_train_allowed(None) is False
    assert is_train_allowed(resolve_asset_right("k")) is False  # unknown scope
    assert is_train_allowed(resolve_asset_right("k", scope="train_ok")) is True
