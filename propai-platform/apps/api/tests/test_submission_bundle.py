"""WP-F 제출 번들 컴파일러(submission_bundle) 단위 테스트.

검증축(계획서 §4 WP-F 게이트): (1) 매니페스트 파일별 sha256 전수 대조(zip 재열기 검증),
(2) 필수시트 누락=산출 거부+누락목록(무음 부분산출 금지), (3) 번들 결정성(같은 입력→같은 zip
바이트 — zip 내부 타임스탬프 고정), (4) 변조탐지(파일·매니페스트 자체 위변조).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from app.services.cad.sheet_frame import required_sheet_codes
from app.services.report.submission_bundle import (
    FIXED_ZIP_DT,
    MANIFEST_NAME,
    RequiredSheetsMissingError,
    build_submission_bundle,
    verify_bundle,
)

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><rect width="100" height="50"/></svg>'


def _all_required_svgs() -> dict[str, str]:
    """필수시트 5종을 전부 채운 최소 SVG 세트(성공 경로 픽스처)."""
    return {code: _SVG for code in required_sheet_codes()}


# ── 1) 필수시트 게이트 ────────────────────────────────────────────────


def test_build_bundle_missing_all_required_sheets_raises_with_full_list():
    with pytest.raises(RequiredSheetsMissingError) as exc_info:
        build_submission_bundle(project_id="p1", project_name="테스트", drawings_svg={})
    missing_codes = {m["code"] for m in exc_info.value.missing}
    assert missing_codes == set(required_sheet_codes())


def test_build_bundle_missing_one_required_sheet_raises_with_that_one():
    partial = _all_required_svgs()
    del partial["B-03"]
    with pytest.raises(RequiredSheetsMissingError) as exc_info:
        build_submission_bundle(project_id="p1", project_name="테스트", drawings_svg=partial)
    assert [m["code"] for m in exc_info.value.missing] == ["B-03"]


def test_build_bundle_empty_string_sheet_counts_as_missing():
    """SVG 값이 빈 문자열이면 '있지만 내용없음' = 미존재로 판정(무음 부분산출 금지)."""
    partial = _all_required_svgs()
    partial["B-04-S"] = ""
    with pytest.raises(RequiredSheetsMissingError) as exc_info:
        build_submission_bundle(project_id="p1", project_name="테스트", drawings_svg=partial)
    assert [m["code"] for m in exc_info.value.missing] == ["B-04-S"]


def test_build_bundle_all_required_present_succeeds_without_optional_parts():
    """필수시트만 있어도(보고서·BOQ·DXF 없이) 산출은 성공한다(부가물은 필수 아님)."""
    zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    assert len(zip_bytes) > 0
    assert manifest["file_count"] == 5  # SVG 5장만


# ── 2) 매니페스트 해시 전수 대조 ──────────────────────────────────────


def test_manifest_file_hashes_match_actual_zip_contents():
    """매니페스트에 기록된 sha256이 zip을 다시 열어 재계산한 값과 전건 일치."""
    svgs = _all_required_svgs()
    report_pdf = b"%PDF-1.4 fake report"
    boq_xlsx = b"PK\x03\x04 fake xlsx bytes"
    zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=svgs,
        report_pdf=report_pdf, boq_xlsx=boq_xlsx,
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for entry in manifest["files"]:
            actual = hashlib.sha256(zf.read(entry["arcname"])).hexdigest()
            assert actual == entry["sha256"], f"{entry['arcname']} 해시 불일치"


def test_verify_bundle_helper_reports_ok_for_untampered_zip():
    zip_bytes, _manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    ok, problems = verify_bundle(zip_bytes)
    assert ok is True
    assert problems == []


def test_verify_bundle_detects_tampered_file_content():
    """zip 내부 파일 하나를 바꿔치기하면 verify_bundle이 해시 불일치를 잡아낸다(변조탐지)."""
    zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    target = manifest["files"][0]["arcname"]
    # zipfile은 기존 엔트리 덮어쓰기를 지원하지 않으므로 전체를 재작성해 변조를 재현한다.
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf_in:
        names = zf_in.namelist()
        contents = {n: zf_in.read(n) for n in names}
    contents[target] = contents[target] + b"TAMPERED"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf_out:
        for n in names:
            zf_out.writestr(n, contents[n])
    ok, problems = verify_bundle(out.getvalue())
    assert ok is False
    assert any(target in p for p in problems)


def test_verify_bundle_detects_tampered_manifest_bundle_hash():
    """manifest.json 내부 필드를 조작하면 bundle_hash 재계산 불일치로 탐지."""
    zip_bytes, _manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf_in:
        names = zf_in.namelist()
        contents = {n: zf_in.read(n) for n in names}
    manifest = json.loads(contents[MANIFEST_NAME].decode("utf-8"))
    manifest["project_name"] = "위조된이름"  # bundle_hash 재계산 전 원본 값을 몰래 바꿈
    contents[MANIFEST_NAME] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf_out:
        for n in names:
            zf_out.writestr(n, contents[n])
    ok, problems = verify_bundle(out.getvalue())
    assert ok is False
    assert any("bundle_hash" in p for p in problems)


def test_verify_bundle_missing_manifest_returns_false():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("drawings/A-001.svg", _SVG)
    ok, problems = verify_bundle(out.getvalue())
    assert ok is False
    assert MANIFEST_NAME in problems[0]


def test_verify_bundle_corrupt_zip_bytes_fails_gracefully():
    ok, problems = verify_bundle(b"not a zip at all")
    assert ok is False
    assert problems


# ── 3) 번들 결정성 ───────────────────────────────────────────────────


def test_build_bundle_same_input_yields_identical_bytes():
    """같은 입력으로 두 번 빌드하면 zip 바이트가 완전히 동일(결정성 — now()/uuid 미사용)."""
    kwargs = dict(
        project_id="p1", project_name="테스트", issue_date="2026-07-15",
        drawings_svg=_all_required_svgs(),
        provenance={"run_id": "c2r_abc", "input_hash": "xyz"},
    )
    zip1, manifest1 = build_submission_bundle(**kwargs)
    zip2, manifest2 = build_submission_bundle(**kwargs)
    assert zip1 == zip2
    assert manifest1["bundle_hash"] == manifest2["bundle_hash"]


def test_build_bundle_different_project_name_yields_different_bytes():
    """입력이 다르면(정직) 바이트도 달라진다(항상 같은 값을 내는 가짜 결정성이 아님)."""
    svgs = _all_required_svgs()
    zip1, _m1 = build_submission_bundle(project_id="p1", project_name="A", drawings_svg=svgs)
    zip2, _m2 = build_submission_bundle(project_id="p1", project_name="B", drawings_svg=svgs)
    assert zip1 != zip2


def test_zip_entry_timestamps_are_fixed_not_wall_clock():
    """zip 내부 모든 엔트리의 date_time이 고정값(FIXED_ZIP_DT) — now() 미사용 증거."""
    zip_bytes, _manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            assert info.date_time == FIXED_ZIP_DT, f"{info.filename} 타임스탬프가 고정값이 아님"


# ── 4) provenance(생성근거) 정직 표기 ─────────────────────────────────


def test_manifest_provenance_records_run_id_and_input_hash():
    zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
        provenance={"run_id": "c2r_deadbeef", "input_hash": "feedface", "compiler_version": "v1"},
    )
    assert manifest["provenance"]["run_id"] == "c2r_deadbeef"
    assert manifest["provenance"]["input_hash"] == "feedface"
    assert manifest["provenance"]["compiler_version"] == "v1"


def test_manifest_provenance_absent_is_honestly_none():
    """provenance 미제공 시 가짜 run_id를 만들지 않는다(정직 None)."""
    zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    assert manifest["provenance"]["run_id"] is None
    assert manifest["provenance"]["input_hash"] is None


def test_manifest_required_sheets_field_matches_registry():
    zip_bytes, manifest = build_submission_bundle(
        project_id="p1", project_name="테스트", drawings_svg=_all_required_svgs(),
    )
    assert set(manifest["required_sheets"]) == set(required_sheet_codes())
