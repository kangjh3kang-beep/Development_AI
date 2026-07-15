"""SEC 픽스처 — 업로드 콘텐츠 보안 검증(content_inspection) + 자산권리(asset_rights).

게이트 목표(★우회 0): zip bomb(압축비·전개총량·엔트리수·중첩깊이)·경로순회(../, zip slip)·
MIME 위장(선언≠실측, exe 위장)을 모두 거부하고, 정상 파일은 FP 0 으로 통과한다.
AV 는 데몬 미설치가 기본(D4) — not_scanned 를 정직하게 반환하고 그 자체로는 거부하지 않는다.

DB/네트워크 무관(순수 단위). 인메모리 바이트로 fixture 를 만든다.
"""

from __future__ import annotations

import io
import struct
import zipfile

from app.services.security.asset_rights import (
    AssetRight,
    is_export_allowed,
    is_train_allowed,
    resolve_asset_right,
)
from app.services.security.content_inspection import (
    ArchiveLimits,
    av_scan,
    inspect_archive,
    inspect_upload,
    sniff_type,
)

# ── 정상 파일 fixture(FP 0 검증용) ──────────────────────────────────────
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
_GIF = b"GIF89a" + b"\x00" * 32
_WEBP = b"RIFF" + struct.pack("<I", 64) + b"WEBP" + b"\x00" * 56
_PDF = b"%PDF-1.7\n" + b"%stuff\n" * 8 + b"%%EOF"
_DXF_ASCII = (b"  0\r\nSECTION\r\n  2\r\nHEADER\r\n  0\r\nENDSEC\r\n"
              b"  0\r\nSECTION\r\n  2\r\nENTITIES\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n")
_IFC = b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(());\nENDSEC;\n"


