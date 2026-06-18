"""중심엔진 통합 Phase 1 — vendored 엔진 계약(input_hash) parity 검증.

골든값은 엔진 실제 `core/hashing`로 산출(deliberation 워크트리, propai-review venv):
  input_hash({"input": {대표입력}}) = 15f70dde...  → vendored가 비트동일해야(drift 차단).
"""
from app.services.deliberation._engine_contract import (
    analysis_input_hash,
    build_input_dump,
    canonical,
    content_input_hash,
)

# 엔진 대조 입력(한글·리스트 순서·중첩) — 직렬화 규칙 전수 검증.
_SAMPLE = {
    "pnu": "1111010100100000002",
    "snapshot_id": "snap-1",
    "nums": [3, 1, 2],
    "ko": "한글",
    "nested": {"b": 2, "a": 1},
}
# 엔진 canonical({"input": _SAMPLE}) 실측 골든.
_GOLDEN_CANON = (
    '{"input":{"ko":"한글","nested":{"a":1,"b":2},"nums":[3,1,2],'
    '"pnu":"1111010100100000002","snapshot_id":"snap-1"}}'
)
_GOLDEN_IHASH = "15f70dde8a6305a5059beccea9e9441760056448ed79f4c1456e2e5f30632742"


def test_canonical_parity_with_engine():
    # 키 정렬·한글 보존(ensure_ascii=False)·무공백 separators — 엔진과 글자단위 동일.
    assert canonical({"input": _SAMPLE}) == _GOLDEN_CANON


def test_input_hash_parity_golden():
    # 엔진 input_hash({"input": inp.model_dump})와 비트동일(멱등/부분응답 parity 토대).
    assert analysis_input_hash(_SAMPLE) == _GOLDEN_IHASH


def test_content_input_hash_excludes_only_snapshot_id():
    a = {"pnu": "P", "snapshot_id": "s1", "x": 1}
    b = {"pnu": "P", "snapshot_id": "s2", "x": 1}
    # snapshot만 다른 동일 사안 → content_input_hash 동일(lineage), input_hash는 다름(snapshot 포함).
    assert content_input_hash(a) == content_input_hash(b)
    assert analysis_input_hash(a) != analysis_input_hash(b)
    # 다른 입력은 content_input_hash도 달라야.
    assert content_input_hash(a) != content_input_hash({"pnu": "Q", "snapshot_id": "s1", "x": 1})


# 엔진 AnalysisInput(pnu, application_date, calc_targets) 실측 model_dump → input_hash 골든.
_GOLDEN_MIRROR_IHASH = "cecb96fedce399960665dbbf193c8f12286163719ea6df94670f47c0d08714af"


def test_mirror_fills_defaults_and_matches_engine_input_hash():
    # 플랫폼 부분입력 → 미러가 엔진 기본값(snapshot_id "snap-1"·model_version·surrounding_radius_m 150 등)
    # 동일하게 채워 model_dump → analysis_input_hash가 엔진과 비트동일(멱등/parity 토대).
    payload = {
        "pnu": "1111010100100000002",
        "application_date": "2026-01-01",
        "calc_targets": [{"target": "building_area", "payload": {"outer_area": 500.0}}],
    }
    dump = build_input_dump(payload)
    assert dump["snapshot_id"] == "snap-1" and dump["surrounding_radius_m"] == 150
    assert analysis_input_hash(dump) == _GOLDEN_MIRROR_IHASH


def test_mirror_ignores_extra_keys():
    # 플랫폼 잉여 키는 엔진처럼 무시(extra=ignore) → 해시 오염 없음.
    base = build_input_dump({"pnu": "P"})
    with_extra = build_input_dump({"pnu": "P", "platform_only_field": "x"})
    assert analysis_input_hash(base) == analysis_input_hash(with_extra)
