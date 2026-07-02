"""C2R/HITL 실행(run) 상태 SSOT — RunStateEnum.

C2R 파이프라인(4-track DAG·검증 오버레이·HITL 승인)이 공유하는 단일 실행 상태 열거형.

★설계 주의(그린필드 금지·회귀 0):
- 기존 배치 잡 상태(`app/foundation/parcel/contracts/batch.py`의 JobState:
  RUNNING/COMPLETE/PARTIAL/CANCELLED, '진행성')와는 **의미론이 다른 별개 상태머신**이다
  (RunStateEnum은 '검증·승인성'). 강제로 하나로 합치면 배치≠검증 의미가 파괴된다.
- 그래서 P0에서는 **이 SSOT만 신규 도입**하고, 기존 상태머신은 손대지 않는다(회귀 0).
  실제 3곳(job_state/pipeline/orchestration) 통일 배선은 이들이 C2R을 소비하는
  단계(P3 orchestration)가 생길 때 점진적으로 적용한다.
"""

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - Python 3.10 백포트
    from enum import Enum

    class StrEnum(str, Enum):
        pass


class RunStateEnum(StrEnum):
    """C2R run/검증 파이프라인 실행 상태(단일 소스).

    전이(예): DRAFT → (검증) → PASS | PASS_WITH_WARNINGS | FAIL | MANUAL_REVIEW_REQUIRED
              → (HITL 승인) → HUMAN_APPROVED → LOCKED.
    """

    DRAFT = "draft"                                   # 초안 생성(미검증)
    PASS = "pass"                                      # 검증 통과
    PASS_WITH_WARNINGS = "pass_with_warnings"          # 통과(경고 동반)
    FAIL = "fail"                                      # 검증 실패
    MANUAL_REVIEW_REQUIRED = "manual_review_required"  # 수동 검토 필요(게이트)
    HUMAN_APPROVED = "human_approved"                  # 인간 승인 완료(HITL)
    LOCKED = "locked"                                  # 확정·잠금(불변)


# `from packages.schemas.run_state import *` 시 RunStateEnum 만 노출(StrEnum 백포트 누출 방지).
__all__ = ["RunStateEnum"]
