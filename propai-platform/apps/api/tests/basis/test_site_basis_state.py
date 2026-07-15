"""부지기반(site basis) 상태머신(WP-G, 명세 P7) 단위 테스트 — 순수 함수·무 DB.

수용 게이트(원 지시 6항목)를 그대로 픽스처로 사상한다:
 ① P0 게이트(접도 RAC/개발행위 BLOCKED/권리 미확정) 각각이 AUTHORIZED를 차단
 ② 전건 P0 충족 + 인간승인 시에만 AUTHORIZED
 ③ 인간승인 없는 자동 AUTHORIZED 0 불변식
 ④ STALE 전파 실증(≥1 경로)
 ⑤ 상태전이 불법 경로 거부(예: DRAFT→APPROVED 직행 금지)
 ⑥ 원장 무결성 훼손 0(별도 파일 test_site_basis_service_static.py에서 검증)

추가로 분리 리뷰 MEDIUM-3(게이트 status 신뢰경계) 교정분 — reconcile_status(권위 재도출값과
caller 자기신고 교차검증)·cap_status_by_trust(미검증 자기신고만으로는 ANALYZED 승격 금지)를
검증한다.

★fastapi·DB 미의존(순수 서비스 직접 호출) — 시스템 파이썬으로도 실행 가능.
"""
from __future__ import annotations

import pytest

from app.services.basis.site_basis_state import (
    ArtifactStatus,
    BasisStatus,
    GateResult,
    IllegalTransitionError,
    aggregate_p0,
    apply_transition,
    basis_status_of,
    can_approve,
    cap_status_by_trust,
    classify_after_assess,
    evaluate_gate,
    is_stale,
    reconcile_status,
)

# ── ① P0 게이트 각각의 단독 차단 ────────────────────────────────────────────


def test_access_rac_blocks_authorized_even_if_others_clear():
    """P4 접도가 REQUIRES_AUTHORITY_CONFIRMATION이면, P2·P3가 전건 충족이어도 AUTHORIZED 불가."""
    all_clear, gates = aggregate_p0(
        access_status="REQUIRES_AUTHORITY_CONFIRMATION", dev_act_status="PASS", rights_confirmed=True,
    )
    assert all_clear is False
    access_gate = next(g for g in gates if g.name == "access")
    assert access_gate.clear is False
    assert access_gate.status == "REQUIRES_AUTHORITY_CONFIRMATION"


def test_dev_act_blocked_blocks_authorized_even_if_others_clear():
    """P2 개발행위가 BLOCKED면, P4·P3가 전건 충족이어도 AUTHORIZED 불가."""
    all_clear, gates = aggregate_p0(
        access_status="PASS", dev_act_status="BLOCKED", rights_confirmed=True,
    )
    assert all_clear is False
    dev_gate = next(g for g in gates if g.name == "dev_act_permit")
    assert dev_gate.clear is False
    assert dev_gate.status == "BLOCKED"


def test_rights_unconfirmed_none_blocks_authorized_even_if_others_clear():
    """P3 권리 미확정(None — 보수 게이트)이면, P2·P4가 전건 충족이어도 AUTHORIZED 불가."""
    all_clear, gates = aggregate_p0(
        access_status="PASS", dev_act_status="CONDITIONAL", rights_confirmed=None,
    )
    assert all_clear is False
    rights_gate = next(g for g in gates if g.name == "rights")
    assert rights_gate.clear is False


def test_rights_explicitly_false_blocks_authorized():
    """P3 권리확정=False(명시 미확정)도 동일하게 차단(None과 동치 취급)."""
    all_clear, gates = aggregate_p0(
        access_status="PASS", dev_act_status="PASS", rights_confirmed=False,
    )
    assert all_clear is False
    rights_gate = next(g for g in gates if g.name == "rights")
    assert rights_gate.status == "UNCONFIRMED"


# ── ② 전건 P0 충족 + 인간승인 시에만 AUTHORIZED ─────────────────────────────


