"""LiveKit 화상회의 — 룸명·권한 순수 규칙(결정론, 인프라/키 불요).

프로젝트 스코프 룸명과 역할별 VideoGrant(publish/subscribe/roomAdmin)·녹화 권한을 결정론으로 산출한다.
접근 가능 여부(멤버십)는 라우터 require_project_member가 1차 강제하고, 본 규칙은 그 위에서 역할별
권한만 부여한다(LLM·외부호출 0 — 단위테스트로 완전 검증).
"""

from __future__ import annotations

# host: 룸 관리(킥·녹화). 내부 PM·소유자.
HOST_ROLES = ("owner", "manager")
# 발화(카메라/마이크 송출) 허용 역할. viewer·미지 역할은 구독(시청)만.
PUBLISH_ROLES = ("owner", "manager", "contributor", "reviewer_internal", "external_reviewer")


def room_name(project_id: str, room_key: str = "main") -> str:
    """프로젝트 스코프 룸명(결정론) — 프로젝트 간 룸 충돌 방지. 안전 문자(영숫자·-_)만 허용·40자 제한.

    비안전/비ASCII만 있거나 빈값이면 'main'으로 폴백(룸명 누락 방지).
    """
    safe = "".join(ch for ch in (room_key or "") if ch.isalnum() and ch.isascii() or ch in "-_")[:40]
    return f"proj-{project_id}-{safe or 'main'}"


def video_grant(project_role: str, room: str) -> dict:
    """역할 → LiveKit VideoGrant 권한(결정론).

    host(owner/manager)=roomAdmin+발화, participant=발화, viewer/미지=구독만(최소권한). 멤버 여부는
    라우터가 이미 검증했다는 전제(본 규칙은 역할별 권한만).
    """
    is_host = project_role in HOST_ROLES
    can_publish = project_role in PUBLISH_ROLES
    return {
        "room": room,
        "room_join": True,
        "can_publish": can_publish,
        "can_publish_data": can_publish,
        "can_subscribe": True,
        "room_admin": is_host,
    }


def can_record(project_role: str) -> bool:
    """녹화(Egress) 시작/중지 권한 — host(owner/manager)만."""
    return project_role in HOST_ROLES
