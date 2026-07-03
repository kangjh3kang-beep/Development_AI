"""v2 수지분석 라우터 테스트 — 경량 TestClient (전체 앱 비의존).

VCS 4종 엔드포인트는 Phase1 보안강화로 Depends(get_current_user)가 의도적으로
추가됨(app/routers/v2_feasibility.py:861~913) → test_design_v61_router.py:98-101
패턴을 재사용해 dependency_overrides로 가짜 사용자를 주입한다.
DB 비의존 원칙 유지 — get_db는 FeasibilityVCSDB가 사용하는 ORM 호출
(select/add/flush)만 흉내내는 인메모리 세션으로 override한다.
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.v2_feasibility import router
from app.services.auth.auth_service import get_current_user
from database.models.feasibility_vcs import FeasibilityBranch, FeasibilityCommit

_TENANT_ID = uuid.uuid4()


class _FakeUser:
    """get_current_user override용 가짜 사용자 — VCS 경로는 tenant_id만 사용."""

    def __init__(self, tenant_id=_TENANT_ID):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeVCSSession:
    """FeasibilityVCSDB가 쓰는 ORM select/add/flush만 흉내내는 인메모리 세션.

    select 문의 entity(column_descriptions)와 바인드 파라미터(compile().params)로
    분기해 project_id/sha 필터를 적용한다 — 실 DB 불요(경량앱 원칙 유지).
    """

    def __init__(self):
        self.branches: list = []
        self.commits: list = []

    def add(self, obj):
        if isinstance(obj, FeasibilityBranch):
            self.branches.append(obj)
        elif isinstance(obj, FeasibilityCommit):
            self.commits.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None

    async def execute(self, stmt, params=None):  # noqa: ANN001
        entity = stmt.column_descriptions[0]["entity"]
        bound = stmt.compile().params

        def _param(prefix):
            for key, value in bound.items():
                if key.startswith(prefix):
                    return value
            return None

        pid = _param("project_id")
        if entity is FeasibilityBranch:
            return _FakeResult(
                [b for b in self.branches if pid is None or b.project_id == pid]
            )
        if entity is FeasibilityCommit:
            sha = _param("sha")
            return _FakeResult([
                c for c in self.commits
                if (pid is None or c.project_id == pid)
                and (sha is None or c.sha == sha)
            ])
        return _FakeResult([])


_vcs_session = _FakeVCSSession()


async def _override_get_db():
    yield _vcs_session


# 경량 테스트 앱: v2_feasibility 라우터만 등록 + 인증·DB 의존성 override
_app = FastAPI()
_app.include_router(router)
_app.dependency_overrides[get_current_user] = lambda: _FakeUser()
_app.dependency_overrides[get_db] = _override_get_db
client = TestClient(_app)


class TestCalculateEndpoint:
    def test_basic_calculate(self):
        resp = client.post("/api/v2/feasibility/calculate", json={
            "development_type": "M06",
            "total_land_area_sqm": 50000,
            "total_gfa_sqm": 100000,
            "total_households": 1000,
            "avg_sale_price_per_pyeong": 15000000,
            "avg_area_pyeong": 30,
            "sido_name": "경기",
            "sigungu_name": "수원시",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["development_type"] == "M06"
        assert data["grade"] in "ABCDEF"
        assert data["total_revenue_won"] > 0

    def test_invalid_type(self):
        resp = client.post("/api/v2/feasibility/calculate", json={
            "development_type": "M99",
            "total_land_area_sqm": 50000,
            "total_gfa_sqm": 100000,
        })
        assert resp.status_code == 422

    def test_zero_area(self):
        resp = client.post("/api/v2/feasibility/calculate", json={
            "development_type": "M06",
            "total_land_area_sqm": 0,
            "total_gfa_sqm": 100000,
        })
        assert resp.status_code == 422


class TestCompareEndpoint:
    def test_compare_two(self):
        resp = client.post("/api/v2/feasibility/compare", json={
            "projects": [
                {
                    "development_type": "M01",
                    "total_land_area_sqm": 50000,
                    "total_gfa_sqm": 100000,
                    "total_households": 1000,
                    "avg_sale_price_per_pyeong": 15000000,
                    "avg_area_pyeong": 30,
                },
                {
                    "development_type": "M06",
                    "total_land_area_sqm": 50000,
                    "total_gfa_sqm": 100000,
                    "total_households": 1000,
                    "avg_sale_price_per_pyeong": 15000000,
                    "avg_area_pyeong": 30,
                },
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert "comparison" in data


class TestModulesEndpoint:
    def test_list_modules(self):
        resp = client.get("/api/v2/feasibility/modules")
        assert resp.status_code == 200
        assert len(resp.json()["modules"]) == 15


class TestMonteCarloEndpoint:
    def test_basic(self):
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "variables": [
                {"name": "revenue", "mean": 1000, "std": 100},
                {"name": "cost", "mean": 800, "std": 50},
            ],
            "n_simulations": 1000,
            "seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["n_simulations"] == 1000
        assert data["probability_positive"] > 0


class TestVCSEndpoints:
    def test_commit_and_log(self):
        pid = "test-project-001"
        resp = client.post(f"/api/v2/feasibility/repos/{pid}/commit", json={
            "message": "초기 커밋",
            "snapshot": {"revenue": 100, "cost": 80},
        })
        assert resp.status_code == 200
        resp.json()["sha"]

        resp = client.get(f"/api/v2/feasibility/repos/{pid}/log")
        assert resp.status_code == 200
        assert len(resp.json()["commits"]) >= 1

    def test_rollback(self):
        pid = "test-rollback-001"
        r1 = client.post(f"/api/v2/feasibility/repos/{pid}/commit", json={
            "message": "v1", "snapshot": {"v": 1},
        })
        sha1 = r1.json()["sha"]
        client.post(f"/api/v2/feasibility/repos/{pid}/commit", json={
            "message": "v2", "snapshot": {"v": 2},
        })

        resp = client.post(f"/api/v2/feasibility/repos/{pid}/rollback", json={
            "target_sha": sha1,
        })
        assert resp.status_code == 200


class TestRecommendationsEndpoint:
    def test_basic(self):
        resp = client.post("/api/v2/feasibility/recommendations", json={
            "development_type": "M06",
            "total_land_area_sqm": 50000,
            "total_gfa_sqm": 100000,
            "total_households": 1000,
            "avg_sale_price_per_pyeong": 15000000,
            "avg_area_pyeong": 30,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