def test_full_p0_clear_plus_human_approval_yields_authorized():
    """CONDITIONAL도 P0 충족으로 인정 — 전건 충족 + 승인 → APPROVED(=AUTHORIZED)."""
    all_clear, _gates = aggregate_p0(
        access_status="PASS", dev_act_status="CONDITIONAL", rights_confirmed=True,
    )
    assert all_clear is True

    analyzed = apply_transition(ArtifactStatus.DRAFT, "assess", all_p0_clear=all_clear)
    assert analyzed == ArtifactStatus.ANALYZED
    assert basis_status_of(analyzed) == BasisStatus.ADVISORY  # 승인 전엔 아직 ADVISORY

    approved = apply_transition(
        analyzed, "approve", approved_by="reviewer@propai.dev", all_p0_clear=all_clear,
    )
    assert approved == ArtifactStatus.APPROVED
    assert basis_status_of(approved) == BasisStatus.AUTHORIZED


def test_p0_not_clear_yields_review_required_not_analyzed():
    """P0 미충족이면 자동판정이 ANALYZED가 아니라 REVIEW_REQUIRED(인간 검토 필요)로 정직 강등."""
    all_clear, _ = aggregate_p0(access_status="BLOCKED", dev_act_status="PASS", rights_confirmed=True)
    status = classify_after_assess(all_clear)
    assert status == ArtifactStatus.REVIEW_REQUIRED


# ── ③ 인간승인 없는 자동 AUTHORIZED 0 불변식 ────────────────────────────────


def test_authorized_never_reached_via_assess_alone():
    """assess 액션만으로는 어떤 P0 조합에서도 AUTHORIZED(APPROVED)에 도달하지 않는다."""
    combos = [
        ("PASS", "PASS", True), ("PASS", "CONDITIONAL", True),
        ("BLOCKED", "PASS", True), ("PASS", "PASS", None), ("PASS", "PASS", False),
    ]
    for access_status, dev_status, rights in combos:
        all_clear, _ = aggregate_p0(
            access_status=access_status, dev_act_status=dev_status, rights_confirmed=rights,
        )
        status = apply_transition(ArtifactStatus.DRAFT, "assess", all_p0_clear=all_clear)
        assert status != ArtifactStatus.APPROVED
        assert basis_status_of(status) == BasisStatus.ADVISORY


def test_approve_without_approver_is_rejected_even_if_p0_clear():
    """approved_by 미제공이면(자동 호출 흉내) P0 전건 충족이어도 승인 거부."""
    ok, reason = can_approve(ArtifactStatus.ANALYZED, all_p0_clear=True, approved_by=None)
    assert ok is False
    assert reason

    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.ANALYZED, "approve", approved_by="", all_p0_clear=True)


def test_approve_with_blank_whitespace_approver_is_rejected():
    """공백만 있는 approved_by도 승인자 부재로 취급(문자열 존재만으로 우회 금지)."""
    ok, _reason = can_approve(ArtifactStatus.ANALYZED, all_p0_clear=True, approved_by="   ")
    assert ok is False


# ── ④ STALE 전파 실증(≥1 경로) ──────────────────────────────────────────────


def test_is_stale_detects_content_hash_mismatch():
    assert is_stale("hash_v1", "hash_v2") is True
    assert is_stale("hash_v1", "hash_v1") is False
    assert is_stale(None, "hash_v2") is False  # 근거 미상 — 낙관 STALE 단정 금지
    assert is_stale("hash_v1", None) is False


def test_stale_propagation_path_from_approved_via_evidence_changed():
    """APPROVED(AUTHORIZED) 상태가 의존 evidence 변경 감지 시 STALE로 강등되는 1경로 실증."""
    approved = ArtifactStatus.APPROVED
    assert basis_status_of(approved) == BasisStatus.AUTHORIZED

    # 재분석으로 content_hash가 바뀌었다고 가정(예: P2 게이트 재판정으로 새 run_id) — evidence_changed.
    old_hash, new_hash = "content_hash_v1", "content_hash_v2"
    assert is_stale(old_hash, new_hash) is True

    degraded = apply_transition(approved, "evidence_changed")
    assert degraded == ArtifactStatus.STALE
    assert basis_status_of(degraded) == BasisStatus.ADVISORY  # AUTHORIZED 자동 박탈(정직 강등)


