"""§4-E: /drawing/export-ifc — 설계 매스를 IFC4(.ifc) 파일로 내보낸다(BIM 저작도구용 export).

파라미터→IFC 생성(build_ifc_from_mass)을 다운로드 가능한 STEP(.ifc) 파일로 반환한다 —
설계 스튜디오의 param-based IFC export(`/drawing/export-dxf` 미러). LLM·DB 없이 무인증이라
bare-app TestClient로 직접 호출한다.

정직: 기하·구조는 결정론이나 IFC GlobalId·STEP 타임스탬프는 표준상 매 생성 고유 → bytes는
재현되지 않으므로 '동일 bytes' 단언은 하지 않는다(기하 헤더·엔티티 존재·층수 반영으로 검증).
"""

import pytest

# ifcopenshell 미설치 환경에서는 IFC 생성 자체가 불가 — 스킵(엔드포인트는 501 반환 설계).
pytest.importorskip("ifcopenshell", reason="ifcopenshell 미설치 — IFC export 테스트 스킵")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers.drawing import router as drawing_router

_app = FastAPI()
_app.include_router(drawing_router, prefix="/api/v1/drawing")
client = TestClient(_app)

_BASE = {
    "building_width_m": 24.0,
    "building_depth_m": 14.0,
    "num_floors": 5,
    "floor_height_m": 3.0,
    "project_name": "테스트동",
}


class TestExportIfc:

    def test_returns_ifc_file(self):
        r = client.post("/api/v1/drawing/export-ifc", json=_BASE)
        assert r.status_code == 200
        # STEP/IFC 헤더·스키마·핵심 엔티티 — 실제 IFC SPF인지 검증(가짜 아님)
        body = r.text
        assert "ISO-10303-21" in body
        assert "IFC4" in body
        assert "IFCPROJECT" in body.upper()
        assert "IFCBUILDINGSTOREY" in body.upper()

    def test_content_disposition_attachment_ifc(self):
        r = client.post("/api/v1/drawing/export-ifc", json=_BASE)
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and ".ifc" in cd
        ct = r.headers.get("content-type", "")
        assert "step" in ct or "ifc" in ct or "octet-stream" in ct

    def test_floor_count_reflected_in_ifc(self):
        """num_floors가 IFC 층(IfcBuildingStorey) 수에 반영(결정론·실 산출)."""
        r3 = client.post("/api/v1/drawing/export-ifc", json={**_BASE, "num_floors": 3})
        r7 = client.post("/api/v1/drawing/export-ifc", json={**_BASE, "num_floors": 7})
        n3 = r3.text.upper().count("IFCBUILDINGSTOREY")
        n7 = r7.text.upper().count("IFCBUILDINGSTOREY")
        assert n7 > n3

    def test_filename_rfc5987_preserves_unicode_safely(self):
        """파일명 — ASCII filename= 폴백(ascii·슬래시 없음) + RFC 5987 filename*로 한글 보존.

        HTTP 헤더는 latin-1만 허용 — 한글이 filename=에 새면 크래시. ASCII 폴백 + filename*=
        UTF-8''<percent-encoded>로 원본을 보존하고, 헤더는 latin-1 인코딩 가능해야 한다(주입 방지).
        """
        from urllib.parse import unquote
        r = client.post("/api/v1/drawing/export-ifc",
                        json={**_BASE, "project_name": "강남 A동/타워#1"})
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        # ASCII filename= 폴백: ascii·슬래시 없음·.ifc
        ascii_part = cd.split('filename="', 1)[1].split('"', 1)[0]
        assert ascii_part.isascii() and "/" not in ascii_part and ascii_part.endswith(".ifc")
        # RFC 5987 filename*로 원본(한글) 보존
        assert "filename*=UTF-8''" in cd
        assert "강남" in unquote(cd)
        # 헤더가 latin-1 인코딩 가능해야 함(비-ASCII 누수 시 raise)
        cd.encode("latin-1")

    def test_invalid_dims_rejected(self):
        """건물 폭/깊이 ≤ 0은 422(pydantic gt=0) — 가짜 IFC 생성 금지."""
        r = client.post("/api/v1/drawing/export-ifc", json={**_BASE, "building_width_m": 0})
        assert r.status_code == 422

    def test_missing_ifcopenshell_returns_501(self, monkeypatch):
        """ifcopenshell 미설치(생성 호출 ImportError) → 500이 아닌 501로 정직 표기(침묵 금지).

        importorskip가 파일을 스킵하면 501 분기가 영영 안 타므로, 생성 함수를 ImportError로
        monkeypatch해 의존성 누락 경로를 실제로 검증한다(정직 계약 회귀 가드).
        """
        from app.services.bim import ifc_generator_service

        def _no_dep(*a, **k):
            raise ImportError("No module named 'ifcopenshell'")

        monkeypatch.setattr(ifc_generator_service, "build_ifc_from_mass", _no_dep)
        r = client.post("/api/v1/drawing/export-ifc", json=_BASE)
        assert r.status_code == 501

    def test_core_positions_wiring(self):
        """옵셔널 실내요소(core_positions 등)가 mass dict로 전달돼 IFC에 반영(배선 가드)."""
        r = client.post("/api/v1/drawing/export-ifc", json={
            **_BASE, "num_floors": 3,
            "core_positions": [{"x": 6.0, "y": 4.0}], "core_size_m": 4.0,
            "corridor_width_m": 1.8, "windows_per_side": 2,
        })
        assert r.status_code == 200
        up = r.text.upper()
        assert "IFCBUILDINGSTOREY" in up  # 유효 IFC
        assert "IFCCOLUMN" in up or "IFCSTAIR" in up  # 코어 요소 압출됨
