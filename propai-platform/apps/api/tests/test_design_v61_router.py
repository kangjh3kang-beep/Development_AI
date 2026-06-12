"""v61 설계도면 라우터 테스트 — 경량 TestClient (전체 앱 비의존).

WP-16 계약:
- save/load 인증(무인증 401) + tenant 소유권(타 tenant 403)
- CADSaveRequest 매스치수 3필드 echo·영속 페이로드 반영
- export-dxf drawing_type 5종 분기(평면/상세/단면/입면/배치) DXF 200
- export-edited-dxf: 저장본 있으면 DXF 200, 없으면 404(가짜 금지) + 인증·소유권
- select-alternative mc_results dict 계약
- unit-mix/simulate footprint_sqm 반영(연면적·전용면적)

DB 비의존 — get_db override(SQL 텍스트로 분기하는 가짜 세션) + get_current_user override(가짜 user).
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.design_v61 import router
from app.services.auth.auth_service import get_current_user
from apps.api.database.session import get_db

PROJECT_ID = "test-project-001"            # 비UUID(데모) — 소유권 검사 생략 경로
UUID_PROJECT_ID = str(uuid.uuid4())        # 영속/소유권 경로
TENANT_A = str(uuid.uuid4())               # 인증 사용자 tenant
TENANT_B = str(uuid.uuid4())               # 타 tenant(소유주)


class _FakeUser:
    def __init__(self, tenant_id: str):
        self.id = str(uuid.uuid4())
        self.tenant_id = tenant_id


class _Row(tuple):
    """db.execute(...).first() 가 반환하는 Row 흉내(인덱스 접근)."""


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    """SQL 텍스트로 분기해 고정 행을 반환하는 가짜 비동기 세션.

    project_tenant: projects.tenant_id 조회 결과(None이면 프로젝트 없음).
    saved_json: design_versions 최신 design_data_json(None이면 저장본 없음).
    """

    def __init__(self, project_tenant=None, saved_json=None):
        self.project_tenant = project_tenant
        self.saved_json = saved_json
        self.inserted = None

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement).lower()
        if "from projects" in sql:
            row = _Row((self.project_tenant,)) if self.project_tenant is not None else None
            return _FakeResult(row)
        if "max(version_number)" in sql:
            return _FakeResult(_Row((0,)))
        if "insert into design_versions" in sql:
            self.inserted = params
            return _FakeResult(None)
        if "from design_versions" in sql:
            row = _Row((self.saved_json,)) if self.saved_json is not None else None
            # load_drawing 은 (version, json, updated_at) 3-튜플을 기대
            if "version_number, design_data_json" in sql:
                row = _Row((1, self.saved_json, None)) if self.saved_json is not None else None
            return _FakeResult(row)
        return _FakeResult(None)

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _make_client(*, user_tenant=TENANT_A, authed=True,
                 project_tenant=None, saved_json=None):
    """라우터 단독 앱 + 의존성 override 클라이언트.

    authed=False → get_current_user 미override(실 게이트, 무인증 401 검증용).
    """
    app = FastAPI()
    app.include_router(router)

    session = _FakeSession(project_tenant=project_tenant, saved_json=saved_json)

    async def _override_db():
        yield session

    app.dependency_overrides[get_db] = _override_db
    if authed:
        app.dependency_overrides[get_current_user] = lambda: _FakeUser(user_tenant)
    client = TestClient(app)
    client._session = session  # 검증용 핸들
    return client


# ════════════════════════════════════════════════════════
# 기존 계약(회귀) — 도면세트·SVG·인허가
# ════════════════════════════════════════════════════════


class TestGenerateFullSet:

    def test_generate_full_set(self):
        client = _make_client()
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/generate-full-set", json={
            "site_width_m": 60, "site_depth_m": 40,
            "building_width_m": 40, "building_depth_m": 20,
            "floor_count": 5, "floor_height_m": 3.0,
            "basement_floors": 1, "unit_width_m": 8.0,
            "setback_m": 3.0, "parking_count": 50,
            "project_name": "테스트빌딩",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == PROJECT_ID
        assert data["drawing_count"] >= 7

    def test_generate_full_set_defaults(self):
        client = _make_client()
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/generate-full-set", json={})
        assert resp.status_code == 200


class TestGetDrawingSVG:

    def test_get_existing_drawing(self):
        client = _make_client()
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/B-01/svg")
        assert resp.status_code == 200
        assert "svg" in resp.headers.get("content-type", "")

    def test_get_nonexistent_drawing(self):
        client = _make_client()
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/Z-99/svg")
        assert resp.status_code == 404


class TestPermitDocs:

    def test_get_permit_docs(self):
        client = _make_client()
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/permit-docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 37


# ════════════════════════════════════════════════════════
# ① 인증 + 소유권(save/load)
# ════════════════════════════════════════════════════════


class TestSaveLoadAuth:

    def test_save_requires_auth_401(self):
        """무인증 save → 401."""
        client = _make_client(authed=False)
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/drawings/save", json={
            "drawing_code": "B-01", "svg_content": "<svg></svg>",
        })
        assert resp.status_code == 401

    def test_load_requires_auth_401(self):
        """무인증 load → 401."""
        client = _make_client(authed=False)
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/load")
        assert resp.status_code == 401

    def test_save_other_tenant_forbidden_403(self):
        """UUID 프로젝트가 타 tenant 소유 → 403."""
        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_B)
        resp = client.post(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/save", json={
            "drawing_code": "B-01", "svg_content": "<svg></svg>",
        })
        assert resp.status_code == 403

    def test_load_other_tenant_forbidden_403(self):
        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_B)
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/load")
        assert resp.status_code == 403

    def test_save_owner_persists(self):
        """소유 tenant 일치 → 영속(saved) + 매스치수 페이로드 반영."""
        import json as _json

        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_A)
        resp = client.post(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/save", json={
            "drawing_code": "CAD-EDIT", "drawing_type": "평면도",
            "svg_content": "<svg></svg>",
            "layers": [{"name": "A-WALL", "visible": True}],
            "points": [{"id": "a", "x": 0, "y": 0}],
            "surfaces": [{"point_ids": ["a"]}],
            "building_width_m": 30.0, "building_depth_m": 15.0, "floor_height_m": 3.2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"].startswith("saved")
        assert data["layer_count"] == 1
        # ② 매스치수 3필드가 design_data_json 페이로드에 기록됐는지 검증.
        inserted = client._session.inserted
        assert inserted is not None
        dj = _json.loads(inserted["dj"])
        assert dj["building_width_m"] == 30.0
        assert dj["building_depth_m"] == 15.0
        assert dj["floor_height_m"] == 3.2


class TestSaveDrawing:

    def test_save_drawing_demo_echo(self):
        """비UUID(데모) project_id → echo 계약(비영속). 인증은 필수."""
        client = _make_client()
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/drawings/save", json={
            "drawing_code": "B-01",
            "drawing_type": "배치도",
            "svg_content": "<svg></svg>",
            "layers": [{"name": "A-WALL", "visible": True}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"].startswith("echo")
        assert data["layer_count"] == 1
        assert data["drawing_code"] == "B-01"


class TestLoadDrawing:

    def test_load_demo_not_saved(self):
        client = _make_client()
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/load")
        assert resp.status_code == 200
        assert resp.json()["saved"] is False

    def test_load_owner_echo_contract(self):
        """저장본(JSON)이 있으면 saved=true + data echo."""
        import json as _json

        saved = _json.dumps({
            "drawing_code": "CAD-EDIT",
            "points": [{"id": "a", "x": 0, "y": 0}],
            "surfaces": [{"point_ids": ["a"]}],
            "building_width_m": 30.0,
        }, ensure_ascii=False)
        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_A, saved_json=saved)
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/load")
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["data"]["building_width_m"] == 30.0
        assert data["data"]["points"][0]["id"] == "a"


# ════════════════════════════════════════════════════════
# ④ select-alternative — mc_results dict 계약
# ════════════════════════════════════════════════════════


class TestSelectAlternative:

    def test_select_alternative(self):
        client = _make_client()
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/select-alternative", json={
            "alternatives": [
                {"name": "A", "profit_score": 80, "legal_score": 90,
                 "design_score": 70, "esg_score": 60},
                {"name": "B", "profit_score": 70, "legal_score": 85,
                 "design_score": 80, "esg_score": 75},
            ],
            "iterations": 1000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ranked"]) == 2
        assert data["winner"] is not None
        # mc_results 는 list 가 아닌 dict(iterations/noise_pct/win_rates).
        assert isinstance(data["mc_results"], dict)
        assert data["mc_results"]["iterations"] == 1000
        assert "win_rates" in data["mc_results"]


# ════════════════════════════════════════════════════════
# ⑤ export-dxf — drawing_type 5종 분기
# ════════════════════════════════════════════════════════


class TestExportDxfByType:

    _BODY = {
        "site_width_m": 60, "site_depth_m": 40,
        "building_width_m": 40, "building_depth_m": 20,
        "floor_count": 5, "floor_height_m": 3.0,
        "basement_floors": 1, "unit_width_m": 8.0, "parking_count": 30,
    }

    def _post(self, client, drawing_type=None):
        body = dict(self._BODY)
        if drawing_type is not None:
            body["drawing_type"] = drawing_type
        return client.post(f"/api/v1/design/{PROJECT_ID}/drawings/export-dxf", json=body)

    def test_default_floor_plan_backward_compat(self):
        """drawing_type 미전달 → floor_plan(하위호환) 200 + DXF 본문."""
        client = _make_client()
        resp = self._post(client)
        assert resp.status_code == 200
        assert "dxf" in resp.headers.get("content-type", "")
        assert resp.content and resp.content != b"DXF_PLACEHOLDER"

    def test_each_drawing_type_200(self):
        """평면/상세/단면/입면/배치 5종 모두 DXF 200."""
        client = _make_client()
        for dtype in ("floor_plan", "detail", "section", "elevation", "site"):
            resp = self._post(client, dtype)
            assert resp.status_code == 200, dtype
            assert "dxf" in resp.headers.get("content-type", ""), dtype
            assert dtype in resp.headers.get("content-disposition", ""), dtype
            # ezdxf 설치 환경 → 실제 DXF 바이트(플레이스홀더 아님).
            assert resp.content and resp.content != b"DXF_PLACEHOLDER", dtype


# ════════════════════════════════════════════════════════
# ③ export-edited-dxf — 저장본 직변환 + 404 정직 + 인증·소유권
# ════════════════════════════════════════════════════════


def _edited_saved_json():
    import json as _json

    return _json.dumps({
        "points": [
            {"id": "a", "x": 0, "y": 0},
            {"id": "b", "x": 100, "y": 0},
            {"id": "c", "x": 100, "y": 80},
            {"id": "d", "x": 0, "y": 80},
        ],
        "surfaces": [{"point_ids": ["a", "b", "c", "d", "a"]}],
        "vector_data": {"scale": 10.0},
    }, ensure_ascii=False)


class TestExportEditedDxf:

    def test_requires_auth_401(self):
        client = _make_client(authed=False)
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 401

    def test_other_tenant_forbidden_403(self):
        client = _make_client(
            user_tenant=TENANT_A, project_tenant=TENANT_B, saved_json=_edited_saved_json(),
        )
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 403

    def test_no_saved_returns_404(self):
        """저장본 없음 → 404(가짜 도면 생성 금지)."""
        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_A, saved_json=None)
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 404

    def test_demo_project_id_404(self):
        """비UUID project_id → 404(저장 영속 불가)."""
        client = _make_client()
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 404

    def test_saved_returns_dxf_200(self):
        """저장본(points/surfaces/scale) → 편집본 DXF 200."""
        client = _make_client(
            user_tenant=TENANT_A, project_tenant=TENANT_A, saved_json=_edited_saved_json(),
        )
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 200
        assert "dxf" in resp.headers.get("content-type", "")
        assert resp.content and resp.content != b"DXF_PLACEHOLDER"


# ════════════════════════════════════════════════════════
# ⑥ unit-mix/simulate — footprint_sqm 반영
# ════════════════════════════════════════════════════════


class TestUnitMixFootprint:

    def _body(self, **extra):
        body = {
            "building_width_m": 40, "building_depth_m": 20,
            "floor_count": 5, "efficiency_pct": 75,
            "mix": [{"type": "84A", "area_sqm": 84.0, "ratio_pct": 100.0}],
        }
        body.update(extra)
        return body

    def test_footprint_default_from_dims(self):
        """footprint_sqm 미전달 → 폭×깊이(=800) × 층수 연면적."""
        client = _make_client()
        resp = client.post(
            f"/api/v1/design/{PROJECT_ID}/unit-mix/simulate", json=self._body(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["gfa_sqm"] == round(40 * 20 * 5, 1)  # 4000.0

    def test_footprint_override_reflected(self):
        """footprint_sqm 전달 → 폭×깊이 대신 그 값으로 연면적 산정."""
        client = _make_client()
        resp = client.post(
            f"/api/v1/design/{PROJECT_ID}/unit-mix/simulate",
            json=self._body(footprint_sqm=500.0),
        )
        assert resp.status_code == 200
        data = resp.json()
        # 500 × 5층 = 2500(폭×깊이 800×5=4000 과 다름 → footprint 반영 확인).
        assert data["gfa_sqm"] == 2500.0
        assert data["sellable_area_sqm"] == round(2500.0 * 0.75, 1)

    def test_footprint_must_be_positive(self):
        """footprint_sqm <= 0 → 422(검증)."""
        client = _make_client()
        resp = client.post(
            f"/api/v1/design/{PROJECT_ID}/unit-mix/simulate",
            json=self._body(footprint_sqm=0),
        )
        assert resp.status_code == 422


# ════════════════════════════════════════════════════════
# ⑦ CAD2.0 (U1) — shapes 영속(save) + DXF 가져오기(import-dxf) + shapes 내보내기
# ════════════════════════════════════════════════════════


def _import_dxf_bytes():
    """업로드 테스트용 소형 DXF(WALL 닫힌 사각형 1개, $INSUNITS=6) 바이트."""
    import io as _io

    ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.modelspace().add_lwpolyline(
        [(0, 0), (12, 0), (12, 8), (0, 8)], close=True,
        dxfattribs={"layer": "WALL"},
    )
    buf = _io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


class TestSaveShapes:
    """CADSaveRequest.shapes 가산 필드 — 전달 시에만 design_data_json에 기록."""

    def _save_body(self, **extra):
        body = {"drawing_code": "CAD-EDIT", "svg_content": "<svg></svg>"}
        body.update(extra)
        return body

    def test_save_with_shapes_persists_payload(self):
        import json as _json

        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_A)
        shapes = [{"kind": "rect", "layer": "wall", "x": 0, "y": 0, "w": 50, "h": 30}]
        resp = client.post(
            f"/api/v1/design/{UUID_PROJECT_ID}/drawings/save",
            json=self._save_body(shapes=shapes),
        )
        assert resp.status_code == 200
        assert resp.json()["status"].startswith("saved")
        dj = _json.loads(client._session.inserted["dj"])
        assert dj["shapes"] == shapes

    def test_save_without_shapes_omits_key(self):
        """shapes 미전달 → 저장 JSON에 키 미기록(기존 저장본과 동일, 하위호환)."""
        import json as _json

        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_A)
        resp = client.post(
            f"/api/v1/design/{UUID_PROJECT_ID}/drawings/save", json=self._save_body(),
        )
        assert resp.status_code == 200
        dj = _json.loads(client._session.inserted["dj"])
        assert "shapes" not in dj

    def test_save_empty_shapes_omits_key(self):
        """shapes=[](빈 배열) → 미기록(빈 배열 미기록 계약)."""
        import json as _json

        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_A)
        resp = client.post(
            f"/api/v1/design/{UUID_PROJECT_ID}/drawings/save",
            json=self._save_body(shapes=[]),
        )
        assert resp.status_code == 200
        dj = _json.loads(client._session.inserted["dj"])
        assert "shapes" not in dj


class TestImportDxf:
    """import-dxf — 인증·소유권 + 확장자 415 + 20MB 413 + 파싱 422 + 성공 계약."""

    def _post(self, client, content=b"x", name="plan.dxf", project_id=PROJECT_ID):
        return client.post(
            f"/api/v1/design/{project_id}/drawings/import-dxf",
            files={"file": (name, content, "application/dxf")},
        )

    def test_requires_auth_401(self):
        client = _make_client(authed=False)
        assert self._post(client).status_code == 401

    def test_other_tenant_forbidden_403(self):
        client = _make_client(user_tenant=TENANT_A, project_tenant=TENANT_B)
        assert self._post(client, project_id=UUID_PROJECT_ID).status_code == 403

    def test_non_dxf_extension_415_with_dwg_guidance(self):
        client = _make_client()
        resp = self._post(client, name="plan.dwg")
        assert resp.status_code == 415
        assert "DXF로 저장" in resp.json()["detail"]

    def test_empty_file_400(self):
        client = _make_client()
        assert self._post(client, content=b"").status_code == 400

    def test_oversize_413(self, monkeypatch):
        from app.routers import design_v61 as mod

        monkeypatch.setattr(mod, "_MAX_DXF_UPLOAD_BYTES", 10)
        client = _make_client()
        resp = self._post(client, content=b"0123456789ABCDEF")
        assert resp.status_code == 413

    def test_invalid_dxf_422(self):
        """비DXF 바이트 → 422(정직 — 가짜 셰이프 생성 금지)."""
        client = _make_client()
        resp = self._post(client, content=b"NOT A DXF FILE AT ALL")
        assert resp.status_code == 422

    def test_import_success_returns_shapes_and_unit(self):
        client = _make_client()
        resp = self._post(client, content=_import_dxf_bytes())
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == PROJECT_ID
        assert data["unit"] == {"detected": "m", "source": "insunits"}
        assert data["truncated"] is False
        shapes = data["shapes"]
        assert len(shapes) == 1
        assert shapes[0]["kind"] == "polyline"
        assert shapes[0]["closed"] is True
        assert shapes[0]["layer"] == "outline"  # WALL 역매핑
        assert data["main_outline_index"] == 0


class TestExportEditedDxfShapesMode:
    """export-edited-dxf — 저장본에 CAD2.0 shapes가 있으면 shapes 모드로 내보내기."""

    def _shapes_saved_json(self):
        import json as _json

        return _json.dumps({
            "shapes": [
                {"kind": "polygon", "layer": "outline",
                 "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0},
                            {"x": 100, "y": 80}, {"x": 0, "y": 80}]},
                {"kind": "circle", "layer": "wall", "cx": 50, "cy": 40, "r": 10},
            ],
            "vector_data": {"scale": 10.0},
        }, ensure_ascii=False)

    def test_saved_shapes_without_points_export_200(self):
        """points 없이 shapes만 저장돼 있어도 DXF 200(기존엔 404였던 케이스 확장)."""
        client = _make_client(
            user_tenant=TENANT_A, project_tenant=TENANT_A,
            saved_json=self._shapes_saved_json(),
        )
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 200
        assert "dxf" in resp.headers.get("content-type", "")
        assert resp.content and resp.content != b"DXF_PLACEHOLDER"

    def test_saved_shapes_dxf_contains_circle_and_wall(self):
        """shapes 모드 산출 DXF 재파싱 — CIRCLE + WALL 닫힌 LWPOLYLINE 포함."""
        import io as _io

        ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")
        client = _make_client(
            user_tenant=TENANT_A, project_tenant=TENANT_A,
            saved_json=self._shapes_saved_json(),
        )
        resp = client.get(f"/api/v1/design/{UUID_PROJECT_ID}/drawings/export-edited-dxf")
        assert resp.status_code == 200
        doc = ezdxf.read(_io.StringIO(resp.content.decode("utf-8")))
        msp = doc.modelspace()
        assert len(msp.query("CIRCLE")) == 1
        walls = msp.query('LWPOLYLINE[layer=="WALL"]')
        assert len(walls) == 1
        assert walls[0].closed
