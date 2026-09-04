"""SEC 픽스처 — 업로드 콘텐츠 보안 검증(content_inspection) + 자산권리(asset_rights).

게이트 목표(★우회 0): zip bomb(압축비·전개총량·엔트리수·중첩깊이)·경로순회(../, zip slip)·
MIME 위장(선언≠실측, exe 위장)을 모두 거부하고, 정상 파일은 FP 0 으로 통과한다.
AV 는 데몬 미설치가 기본(D4) — not_scanned 를 정직하게 반환하고 그 자체로는 거부하지 않는다.

★분리리뷰 REVISE 재현 회귀(우회 PoC 5종, 모두 이 파일에서 재현·수정 검증):
  #1 폴리글랏(선두 매직 위장) + 확장자 리네임 중첩 아카이브 — content-based 트리거로 봉합.
  #2 콘텐츠 거부가 502 로 오분류 — ContentRejectedError.http_status(4xx) 로 봉합.
  #3 expected_kinds 미지정으로 미인식 형식 무통제 통과 — 실제 결선(ingest/storage) 회귀 확인.
  #4 HTML/SVG 등 웹 활성 콘텐츠가 이미지·문서 위장으로 통과 — _BLOCKED_EXTS·MIME 확장.
  #5 central directory 크기신뢰 한계 — docstring 정직화(코드는 스푸핑 감지 백스톱 추가).

DB/네트워크 무관(순수 단위). 인메모리 바이트로 fixture 를 만든다.
"""

from __future__ import annotations

import io
import struct
import zipfile

from app.services.design_ingest.ingest_service import ingest_design_file
from app.services.security.asset_rights import (
    AssetRight,
    is_export_allowed,
    is_train_allowed,
    resolve_asset_right,
)
from app.services.security.content_inspection import (
    ArchiveLimits,
    av_scan,
    http_status_for,
    inspect_archive,
    inspect_upload,
    sniff_type,
)
from apps.api.services.storage_service import ContentRejectedError, upload_design_file

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


def test_percent_encoded_traversal_blocked():
    # 권장 반영 — 퍼센트 인코딩 우회(%2e%2e%2f = ../) 도 1회 unquote 정규화 후 차단.
    v = inspect_upload(_PNG, "..%2f..%2fetc%2fpasswd.png", "image/png")
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


# ══════════════════════════════════════════════════════════════════════
# 10) 분리리뷰 REVISE 재현 회귀 — 우회 PoC #1: 폴리글랏(선두매직 위장)
# ══════════════════════════════════════════════════════════════════════
def test_poc1_polyglot_leading_png_with_embedded_zip_traversal_detected():
    """PoC #1a — PNG 매직으로 시작하지만 꼬리에 유효한 zip(EOCD)이 붙은 폴리글랏.

    과거 코드는 `detected == "zip"`에만 아카이브 검사가 걸려, sniff_type 이 선두 PNG 매직만
    보고 "png"를 반환하면 내부에 숨은 zip(경로순회 포함)이 전혀 검사되지 않고 통과했다.
    zipfile.is_zipfile 은 파일 끝에서 EOCD 를 찾아 판정하므로 프리픽스가 있어도 zip 을 인식한다
    (self-extracting 아카이브와 동일 원리) — 아래는 그 폴리글랏이 실제로 파싱 가능함을 전제로
    한 재현이다.
    """
    inner = _zip_bytes([("../../evil.txt", b"pwned")])
    polyglot = _PNG + inner
    assert zipfile.is_zipfile(io.BytesIO(polyglot)), "테스트 전제(폴리글랏 zip 파싱 가능) 실패"

    v = inspect_upload(polyglot, "cover.png", "image/png")
    assert not v.allowed, "폴리글랏이 통과함(우회) — 아카이브 검사가 발동하지 않았다"
    assert v.code == "path_traversal"


