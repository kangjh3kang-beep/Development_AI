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
    """FastAPI 의존성: 지정 역할만 접근 허용.

    사용 예:
        @router.get("/admin-only", dependencies=[Depends(require_role(Role.ADMIN))])
    """
    def dependency(request=None):
        if request is None:
            return True

        # 헤더에서 역할 추출 (실제 환경: JWT 토큰에서)
        user_role_str = None
        if hasattr(request, "headers"):
            user_role_str = request.headers.get("x-user-role")
        if hasattr(request, "state") and hasattr(request.state, "user_role"):
            user_role_str = request.state.user_role

        if user_role_str is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="인증 필요")

        try:
            user_role = Role(user_role_str)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail=f"알 수 없는 역할: {user_role_str}")

        if user_role not in roles:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail=f"권한 부족: {user_role.value} 역할로는 접근할 수 없습니다",
            )
        return user_role

    return dependency
