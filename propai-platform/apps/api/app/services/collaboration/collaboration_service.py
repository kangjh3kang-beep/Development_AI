"""SP2 협업 서비스 코어 — 초대 생성·멤버 접근결정·수락 판정(결정론·DB세션 무관).

DB CRUD(insert/query)는 라우터 의존성(후속 SP2-3)이 담당하고, 본 모듈은 토큰/만료/심의범위/역할
결정을 결정론 코어로 제공한다(token_factory·now 주입 → 테스트 가능). require_project_member의
접근 판정도 member_allows로 분리해 단위검증 가능하게 한다.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from app.services.collaboration.collaboration_rules import (
    filter_scope_categories,
    is_invite_acceptable,
    validate_project_role,
)

DEFAULT_INVITE_TTL_DAYS = 14


def build_invite_fields(
    *,
    project_id: str,
    organization_id: str,
    email: str,
    project_role: str,
    requested_categories,
    allowed_categories,
    invited_by: str | None,
    now: datetime,
    token_factory: Callable[[], str],
    ttl_days: int = DEFAULT_INVITE_TTL_DAYS,
) -> dict[str, Any]:
    """CollaboratorInvite 행 생성 필드를 결정론으로 산출한다(아직 DB 미저장).

    역할 검증 + 심의범위 화이트리스트 필터 + 만료(now+ttl) + 토큰(주입 팩토리)을 적용한다.
    유효하지 않은 이메일/역할/ttl은 ValueError(가짜 초대 금지). 이메일은 trim+lower 정규화.
    """
    norm_email = (email or "").strip().lower()
    if "@" not in norm_email or norm_email.startswith("@") or norm_email.endswith("@"):
        raise ValueError("유효한 이메일이 필요합니다")
    if not validate_project_role(project_role):
        raise ValueError(f"허용되지 않은 프로젝트 역할: {project_role}")
    if ttl_days <= 0:
        raise ValueError("만료 기간(ttl_days)은 양수여야 합니다")

    return {
        "project_id": project_id,
        "organization_id": organization_id,
        "invite_token": token_factory(),
        "email": norm_email,
        "project_role": project_role,
        "scope_categories": filter_scope_categories(requested_categories, allowed_categories),
        "status": "pending",
        "expires_at": now + timedelta(days=ttl_days),
        "invited_by": invited_by,
    }


def member_allows(project_role: str, allowed_roles, status: str) -> bool:
    """엔드포인트 접근 허용 판정(require_project_member 코어) — active 상태 + 허용역할 포함."""
    return status == "active" and project_role in set(allowed_roles or [])


def accept_invite_result(status: str, expires_at: datetime, now: datetime) -> tuple[bool, str]:
    """초대 수락 판정 — (ok, reason). pending이고 미만료면 수락 가능."""
    if is_invite_acceptable(status, expires_at, now):
        return True, "ok"
    if status != "pending":
        return False, f"이미 처리된 초대(status={status})"
    return False, "만료된 초대"