def test_poc1_polyglot_pdf_with_embedded_zip_bomb_ratio_detected():
    """PoC #1a 변형 — PDF 매직 + 꼬리 zip(압축비 폭탄). expected_kinds 화이트리스트가 "pdf"만
    허용해도(detected="pdf") 폴리글랏 내부 zip bomb 은 형식 화이트리스트와 무관하게 걸려야 한다.
    """
    bomb = _zip_bytes([("z.bin", b"\x00" * (20 * 1024 * 1024))])
    polyglot = _PDF + bomb
    assert zipfile.is_zipfile(io.BytesIO(polyglot))

    v = inspect_upload(polyglot, "doc.pdf", "application/pdf", expected_kinds={"pdf"})
    assert not v.allowed
    assert v.code == "archive_bomb"


def test_poc1_nested_archive_renamed_bin_extension_still_detected():
    """PoC #1b — 내부 중첩 zip 을 `.bin`으로 리네임해 확장자 기반 판별을 우회하는 공격.

    과거 코드(`_entry_is_nested_archive`)는 엔트리 파일명이 .zip/.xlsx/... 로 끝나야만 재귀
    검사를 시도했다. 지금은 확장자와 무관하게 엔트리 내용 앞 2바이트(PK)를 peek 해서 판별한다.
    """
    inner = _zip_bytes([("../evil.txt", b"pwned")])  # 내부에 경로순회 위반을 심어 재귀발동 증명
    outer = _zip_bytes([("payload.bin", inner), ("readme.txt", b"hi")])  # .bin 위장(확장자 무관)

    v = inspect_upload(outer, "bundle.zip", "application/zip")
    assert not v.allowed, "확장자 위장 중첩 아카이브가 재귀검사를 우회함(우회)"
    assert v.code == "path_traversal"


def test_poc1_nested_archive_no_extension_at_all_still_detected():
    """PoC #1b 변형 — 확장자가 아예 없는 엔트리명도 내용(PK peek)으로 판별돼야 한다."""
    inner = _zip_bytes([("z.bin", b"\x00" * (2 * 1024 * 1024))])  # 작은 압축비 폭탄
    outer = _zip_bytes([("data", inner)])  # 확장자 없음
    limits = ArchiveLimits(max_ratio=10, ratio_min_compressed=64)
    v = inspect_archive(outer, limits)
    assert not v.allowed and v.code == "archive_bomb"


def test_has_archive_structure_true_for_zip_false_for_plain_png():
    from app.services.security.content_inspection import _has_archive_structure

    assert _has_archive_structure(_normal_xlsx_like()) is True
    assert _has_archive_structure(_PNG) is False
    assert _has_archive_structure(_PNG + _zip_bytes([("a.txt", b"hi")])) is True  # 폴리글랏


# ══════════════════════════════════════════════════════════════════════
# 11) 우회 PoC #2 — 콘텐츠 거부가 502(인프라)로 오분류되던 문제
# ══════════════════════════════════════════════════════════════════════
def test_content_rejected_error_carries_4xx_status_not_502():
    exc = ContentRejectedError("mime_mismatch", "위장 파일")
    assert exc.http_status == 415
    assert exc.code == "mime_mismatch"
    assert isinstance(exc, Exception)


def test_http_status_for_maps_all_known_codes_to_4xx():
    known_codes = [
        "empty", "too_large", "executable", "path_traversal", "mime_mismatch",
        "unsupported_type", "archive_bomb", "archive_corrupt", "av_infected", "inspection_error",
    ]
    for code in known_codes:
        status = http_status_for(code)
        assert 400 <= status < 500, f"{code} → {status} (4xx 아님 — 502 로 오분류될 위험)"


def test_http_status_for_unknown_code_falls_back_to_400():
    assert http_status_for("some_new_future_code") == 400


