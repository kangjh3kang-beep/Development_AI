"""중심엔진 통합 Phase 0 — BFF 심의분석 헬스 프록시(`/api/v1/deliberation/health`).

엔진(별도 서비스)의 `/api/v1/doctor`를 인증 후 프록시하되 **화이트리스트 필드만 재발행**
(api_auth.enabled·*_key_present·master_key·model 등 보안태세 핑거프린트 비노출). 엔진 미연결 시 degraded.
격리 FastAPI 앱 + dependency_overrides(인증) + _fetch_engine_doctor monkeypatch(엔진 비의존).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.auth.auth_service import get_current_user
from apps.api.app.routers import deliberation as delib


class _FakeUser:
    def __init__(self, tenant_id="tenant-x"):
        self.id = "u1"
        self.tenant_id = tenant_id


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(delib.router)
    return app


def test_health_requires_auth():
    # 무인증 → 차단(보안 경계).
    r = TestClient(_app()).get("/api/v1/deliberation/health")
    assert r.status_code in (401, 403)


def test_health_returns_only_whitelisted_status(monkeypatch):
    async def fake_doctor():
        return ({
            "api_auth": {"enabled": False},          # 핑거프린트 — 비노출이어야
            "master_key_present": True,              # 비노출
            "openai_key_present": True,              # 비노출
            "sheet_classifier": {"live": True, "model": "claude-x"},  # live만 노출, model 비노출
            "jurisdiction": {"live": False},
            "embedder": {"semantic": True},
            "database": {"configured": True},
        }, "ok")
    monkeypatch.setattr(delib, "_fetch_engine_doctor", fake_doctor)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine"] == {
        "database_configured": True,
        "sheet_classifier_live": True,
        "jurisdiction_live": False,
        "embedder_semantic": True,
    }
    flat = str(body)
    for leak in ("master_key", "key_present", "api_auth", "claude-x", "model"):
        assert leak not in flat, f"핑거프린트 누출: {leak}"


def test_health_degraded_when_engine_unreachable(monkeypatch):
    async def none_doctor():
        return None, "engine_unreachable"  # 미연결/실패
    monkeypatch.setattr(delib, "_fetch_engine_doctor", none_doctor)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/health")
    assert r.status_code == 200  # 헬스카드는 degraded 표면화(무음0), 502 아님
    body = r.json()
    assert body["status"] == "degraded" and body["reason"] == "engine_unreachable"
    assert body["engine"] is None


def test_health_degraded_distinguishes_engine_rejected(monkeypatch):
    # 토큰 오설정(401/403)은 미연결과 구분 — 운영자가 토큰 결함을 찾을 수 있게 정직하게 표면화.
    async def rejected_doctor():
        return None, "engine_rejected"
    monkeypatch.setattr(delib, "_fetch_engine_doctor", rejected_doctor)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    r = TestClient(app).get("/api/v1/deliberation/health")
    body = r.json()
    assert body["status"] == "degraded" and body["reason"] == "engine_rejected"
