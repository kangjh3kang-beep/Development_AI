"""mass_backbone D1.5-wire — mass-templates 라우터 통합테스트(앱 전체 임포트 없이 라우터만 마운트).

get_db·get_current_user를 dependency_overrides로 대체하고 BuildingRegistryService를 stub으로
교체해, 라이브 DB/건축HUB 없이 라우팅·관리자 게이트·수집→저장·조회 응답을 검증한다.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import mass_templates as mt
from app.services.auth.auth_service import get_current_user
from apps.api.database.session import get_db


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _StubSession:
    """AsyncSession 대역 — execute/commit 캡쳐(라이브 DB 무관)."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _StubResult(self._rows)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _Admin:
    is_superuser = True


class _NonAdmin:
    is_superuser = False


class _FakeRegistry:
    """get_building_by_pnu stub — '1'/'2'는 아파트, 그 외 None(무자료)."""

    _DATA = {
        "1": {"main_purpose": "아파트", "bcr_pct": 20, "far_pct": 200, "ground_floors": 20, "total_area_sqm": 50000},
        "2": {"main_purpose": "아파트", "bcr_pct": 24, "far_pct": 240, "ground_floors": 25, "total_area_sqm": 60000},
    }

    async def get_building_by_pnu(self, pnu):
        return self._DATA.get(pnu)


def _make_app(rows=None, user=None):
    app = FastAPI()
    app.include_router(mt.router)
    sess = _StubSession(rows=rows)

    async def _db():
        yield sess

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: (user or _Admin())
    return app, sess


def test_collect_admin_persists(monkeypatch):
    monkeypatch.setattr(mt, "BuildingRegistryService", _FakeRegistry)
    app, sess = _make_app(user=_Admin())
    client = TestClient(app)
    r = client.post(
        "/api/v1/mass-templates/collect",
        json={"region": "동탄2", "zone_code": "3종", "pnus": ["1", "2", "3"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requested"] == 3 and body["fetched"] == 2   # '3'은 무자료 → 건너뜀(가짜 생성 금지)
    assert body["saved"] == len(body["templates"]) >= 1
    apt = next(t for t in body["templates"] if t["building_type"] == "공동주택")
    assert apt["sample_count"] == 2
    assert any("DELETE" in c[0].upper() for c in sess.calls)   # 저장(스냅샷 교체) 경로 실행됨


def test_collect_blocks_non_admin(monkeypatch):
    monkeypatch.setattr(mt, "BuildingRegistryService", _FakeRegistry)
    app, _ = _make_app(user=_NonAdmin())
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect", json={"region": "x", "pnus": ["1"]})
    assert r.status_code == 403   # superuser 아님 → require_role(ADMIN) 차단


def test_collect_validation_empty_pnus():
    app, _ = _make_app(user=_Admin())
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect", json={"region": "x", "pnus": []})
    assert r.status_code == 422   # pnus min_length=1 검증


def test_list_requires_auth():
    # get_current_user 미override → auth_service가 무토큰 401(인증 게이트 실경로 회귀방어).
    app = FastAPI()
    app.include_router(mt.router)
    sess = _StubSession(rows=[])

    async def _db():
        yield sess

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    r = client.get("/api/v1/mass-templates", params={"region": "x"})
    assert r.status_code in (401, 403)   # 무인증 차단


def test_list_templates_returns_store_rows():
    rows = [{
        "region": "동탄2", "building_type": "공동주택", "sample_count": 3,
        "median_bcr_pct": 22.0, "median_far_pct": 200.0,
    }]
    app, _ = _make_app(rows=rows, user=_Admin())
    client = TestClient(app)
    r = client.get("/api/v1/mass-templates", params={"region": "동탄2"})
    assert r.status_code == 200
    body = r.json()
    assert body["region"] == "동탄2" and body["count"] == 1
    assert body["templates"][0]["building_type"] == "공동주택"
