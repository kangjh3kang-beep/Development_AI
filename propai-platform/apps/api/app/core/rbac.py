"""역할기반 접근제어(RBAC) 엔진.

6개 역할(admin/manager/developer/user/viewer/auditor)에 대해
경로·메서드 기반 정책을 정의하고, FastAPI 의존성으로 주입한다.
"""

from enum import Enum
from typing import Optional
import fnmatch


class Role(str, Enum):
    """시스템 역할."""
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"
    USER = "user"
    VIEWER = "viewer"
    AUDITOR = "auditor"


# 역할별 허용 정책: {경로 패턴: {HTTP 메서드 집합}}
ROLE_POLICIES: dict[Role, dict[str, set[str]]] = {
    Role.ADMIN: {
        "/api/*": {"GET", "POST", "PUT", "PATCH", "DELETE"},
    },
    Role.MANAGER: {
        "/api/v1/projects/*": {"GET", "POST", "PUT", "DELETE"},
        "/api/v1/agents/*": {"GET", "POST"},
        "/api/v1/finance/*": {"GET", "POST"},
        "/api/v1/avm/*": {"GET", "POST"},
        "/api/v1/esg/*": {"GET", "POST"},
        "/api/v1/auth/me": {"GET"},
    },
    Role.DEVELOPER: {
        "/api/v1/*": {"GET", "POST", "PUT"},
        "/api/v2/*": {"GET", "POST", "PUT"},
        "/health": {"GET"},
        "/health/*": {"GET"},
        "/metrics": {"GET"},
    },
    Role.USER: {
        "/api/v1/avm/*": {"GET", "POST"},
        "/api/v1/projects/*": {"GET", "POST"},
        "/api/v1/finance/*": {"GET"},
        "/api/v1/esg/*": {"GET"},
        "/api/v1/auth/me": {"GET"},
    },
    Role.VIEWER: {
        "/api/v1/*": {"GET"},
        "/api/v2/*": {"GET"},
        "/health": {"GET"},
    },
    Role.AUDITOR: {
        "/api/v1/audit/*": {"GET"},
        "/api/v1/auth/me": {"GET"},
        "/health": {"GET"},
    },
}


class RBACEngine:
    """역할기반 접근제어 엔진."""

    def __init__(self, policies: Optional[dict] = None):
        self._policies = policies or ROLE_POLICIES

    def check_permission(self, role: Role, path: str, method: str) -> bool:
        """역할·경로·메서드 조합의 접근 허용 여부를 반환한다."""
        method = method.upper()
        role_policy = self._policies.get(role, {})

        for pattern, allowed_methods in role_policy.items():
            if fnmatch.fnmatch(path, pattern) and method in allowed_methods:
                return True
        return False

    def get_allowed_methods(self, role: Role, path: str) -> set[str]:
        """특정 역할·경로에 허용된 메서드 집합을 반환한다."""
        role_policy = self._policies.get(role, {})
        methods: set[str] = set()
        for pattern, allowed_methods in role_policy.items():
            if fnmatch.fnmatch(path, pattern):
                methods |= allowed_methods
        return methods

    def list_accessible_paths(self, role: Role) -> list[str]:
        """역할에 허용된 모든 경로 패턴을 반환한다."""
        return list(self._policies.get(role, {}).keys())


_engine = RBACEngine()


def get_rbac_engine() -> RBACEngine:
    """전역 RBAC 엔진 반환."""
    return _engine


def require_role(*roles: Role):
    """FastAPI 의존성: 인증된 사용자만 접근 허용 (P0-5 보안 수정).

    get_current_user로 JWT 인증을 강제한다(토큰 없으면 get_current_user가 401). Role.ADMIN
    요구 시 User.is_superuser로 게이트 — 가입 시 role 문자열이 일괄 'admin'이라 신뢰 불가하므로
    신뢰 가능한 is_superuser 플래그를 쓴다.

    ⚠️ 기존의 `request=None → return True` 폴스루(FastAPI가 미타입 request를 주입하지 않아 사실상
    상시 우회) + `x-user-role` 헤더 신뢰(클라이언트 조작 가능)는 인증 우회였으므로 제거.

    사용 예:
        @router.get("/admin-only", dependencies=[Depends(require_role(Role.ADMIN))])
    """
    from fastapi import Depends, HTTPException
    from app.services.auth.auth_service import get_current_user

    async def dependency(current_user=Depends(get_current_user)):
        # get_current_user가 유효 토큰을 강제 → 인증된 사용자만 여기 도달.
        if Role.ADMIN in roles and not getattr(current_user, "is_superuser", False):
            raise HTTPException(
                status_code=403, detail="관리자(superuser) 권한이 필요합니다",
            )
        # 비-ADMIN 역할: 현재 사용처 없음. 인증 사용자면 통과(향후 DB user_roles 모델로 세분화).
        return current_user

    return dependency
