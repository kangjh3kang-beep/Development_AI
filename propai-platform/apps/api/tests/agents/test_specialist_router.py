"""Phase 3.2 — SpecialistAgent HTTP 라우터(W4 노출) 테스트. 경량 TestClient + 인증 오버라이드.

casbin 미설치 env에서도 동작: 라우터는 jwt_handler.get_current_user(인증)만 의존(RBAC/casbin 불요).
coordinator.dispatch는 monkeypatch로 격리(원장/DB 비의존 — 라우터 계약·테넌트 스코프만 검증).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt_handler import get_current_user
from apps.api.routers.specialist_agents import router


class _FakeUser:
    def __init__(self, tenant_id="tenant-x"):
        self.user_id = "u1"
        self.tenant_id = tenant_id


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/agents/specialist")
    return app


def test_dispatch_requires_auth():
    c = TestClient(_app())
    r = c.post("/api/v1/agents/specialist/dispatch", json={"domain": "permit", "data": {}})
    assert r.status_code in (401, 403)        # 무토큰 → 인증 차단(보안)


def test_dispatch_scopes_tenant_and_returns(monkeypatch):
    from apps.api.core.coordinator import AgentCoordinator
    captured = {}

    async def fake(self, domain, data, **ctx):
        captured.update({"domain": domain, **ctx})
        return {"ok": True, "domain": domain, "ledger": {"ok": True}}

    monkeypatch.setattr(AgentCoordinator, "dispatch", fake)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser("tenant-x")
    c = TestClient(app)
    r = c.post("/api/v1/agents/specialist/dispatch",
               json={"domain": "permit",
                     "data": {"dev_type": "M06", "zone_type": "제2종일반주거지역"}, "pnu": "P1"})
    assert r.status_code == 200 and r.json()["ok"] is True
    # 테넌트는 클라이언트 입력이 아닌 인증 사용자로 강제(교차테넌트 차단)
    assert captured["tenant_id"] == "tenant-x" and captured["pnu"] == "P1"


def test_dispatch_unknown_domain_returns_400(monkeypatch):
    from apps.api.core.coordinator import AgentCoordinator

    async def fake(self, domain, data, **ctx):
        return {"ok": False, "message": "unknown domain: x"}

    monkeypatch.setattr(AgentCoordinator, "dispatch", fake)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    c = TestClient(app)
    r = c.post("/api/v1/agents/specialist/dispatch", json={"domain": "x", "data": {}})
    assert r.status_code == 400


# ── #2 prod RBAC(domain_agents:write) — casbin 가용 seam을 monkeypatch로 검증 ──

def test_dispatch_rbac_denied_returns_403(monkeypatch):
    from apps.api.routers import specialist_agents as mod
    monkeypatch.setattr(mod, "_rbac_check", lambda role, res, act: False)  # 권한 거부 시뮬
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    c = TestClient(app)
    r = c.post("/api/v1/agents/specialist/dispatch", json={"domain": "permit", "data": {}})
    assert r.status_code == 403   # RBAC 거부 → coordinator 호출 전 차단


def test_dispatch_rbac_allowed_passes(monkeypatch):
    from apps.api.routers import specialist_agents as mod
    from apps.api.core.coordinator import AgentCoordinator
    monkeypatch.setattr(mod, "_rbac_check", lambda role, res, act: True)

    async def fake(self, domain, data, **ctx):
        return {"ok": True, "domain": domain, "ledger": {"ok": True}}

    monkeypatch.setattr(AgentCoordinator, "dispatch", fake)
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    c = TestClient(app)
    r = c.post("/api/v1/agents/specialist/dispatch", json={"domain": "permit", "data": {}})
    assert r.status_code == 200 and r.json()["ok"] is True
