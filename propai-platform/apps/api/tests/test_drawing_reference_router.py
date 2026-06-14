"""§4-B: /drawing/auto-design·/drawing/design-alternatives 참조설계 피드백 배선.

라우터가 옵셔널 use_references=True일 때만 유사사례 기하 힌트를 도출해 SiteInput에
주입하고, 응답에 reference 블록을 정직하게 가산하는지 검증한다. 미지정(기본 False)은
기존 동작 완전 불변(reference 키 없음·DB 미접근). 조회 실패/미일치는 used=False로
정직 표기하되 핵심 설계는 200을 유지(침묵 실패 금지).

DB 비접근 — use_references=False는 _reference_hint가 즉시 None을 반환해 세션을 열지
않는다. use_references=True 경로는 _reference_hint를 monkeypatch로 대체해 실DB 없이
라우터 계약만 검증한다(힌트 도출 로직 자체는 test_reference_feedback에서 검증).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import apps.api.routers.drawing as drawing
from apps.api.routers.drawing import router as drawing_router

_app = FastAPI()
_app.include_router(drawing_router, prefix="/api/v1/drawing")
client = TestClient(_app)

_BASE = {
    "site_area_sqm": 4000,
    "zone_code": "2R",
    "building_use": "공동주택",
    "target_unit_types": ["84A"],
    "floor_height_m": 3.0,
}

# monkeypatch가 반환할 가짜 힌트(전면 넓은 참조, 종횡비 2.5).
_FAKE_HINT_USED = {
    "used": True,
    "hint": {"aspect": 2.5, "ref_id": "ref-x", "title": "참조 판상", "similarity": 90.0,
             "source": "design_reference", "basis": "종횡비 2.5 주입"},
    "ref": {"id": "ref-x", "title": "참조 판상", "similarity_v2": 90.0,
            "area_sqm": 3900, "floors": 6, "building_width_m": 60.0, "building_depth_m": 24.0},
    "note": "기하 보유 후보 1개 중 최상위 적합 사례 적용",
    "candidates": 1,
}
_FAKE_HINT_NONE = {
    "used": False, "hint": None, "ref": None,
    "note": "유사 사례 라이브러리에 부합 사례 없음", "candidates": 0,
}
_FAKE_HINT_FAIL = {
    "used": False, "hint": None, "ref": None,
    "note": "참조 라이브러리 조회 실패: connection refused", "candidates": 0,
}


def _patch_hint(monkeypatch, result):
    async def _fake(use_references, **kw):  # noqa: ANN001
        return result if use_references else None
    monkeypatch.setattr(drawing, "_reference_hint", _fake)


class TestAutoDesignUseReferences:

    def test_omitted_use_references_has_no_reference_block(self):
        """use_references 미지정 → 응답·summary에 reference 키 없음(하위호환·DB 미접근)."""
        r = client.post("/api/v1/drawing/auto-design", json=_BASE)
        assert r.status_code == 200
        body = r.json()
        assert "reference" not in body
        assert "reference" not in body["summary"]

    def test_use_references_injects_aspect_and_reports(self, monkeypatch):
        """use_references=True + 적합 사례 → 종횡비 주입(폭>깊이) + 응답 reference 정직 표기."""
        _patch_hint(monkeypatch, _FAKE_HINT_USED)
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "use_references": True})
        assert r.status_code == 200
        body = r.json()
        assert body["reference"]["used"] is True
        assert body["reference"]["ref"]["title"] == "참조 판상"
        # 엔진 summary에도 적용 프로비넌스 반영, 매스가 폭>깊이로 편향.
        assert body["summary"]["reference"]["used"] is True
        assert body["summary"]["building_width_m"] > body["summary"]["building_depth_m"]

    def test_use_references_no_match_is_honest_200(self, monkeypatch):
        """적합 사례 없음 → used=False 정직 표기, 설계 자체는 정상 200(매스 auto)."""
        _patch_hint(monkeypatch, _FAKE_HINT_NONE)
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "use_references": True})
        assert r.status_code == 200
        body = r.json()
        assert body["reference"]["used"] is False
        assert body["reference"]["note"]
        # 참조 미적용 → 엔진 summary엔 reference 키 없음(auto 동작).
        assert "reference" not in body["summary"]
        assert body["summary"]["massing_kind"] == "auto"

    def test_lookup_failure_is_honest_not_500(self, monkeypatch):
        """조회 실패도 500이 아닌 used=False+사유로 정직 표기(침묵·중단 금지)."""
        _patch_hint(monkeypatch, _FAKE_HINT_FAIL)
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "use_references": True})
        assert r.status_code == 200
        assert r.json()["reference"]["used"] is False
        assert "조회 실패" in r.json()["reference"]["note"]


class TestAlternativesUseReferences:

    def test_omitted_no_reference_block(self):
        """use_references 미지정 → 응답에 reference 키 없음(하위호환)."""
        r = client.post("/api/v1/drawing/design-alternatives",
                        json={**_BASE, "count": 3})
        assert r.status_code == 200
        assert "reference" not in r.json()

    def test_use_references_applies_to_alternative_a_only(self, monkeypatch):
        """use_references=True → A는 참조 비례 적용, B(타워)는 명시 형상 우선(정직)."""
        _patch_hint(monkeypatch, _FAKE_HINT_USED)
        r = client.post("/api/v1/drawing/design-alternatives",
                        json={**_BASE, "count": 3, "use_references": True})
        assert r.status_code == 200
        body = r.json()
        assert body["reference"]["used"] is True
        # 생성 순서 A,B,C — A는 참조 적용, B는 tower 명시 우선(used=False).
        alts = body["alternatives"]
        a = next(x for x in alts if x["summary"].get("alternative_name", "").startswith("A"))
        b = next(x for x in alts if x["summary"].get("alternative_name", "").startswith("B"))
        c = next(x for x in alts if x["summary"].get("alternative_name", "").startswith("C"))
        assert a["summary"]["reference"]["used"] is True
        # B(tower)·C(lshape)는 참조 힌트를 받지 않고 명시 형상만 적용 — reference 키 없음(정직).
        assert "reference" not in b["summary"]
        assert b["summary"]["massing_kind"] == "tower"
        assert "reference" not in c["summary"]
        assert c["summary"]["massing_kind"] == "lshape"
