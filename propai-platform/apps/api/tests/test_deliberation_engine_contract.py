"""중심엔진 통합 Phase 1 — vendored 엔진 계약(input_hash) parity 검증.

골든값은 엔진 실제 `core/hashing`로 산출(deliberation 워크트리, propai-review venv):
  input_hash({"input": {대표입력}}) = 15f70dde...  → vendored가 비트동일해야(drift 차단).
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

from app.services.deliberation._engine_contract import (
    ENGINE_HASHING_PINNED,
    analysis_input_hash,
    build_input_dump,
    canonical,
    content_input_hash,
    is_deterministic_path,
    mirror_contract_fingerprint,
    mirror_field_manifest,
    prevalidate,
)

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "engine_input_contract.json"
_ENGINE_API = (pathlib.Path.home()
               / "My_Projects/Development_AI_deliberation/propai-platform"
               / "services/deliberation-review/apps/api")


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))

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


def _d(**kw):
    return build_input_dump(kw)


def test_prevalidate_accepts_clean_pure_input():
    assert prevalidate(_d(pnu="1111010100100000002",
                          calc_targets=[{"target": "building_area", "payload": {"outer_area": 5.0}}],
                          rules=[{"rule": {"comparator": "<="}, "measured": 1.0, "limit": 2.0}])) is None


def test_prevalidate_rejects_bad_values():
    # §6 체크리스트 — 키 존재가 아니라 값/enum까지(엔진 500 회피).
    assert prevalidate(_d(pnu="123"))[:].startswith("invalid_input:pnu_invalid")  # 19자리 아님
    assert "target_enum" in prevalidate(_d(calc_targets=[{"target": "BOGUS"}]))
    assert "comparator" in prevalidate(_d(rules=[{"rule": {"comparator": "≈"}}]))
    assert "rule_missing" in prevalidate(_d(rules=[{"measured": 1}]))
    assert "fact_key_missing" in prevalidate(_d(cross_facts=[{"x": 1}]))
    assert "element_id_missing" in prevalidate(_d(elements=[{"features": {}}]))
    assert "semantic_type" in prevalidate(_d(
        calc_targets=[{"target": "building_area", "elements": [{"semantic_type": "NOPE"}]}]))
    assert "confidence" in prevalidate(_d(
        calc_targets=[{"target": "building_area", "elements": [{"confidence": 1.5}]}]))
    assert "nonfinite" in prevalidate({"pnu": "", "rules": [{"rule": {}, "measured": float("inf")}]})


# ── 살아있는 parity 가드(HIGH): frozen 골든 stale 방지 2단 체인 ──


def test_mirror_matches_committed_engine_contract():
    # (1단) 미러 매니페스트가 커밋된 엔진 fixture와 비트동일 — 미러 필드/기본값 drift 시 RED.
    fx = _load_fixture()
    m = mirror_field_manifest()
    assert m["field_names"] == fx["field_names"]          # 필드 추가/삭제 즉시 RED
    assert m["defaults"] == fx["defaults"]                 # 기본값 drift 즉시 RED
    assert mirror_contract_fingerprint() == fx["fingerprint"]
    assert fx["hashing"] == ENGINE_HASHING_PINNED          # dead 상수 → 활성 어서션


def test_engine_live_contract_matches_fixture():
    """(2단) 엔진 워크트리가 있으면 실 AnalysisInput을 재덤프해 fixture와 대조 — 엔진이 필드/기본값을
    추가하면 RED(fixture 재생성 강제). 엔진 미체크아웃(CI 등) 시 명시적 skip(무음 green 아님)."""
    if not (_ENGINE_API / "app/contracts/analysis.py").exists():
        pytest.skip(f"engine worktree absent: {_ENGINE_API}")
    code = (
        "import hashlib,json;"
        "from app.contracts.analysis import AnalysisInput as A;"
        "d={n:(g.default_factory() if g.default_factory is not None else g.default)"
        " for n,g in A.model_fields.items()};"
        "d={k:json.loads(json.dumps(v,default=str)) for k,v in d.items()};"
        "names=sorted(d);"
        "c=json.dumps({'field_names':names,'defaults':{k:d[k] for k in names}},"
        "sort_keys=True,ensure_ascii=False,separators=(',',':'));"
        "print(json.dumps({'field_names':names,'fingerprint':hashlib.sha256(c.encode()).hexdigest()}))"
    )
    env = dict(os.environ, PYTHONPATH=str(_ENGINE_API))
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(_ENGINE_API), env=env,
                          capture_output=True, text=True, timeout=90)
    assert proc.returncode == 0, proc.stderr[-800:]
    live = json.loads(proc.stdout.strip().splitlines()[-1])
    fx = _load_fixture()
    assert live["field_names"] == fx["field_names"]        # 엔진 실모델 필드 drift → RED
    assert live["fingerprint"] == fx["fingerprint"]        # 엔진 실모델 기본값 drift → RED


def test_is_deterministic_path():
    # 순수(결정론) 입력만 멱등 캐싱 대상.
    assert is_deterministic_path(_d(pnu="1111010100100000002",
                                    calc_targets=[{"target": "building_area"}],
                                    rules=[{"rule": {}}])) is True
    # 비결정 발화: VLLM 도면·라이브 수집·다출처.
    assert is_deterministic_path(_d(drawings=[{"sheet_id": "s1"}])) is False
    assert is_deterministic_path(_d(ifc="ISO-10303")) is False
    assert is_deterministic_path(_d(elements=[{"element_id": "e1"}])) is False
    assert is_deterministic_path(_d(cross_facts=[{"fact_key": "k"}])) is False
    assert is_deterministic_path(_d(collect_land_card=True)) is False
    assert is_deterministic_path(_d(collect_surrounding=True)) is False
    # address는 pnu 19자리면 지오코딩 미발화 → 결정론; 비19자리면 라이브 → 비결정.
    assert is_deterministic_path(_d(pnu="1111010100100000002", address="서울 어딘가")) is True
    assert is_deterministic_path(_d(address="서울 어딘가")) is False
