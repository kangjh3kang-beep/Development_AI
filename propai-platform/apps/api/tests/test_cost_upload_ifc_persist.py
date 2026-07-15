"""회귀 테스트 — /api/v1/cost/{project_id}/upload-ifc 의 'bim_quantities 미영속' 결함 봉합.

결함(수정 전): upload_ifc 가 요소를 공종코드로 매핑만 하고 bim_quantities 에 영속하지
않아, GET /{project_id}/bim-quantities/origin-cost 체인이 항상 no_bim_quantities 로 단절.

수정: 매핑 결과를 bim_quantities(app.models.v61_cost.BimQuantity — 부트스트랩 테이블과
동일 컬럼)로 영속하고 persisted_rows 로 정직 표기. DB 미가용 시 graceful(persisted_rows=0).

DB 비의존 — get_db override(add_all/commit 캡처 가짜 세션) + _ensure_cost_tables no-op patch.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.cost import router
from app.services.auth.auth_service import get_current_user
from apps.api.database.session import get_db

TEST_PROJECT_ID = str(uuid.uuid4())

IFC_ELEMENTS = [
    {"element_type": "IfcWall", "quantity": 100, "global_id": "w1",
     "name": "외벽", "unit": "m3"},
    {"element_type": "IfcSlab", "quantity": 200, "global_id": "s1",
     "name": "슬래브", "unit": "m3"},
]


class _User:
    id = "00000000-0000-0000-0000-000000000001"
    tenant_id = "00000000-0000-0000-0000-000000000002"
    role = "user"
    is_active = True


class _CapturingSession:
    """add_all/commit 만 캡처하는 가짜 비동기 세션(실 DB 비의존)."""

    def __init__(self) -> None:
        self.added: list = []
        self.committed = False

    def add_all(self, rows) -> None:
        self.added.extend(rows)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:  # pragma: no cover — 정상 경로 미도달
        pass

    async def close(self) -> None:
        pass


def _build_client(session: _CapturingSession) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User()

    async def _override_db():
        yield session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


class TestUploadIFCPersists:
    def test_upload_ifc_persists_bim_quantities(self):
        session = _CapturingSession()
        client = _build_client(session)

        # _ensure_cost_tables 는 DDL 실행(실 DB 필요)이므로 no-op 로 대체 — 영속 로직만 검증.
        with patch(
            "app.services.cost.cost_tables_bootstrap._ensure_cost_tables",
            new=AsyncMock(return_value=None),
        ):
            resp = client.post(
                f"/api/v1/cost/{TEST_PROJECT_ID}/upload-ifc",
                json={"elements": IFC_ELEMENTS},
            )

        assert resp.status_code == 200
        data = resp.json()
        # 기존 계약 불변(회귀 0).
        assert data["item_count"] > 0
        assert len(data["unique_work_codes"]) > 0
        assert len(data["mapped_items"]) == data["item_count"]
        # 신규 계약: 매핑 항목 전부 bim_quantities 로 영속(persisted_rows == item_count).
        assert data["persisted_rows"] == data["item_count"]
        assert session.committed is True
        assert len(session.added) == data["item_count"]
        # 영속 행이 공종코드·프로젝트를 실제로 담고 있음(origin-cost 체인 입력 정합).
        for row in session.added:
            assert row.work_code, "work_code 누락 — origin-cost 집계 불가"
            assert str(row.project_id) == TEST_PROJECT_ID

    def test_upload_ifc_graceful_when_persist_fails(self):
        """DB/부트스트랩 실패 시에도 매핑은 반환하되 persisted_rows=0(정직·가짜 성공 없음)."""
        session = _CapturingSession()
        client = _build_client(session)

        with patch(
            "app.services.cost.cost_tables_bootstrap._ensure_cost_tables",
            new=AsyncMock(side_effect=RuntimeError("DB 연결 실패(테스트 주입)")),
        ):
            resp = client.post(
                f"/api/v1/cost/{TEST_PROJECT_ID}/upload-ifc",
                json={"elements": IFC_ELEMENTS},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] > 0  # 매핑 응답은 무영향
        assert data["persisted_rows"] == 0  # 영속 실패 정직 표기
        assert session.committed is False
