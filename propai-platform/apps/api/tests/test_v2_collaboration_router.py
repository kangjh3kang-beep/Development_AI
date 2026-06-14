"""SP2-3b: v2_collaboration 라우터 contract — 초대 발급 엔드포인트(인증·빌드·화이트리스트·검증).

DB I/O(repo)는 monkeypatch, 인증 의존성은 override해 라우터의 HTTP 계약 + 서비스코어 배선을
실검증한다(실제 DB 영속은 통합 경계 — 테스트 Postgres 가용 시). require_project_member의 강제는
test_collaboration_deps에서 별도 검증됨.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.collaboration.collaboration_repo as repo
from app.core.database import get_db
from app.routers.v2_collaboration import router, _require_admin, _require_member
from app.services.auth.auth_service import get_current_user

OID = uuid.uuid4()
UID = uuid.uuid4()
PID = str(uuid.uuid4())


class _Member:
    organization_id = OID
    project_id = PID


class _User:
    id = UID


class _Invite:
    """repo.insert_invite가 돌려주는 가짜 — build_invite_fields의 dict로 채워진다."""

    def __init__(self, fields):
        self.id = uuid.uuid4()
        for k, v in fields.items():
            setattr(self, k, v)


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_admin] = lambda: _Member()
    app.dependency_overrides[_require_member] = lambda: _Member()
    app.dependency_overrides[get_current_user] = lambda: _User()

    async def _fake_db():
        yield None  # repo가 monkeypatch라 db 미사용

    app.dependency_overrides[get_db] = _fake_db

    async def _fake_insert(db, fields):
        return _Invite(fields)

    monkeypatch.setattr(repo, "insert_invite", _fake_insert)
    return TestClient(app)


def _post(client, **body):
    return client.post(f"/api/v2/collaboration/projects/{PID}/invites", json=body)


class TestCreateInvite:
    def test_creates_with_filtered_scope_and_token(self, client):
        r = _post(
            client,
            email="vendor@traffic.co",
            project_role="external_reviewer",
            scope_categories=["traffic", "fire", "hacking"],
            ttl_days=7,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["scope_categories"] == ["traffic", "fire"]  # 6 카테고리 화이트리스트(hacking 제거)
        assert j["status"] == "pending"
        assert j["email"] == "vendor@traffic.co"
        assert j["invite_token"]  # 생성 직후 1회 토큰 노출

    def test_invalid_email_rejected_400(self, client):
        r = _post(client, email="no-at-sign", scope_categories=[])
        assert r.status_code == 400

    def test_invalid_role_rejected_400(self, client):
        r = _post(client, email="x@y.zz", project_role="hacker", scope_categories=[])
        assert r.status_code == 400

    def test_empty_scope_allowed_returns_empty(self, client):
        r = _post(client, email="x@y.zz", scope_categories=[])
        assert r.status_code == 200
        assert r.json()["scope_categories"] == []
