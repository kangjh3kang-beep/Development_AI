"""3원형(site_basis · design_runs · run_state) ↔ 공용 ApprovalState 매핑 어댑터(W1-A).

★재구현 금지: 3원형의 상태 정의·전이 로직은 원본 파일에서 단 한 줄도 옮기거나 고치지
  않는다. 이 파일은 순수 "번역기"만 제공한다 — 원형 상태값을 받아 공용 ApprovalState로,
  또는 그 반대로 변환한다. 원형의 실제 전이 규칙(assess/approve 등)은 여전히 원형 자신의
  함수(site_basis_state.apply_transition 등)가 전담하고, 이 어댑터는 "지금 이 원형 상태가
  v4.0 승인등급으로는 무엇에 해당하는가"만 답한다.

★무손실 vs 비가역(정직 표기 — 무목업 원칙):
  - site_basis(5상태)·design_runs(2상태)는 공용 5상태의 부분/전체와 정확히 1:1 대응한다
    → 원형→공용→원형 왕복이 항상 원래 값을 그대로 복원한다(엄밀히 무손실).
  - run_state(RunStateEnum, 7상태)는 5상태보다 상태가 더 많다 — 구조적으로 1:1이 불가능
    하다(정보이론적으로 7종을 5종에 무손실로 욱여넣을 수 없다). 이 어댑터는 그 사실을
    숨기지 않고, "같은 공용 상태로 접히는 원형 상태들"을 주석으로 명시한다. 대신
    "공용상태 보존 왕복"(원형→공용→대표원형→공용 이 처음 공용값과 같다)은 항상 성립한다
    — 이것이 run_state에 대해 실제로 참인, 정직한 무손실 보장의 범위다.
"""
from __future__ import annotations

from app.services.basis.site_basis_state import ArtifactStatus
from app.services.cad import design_run_store
from packages.schemas.run_state import RunStateEnum

from .approval_state import ApprovalState


class UnmappedApprovalStateError(Exception):
    """공용 ApprovalState가 해당 원형에 대응값이 없을 때(무날조 — 값을 지어내지 않고 예외)."""


# ══════════════════════════════════════════════════════════════════════════
# ① site_basis.ArtifactStatus ↔ ApprovalState — 5:5 완전 1:1(엄밀 무손실)
# ══════════════════════════════════════════════════════════════════════════
# 근거(site_basis_state.py 정독):
#   DRAFT            = 아직 판정 없음                              → DRAFT(초안)
#   ANALYZED         = P0 게이트 전건 충족(자동판정) — 인간승인 대기 → MACHINE_VALIDATED
#   REVIEW_REQUIRED  = P0 게이트 미충족/미검증 자기신고만 있어 인간   → EXPERT_REVIEWED
#                      재검토가 필요한 상태(★주의: "전문가가 이미 검토완료"가 아니라
#                      "전문가 검토 대기" 의미 — site_basis에는 검토완료 전용 상태가
#                      따로 없고, 검토 행위 자체가 approve() 호출로 ANALYZED→APPROVED를
#                      직행하며 완결되기 때문이다. 정직하게 남겨두는 의미론적 간극.)
#   APPROVED         = approve_site_basis()로 인간승인 완료(approved_by 강제)   → APPROVED
#   STALE            = evidence 변경으로 기존 승인/판정이 강등됨            → SUPERSEDED
_ARTIFACT_STATUS_TO_APPROVAL: dict[ArtifactStatus, ApprovalState] = {
    ArtifactStatus.DRAFT: ApprovalState.DRAFT,
    ArtifactStatus.ANALYZED: ApprovalState.MACHINE_VALIDATED,
    ArtifactStatus.REVIEW_REQUIRED: ApprovalState.EXPERT_REVIEWED,
    ArtifactStatus.APPROVED: ApprovalState.APPROVED,
    ArtifactStatus.STALE: ApprovalState.SUPERSEDED,
}
_APPROVAL_TO_ARTIFACT_STATUS: dict[ApprovalState, ArtifactStatus] = {
    v: k for k, v in _ARTIFACT_STATUS_TO_APPROVAL.items()
}


def artifact_status_to_approval(status: ArtifactStatus | str) -> ApprovalState:
    """site_basis artifact_status → 공용 ApprovalState(전 5종 총함수 — 매핑 누락 없음)."""
    return _ARTIFACT_STATUS_TO_APPROVAL[ArtifactStatus(status)]


