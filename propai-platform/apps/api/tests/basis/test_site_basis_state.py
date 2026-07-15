"""부지기반(site basis) 상태머신(WP-G, 명세 P7) 단위 테스트 — 순수 함수·무 DB.

수용 게이트(원 지시 6항목)를 그대로 픽스처로 사상한다:
 ① P0 게이트(접도 RAC/개발행위 BLOCKED/권리 미확정) 각각이 AUTHORIZED를 차단
 ② 전건 P0 충족 + 인간승인 시에만 AUTHORIZED
 ③ 인간승인 없는 자동 AUTHORIZED 0 불변식
 ④ STALE 전파 실증(≥1 경로)
 ⑤ 상태전이 불법 경로 거부(예: DRAFT→APPROVED 직행 금지)
 ⑥ 원장 무결성 훼손 0(별도 파일 test_site_basis_service_static.py에서 검증)

★fastapi·DB 미의존(순수 서비스 직접 호출) — 시스템 파이썬으로도 실행 가능.
"""
from __future__ import annotations

import pytest

from app.services.basis.site_basis_state import (
    ArtifactStatus,
    BasisStatus,
    IllegalTransitionError,
    aggregate_p0,
    apply_transition,
    basis_status_of,
    can_approve,
    classify_after_assess,
    is_stale,
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
