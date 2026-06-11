"""WP-18 계약 테스트 — bim_quantities INSERT 배선 + origin-cost 엔드포인트.

검증 범위:
1) _parse_ifc — 기존 키 불변 + 신규 elements(요소 단위 물량) 반환.
2) analyze_ifc — 요소→공종코드 매핑→BimQuantity bulk INSERT(동일 세션), 0요소 하위호환.
3) GET /{pid}/bim-quantities/origin-cost — 단가 SSOT 결합 12단계 원가(정답값 고정),
   0건이면 status="no_bim_quantities" 정직 응답, 단가 미보유 공종 priced=false.

DB 비의존 — 경량 FastAPI + get_db override(가짜 세션) + 단가 fallback 고정.
정답값은 OriginCostCalculator(2026 법정요율) + UNIT_PRICES_2026 fallback 단가로 고정.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.cost import _BIM_WORKCODE_TO_PRICE_KEY, router
from app.services.cost.standard_quantity_estimator import UNIT_PRICES_2026
from apps.api.database.session import get_db

TEST_PROJECT_ID = str(uuid.uuid4())
TEST_TENANT_ID = uuid.uuid4()


# ── 단가 fallback 묶음(UnitPriceRepository.get_prices() 형식) — DB 비의존 고정 ──
def _fallback_prices() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, p in UNIT_PRICES_2026.items():
        out[key] = {
            "key": key, "spec": p["spec"], "unit": p["unit"],
            "mat_unit": float(p["mat_unit"]), "labor_unit": float(p["labor_unit"]),
            "exp_unit": float(p["exp_unit"]),
            "price_source": "fallback", "price_basis_year": 2026, "region": "경기도",
        }
    return out


# ── 가짜 비동기 세션 — execute().mappings().all() 만 흉내낸다 ──
class _FakeMappings:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _FakeSession:
    """bim_quantities 그룹조회 결과를 고정 반환하는 가짜 세션."""

    def __init__(self, grouped_rows: list[dict]):
        self._rows = grouped_rows

    async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeResult(self._rows)


def _make_client(grouped_rows: list[dict]) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield _FakeSession(grouped_rows)

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


# ═══════════════════════════════════════════════
# 1. _parse_ifc — elements 반환(기존 키 불변)
# ═══════════════════════════════════════════════


class TestParseIfcElements:
    def _build_service(self):
        from apps.api.services.bim_ifc_service import BIMIFCService

        svc = BIMIFCService.__new__(BIMIFCService)
        svc.db = AsyncMock()
        svc.settings = MagicMock()
        return svc

    def _mock_ifcopenshell(self, ifc_type: str, volume: float, area: float):
        mock_element = MagicMock()
        mock_element.is_a.return_value = ifc_type
        mock_element.GlobalId = "GID-1"
        mock_element.Name = "요소-1"

        q_vol = MagicMock()
        q_vol.is_a = lambda name: name == "IfcQuantityVolume"
        q_vol.VolumeValue = volume
        q_area = MagicMock()
        q_area.is_a = lambda name: name == "IfcQuantityArea"
        q_area.AreaValue = area

        prop_set = MagicMock()
        prop_set.is_a = lambda name: name == "IfcElementQuantity"
        prop_set.Quantities = [q_vol, q_area]

        defn = MagicMock()
        defn.is_a = lambda name: name == "IfcRelDefinesByProperties"
        defn.RelatingPropertyDefinition = prop_set
        mock_element.IsDefinedBy = [defn]

        mock_file = MagicMock()
        mock_file.schema = "IFC4"
        mock_file.by_type.return_value = [mock_element]

        mod = MagicMock()
        mod.open.return_value = mock_file
        return mod

    def test_keeps_existing_keys_and_adds_elements(self):
        svc = self._build_service()
        mod = self._mock_ifcopenshell("IfcWall", volume=10.0, area=25.0)
        with patch.dict("sys.modules", {"ifcopenshell": mod}):
            result = svc._parse_ifc("/tmp/test.ifc")
        # 기존 키 불변(하위호환).
        assert result["ifc_version"] == "IFC4"
        assert result["element_count"] == 1
        assert result["total_volume_m3"] == 10.0
        assert result["total_area_sqm"] == 25.0
        assert len(result["material_breakdown"]) == 1
        # 신규 elements 키.
        assert "elements" in result
        assert len(result["elements"]) == 1
        el = result["elements"][0]
        assert el["element_type"] == "IfcWall"
        assert el["global_id"] == "GID-1"
        assert el["quantity"] == 10.0       # 체적 우선
        assert el["unit"] == "m3"

    def test_quantity_falls_back_to_area_when_no_volume(self):
        svc = self._build_service()
        mod = self._mock_ifcopenshell("IfcWindow", volume=0.0, area=8.0)
        with patch.dict("sys.modules", {"ifcopenshell": mod}):
            result = svc._parse_ifc("/tmp/test.ifc")
        el = result["elements"][0]
        assert el["quantity"] == 8.0        # 체적 0 → 면적 사용(정직)
        assert el["unit"] == "m2"


# ═══════════════════════════════════════════════
# 2. analyze_ifc — bim_quantities bulk INSERT
# ═══════════════════════════════════════════════


def _mock_db_with_refresh():
    from datetime import datetime, timezone

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
    mock_db.commit = AsyncMock()

    async def _set_attrs(obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if not getattr(obj, "created_at", None):
            obj.created_at = datetime.now(tz=timezone.utc)

    mock_db.refresh = AsyncMock(side_effect=_set_attrs)
    return mock_db


class TestAnalyzeIfcInsert:
    @pytest.mark.asyncio
    async def test_inserts_bim_quantities_for_mapped_elements(self):
        from apps.api.database.models.v61_cost import BimQuantity
        from apps.api.services.bim_ifc_service import BIMIFCService

        db = _mock_db_with_refresh()
        svc = BIMIFCService(db=db)

        # IfcWall(4 work_code) + IfcWindow(3 work_code) = 7 BimQuantity 행.
        parse_result = {
            "ifc_version": "IFC4",
            "total_volume_m3": 55.0,
            "total_area_sqm": 0.0,
            "element_count": 2,
            "material_breakdown": [],
            "elements": [
                {"element_type": "IfcWall", "global_id": "w1", "name": "벽",
                 "quantity": 50.0, "unit": "m3", "floor_level": "1F"},
                {"element_type": "IfcWindow", "global_id": "win1", "name": "창",
                 "quantity": 5.0, "unit": "m2", "floor_level": ""},
            ],
        }
        with (
            patch.object(svc, "_download_ifc", new_callable=AsyncMock, return_value="/tmp/t.ifc"),
            patch.object(svc, "_parse_ifc", return_value=parse_result),
            patch("os.unlink"),
        ):
            await svc.analyze_ifc(
                project_id=uuid.uuid4(), tenant_id=TEST_TENANT_ID,
                file_url="minio://propai-bim/t.ifc",
            )

        # add_all 이 1회 호출되고 7 BimQuantity 행이 전달됐는지 검증.
        assert db.add_all.call_count == 1
        rows = db.add_all.call_args.args[0]
        assert len(rows) == 7
        assert all(isinstance(r, BimQuantity) for r in rows)
        wall_codes = sorted(r.work_code for r in rows if r.ifc_object_type == "IfcWall")
        assert wall_codes == ["A01", "A01-01", "A01-02", "A01-03"]
        # 물량·테넌트·추출방식 정합.
        wall_row = next(r for r in rows if r.ifc_object_type == "IfcWall")
        assert float(wall_row.quantity) == 50.0
        assert wall_row.tenant_id == TEST_TENANT_ID
        assert wall_row.extraction_method == "AI_AUTO"

    @pytest.mark.asyncio
    async def test_no_elements_skips_insert_backward_compat(self):
        """elements 키 없는 _parse_ifc(구버전/mock) 는 INSERT 스킵 — 하위호환."""
        from apps.api.services.bim_ifc_service import BIMIFCService

        db = _mock_db_with_refresh()
        svc = BIMIFCService(db=db)
        parse_result = {
            "ifc_version": "IFC4",
            "total_volume_m3": 100.0,
            "total_area_sqm": 500.0,
            "element_count": 20,
            "material_breakdown": [
                {"type": "IfcWall", "count": 10, "volume_m3": 60.0, "area_sqm": 300.0},
            ],
        }
        with (
            patch.object(svc, "_download_ifc", new_callable=AsyncMock, return_value="/tmp/t.ifc"),
            patch.object(svc, "_parse_ifc", return_value=parse_result),
            patch("os.unlink"),
        ):
            result = await svc.analyze_ifc(
                project_id=uuid.uuid4(), tenant_id=TEST_TENANT_ID,
                file_url="minio://propai-bim/t.ifc",
            )
        assert result.element_count == 20
        db.add_all.assert_not_called()


# ═══════════════════════════════════════════════
# 3. GET origin-cost 엔드포인트
# ═══════════════════════════════════════════════


class TestOriginCostEndpoint:
    def test_no_bim_quantities_honest_response(self):
        client = _make_client([])
        resp = client.get(f"/api/v1/cost/{TEST_PROJECT_ID}/bim-quantities/origin-cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_bim_quantities"
        assert data["items"] == []
        assert data["priced_item_count"] == 0

    def test_single_priced_line_locked_total(self):
        # A01-03(콘크리트) 단일 leaf, 합산물량 50 → 정답값 고정.
        grouped = [{"work_code": "A01-03", "unit": "m3", "quantity": 50.0, "line_count": 1}]
        client = _make_client(grouped)
        with patch(
            "app.services.cost.unit_price_repository.UnitPriceRepository.get_prices",
            new_callable=AsyncMock, return_value=_fallback_prices(),
        ):
            resp = client.get(f"/api/v1/cost/{TEST_PROJECT_ID}/bim-quantities/origin-cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["priced_item_count"] == 1
        assert data["unpriced_work_codes"] == []
        # 정답값 고정(OriginCostCalculator 12단계 + fallback 단가).
        assert data["cost"]["direct_cost"] == 6_600_000
        assert data["total_project_cost"] == 8_964_975
        assert data["cost"]["item_count"] == 1

    def test_multi_line_with_unpriced_code(self):
        # A01-03 concrete(50) + A01-02 rebar(2) priced, B01 배관 unpriced.
        grouped = [
            {"work_code": "A01-02", "unit": "ton", "quantity": 2.0, "line_count": 1},
            {"work_code": "A01-03", "unit": "m3", "quantity": 50.0, "line_count": 1},
            {"work_code": "B01", "unit": "m", "quantity": 30.0, "line_count": 1},
        ]
        client = _make_client(grouped)
        with patch(
            "app.services.cost.unit_price_repository.UnitPriceRepository.get_prices",
            new_callable=AsyncMock, return_value=_fallback_prices(),
        ):
            resp = client.get(f"/api/v1/cost/{TEST_PROJECT_ID}/bim-quantities/origin-cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["priced_item_count"] == 2
        # B01(배관) 은 단가 미보유 → unpriced + priced=false 정직 표기.
        assert "B01" in data["unpriced_work_codes"]
        b01 = next(it for it in data["items"] if it["work_code"] == "B01")
        assert b01["priced"] is False
        assert b01["amount"] == 0
        # 정답값 고정(concrete+rebar 2종).
        assert data["cost"]["direct_cost"] == 9_200_000
        assert data["total_project_cost"] == 12_410_023
        assert data["cost"]["item_count"] == 2

    def test_price_key_map_is_leaf_only(self):
        # 부모 집계코드(A01/A05) 는 단가매핑에서 제외(중복합산 방지) — 계약 고정.
        assert "A01" not in _BIM_WORKCODE_TO_PRICE_KEY
        assert "A05" not in _BIM_WORKCODE_TO_PRICE_KEY
        assert _BIM_WORKCODE_TO_PRICE_KEY["A01-03"] == "concrete"
        assert _BIM_WORKCODE_TO_PRICE_KEY["A01-02"] == "rebar"