def approval_to_artifact_status(state: ApprovalState | str) -> ArtifactStatus:
    """공용 ApprovalState → site_basis artifact_status(전 5종 총함수 — 정확히 역함수)."""
    return _APPROVAL_TO_ARTIFACT_STATUS[ApprovalState(state)]


# ══════════════════════════════════════════════════════════════════════════
# ② design_runs(DRAFT/APPROVED) ↔ ApprovalState — 2상태만 존재(부분함수)
# ══════════════════════════════════════════════════════════════════════════
# 근거(design_run_store.py 정독): 이 원형은 "승인차원"만 딱 2값(DRAFT/APPROVED)으로
# 최소화했다(docstring: "승인차원 status(DRAFT/APPROVED)만 이 테이블이 소유"). 이 2값은
# 공용 5상태 중 양끝(DRAFT·APPROVED)에 정확히 대응한다 — MACHINE_VALIDATED·EXPERT_REVIEWED·
# SUPERSEDED에 대응하는 design_runs 상태는 존재하지 않는다(설계했을 뿐이라 자동/전문가
# 중간검증 단계가 없고, evidence 변경 시 오래된 run은 그냥 새 input_hash로 새 행이 생길
# 뿐 기존 행을 SUPERSEDED로 강등하는 개념이 없다 — persist_design_run 어디에도 그런 강등
# 로직이 없음을 확인). 따라서 반대방향은 부분함수 — 대응 없는 값은 예외로 정직 거부한다.
_DESIGN_RUN_STATUS_TO_APPROVAL: dict[str, ApprovalState] = {
    design_run_store.STATUS_DRAFT: ApprovalState.DRAFT,
    design_run_store.STATUS_APPROVED: ApprovalState.APPROVED,
}
_APPROVAL_TO_DESIGN_RUN_STATUS: dict[ApprovalState, str] = {
    v: k for k, v in _DESIGN_RUN_STATUS_TO_APPROVAL.items()
}


def design_run_status_to_approval(status: str) -> ApprovalState:
    """design_runs.status(DRAFT/APPROVED) → 공용 ApprovalState(2종 총함수)."""
    try:
        return _DESIGN_RUN_STATUS_TO_APPROVAL[str(status)]
    except KeyError as e:
        raise UnmappedApprovalStateError(
            f"design_runs 는 status={status!r} 를 갖지 않습니다"
            f"(유효값: {sorted(_DESIGN_RUN_STATUS_TO_APPROVAL)})."
        ) from e


def approval_to_design_run_status(state: ApprovalState | str) -> str:
    """공용 ApprovalState → design_runs.status — MACHINE_VALIDATED/EXPERT_REVIEWED/SUPERSEDED
    는 design_runs에 대응값이 없어(부분함수) 예외를 던진다(값을 지어내지 않음, 무날조)."""
    state = ApprovalState(state)
    try:
        return _APPROVAL_TO_DESIGN_RUN_STATUS[state]
    except KeyError as e:
        raise UnmappedApprovalStateError(
            f"design_runs 승인차원(DRAFT/APPROVED)에는 {state.value} 에 대응하는 상태가 "
            "없습니다(이 원형은 중간검증·폐기 개념이 없는 2상태 최소 모델입니다)."
        ) from e


