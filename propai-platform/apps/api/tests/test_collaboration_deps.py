"""SP2-3a: require_project_member 의존성 — 프로젝트 멤버십 기반 접근제어(app-level 1차 강제).

공용 get_db가 RLS GUC를 미주입하므로(검증됨), 격리는 본 멤버십 DB조회가 1차로 담당한다. DB는
의존성 오버라이드(가짜 세션)로 대체해 의존성의 결정 로직(member_allows 배선·403/200)을 실검증한다.
"""

import uuid

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import ProjectMember
from app.services.auth.auth_service import get_current_user

PID = str(uuid.uuid4())
UID = uuid.uuid4()


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """execute()가 무엇이 오든 미리 정한 멤버(or None)를 돌려주는 가짜 세션."""

    def __init__(self, member):
        self._member = member

    async def execute(self, *a, **k):
        return _FakeResult(self._member)


class _User:
    id = UID
    tenant_id = uuid.uuid4()


def _member(role: str, status: str = "active") -> ProjectMember:
    m = ProjectMember()
    m.project_id = PID
    m.user_id = UID
    m.project_role = role
    m.status = status
    return m


def _client(member) -> TestClient:
    app = FastAPI()

    @app.get("/p/{project_id}/guard")
    async def guarded(m: ProjectMember = Depends(require_project_member("owner", "manager"))):
        return {"role": m.project_role}

    async def _fake_db():
        yield _FakeSession(member)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _User()
    return TestClient(app)


class TestRequireProjectMember:
    def test_allowed_role_active_passes(self):
        r = _client(_member("manager")).get(f"/p/{PID}/guard")
        assert r.status_code == 200
        assert r.json()["role"] == "manager"

    def test_wrong_role_forbidden(self):
        assert _client(_member("viewer")).get(f"/p/{PID}/guard").status_code == 403

    def test_no_membership_forbidden(self):
        assert _client(None).get(f"/p/{PID}/guard").status_code == 403

    def test_inactive_member_forbidden_even_if_role_ok(self):
        assert _client(_member("manager", status="removed")).get(f"/p/{PID}/guard").status_code == 403