def test_stale_recovers_via_reassess_to_analyzed_or_review_required():
    """STALE에서는 재분석(assess)으로만 복귀 가능 — 승인 없이 되살아나지 않는다."""
    stale = ArtifactStatus.STALE
    recovered_clear = apply_transition(stale, "assess", all_p0_clear=True)
    assert recovered_clear == ArtifactStatus.ANALYZED
    assert basis_status_of(recovered_clear) == BasisStatus.ADVISORY  # 재승인 전까지는 ADVISORY

    recovered_unclear = apply_transition(stale, "assess", all_p0_clear=False)
    assert recovered_unclear == ArtifactStatus.REVIEW_REQUIRED


# ── ⑤ 상태전이 불법 경로 거부 ────────────────────────────────────────────────


def test_illegal_transition_draft_to_approve_direct():
    """DRAFT→APPROVED 직행 금지(먼저 assess로 ANALYZED를 거쳐야 함)."""
    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.DRAFT, "approve", approved_by="reviewer", all_p0_clear=True)


def test_illegal_transition_review_required_to_approve_direct():
    """REVIEW_REQUIRED→APPROVED 직행 금지(게이트 미충족 상태에서 승인 우회 차단)."""
    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.REVIEW_REQUIRED, "approve", approved_by="reviewer", all_p0_clear=True)


def test_illegal_transition_stale_to_approve_direct():
    """STALE→APPROVED 직행 금지(재분석(assess)으로 ANALYZED 재도달 후에만 승인 가능)."""
    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.STALE, "approve", approved_by="reviewer", all_p0_clear=True)


def test_illegal_transition_approved_to_assess_direct_bypasses_staleness():
    """APPROVED→ANALYZED 직행(assess 재호출) 금지 — evidence_changed로 STALE을 먼저 거쳐야 한다."""
    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.APPROVED, "assess", all_p0_clear=True)


def test_illegal_transition_evidence_changed_from_draft():
    """DRAFT는 아직 판정이 없으므로 evidence_changed(재분석 유입 감지) 대상이 아니다."""
    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.DRAFT, "evidence_changed")


def test_illegal_transition_unknown_action_rejected():
    """정의되지 않은 action은 전이 시도 자체가 거부된다(조용한 무시 금지)."""
    with pytest.raises(IllegalTransitionError):
        apply_transition(ArtifactStatus.DRAFT, "teleport_to_authorized")


def test_reapprove_already_approved_rejected():
    """이미 APPROVED인 상태의 재승인 시도는 거부(멱등 재승인 아님 — 명시 오류)."""
    ok, reason = can_approve(ArtifactStatus.APPROVED, all_p0_clear=True, approved_by="reviewer")
    assert ok is False
    assert reason


# ── MEDIUM-3(분리 리뷰 교정): 게이트 status 신뢰경계 ────────────────────────


def test_evaluate_gate_none_status_forces_unknown_source():
    """status 미상(None)은 source를 caller_declared로 넘겨도 'unknown'으로 강제된다(정직 표기)."""
    gate = evaluate_gate("access", None, source="caller_declared")
    assert gate.source == "unknown"
    assert gate.clear is False


def test_evaluate_gate_preserves_declared_source_when_status_present():
    """status가 있으면 호출측이 넘긴 source(server_derived 등)를 그대로 보존한다."""
    gate = evaluate_gate("access", "PASS", source="server_derived")
    assert gate.source == "server_derived"
    assert gate.clear is True


def test_aggregate_p0_threads_source_params_into_gates():
    """aggregate_p0에 넘긴 access_source/dev_act_source가 각 게이트에 그대로 반영된다."""
    _, gates = aggregate_p0(
        access_status="PASS", dev_act_status="CONDITIONAL", rights_confirmed=True,
        access_source="server_derived", dev_act_source="server_derived_conflict_resolved",
    )
    access_gate = next(g for g in gates if g.name == "access")
    dev_gate = next(g for g in gates if g.name == "dev_act_permit")
    assert access_gate.source == "server_derived"
    assert dev_gate.source == "server_derived_conflict_resolved"


def test_reconcile_status_no_authoritative_trusts_caller_declared():
    """재도출 재료 없음(authoritative=None) — caller 자기신고를 그대로 신뢰."""
    status, source = reconcile_status("PASS", None)
    assert status == "PASS"
    assert source == "caller_declared"


