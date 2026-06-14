"""§4-A①: /drawing/auto-design·/drawing/design-alternatives 매스 형상(massing_kind) 수용.

정본 도면 라우터(apps/api/routers/drawing.py)가 요청의 옵셔널 massing_kind를
SiteInput에 전달해 결정론 매스 변형을 구동하는지 검증한다. 미지정·미정의 값은
'auto'로 폴백(가짜값·예외 없음 — 정직). auto-design·design-alternatives 모두
무인증 허용(순수 결정론 산출)이라 의존성 override 없이 TestClient로 직접 호출한다.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers.drawing import router as drawing_router

_app = FastAPI()
_app.include_router(drawing_router, prefix="/api/v1/drawing")
client = TestClient(_app)

# 형상이 시각 클램프에 걸리지 않고 실제로 매스를 구동하도록 충분히 큰 대지.
_BASE = {
    "site_area_sqm": 4000,
    "zone_code": "2R",
    "building_use": "공동주택",
    "target_unit_types": ["84A"],
    "floor_height_m": 3.0,
}


class TestAutoDesignMassingKind:
    """단일 자동설계(/auto-design)가 massing_kind를 수용·전파한다."""

    def test_explicit_kind_propagates_to_summary(self):
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "massing_kind": "tower"})
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert summary["massing_kind"] == "tower"
        assert summary["massing_label"] == "타워형"

    def test_omitted_kind_defaults_to_auto(self):
        """massing_kind 미전달 → 'auto'(대지 종횡비 기반) — 하위호환."""
        r = client.post("/api/v1/drawing/auto-design", json=_BASE)
        assert r.status_code == 200
        assert r.json()["summary"]["massing_kind"] == "auto"

    def test_unknown_kind_falls_back_to_auto(self):
        """미정의 형상 문자열 → 'auto' 폴백(예외·가짜값 없음, 정직)."""
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "massing_kind": "nonsense"})
        assert r.status_code == 200
        assert r.json()["summary"]["massing_kind"] == "auto"

    def test_tower_smaller_footprint_than_slab(self):
        """타워형은 작은 플로어플레이트 → 건축면적 < 판상형(결정론, 엔드투엔드)."""
        slab = client.post(
            "/api/v1/drawing/auto-design", json={**_BASE, "massing_kind": "slab"},
        ).json()["summary"]
        tower = client.post(
            "/api/v1/drawing/auto-design", json={**_BASE, "massing_kind": "tower"},
        ).json()["summary"]
        assert tower["building_area_sqm"] < slab["building_area_sqm"]


class TestDesignAlternativesMassingKind:
    """Top3(/design-alternatives): A=auto(입력 honors)·B=tower·C=lshape 형상 다양화."""

    def test_alternatives_have_distinct_forms(self):
        r = client.post("/api/v1/drawing/design-alternatives", json={**_BASE, "count": 3})
        assert r.status_code == 200
        alts = r.json()["alternatives"]
        assert len(alts) == 3
        # 정렬 후라 순서가 점수 기준 — 형상 집합으로 다양화 확인.
        kinds = {a["summary"]["massing_kind"] for a in alts}
        assert {"tower", "lshape"}.issubset(kinds)

    def test_alternative_a_honors_request_massing_kind(self):
        """요청 massing_kind=court → A 대안(밸런스)이 court를 따른다."""
        r = client.post(
            "/api/v1/drawing/design-alternatives",
            json={**_BASE, "count": 3, "massing_kind": "court"},
        )
        assert r.status_code == 200
        alts = r.json()["alternatives"]
        balanced = next(a for a in alts if a["priority"] == "balanced")
        assert balanced["summary"]["massing_kind"] == "court"

    def test_all_alternatives_compliant(self):
        """형상 배정 후에도 3개 대안 모두 법규 준수(회귀 보호)."""
        r = client.post("/api/v1/drawing/design-alternatives", json={**_BASE, "count": 3})
        assert r.status_code == 200
        for a in r.json()["alternatives"]:
            assert a["compliance"]["bcr_ok"] is True
            assert a["compliance"]["far_ok"] is True