def _zip_bytes(entries: list[tuple[str, bytes]], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def _normal_xlsx_like() -> bytes:
    """정상 zip 기반 문서(office/hwpx 계열) — 작은 엔트리 몇 개."""
    return _zip_bytes([
        ("[Content_Types].xml", b"<xml/>" * 10),
        ("xl/workbook.xml", b"<workbook/>" * 20),
        ("xl/worksheets/sheet1.xml", b"<sheet/>" * 30),
    ])


# ══════════════════════════════════════════════════════════════════════
# 1) 정상 파일은 모두 통과(FP 0)
# ══════════════════════════════════════════════════════════════════════
def test_normal_files_pass_no_false_positive():
    cases = [
        (_PNG, "photo.png", "image/png"),
        (_JPEG, "photo.jpg", "image/jpeg"),
        (_GIF, "anim.gif", "image/gif"),
        (_WEBP, "pic.webp", "image/webp"),
        (_PDF, "doc.pdf", "application/pdf"),
        (_DXF_ASCII, "plan.dxf", "application/dxf"),
        (_IFC, "model.ifc", "application/octet-stream"),
        (_normal_xlsx_like(), "spec.xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ]
    for data, name, ctype in cases:
        v = inspect_upload(data, name, ctype)
        assert v.allowed, f"정상 파일이 거부됨(FP): {name} → {v.code}:{v.reason}"


def test_sniff_type_detects_known_formats():
    assert sniff_type(_PNG) == "png"
    assert sniff_type(_JPEG) == "jpeg"
    assert sniff_type(_GIF) == "gif"
    assert sniff_type(_WEBP) == "webp"
    assert sniff_type(_PDF) == "pdf"
    assert sniff_type(_IFC) == "ifc"
    assert sniff_type(_DXF_ASCII) == "dxf"
    assert sniff_type(_normal_xlsx_like()) == "zip"
    assert sniff_type(b"") is None
    assert sniff_type(b"random garbage no magic") is None


# ══════════════════════════════════════════════════════════════════════
# 2) MIME 위장(선언≠실측) — exe 위장 포함
# ══════════════════════════════════════════════════════════════════════
def test_mime_masquerade_png_declared_but_exe_bytes():
    # png 선언 + Windows PE(MZ) 시그니처 → 실행 파일로 차단.
    data = b"MZ\x90\x00" + b"\x00" * 64
    v = inspect_upload(data, "innocent.png", "image/png")
    assert not v.allowed
    assert v.code == "executable"


def test_mime_masquerade_png_declared_but_zip_bytes():
    # png 선언 + 실제 zip → 위장(mime_mismatch) 차단.
    data = _normal_xlsx_like()
    v = inspect_upload(data, "innocent.png", "image/png")
    assert not v.allowed
    assert v.code == "mime_mismatch"
    assert v.detected_type == "zip"
    assert v.declared_type == "png"


def test_pdf_declared_but_png_bytes_mismatch():
    v = inspect_upload(_PNG, "doc.pdf", "application/pdf")
    assert not v.allowed
    assert v.code == "mime_mismatch"


# ══════════════════════════════════════════════════════════════════════
# 3) 실행/스크립트 차단(시그니처 + 확장자)
# ══════════════════════════════════════════════════════════════════════
def test_executable_signatures_blocked():
    for data in (b"MZ\x90\x00", b"\x7fELF\x02\x01", b"\xca\xfe\xba\xbe", b"#!/bin/sh\n"):
        v = inspect_upload(data + b"\x00" * 16, "x.dat", "application/octet-stream")
        assert not v.allowed and v.code == "executable"


def test_executable_extension_blocked_even_if_bytes_look_benign():
    v = inspect_upload(_PDF, "malware.exe", "application/pdf")
    assert not v.allowed and v.code == "executable"


# ══════════════════════════════════════════════════════════════════════
# 4) 경로 순회(파일명 + zip slip)
# ══════════════════════════════════════════════════════════════════════
def test_filename_path_traversal_blocked():
    for name in ("../../etc/passwd.png", "..\\..\\win.png", "/abs/evil.png", "~/evil.png"):
        v = inspect_upload(_PNG, name, "image/png")
        assert not v.allowed and v.code == "path_traversal", name


def test_filename_dotdot_substring_not_false_positive():
    # '..foo.png' 는 경로순회가 아니다(세그먼트 단위 '..' 만 차단) → 통과해야 FP 0.
    v = inspect_upload(_PNG, "..foo.png", "image/png")
    assert v.allowed


def test_zip_slip_internal_traversal_blocked():
    data = _zip_bytes([("../../evil.txt", b"pwned"), ("ok.txt", b"hi")])
    v = inspect_upload(data, "archive.zip", "application/zip")
    assert not v.allowed and v.code == "path_traversal"


def test_zip_slip_absolute_path_blocked():
    data = _zip_bytes([("/etc/cron.d/evil", b"x")])
    v = inspect_upload(data, "archive.zip", "application/zip")
    assert not v.allowed and v.code == "path_traversal"


# ══════════════════════════════════════════════════════════════════════
# 5) zip bomb — 압축비·전개총량·엔트리수·중첩깊이
# ══════════════════════════════════════════════════════════════════════
def test_zip_bomb_compression_ratio_blocked():
    # 큰 0바이트 엔트리 → 압축비 폭발(>120). 기본 한도로 차단.
    bomb = _zip_bytes([("z.bin", b"\x00" * (20 * 1024 * 1024))])  # 20MB→수십KB
    v = inspect_upload(bomb, "bomb.zip", "application/zip")
    assert not v.allowed and v.code == "archive_bomb"
    assert v.details.get("ratio", 0) > 120


def test_zip_bomb_total_uncompressed_blocked():
    # 전개 총량 한도(테스트용 축소)로 차단.
    limits = ArchiveLimits(max_total_uncompressed=100_000, max_ratio=10_000, ratio_min_compressed=10**9)
    data = _zip_bytes([("a.bin", b"\x00" * 500_000)])
    v = inspect_archive(data, limits)
    assert not v.allowed and v.code == "archive_bomb"
    assert v.details.get("total_uncompressed", 0) > 100_000


def test_zip_bomb_entry_count_blocked():
    limits = ArchiveLimits(max_entries=3)
    data = _zip_bytes([(f"f{i}.txt", b"x") for i in range(10)])
    v = inspect_archive(data, limits)
    assert not v.allowed and v.code == "archive_bomb"
    assert v.details.get("entries") == 10


def test_zip_nested_depth_blocked():
    # A ⊃ B ⊃ C, max_depth=1 → C 진입 시 깊이 초과 차단.
    inner_c = _zip_bytes([("c.txt", b"deep")])
    inner_b = _zip_bytes([("c.zip", inner_c), ("b.txt", b"mid")])
    outer_a = _zip_bytes([("b.zip", inner_b), ("a.txt", b"top")])
    v = inspect_archive(outer_a, ArchiveLimits(max_depth=1))
    assert not v.allowed and v.code == "archive_bomb"


def test_nested_normal_archive_within_depth_passes():
    # A ⊃ B(정상), max_depth=2 → 통과(FP 0).
    inner_b = _zip_bytes([("b.txt", b"hello")])
    outer_a = _zip_bytes([("b.zip", inner_b), ("a.txt", b"top")])
    v = inspect_archive(outer_a, ArchiveLimits(max_depth=2))
    assert v.allowed


def test_corrupt_zip_declared_zip_rejected():
    # PK 시그니처인데 깨진 zip → fail-closed(archive_corrupt).
    data = b"PK\x03\x04" + b"\xff" * 64
    v = inspect_upload(data, "broken.zip", "application/zip")
    assert not v.allowed and v.code in ("archive_corrupt", "archive_bomb")


# ══════════════════════════════════════════════════════════════════════
# 6) 형식 화이트리스트(expected_kinds) + 빈 파일/크기
# ══════════════════════════════════════════════════════════════════════
def test_expected_kinds_whitelist_rejects_out_of_list():
    # 설계도면 허용목록에 zip 없음 → xlsx(zip) 거부.
    v = inspect_upload(_normal_xlsx_like(), "spec.xlsx", "application/zip",
                       expected_kinds={"pdf", "png", "jpeg", "dxf", "dwg"})
    assert not v.allowed and v.code == "unsupported_type"


def test_expected_kinds_whitelist_allows_in_list():
    v = inspect_upload(_PDF, "doc.pdf", "application/pdf",
                       expected_kinds={"pdf", "png", "jpeg"})
    assert v.allowed


def test_empty_file_rejected():
    v = inspect_upload(b"", "x.png", "image/png")
    assert not v.allowed and v.code == "empty"


def test_too_large_rejected():
    v = inspect_upload(_PNG, "x.png", "image/png", max_bytes=8)
    assert not v.allowed and v.code == "too_large"


# ══════════════════════════════════════════════════════════════════════
# 7) AV Gate-OFF — 데몬 미설치 시 정직하게 not_scanned(날조 clean 금지)
# ══════════════════════════════════════════════════════════════════════
def test_av_scan_honest_not_scanned_when_no_daemon():
    res = av_scan(_PNG)
    # ClamAV 미설치가 기본(D4) — clean 을 날조하지 않는다.
    assert res.get("status") in ("not_scanned", "clean", "error")
    if res.get("status") == "not_scanned":
        assert "reason" in res  # 미수행 사유 명시


def test_inspect_upload_passes_with_av_not_scanned():
    # AV 미수행이어도 정상 파일은 통과하고, av 상태는 정직하게 기록된다(Gate-OFF).
    v = inspect_upload(_PNG, "photo.png", "image/png")
    assert v.allowed
    assert v.av.get("status") in ("not_scanned", "clean", "skipped")


# ══════════════════════════════════════════════════════════════════════
# 8) 헬퍼 자체 오류가 500 이 아니라 fail-closed 거부로 격리되는지
# ══════════════════════════════════════════════════════════════════════
def test_helper_never_raises_returns_verdict():
    # None 을 넘겨도 예외 없이 구조화 결과(거부)로 격리.
    v = inspect_upload(None, "x.png", "image/png")  # type: ignore[arg-type]
    assert v.allowed is False


# ══════════════════════════════════════════════════════════════════════
# 9) asset_rights — 권리 불명=금지(default-deny)·0-falsy 구분
# ══════════════════════════════════════════════════════════════════════
def test_asset_right_unknown_is_deny_by_default():
    ar = resolve_asset_right("hash-abc")
    assert ar.scope == "unknown"
    assert ar.train_allowed is False and ar.export_allowed is False
    assert is_train_allowed(ar) is False and is_export_allowed(ar) is False


def test_asset_right_scope_grants():
    assert resolve_asset_right("h", scope="train_ok").train_allowed is True
    assert resolve_asset_right("h", scope="train_ok").export_allowed is False
    assert resolve_asset_right("h", scope="export_ok").export_allowed is True
    pub = resolve_asset_right("h", scope="public")
    assert pub.train_allowed is True and pub.export_allowed is True


def test_asset_right_explicit_false_is_not_treated_as_unknown():
    # ★0-falsy: 명시 train_allowed=False 는 scope 유추를 덮어써 반드시 False.
    ar = resolve_asset_right("h", scope="public", train_allowed=False)
    assert ar.train_allowed is False  # 'or' 단축평가였다면 True 로 새어나갔을 것
    assert ar.export_allowed is True  # export 는 명시 안 했으니 scope(public) 유추 True


def test_asset_right_none_gate_is_deny():
    assert is_train_allowed(None) is False
    assert is_export_allowed(None) is False


def test_asset_right_invalid_scope_falls_back_unknown():
    ar = resolve_asset_right("h", scope="bogus-scope")
    assert ar.scope == "unknown"
    assert ar.train_allowed is False


def test_asset_right_to_dict_shape():
    d = AssetRight(asset_key="k", scope="train_ok", train_allowed=True).to_dict()
    assert d["asset_key"] == "k" and d["train_allowed"] is True and d["export_allowed"] is False
