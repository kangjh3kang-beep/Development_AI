"""3원형 ↔ ApprovalState 매핑 왕복(round-trip) 검증(W1-A) — 순수 함수·무 DB.

- site_basis(ArtifactStatus)·design_runs(DRAFT/APPROVED): 5:5·2:2로 정확히 1:1 대응하므로
  "원형→공용→원형" 왕복이 원래 값을 정확히 복원해야 한다(엄밀 무손실).
- run_state(RunStateEnum, 7상태): 5상태보다 많아 구조적으로 1:1이 불가능하다(문서화된
  다대일 접힘). 이 경우는 더 약하지만 여전히 참인 불변식 — "공용상태 보존 왕복"
  (원형→공용→대표원형→공용 이 처음 공용값과 같다)만 검증한다(거짓 무손실 주장 금지).
"""
from __future__ import annotations

import pytest
from packages.schemas.run_state import RunStateEnum

from app.services.approval.approval_state import ApprovalState
from app.services.approval.archetype_adapters import (
    UnmappedApprovalStateError,
    approval_to_artifact_status,
    approval_to_design_run_status,
    approval_to_run_state,
    artifact_status_to_approval,
    design_run_status_to_approval,
    run_state_to_approval,
)
from app.services.basis.site_basis_state import ArtifactStatus
from app.services.cad import design_run_store

# ── ① site_basis — 5:5 완전 1:1(엄밀 무손실) ────────────────────────────────


@pytest.mark.parametrize("status", list(ArtifactStatus))
def test_site_basis_roundtrip_is_lossless(status):
    """artifact_status → ApprovalState → artifact_status 가 원래 값을 정확히 복원."""
    canonical = artifact_status_to_approval(status)
    assert approval_to_artifact_status(canonical) == status


def test_site_basis_mapping_is_bijective_covers_all_five():
    """5개 ArtifactStatus 가 5개 ApprovalState 에 중복 없이 정확히 1:1 대응."""
    mapped = {artifact_status_to_approval(s) for s in ArtifactStatus}
    assert mapped == set(ApprovalState)


def test_site_basis_semantic_anchors():
    """스파이크에서 확인한 핵심 의미론 고정(회귀 방지) — APPROVED/STALE 앵커."""
    assert artifact_status_to_approval(ArtifactStatus.APPROVED) == ApprovalState.APPROVED
    assert artifact_status_to_approval(ArtifactStatus.STALE) == ApprovalState.SUPERSEDED
    assert artifact_status_to_approval(ArtifactStatus.DRAFT) == ApprovalState.DRAFT


# ── ② design_runs — 2상태 부분함수(존재하는 2종은 엄밀 무손실) ──────────────


@pytest.mark.parametrize(
    "status", [design_run_store.STATUS_DRAFT, design_run_store.STATUS_APPROVED]
)
def test_design_run_roundtrip_is_lossless(status):
    canonical = design_run_status_to_approval(status)
    assert approval_to_design_run_status(canonical) == status


@pytest.mark.parametrize(
    "state", [ApprovalState.MACHINE_VALIDATED, ApprovalState.EXPERT_REVIEWED, ApprovalState.SUPERSEDED]
)
def test_design_run_has_no_representative_for_middle_states(state):
    """design_runs는 2상태 최소모델이라 중간/폐기 승인등급에 대응값이 없다(무날조 — 예외)."""
    with pytest.raises(UnmappedApprovalStateError):
        approval_to_design_run_status(state)


def test_design_run_unknown_status_rejected():
    with pytest.raises(UnmappedApprovalStateError):
        design_run_status_to_approval("QUEUED")  # job_status 계열은 이 축이 아님(혼용 금지)


# ── ③ run_state — 7:5 다대일(공용상태 보존 왕복만 성립·문서화된 비가역) ─────


@pytest.mark.parametrize("state", list(RunStateEnum))
def test_run_state_canonical_preserving_roundtrip(state):
    """원형→공용→대표원형→공용 이 처음 공용값과 같다(공용 '의미'는 왕복해도 보존됨)."""
    canonical = run_state_to_approval(state)
    representative = approval_to_run_state(canonical)
    assert run_state_to_approval(representative) == canonical


@pytest.mark.parametrize(
    "state,expected",
    [
        (RunStateEnum.DRAFT, ApprovalState.DRAFT),
        (RunStateEnum.FAIL, ApprovalState.DRAFT),
        (RunStateEnum.PASS, ApprovalState.MACHINE_VALIDATED),
        (RunStateEnum.PASS_WITH_WARNINGS, ApprovalState.MACHINE_VALIDATED),
        (RunStateEnum.MANUAL_REVIEW_REQUIRED, ApprovalState.EXPERT_REVIEWED),
        (RunStateEnum.HUMAN_APPROVED, ApprovalState.APPROVED),
        (RunStateEnum.LOCKED, ApprovalState.APPROVED),
    ],
)
def test_run_state_forward_mapping_matches_spike_findings(state, expected):
    """스파이크 근거 주석에 명시한 매핑 표 고정(회귀 방지)."""
    assert run_state_to_approval(state) == expected


def test_run_state_has_no_representative_for_superseded():
    """run_state는 SUPERSEDED 개념이 없다(오래된 run은 강등이 아니라 새 run_id 재발급)."""
    with pytest.raises(UnmappedApprovalStateError):
        approval_to_run_state(ApprovalState.SUPERSEDED)


def test_run_state_documented_collisions_are_intentional():
    """다대일 접힘 3그룹이 실제로 같은 공용상태로 접히는지 확인(우발적 충돌이 아님을 고정)."""
    assert run_state_to_approval(RunStateEnum.FAIL) == run_state_to_approval(RunStateEnum.DRAFT)
    assert (
        run_state_to_approval(RunStateEnum.PASS_WITH_WARNINGS)
        == run_state_to_approval(RunStateEnum.PASS)
    )
    assert (
        run_state_to_approval(RunStateEnum.LOCKED)
        == run_state_to_approval(RunStateEnum.HUMAN_APPROVED)
    )
