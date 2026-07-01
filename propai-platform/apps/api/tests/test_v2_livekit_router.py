"""LiveKit T2: v2_livekit 라우터 contract — 토큰·녹화 가드(미설정 503·비host 403).

LiveKit Cloud 키 없이 검증 가능한 가드 경로만(실 토큰 발급·Egress는 스테이징 검증 대상). 멤버십 강제는
require_project_member에서 별도 검증됨 — 본 테스트는 _require_member를 override해 권한·503 분기만 본다.
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.v2_livekit import _require_member, router
from app.services.auth.auth_service import get_current_user
from app.services.livekit import livekit_service

PID = str(uuid.uuid4())
UID = uuid.uuid4()


class _Member:
    def __init__(self, role="owner"):
        self.organization_id = uuid.uuid4()
        self.project_id = PID
        self.project_role = role
        self.user_id = UID


class _User:
    id = UID
    name = "테스터"
    email = "t@x.co"


def _client(role="owner") -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_member] = lambda: _Member(role)
    app.dependency_overrides[get_current_user] = lambda: _User()

    async def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


class TestToken:
    def test_unconfigured_503(self):
        # 테스트 환경엔 LIVEKIT 키 없음 → 503 정직 degrade(크래시 금지)
        r = _client("owner").post(f"/api/v2/livekit/projects/{PID}/rooms/main/token")
        assert r.status_code == 503


class TestRecordingGuards:
    def test_non_host_forbidden_403(self):
        for role in ("viewer", "external_reviewer", "contributor", "reviewer_internal"):
            r = _client(role).post(
                f"/api/v2/livekit/projects/{PID}/rooms/main/recording/start"
            )
            assert r.status_code == 403, role

    def test_host_egress_unconfigured_503(self):
        # host(owner/manager)지만 Egress/S3 미설정 → 503
        r = _client("owner").post(f"/api/v2/livekit/projects/{PID}/rooms/main/recording/start")
        assert r.status_code == 503
        assert _client("manager").post(
            f"/api/v2/livekit/projects/{PID}/rooms/main/recording/start"
        ).status_code == 503

    def test_stop_non_host_403(self):
        r = _client("viewer").post(
            f"/api/v2/livekit/projects/{PID}/recording/{uuid.uuid4()}/stop"
        )
        assert r.status_code == 403


class _Rec:
    def __init__(self, egress_id):
        self.id = uuid.uuid4()
        self.project_id = PID
        self.egress_id = egress_id
        self.s3_key = None
        self.status = "recording"
        self.room = "proj-x-supervision"
        self.started_at = None
        self.ended_at = None


class _RecResult:
    def __init__(self, rec):
        self._rec = rec

    def scalar_one_or_none(self):
        return self._rec


class _RecSession:
    def __init__(self, rec):
        self._rec = rec

    async def execute(self, *a, **k):
        return _RecResult(self._rec)

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


def _client_rec(rec, role="owner") -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_require_member] = lambda: _Member(role)
    app.dependency_overrides[get_current_user] = lambda: _User()

    async def _fake_db():
        yield _RecSession(rec)

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


class TestRecordingStopStatus:
    """정직: 실제 Egress 중지 성공 시에만 completed. egress 없음/실패는 failed(과대표기 금지)."""

    def test_null_egress_marked_failed(self):
        rec = _Rec(egress_id=None)  # start가 빈 egress_id 반환한 경우(추적 안 됨)
        r = _client_rec(rec).post(f"/api/v2/livekit/projects/{PID}/recording/{rec.id}/stop")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "failed"

    def test_stop_success_completed(self, monkeypatch):
        rec = _Rec(egress_id="eg-1")

        async def _ok(eid):
            return None

        monkeypatch.setattr(livekit_service, "stop_recording", _ok)
        r = _client_rec(rec).post(f"/api/v2/livekit/projects/{PID}/recording/{rec.id}/stop")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"

    def test_stop_failure_marked_failed(self, monkeypatch):
        rec = _Rec(egress_id="eg-1")

        async def _raise(eid):
            raise RuntimeError("egress down")

        monkeypatch.setattr(livekit_service, "stop_recording", _raise)
        r = _client_rec(rec).post(f"/api/v2/livekit/projects/{PID}/recording/{rec.id}/stop")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "failed"