async def test_storage_upload_design_file_rejects_executable_before_network_call():
    """content_inspection 거부는 Supabase 네트워크 호출(_sb_conf) 전에 일어나야 한다 — 여기선
    Supabase 환경변수가 전혀 없는 테스트 환경에서도 ContentRejectedError 가 먼저 발생함으로써
    검증 순서(검증→네트워크)와 4xx 매핑을 동시에 증명한다.
    """
    import pytest

    with pytest.raises(ContentRejectedError) as exc_info:
        await upload_design_file(b"MZ\x90\x00" + b"\x00" * 32, "application/pdf", "malware.pdf")
    assert exc_info.value.http_status == 400
    assert exc_info.value.code == "executable"


async def test_storage_upload_design_file_expected_kinds_blocks_unsupported():
    """PoC #3 — storage_service.upload_design_file 에 expected_kinds 가 없던 과거엔 미인식
    형식(예: zip)도 그대로 통과해 버킷에 업로드됐다. 지금은 _DESIGN_UPLOAD_KINDS 화이트리스트로
    zip 계열(설계도면 업로드 목적과 무관한 형식)을 명시 거부한다.
    """
    import pytest

    with pytest.raises(ContentRejectedError) as exc_info:
        await upload_design_file(_normal_xlsx_like(), "application/zip", "sneaky.zip")
    assert exc_info.value.code == "unsupported_type"
    assert exc_info.value.http_status == 415


# ══════════════════════════════════════════════════════════════════════
# 12) 우회 PoC #3 — expected_kinds 미지정으로 미인식 형식 무통제 통과(design_ingest 실결선)
# ══════════════════════════════════════════════════════════════════════
async def test_ingest_design_file_rejects_unrecognized_extension_content():
    """과거엔 ingest_design_file 이 expected_kinds 없이 inspect_upload 를 호출해, 매직바이트가
    전혀 인식되지 않는 임의 바이너리(.dat 등)도 위조가 아니면 그냥 파싱 단계로 넘어갔다(파싱은
    실패해도 콘텐츠 검증 게이트 자체는 통과). 지금은 _INGEST_UPLOAD_KINDS 화이트리스트로 미인식
    형식을 게이트 단계에서 명시 거부한다.
    """
    res = await ingest_design_file(filename="mystery.dat", content=b"\x01\x02\x03\x04\x05" * 20)
    assert res["ok"] is False
    assert res.get("rejected") is True
    assert res["code"] == "unsupported_type"


async def test_ingest_design_file_rejects_polyglot_nested_bomb():
    """PoC #1 을 실제 ingest_design_file 결선 경로에서도 재현 — 파싱/저장/인덱싱 전에 거부."""
    inner = _zip_bytes([("../evil.txt", b"pwned")])
    outer = _zip_bytes([("cad.bin", inner)])  # 확장자 위장 중첩
    res = await ingest_design_file(filename="drawing.zip", content=outer)
    assert res["ok"] is False and res.get("rejected") is True
    assert res["code"] == "path_traversal"


async def test_ingest_design_file_allows_legacy_xls_ole2_and_xlsx_zip():
    """엑셀 스펙시트(xlsx=zip, xls=OLE2 CFBF)는 화이트리스트 추가 후에도 계속 통과해야 한다
    (expected_kinds 도입이 기존 지원 형식을 깨지 않는지 확인 — FP 0 유지)."""
    xlsx_data = _normal_xlsx_like()
    res_xlsx = await ingest_design_file(filename="spec.xlsx", content=xlsx_data)
    assert res_xlsx.get("rejected") is not True, res_xlsx.get("reason")

    ole2_data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512  # 최소 OLE2 CFBF 헤더
    res_xls = await ingest_design_file(filename="legacy_spec.xls", content=ole2_data)
    assert res_xls.get("rejected") is not True, res_xls.get("reason")


# ══════════════════════════════════════════════════════════════════════
# 13) 우회 PoC #4 — 웹 활성 콘텐츠(HTML/SVG/JS)가 이미지·문서로 위장해 통과
# ══════════════════════════════════════════════════════════════════════
def test_poc4_svg_extension_blocked_regardless_of_content():
    svg_payload = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    v = inspect_upload(svg_payload, "innocent.svg", "image/svg+xml")
    assert not v.allowed and v.code == "executable"


