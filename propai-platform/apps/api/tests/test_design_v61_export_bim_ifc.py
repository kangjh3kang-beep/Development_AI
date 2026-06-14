"""SP0 E5: /design/{project_id}/bim/export-ifc(project-based) 하드닝 — 정직 응답 + 안전 헤더.

기존 export_bim_ifc(design_v61.py)는 try/except 없이 build_ifc_from_mass를 호출하고 원시
Content-Disposition(filename={project_id}.ifc)을 썼다. 의존성 누락 시 raw 500, 한글 이름 시
latin-1 크래시 위험. 본 작업은 param-based /drawing/export-ifc와 동일 견고성으로 맞춘다:
ifcopenshell 누락→501, 입력오류→400, 그 외→500(무누수), Content-Disposition→RFC 5987.

정직: IFC GlobalId·STEP 타임스탬프는 매 생성 고유 → bytes 재현 단언 안 함(엔티티 존재로 검증).
"""

import pytest

pytest.importorskip("ifcopenshell", reason="ifcopenshell 미설치 — IFC export 테스트 스킵")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.design_v61 import router as design_v61_router

_app = FastAPI()
_app.include_router(design_v61_router)  # 라우터가 prefix="/api/v1/design" 자체 보유
client = TestClient(_app)

_BASE = {
    "building_width_m": 24.0,
    "building_depth_m": 14.0,
    "floor_count": 5,
    "floor_height_m": 3.0,
    "project_name": "테스트동",
}
_URL = "/api/v1/design/proj-abc/bim/export-ifc"


class TestExportBimIfc:

    def test_returns_ifc_file(self):
        r = client.post(_URL, json=_BASE)
        assert r.status_code == 200
        body = r.text
        assert "ISO-10303-21" in body
        assert "IFC4" in body
        assert "IFCPROJECT" in body.upper()
        assert "IFCBUILDINGSTOREY" in body.upper()

    def test_content_disposition_rfc5987(self):
        """원시 헤더 → RFC 5987(ASCII 폴백 + filename*) — 한글 이름 latin-1 크래시 방지."""
        from urllib.parse import unquote
        r = client.post(_URL, json={**_BASE, "project_name": "강남 A동/타워#1"})
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        assert "attachment" in cd and ".ifc" in cd
        # ASCII filename= 폴백: ascii·슬래시 없음
        ascii_part = cd.split('filename="', 1)[1].split('"', 1)[0]
        assert ascii_part.isascii() and "/" not in ascii_part and ascii_part.endswith(".ifc")
        # RFC 5987 filename*로 원본(한글) 보존 + 헤더 latin-1 인코딩 가능(누수 시 raise)
        assert "filename*=UTF-8''" in cd
        assert "강남" in unquote(cd)
        cd.encode("latin-1")

    def test_missing_ifcopenshell_returns_501(self, monkeypatch):
        """ifcopenshell 미설치(생성 ImportError) → 500 아닌 501 정직 표기(무음/원시 트레이스 금지)."""
        from app.services.bim import ifc_generator_service

        def _no_dep(*a, **k):
            raise ImportError("No module named 'ifcopenshell'")

        monkeypatch.setattr(ifc_generator_service, "build_ifc_from_mass", _no_dep)
        r = client.post(_URL, json=_BASE)
        assert r.status_code == 501

    def test_value_error_returns_400(self, monkeypatch):
        """생성 입력 오류(ValueError) → 400(가짜 IFC·원시 500 금지)."""
        from app.services.bim import ifc_generator_service

        def _bad_input(*a, **k):
            raise ValueError("매스 치수 비정상")

        monkeypatch.setattr(ifc_generator_service, "build_ifc_from_mass", _bad_input)
        r = client.post(_URL, json=_BASE)
        assert r.status_code == 400

    def test_generic_error_returns_500_without_leak(self, monkeypatch):
        """예기치 못한 오류 → 500이되 원시 예외 메시지를 응답에 누수하지 않는다."""
        from app.services.bim import ifc_generator_service

        def _boom(*a, **k):
            raise RuntimeError("INTERNAL_SECRET_PATH /etc/x")

        monkeypatch.setattr(ifc_generator_service, "build_ifc_from_mass", _boom)
        r = client.post(_URL, json=_BASE)
        assert r.status_code == 500
        assert "INTERNAL_SECRET_PATH" not in r.text

    def test_invalid_dims_rejected_422(self):
        """건물 폭 ≤ 0은 422(pydantic gt=0) — 가짜 IFC 생성 금지."""
        r = client.post(_URL, json={**_BASE, "building_width_m": 0})
        assert r.status_code == 422
