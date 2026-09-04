"""회귀 테스트 — /api/v1/cost/{project_id}/upload-ifc 의 'bim_quantities 미영속' 결함 봉합.

결함(수정 전): upload_ifc 가 요소를 공종코드로 매핑만 하고 bim_quantities 에 영속하지
않아, GET /{project_id}/bim-quantities/origin-cost 체인이 항상 no_bim_quantities 로 단절.

수정: 매핑 결과를 bim_quantities 로 영속하고 persisted_rows 로 정직 표기. DB 미가용 시
graceful(persisted_rows=0). PR#315 리뷰 반영 — 정본 ORM(apps.api.database.models.v61_cost.
BimQuantity, TenantMixin)을 쓰는 공용 헬퍼 app.services.cost.bim_quantity_writer.
replace_bim_quantities 를 경유(H1 비멱등 이중적재 방지 + H2 ORM 이중정의 일원화).
소유권 검증(assert_project_owned, M1)도 추가 — tenant 불일치 시 403.

DB 비의존 — get_db override(add_all/commit/execute 캡처 가짜 세션) +
_ensure_cost_tables no-op patch. propai-platform/tests/ 하위(루트 계약 스위트 — .github/
workflows/ci.yml "Run root contract suite" 단계, working-directory=propai-platform)로
배치(PR#315 M2 반영). apps/api/tests/ 도 별도 "Run unit tests (apps/api)" 단계로 CI에
수집된다 — 두 스위트 모두 커버되도록 배선을 나눈다.
"""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import AsyncMock, patch

# apps/api(app.* 임포트) + propai-platform 루트(apps.api.* 임포트) 를 sys.path 에 추가
# (apps/api/tests/conftest.py 와 동일 목적 — 이 파일은 apps/api 밖의 tests/unit/ 에 위치).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "apps", "api"))
sys.path.insert(0, os.path.join(_HERE, "..", ".."))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.routers.cost import router  # noqa: E402
from app.services.auth.auth_service import get_current_user  # noqa: E402
from apps.api.database.session import get_db  # noqa: E402

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


class _FakeRow:
    """assert_project_owned 의 `(await db.execute(...)).first()` 계약 — 프로젝트 없음(None)."""

    @staticmethod
    def first():
        return None


class _CapturingSession:
    """add_all/commit/execute 를 캡처하는 가짜 비동기 세션(실 DB 비의존).

    execute() 는 assert_project_owned(소유권 SELECT)와 replace_bim_quantities(DELETE +
    _ensure_cost_tables DDL) 양쪽에서 호출된다 — 전부 무해한 no-op 로 응답.
    """

    def __init__(self) -> None:
        self.added: list = []
        self.committed = False
        self.executed: list = []

    def add_all(self, rows) -> None:
        self.added.extend(rows)

    async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.executed.append(args)
        return _FakeRow()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
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
        # H1: INSERT 전 프로젝트 스코프 DELETE 가 실행됐는지(비멱등 이중적재 방지) — 최소 1회.
        delete_calls = [
            a for a in session.executed
            if a and "DELETE FROM bim_quantities" in str(a[0])
        ]
        assert len(delete_calls) >= 1, "H1: 재삽입 전 기존행 DELETE 가 실행되지 않음"

    def test_upload_ifc_persists_idempotently_on_repeat_call(self):
        """H1 회귀 — 같은 프로젝트를 2회 업로드해도 add_all 누적 행 수가 배가되지 않는다.

        (실 DB 가 아니므로 DELETE 는 물리적으로 기존 행을 지우지 못하지만, 이 테스트는
        '헬퍼가 매 호출마다 DELETE 를 먼저 실행한다'는 계약을 검증한다 — 실 DB 환경에서
        이 DELETE 가 이전 호출의 add_all 산출 행을 지우므로 origin-cost 집계가 배가되지 않는다.)
        """
        session = _CapturingSession()
        client = _build_client(session)

        with patch(
            "app.services.cost.cost_tables_bootstrap._ensure_cost_tables",
            new=AsyncMock(return_value=None),
        ):
            resp1 = client.post(
                f"/api/v1/cost/{TEST_PROJECT_ID}/upload-ifc",
                json={"elements": IFC_ELEMENTS},
            )
            resp2 = client.post(
                f"/api/v1/cost/{TEST_PROJECT_ID}/upload-ifc",
                json={"elements": IFC_ELEMENTS},
            )

        assert resp1.status_code == 200 and resp2.status_code == 200
        # 매 호출마다 DELETE 가 선행됐다(2회 호출 → DELETE 최소 2회).
        delete_calls = [
            a for a in session.executed
            if a and "DELETE FROM bim_quantities" in str(a[0])
        ]
        assert len(delete_calls) >= 2

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

    def test_upload_ifc_denies_tenant_mismatch(self):
        """M1 — project_id 소유 tenant 와 요청자 tenant 가 다르면 403(IDOR 방지)."""

        class _MismatchRow:
            @staticmethod
            def first():
                # projects 테이블에 다른 tenant_id 소유로 존재한다고 가정.
                return ("11111111-1111-1111-1111-111111111111",)

        class _MismatchSession(_CapturingSession):
            async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003
                self.executed.append(args)
                return _MismatchRow()

        session = _MismatchSession()
        client = _build_client(session)

        resp = client.post(
            f"/api/v1/cost/{TEST_PROJECT_ID}/upload-ifc",
            json={"elements": IFC_ELEMENTS},
        )

        assert resp.status_code == 403
        assert session.added == []  # 거부 전 영속 시도 없음