# ══════════════════════════════════════════════════════════════════════════
# ③ RunStateEnum ↔ ApprovalState — 7상태 → 5상태(구조적 비가역·정직 문서화)
# ══════════════════════════════════════════════════════════════════════════
# 근거(run_state.py 정독): "DRAFT → (검증) → PASS|PASS_WITH_WARNINGS|FAIL|
# MANUAL_REVIEW_REQUIRED → (HITL 승인) → HUMAN_APPROVED → LOCKED". 이 열거형은
# "검증 결과"와 "승인 여부"를 한 축에 섞어 담고 있어 v4.0의 순수 승인등급 축(5상태)보다
# 표현력이 더 크다. 여기서는 "승인 관문 통과 정도"만 뽑아 다음처럼 접는다(collision은
# 의도적·문서화된 것이며 아래 round-trip은 "공용상태 보존" 의미로만 성립 — 어댑터
# docstring 상단 참조):
#   DRAFT                    = 초안·미검증                        → DRAFT
#   FAIL                     = 검증 실패(어떤 마일스톤도 미달성)     → DRAFT(★collision — 아직
#                              MachineValidated 관문을 통과 못했다는 점에서 DRAFT와 동치)
#   PASS                     = 자동검증 통과                       → MACHINE_VALIDATED
#   PASS_WITH_WARNINGS       = 자동검증 통과(경고 동반)             → MACHINE_VALIDATED
#                              (★collision — 경고 유무는 승인등급 축의 관심사가 아님)
#   MANUAL_REVIEW_REQUIRED   = 수동 검토 필요(게이트)               → EXPERT_REVIEWED
#   HUMAN_APPROVED           = 인간(HITL) 승인 완료                 → APPROVED
#   LOCKED                   = 승인 후 확정·잠금(불변)              → APPROVED(★collision·
#                              "유지" — LOCKED는 "오래돼 폐기(SUPERSEDED)"가 아니라 "승인된
#                              채로 더 굳어짐"이므로 APPROVED 구간에 남는다. run_state에는
#                              SUPERSEDED에 대응하는 개념 자체가 없다 — C2R은 오래된 run을
#                              강등하지 않고 새 run_id를 새로 만든다.)
_RUN_STATE_TO_APPROVAL: dict[RunStateEnum, ApprovalState] = {
    RunStateEnum.DRAFT: ApprovalState.DRAFT,
    RunStateEnum.FAIL: ApprovalState.DRAFT,
    RunStateEnum.PASS: ApprovalState.MACHINE_VALIDATED,
    RunStateEnum.PASS_WITH_WARNINGS: ApprovalState.MACHINE_VALIDATED,
    RunStateEnum.MANUAL_REVIEW_REQUIRED: ApprovalState.EXPERT_REVIEWED,
    RunStateEnum.HUMAN_APPROVED: ApprovalState.APPROVED,
    RunStateEnum.LOCKED: ApprovalState.APPROVED,
}
# 역방향은 "대표값"만 고른다(위 collision 그룹당 1개) — SUPERSEDED는 run_state에 대표값이
# 아예 없다(위 근거 참조). 대표값 선정 기준: 각 그룹에서 "가장 이르게/보수적으로 도달하는"
# 상태를 고른다(FAIL보다 DRAFT, WARNINGS보다 PASS, LOCKED보다 HUMAN_APPROVED — 재구성 시
# 더 관대한 원형 상태를 임의로 단정하지 않기 위함).
_APPROVAL_TO_RUN_STATE_REPRESENTATIVE: dict[ApprovalState, RunStateEnum] = {
    ApprovalState.DRAFT: RunStateEnum.DRAFT,
    ApprovalState.MACHINE_VALIDATED: RunStateEnum.PASS,
    ApprovalState.EXPERT_REVIEWED: RunStateEnum.MANUAL_REVIEW_REQUIRED,
    ApprovalState.APPROVED: RunStateEnum.HUMAN_APPROVED,
    # ApprovalState.SUPERSEDED: 의도적으로 미등재 — approval_to_run_state()가 예외로 거부.
}


def run_state_to_approval(state: RunStateEnum | str) -> ApprovalState:
    """RunStateEnum → 공용 ApprovalState(전 7종 총함수 — 다대일 접힘은 위 표 참조)."""
    return _RUN_STATE_TO_APPROVAL[RunStateEnum(state)]


def approval_to_run_state(state: ApprovalState | str) -> RunStateEnum:
    """공용 ApprovalState → RunStateEnum 대표값(SUPERSEDED는 대응 없어 예외 — 무날조).

    ★비가역 경고: 이 함수의 반환값이 run_state_to_approval()의 입력과 항등(원문 그대로)
      임을 보장하지 않는다(예: PASS_WITH_WARNINGS로 들어가도 PASS로 나온다). 보장하는 것은
      "공용상태 보존"뿐이다 — approval_to_run_state가 돌려준 대표값을 다시
      run_state_to_approval에 넣으면 원래 넣었던 ApprovalState가 그대로 나온다.
    """
    state = ApprovalState(state)
    try:
        return _APPROVAL_TO_RUN_STATE_REPRESENTATIVE[state]
    except KeyError as e:
        raise UnmappedApprovalStateError(
            f"run_state(RunStateEnum)에는 {state.value} 에 대응하는 상태가 없습니다"
            "(C2R은 오래된 run을 강등하지 않고 새 run_id로 재발급합니다 — SUPERSEDED 개념 부재)."
        ) from e


__all__ = [
    "UnmappedApprovalStateError",
    "approval_to_artifact_status",
    "approval_to_design_run_status",
    "approval_to_run_state",
    "artifact_status_to_approval",
    "design_run_status_to_approval",
    "run_state_to_approval",
]
