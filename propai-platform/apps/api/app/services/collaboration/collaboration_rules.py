"""SP2 협업 순수 규칙 — 초대 라이프사이클·역할검증·심의범위 화이트리스트(결정론·부작용 0).

now를 주입받아 만료 판정을 결정론으로 한다(시계 의존 제거). 접근제어 강제는 라우터 의존성
require_project_member(후속)가 본 규칙을 사용한다.
"""

from datetime import datetime

from app.models.collaboration import PROJECT_ROLES, REVIEW_CATEGORIES


def is_invite_expired(expires_at: datetime, now: datetime) -> bool:
    """초대 만료 여부 — now 주입 결정론."""
    return expires_at < now


def is_invite_acceptable(status: str, expires_at: datetime, now: datetime) -> bool:
    """수락 가능 여부 — pending이고 미만료일 때만(회수·이미수락·만료는 거부)."""
    return status == "pending" and not is_invite_expired(expires_at, now)


def validate_project_role(role: str) -> bool:
    """프로젝트 역할이 허용 집합(PROJECT_ROLES)에 속하는지."""
    return role in PROJECT_ROLES


def filter_scope_categories(requested, allowed) -> list[str]:
    """접근 허용 심의 카테고리 = 요청 ∩ (허용 화이트리스트 ∩ 유효 카테고리).

    순서 보존·중복 제거. allowed가 비면 전부 차단(기밀 기본 비공개). 유효하지 않은 카테고리
    (가짜·범위초과)는 서버측에서 제거한다(클라이언트 숨김에 의존 금지).
    """
    allowed_set = set(allowed or []) & set(REVIEW_CATEGORIES)
    out: list[str] = []
    for c in requested or []:
        if c in allowed_set and c not in out:
            out.append(c)
    return out
