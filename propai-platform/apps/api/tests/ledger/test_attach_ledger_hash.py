"""성장루프 조인키 공용 헬퍼(extract/attach_ledger_hash) 단위테스트.

프론트 피드백(👍/👎)은 응답 최상위 `ledger_hash`(sha256 hex)로 analysis_ledger 와
등가조인한다(learning_loop.curate_few_shot). 과거 프론트가 자체 계산한 32bit base36
해시를 보내 산식·입력·형식 3중 불일치로 조인이 항상 0건이던 단절의 재발을 막는다 —
서버가 append_analysis 결과의 content_hash 를 그대로 노출하는 것이 정답 기준선.
"""
from __future__ import annotations

from app.services.ledger.analysis_ledger_service import (
    attach_ledger_hash,
    extract_ledger_hash,
)

_SHA = "a1" * 32  # sha256 hex 모양(64자)


def test_extract_ok_returns_hash():
    assert extract_ledger_hash({"ok": True, "content_hash": _SHA}) == _SHA


def test_extract_unchanged_still_returns_hash():
    # 동일 내용 재분석(unchanged=True)도 같은 content_hash — 피드백 키잉 계속 유효
    assert extract_ledger_hash(
        {"ok": True, "unchanged": True, "content_hash": _SHA}) == _SHA


def test_extract_failure_or_missing_returns_none():
    assert extract_ledger_hash(None) is None
    assert extract_ledger_hash("문자열") is None                      # dict 아님
    assert extract_ledger_hash({"ok": False, "message": "quota"}) is None
    assert extract_ledger_hash({"ok": True}) is None                  # content_hash 부재
    assert extract_ledger_hash({"ok": True, "content_hash": ""}) is None


def test_attach_sets_top_level_standard_field_in_place():
    resp = {"ok": True, "summary": {"far": 210.0}}
    out = attach_ledger_hash(resp, {"ok": True, "content_hash": _SHA})
    assert out is resp                       # 제자리 수정 + 반환(한 줄 체이닝 계약)
    assert out["ledger_hash"] == _SHA        # ★필드명 고정(프론트 계약)


def test_attach_omits_key_on_failure_no_mock_none():
    # 미적재/실패면 키 자체를 넣지 않는다(정직 — None 목업 금지)
    assert "ledger_hash" not in attach_ledger_hash({"ok": True}, {"ok": False})
    assert "ledger_hash" not in attach_ledger_hash({"ok": True}, None)


def test_attach_non_dict_response_is_noop():
    # 응답이 dict 가 아니면 조용히 그대로 반환(방어적 — 크래시 금지)
    assert attach_ledger_hash(None, {"ok": True, "content_hash": _SHA}) is None  # type: ignore[arg-type]