def test_poc4_svg_mime_declared_blocked_even_with_benign_filename():
    # 파일명은 무해(photo.png)해도 선언 MIME 이 svg 면 차단(확장자 위장의 역방향 우회 방지).
    v = inspect_upload(_PNG, "photo.png", "image/svg+xml")
    assert not v.allowed and v.code == "executable"


def test_poc4_html_extension_blocked():
    v = inspect_upload(b"<html><body>hi</body></html>", "index.html", "text/html")
    assert not v.allowed and v.code == "executable"


def test_poc4_js_extension_blocked():
    v = inspect_upload(b"alert(document.cookie)", "widget.js", "application/javascript")
    assert not v.allowed and v.code == "executable"


def test_poc4_php_extension_blocked_even_with_image_mime_declared():
    # 확장자 위장 방향(활성 확장자 + 무해한 선언 MIME)도 여전히 확장자 기준으로 차단.
    v = inspect_upload(b"<?php system($_GET['c']); ?>", "shell.php", "image/png")
    assert not v.allowed and v.code == "executable"


def test_poc4_normal_png_with_declared_png_still_passes_fp0():
    # 활성콘텐츠 방어 추가가 정상 이미지 FP 를 유발하지 않는지(회귀).
    v = inspect_upload(_PNG, "photo.png", "image/png")
    assert v.allowed


# ══════════════════════════════════════════════════════════════════════
# 14) 우회 PoC #5 — central directory 크기신뢰의 한계(정직화) + 실읽기 백스톱 존재 확인
# ══════════════════════════════════════════════════════════════════════
def test_poc5_oversized_nested_candidate_skips_recursion_but_outer_limits_still_apply():
    """중첩 후보의 선언 크기(zi.file_size)가 max_nested_read 를 넘으면 재귀 판독(peek)은
    건너뛴다 — 하지만 그 경우도 바깥 아카이브의 전개총량·압축비·엔트리수 상한은 계속
    적용되므로(이 테스트에선 정상 크기라 통과) '재귀 스킵'이 전체 우회로 번지지 않는다.

    ★central directory 선언 크기 자체의 위조(로우바이트 조작)는 표준 zipfile 쓰기 API 로는
    재현할 수 없다 — inspect_archive() docstring 에 이 한계를 advisory 로 정직하게 문서화했고
    (항목5), 코드에는 "실제 읽은 바이트가 상한을 넘으면 거부"하는 백스톱을 추가했다
    (_inspect_archive_depth 의 `len(nested) > limits.max_nested_read` 분기).
    """
    inner = _zip_bytes([("z.bin", b"\x00" * (2 * 1024 * 1024))])  # 내부 유효 zip(실제 2MB 데이터)
    outer = _zip_bytes([("nested.zip", inner)])
    # max_nested_read 를 매우 작게 잡아 "선언 크기가 이미 상한 초과 → peek 스킵" 조건을 강제.
    limits = ArchiveLimits(max_nested_read=100, max_total_uncompressed=10**9, max_ratio=10**6)
    v = inspect_archive(outer, limits)
    assert v.allowed is True  # 재귀는 스킵됐지만 바깥 한도(정상 범위)는 그대로 통과 판정을 낸다


def test_poc5_spoof_backstop_exists_in_source():
    """실제읽기 백스톱 분기가 소스에 존재하는지(제거 방지 회귀) — 표준 API로 조작된 헤더를
    만들 수 없어 실행 경로 재현 대신 정적 확인으로 대체한다(정직 명시)."""
    import inspect

    from app.services.security import content_inspection as ci

    src = inspect.getsource(ci._inspect_archive_depth)
    assert "max_nested_read" in src and "archive_bomb" in src
