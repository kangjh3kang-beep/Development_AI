"""mass_backbone D1.5-wire — mass-templates 라우터 통합테스트(앱 전체 임포트 없이 라우터만 마운트).

get_db·get_current_user를 dependency_overrides로 대체하고 BuildingRegistryService를 stub으로
교체해, 라이브 DB/건축HUB 없이 라우팅·관리자 게이트·수집→저장·조회 응답을 검증한다.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db as core_get_db  # require_role 게이트가 쓰는 get_db(핸들러와 별개)
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

    def first(self):
        # is_super_admin의 SELECT tier 경로용 — stub은 tier 미보유 → None(비-super_admin)
        return None


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


class _User:
    id = "u1"


class _FakeRegistry:
    """get_building_by_pnu stub — '1'/'2'는 아파트, 그 외 None(무자료)."""

    _DATA = {
        "1": {"main_purpose": "아파트", "bcr_pct": 20, "far_pct": 200, "ground_floors": 20, "total_area_sqm": 50000},
        "2": {"main_purpose": "아파트", "bcr_pct": 24, "far_pct": 240, "ground_floors": 25, "total_area_sqm": 60000},
    }

    async def get_building_by_pnu(self, pnu):
        return self._DATA.get(pnu)


def _make_app(rows=None, *, super_admin=True):
    app = FastAPI()
    app.include_router(mt.router)
    sess = _StubSession(rows=rows)

    async def _db():
        yield sess

    app.dependency_overrides[get_db] = _db            # 핸들러 세션(apps.api.database.session)
    app.dependency_overrides[core_get_db] = _db       # 게이트 세션(require_role→app.core.database) 격리
    app.dependency_overrides[get_current_user] = lambda: _User()
    if super_admin:
        # 게이트 통과: require_admin(=require_role(ADMIN)) 직접 override(실제 is_super_admin DB조회 우회)
        app.dependency_overrides[mt.require_admin] = lambda: _User()
    # super_admin=False면 require_admin 미override → is_super_admin(stub)→False→403
    return app, sess


def test_collect_admin_persists(monkeypatch):
    monkeypatch.setattr(mt, "BuildingRegistryService", _FakeRegistry)
    app, sess = _make_app()
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
    app, _ = _make_app(super_admin=False)
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect", json={"region": "x", "pnus": ["1"]})
    assert r.status_code == 403   # super_admin 아님 → require_super_admin 차단


def test_collect_requires_auth():
    # get_current_user 미override → 무토큰 401(POST 게이트 인증 실경로 회귀방어).
    app = FastAPI()
    app.include_router(mt.router)
    sess = _StubSession()

    async def _db():
        yield sess

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect", json={"region": "x", "pnus": ["1"]})
    assert r.status_code in (401, 403)   # 무인증 차단


def test_collect_validation_empty_pnus():
    app, _ = _make_app()
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect", json={"region": "x", "pnus": []})
    assert r.status_code == 422   # pnus min_length=1 검증


def test_collect_region_admin_persists(monkeypatch):
    async def search_fn(dong):
        return "4113510800100010000" if "정자동" in dong else None

    async def title_fn(sgg, bjd):
        return [{"main_purpose": "아파트", "bcr_pct": 18, "far_pct": 200, "ground_floors": 20,
                 "total_area_sqm": 50000, "address": "경기도 성남시 분당구 정자동 1"}]

    async def recap_fn(sgg, bjd):
        return []

    monkeypatch.setattr(mt, "_make_region_collectors", lambda: (search_fn, title_fn, recap_fn))
    app, sess = _make_app()
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect-region",
                    json={"groups": [{"dongs": ["경기도 성남시 분당구 정자동", "없는동"]}]})
    assert r.status_code == 200, r.text
    body = r.json()
    g = body["groups"][0]
    assert g["region"] == "분당구" and g["resolved_dongs"] == 1   # 미해석 동 제외
    rgn = next(x for x in body["regions"] if x["region"] == "분당구")
    assert rgn["saved"] >= 1 and rgn["records"] == 1
    assert any("DELETE" in c[0].upper() for c in sess.calls)   # 스냅샷 교체 실행


def test_collect_region_merges_duplicate_region_groups(monkeypatch):
    # ★같은 시군구가 2개 그룹으로 와도 record 병합 → region당 1 스냅샷(후행이 선행 silent 삭제 방지·MEDIUM-1).
    async def search_fn(dong):
        m = {"정자동": "4113510800100010000", "백현동": "4113511800100010000"}
        return next((v for k, v in m.items() if k in dong), None)

    async def title_fn(sgg, bjd):
        addr = "경기도 성남시 분당구 정자동 1" if bjd == "10800" else "경기도 성남시 분당구 백현동 1"
        far = 200 if bjd == "10800" else 240
        return [{"main_purpose": "아파트", "bcr_pct": 20, "far_pct": far, "ground_floors": 20,
                 "total_area_sqm": 50000, "address": addr}]

    async def recap_fn(sgg, bjd):
        return []

    monkeypatch.setattr(mt, "_make_region_collectors", lambda: (search_fn, title_fn, recap_fn))
    app, sess = _make_app()
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect-region", json={"groups": [
        {"dongs": ["경기도 성남시 분당구 정자동"]},
        {"dongs": ["경기도 성남시 분당구 백현동"]},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    # 두 그룹 모두 분당구 → region 1개로 병합, 표본 2건(병합 후 median far=220)
    assert len(body["regions"]) == 1
    rgn = body["regions"][0]
    assert rgn["region"] == "분당구" and rgn["records"] == 2
    apt = next(t for t in rgn["templates"] if t["building_type"] == "공동주택")
    assert apt["sample_count"] == 2 and apt["median_far_pct"] == 220.0
    # DELETE는 분당구에 대해 1회만(스냅샷 충돌 없음)
    assert sum(1 for c in sess.calls if "DELETE" in c[0].upper()) == 1


def test_collect_region_recap_fills_bcr_far(monkeypatch):
    # ★공동주택 표제부는 건폐/용적 결측(0)이나 총괄표제부(recap_fn)에 충실 → 보강 검증.
    async def search_fn(dong):
        return "4113510800100010000"

    async def title_fn(sgg, bjd):  # 표제부: 공동주택 건폐/용적 0(결측)·층수·면적은 있음
        return [{"main_purpose": "아파트", "bcr_pct": 0, "far_pct": 0, "ground_floors": 20,
                 "total_area_sqm": 5000, "address": "경기도 성남시 분당구 정자동 1"}]

    async def recap_fn(sgg, bjd):  # 총괄표제부: 단지 기준 건폐/용적 충실
        return [{"main_purpose": "아파트", "bcr_pct": 18, "far_pct": 220, "ground_floors": 0,
                 "total_area_sqm": 90000, "address": "경기도 성남시 분당구 정자동 1"}]

    monkeypatch.setattr(mt, "_make_region_collectors", lambda: (search_fn, title_fn, recap_fn))
    app, _ = _make_app()
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect-region",
                    json={"groups": [{"dongs": ["경기도 성남시 분당구 정자동"]}]})
    assert r.status_code == 200, r.text
    apt = next(t for t in r.json()["regions"][0]["templates"] if t["building_type"] == "공동주택")
    assert apt["median_bcr_pct"] == 18.0 and apt["median_far_pct"] == 220.0   # 총괄에서 보강
    assert apt["median_total_area_sqm"] == 5000.0   # ★면적은 표제부 기준 유지(총괄 90000 미혼입)
    assert apt["metadata"]["bcr_far_source"] == "recap_title"   # provenance


def test_collect_region_blocks_non_admin(monkeypatch):
    monkeypatch.setattr(mt, "_make_region_collectors", lambda: (None, None, None))  # 게이트가 먼저 차단
    app, _ = _make_app(super_admin=False)
    client = TestClient(app)
    r = client.post("/api/v1/mass-templates/collect-region", json={"groups": [{"dongs": ["x"]}]})
    assert r.status_code == 403


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
    app, _ = _make_app(rows=rows)
    client = TestClient(app)
    r = client.get("/api/v1/mass-templates", params={"region": "동탄2"})
    assert r.status_code == 200
    body = r.json()
    assert body["region"] == "동탄2" and body["count"] == 1
    assert body["templates"][0]["building_type"] == "공동주택"
