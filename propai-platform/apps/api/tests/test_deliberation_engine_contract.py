"""중심엔진 통합 Phase 1 — vendored 엔진 계약(input_hash) parity 검증.

골든값은 엔진 실제 `core/hashing`로 산출(deliberation 워크트리, propai-review venv):
  input_hash({"input": {대표입력}}) = 15f70dde...  → vendored가 비트동일해야(drift 차단).
"""
from app.services.deliberation._engine_contract import (
    analysis_input_hash,
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