def test_reconcile_status_no_caller_uses_authoritative_only():
    """caller 신고 없음 — 권위 재도출값만 사용."""
    status, source = reconcile_status(None, "CONDITIONAL")
    assert status == "CONDITIONAL"
    assert source == "server_derived"


def test_reconcile_status_match_confirms_server_derived():
    """caller 신고와 권위 재도출값이 일치하면 그 값 그대로, source=server_derived(교차검증 확인됨)."""
    status, source = reconcile_status("PASS", "PASS")
    assert status == "PASS"
    assert source == "server_derived"


def test_reconcile_status_mismatch_picks_more_conservative_value():
    """★MEDIUM-3 핵심: 불일치 시 더 보수적(차단쪽) 값을 채택 — caller가 낙관 신고해도 무력화."""
    status, source = reconcile_status("PASS", "BLOCKED")  # caller는 PASS라 우기지만 서버는 BLOCKED.
    assert status == "BLOCKED"
    assert source == "server_derived_conflict_resolved"


def test_reconcile_status_mismatch_conservative_independent_of_argument_order():
    """보수값 채택은 어느 쪽이 caller/authoritative인지와 무관하게 항상 더 차단적인 값이 이긴다."""
    status, _source = reconcile_status("BLOCKED", "PASS")  # 이번엔 caller가 BLOCKED로 신고.
    assert status == "BLOCKED"


def test_cap_status_by_trust_forces_review_required_when_access_unverified():
    """★MEDIUM-3 핵심: access 게이트가 caller_declared(미검증)면, P0 전건 충족(all_clear)이어도
    ANALYZED로 자동 승격하지 않고 REVIEW_REQUIRED로 강등된다(P0 청산 날조 방지)."""
    gates = [
        GateResult(name="access", clear=True, status="PASS", reason="r", source="caller_declared"),
        GateResult(name="dev_act_permit", clear=True, status="CONDITIONAL", reason="r", source="server_derived"),
        GateResult(name="rights", clear=True, status="CONFIRMED", reason="r", source="caller_declared"),
    ]
    capped = cap_status_by_trust(ArtifactStatus.ANALYZED, gates)
    assert capped == ArtifactStatus.REVIEW_REQUIRED


def test_cap_status_by_trust_allows_analyzed_when_access_and_dev_act_server_derived():
    """access·dev_act 둘 다 server_derived(재도출·교차검증됨)면 ANALYZED 승격이 허용된다."""
    gates = [
        GateResult(name="access", clear=True, status="PASS", reason="r", source="server_derived"),
        GateResult(name="dev_act_permit", clear=True, status="CONDITIONAL", reason="r", source="server_derived"),
        GateResult(name="rights", clear=True, status="CONFIRMED", reason="r", source="caller_declared"),
    ]
    capped = cap_status_by_trust(ArtifactStatus.ANALYZED, gates)
    assert capped == ArtifactStatus.ANALYZED


def test_cap_status_by_trust_ignores_rights_source():
    """rights(P3)는 이 WP에서 항상 caller_declared(전용 재도출 서비스 부재)이므로, access·dev_act가
    server_derived라면 rights의 caller_declared만으로는 cap이 걸리지 않는다(대상 게이트 아님)."""
    gates = [
        GateResult(name="access", clear=True, status="PASS", reason="r", source="server_derived"),
        GateResult(name="dev_act_permit", clear=True, status="PASS", reason="r", source="server_derived"),
        GateResult(name="rights", clear=True, status="CONFIRMED", reason="r", source="caller_declared"),
    ]
    assert cap_status_by_trust(ArtifactStatus.ANALYZED, gates) == ArtifactStatus.ANALYZED


def test_cap_status_by_trust_is_noop_for_non_analyzed_status():
    """이미 REVIEW_REQUIRED/DRAFT/STALE/APPROVED인 상태는 신뢰경계 상한 대상이 아니다(no-op)."""
    gates = [GateResult(name="access", clear=True, status="PASS", reason="r", source="caller_declared")]
    for status in (ArtifactStatus.REVIEW_REQUIRED, ArtifactStatus.DRAFT, ArtifactStatus.STALE):
        assert cap_status_by_trust(status, gates) == status
