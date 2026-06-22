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


class _Project:
    def __init__(self, organization_id):
        self.organization_id = organization_id


class _SeqSession:
    """execute() 순서대로 미리 정한 결과를 돌려주는 가짜(1차 멤버조회→2차 프로젝트조회)."""

    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, *a, **k):
        return _FakeResult(self._results.pop(0) if self._results else None)


def _org_client(member, project, *, user_tenant) -> TestClient:
    app = FastAPI()

    @app.get("/p/{project_id}/guard")
    async def guarded(m: ProjectMember = Depends(require_project_member("owner", "manager"))):
        return {"role": m.project_role}

    class _OrgUser:
        id = UID
        tenant_id = user_tenant

    async def _fake_db():
        # 2차 조회는 select(Project.organization_id) — 스칼라(UUID)를 돌려준다(전체 Project 아님).
        yield _SeqSession(member, project.organization_id)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _OrgUser()
    return TestClient(app)


class TestOrgImplicitMembership:
    """프로젝트 소유자/내부팀(멤버 행 없음)도 자기 조직 프로젝트엔 owner로 접근 — 403 회의방 버그 수정."""

    def test_org_user_without_membership_gets_owner(self):
        org = uuid.uuid4()
        r = _org_client(None, _Project(org), user_tenant=org).get(f"/p/{PID}/guard")
        assert r.status_code == 200
        assert r.json()["role"] == "owner"

    def test_other_org_user_forbidden(self):
        # 프로젝트가 다른 조직 소유 → 암묵 멤버십 불가
        r = _org_client(None, _Project(uuid.uuid4()), user_tenant=uuid.uuid4()).get(f"/p/{PID}/guard")
        assert r.status_code == 403

    def test_no_tenant_user_forbidden(self):
        # tenant_id 없는 사용자(이상 케이스)는 암묵 멤버십 불가
        r = _org_client(None, _Project(uuid.uuid4()), user_tenant=None).get(f"/p/{PID}/guard")
        assert r.status_code == 403

    def test_explicit_removed_member_not_escalated_via_fallback(self):
        # 명시적 removed 멤버는 같은 조직이라도 암묵 owner 폴백으로 복원되면 안 됨(권한상승 방지)
        org = uuid.uuid4()
        r = _org_client(_member("manager", status="removed"), _Project(org), user_tenant=org).get(f"/p/{PID}/guard")
        assert r.status_code == 403

    def test_explicit_viewer_not_escalated_to_owner(self):
        # active이지만 허용역할(owner/manager) 아닌 명시 멤버가 owner로 상승되면 안 됨
        org = uuid.uuid4()
        r = _org_client(_member("viewer", status="active"), _Project(org), user_tenant=org).get(f"/p/{PID}/guard")
        assert r.status_code == 403
