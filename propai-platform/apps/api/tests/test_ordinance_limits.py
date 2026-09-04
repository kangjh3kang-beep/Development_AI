"""§4-B 조례 한도 — auto_design 엔진이 지자체 조례 실효 한도를 반영(min(법정,조례,목표)).

조례 데이터 소스(OrdinanceService — 법제처 API→캐시→법정상한)는 기존 존재하나, 설계 엔진은
하드코딩 ZONE_LIMITS(법정상한)만 썼다. 본 작업은 엔진이 옵셔널 ordinance_bcr/far_pct를 받아
min(법정, 조례, 목표)으로 적용하고(가짜 상향 금지), summary.basis에 조례 출처·값을 정직 표기한다.
None=기존 동작 완전 불변(하위호환).
"""

import pytest

from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput


@pytest.fixture()
def engine():
    return AutoDesignEngineService()


def _inp(**kw) -> SiteInput:
    base = dict(site_area_sqm=4000, zone_code="2R", building_use="공동주택", floor_height_m=3.0)
    base.update(kw)
    return SiteInput(**base)


# 2R 법정: 건폐율 60% · 용적률 200%.
class TestEngineOrdinanceLimits:

    def test_ordinance_far_below_statutory_is_applied(self, engine):
        """조례 용적률 180%(<법정 200%) → 적용 한도 180% · 달성 far ≤ 180%."""
        s = engine.generate(_inp(ordinance_far_percent=180)).summary
        assert s["basis"]["applied_limits"]["max_far_percent"] == 180
        assert s["far_percent"] <= 180 + 0.5

    def test_ordinance_above_statutory_is_clamped(self, engine):
        """조례 용적률 300%(>법정 200%) → 법정 200%로 클램프(가짜 한도 상향 금지)."""
        s = engine.generate(_inp(ordinance_far_percent=300)).summary
        assert s["basis"]["applied_limits"]["max_far_percent"] == 200

    def test_min_of_statutory_ordinance_target(self, engine):
        """법정 200 · 조례 190 · 목표 170 → min = 170 적용."""
        s = engine.generate(_inp(ordinance_far_percent=190, target_far_percent=170)).summary
        assert s["basis"]["applied_limits"]["max_far_percent"] == 170

    def test_ordinance_bcr_applied(self, engine):
        """조례 건폐율 50%(<법정 60%) → 적용 건폐율 한도 50% · 달성 bcr ≤ 50%."""
        s = engine.generate(_inp(ordinance_bcr_percent=50)).summary
        assert s["basis"]["applied_limits"]["max_bcr_percent"] == 50
        assert s["bcr_percent"] <= 50 + 0.5

    def test_ordinance_recorded_in_basis_honestly(self, engine):
        """summary.basis.applied_limits에 조례 값이 정직 기록(법정·목표와 구분)."""
        s = engine.generate(_inp(ordinance_bcr_percent=50, ordinance_far_percent=180)).summary
        lim = s["basis"]["applied_limits"]
        assert lim["ordinance_bcr_percent"] == 50
        assert lim["ordinance_far_percent"] == 180
        assert lim["statutory_max_far_percent"] == 200  # 법정은 그대로 보존

    def test_no_ordinance_backward_compatible(self, engine):
        """조례 미지정 → 적용=법정, ordinance 값은 None(기존 동작 불변)."""
        s = engine.generate(_inp()).summary
        lim = s["basis"]["applied_limits"]
        assert lim.get("ordinance_far_percent") is None
        assert lim.get("ordinance_bcr_percent") is None
        assert lim["max_far_percent"] == lim["statutory_max_far_percent"]

    def test_generate_alternatives_propagates_ordinance(self, engine):
        """조례 한도는 법적 한도 — A/B/C 전 대안에 전파·적용(B/C 수기 복사 회귀 가드)."""
        results = engine.generate_alternatives(_inp(ordinance_far_percent=150), count=3)
        assert len(results) == 3
        for r in results:
            assert r.summary["basis"]["applied_limits"]["max_far_percent"] == 150
            assert r.summary["far_percent"] <= 150 + 0.5


class TestOrdinanceLimitsAdapter:
    """drawing._ordinance_limits 본체 — monkeypatch로 우회하지 않고 6분기 직접 검증.

    (라우터 통합 테스트가 _ordinance_limits를 통째 교체해 정직-민감 분기가 미실행되던 갭 보강.
    OrdinanceService.get_ordinance_limits만 대체하고 본체는 실행한다.)
    """

    async def test_opt_out_returns_none(self):
        from apps.api.routers import drawing
        assert await drawing._ordinance_limits(False, address="서울 강남구", zone_code="2R") is None

    async def test_no_address_used_false(self):
        from apps.api.routers import drawing
        out = await drawing._ordinance_limits(True, address=None, zone_code="2R")
        assert out["used"] is False and "주소" in out["note"]

    async def test_unmapped_zone_used_false(self):
        from apps.api.routers import drawing
        out = await drawing._ordinance_limits(True, address="서울 강남구", zone_code="ZZZ")
        assert out["used"] is False and "매핑" in out["note"]

    async def test_ordinance_below_statutory_applied(self, monkeypatch):
        """조례 실효값이 엔진 법정 미만 → used=True·정규화 주입."""
        from app.services.land_intelligence import ordinance_service
        from apps.api.routers import drawing

        async def _fake(self, address, zone_type, **_kwargs):  # noqa: ANN001 — additive 파라미터 수용
            return {"effective_bcr": 50.0, "effective_far": 170.0, "source": "지자체 조례",
                    "sigungu": "강남구", "legal_basis": "서울특별시 도시계획 조례"}

        monkeypatch.setattr(ordinance_service.OrdinanceService, "get_ordinance_limits", _fake)
        out = await drawing._ordinance_limits(True, address="서울 강남구", zone_code="2R")
        assert out["used"] is True
        assert out["ordinance_far_percent"] == 170.0  # 법정 200 미만 → 적용
        assert out["ordinance_bcr_percent"] == 50.0    # 법정 60 미만 → 적용
        assert out["sigungu"] == "강남구"

    async def test_ordinance_not_constraining_used_false(self, monkeypatch):
        """조례 실효값이 엔진 법정 이상(NATIONAL 250 ≥ 엔진 200) → 미적용(정직 — 호도 방지)."""
        from app.services.land_intelligence import ordinance_service
        from apps.api.routers import drawing

        async def _fake(self, address, zone_type, **_kwargs):  # noqa: ANN001 — additive 파라미터 수용
            return {"effective_bcr": 60.0, "effective_far": 250.0, "source": "지자체 조례",
                    "sigungu": "강남구"}

        monkeypatch.setattr(ordinance_service.OrdinanceService, "get_ordinance_limits", _fake)
        out = await drawing._ordinance_limits(True, address="서울 강남구", zone_code="2R")
        assert out["used"] is False
        assert out["ordinance_far_percent"] is None  # 법정 이상이라 미주입

    async def test_lookup_exception_honest_no_secret_leak(self, monkeypatch):
        """조회 예외 → 500 아닌 used=False + 일반화 사유(원시 예외·DSN 미노출, 로그에만)."""
        from app.services.land_intelligence import ordinance_service
        from apps.api.routers import drawing

        async def _boom(self, address, zone_type, **_kwargs):  # noqa: ANN001
            raise RuntimeError("postgres://secret@host/db connection refused")

        monkeypatch.setattr(ordinance_service.OrdinanceService, "get_ordinance_limits", _boom)
        out = await drawing._ordinance_limits(True, address="서울 강남구", zone_code="2R")
        assert out["used"] is False
        assert "법정상한" in out["note"]
        assert "secret" not in out["note"] and "postgres" not in out["note"]


# ── 라우터: /drawing/auto-design use_ordinance (DB/네트워크 없이 monkeypatch) ──

from fastapi import FastAPI
from fastapi.testclient import TestClient

import apps.api.routers.drawing as drawing
from apps.api.routers.drawing import router as drawing_router

_app = FastAPI()
_app.include_router(drawing_router, prefix="/api/v1/drawing")
client = TestClient(_app)

_BASE = {"site_area_sqm": 4000, "zone_code": "2R", "building_use": "공동주택",
         "target_unit_types": ["84A"], "floor_height_m": 3.0}

_FAKE_ORD = {
    "used": True, "ordinance_bcr_percent": 50.0, "ordinance_far_percent": 180.0,
    "source": "지자체 조례", "legal_basis": "서울특별시 도시계획 조례",
    "sigungu": "강남구", "note": "조례 실효 한도 적용",
}
_FAKE_ORD_FAIL = {
    "used": False, "ordinance_bcr_percent": None, "ordinance_far_percent": None,
    "source": "법정상한", "note": "조례 조회 실패 — 법정상한 적용",
}


def _patch_ord(monkeypatch, result):
    async def _fake(use_ordinance, **kw):  # noqa: ANN001
        return result if use_ordinance else None
    monkeypatch.setattr(drawing, "_ordinance_limits", _fake)


class TestAutoDesignOrdinance:

    def test_omitted_no_ordinance_block(self):
        """use_ordinance 미지정 → 응답·basis에 조례 키 없음(하위호환·조회 안 함)."""
        r = client.post("/api/v1/drawing/auto-design", json=_BASE)
        assert r.status_code == 200
        body = r.json()
        assert "ordinance" not in body
        assert body["summary"]["basis"]["applied_limits"]["ordinance_far_percent"] is None

    def test_use_ordinance_applies_and_reports(self, monkeypatch):
        """use_ordinance=True + 조례 180% → 적용 한도 180% + 응답 ordinance 정직 표기."""
        _patch_ord(monkeypatch, _FAKE_ORD)
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "use_ordinance": True})
        assert r.status_code == 200
        body = r.json()
        assert body["ordinance"]["used"] is True
        assert body["ordinance"]["source"] == "지자체 조례"
        lim = body["summary"]["basis"]["applied_limits"]
        assert lim["ordinance_far_percent"] == 180.0
        assert lim["max_far_percent"] == 180.0  # min(법정200, 조례180)

    def test_lookup_failure_is_honest_200(self, monkeypatch):
        """조례 조회 실패 → used=False 정직 표기, 설계는 정상 200(법정상한)."""
        _patch_ord(monkeypatch, _FAKE_ORD_FAIL)
        r = client.post("/api/v1/drawing/auto-design", json={**_BASE, "use_ordinance": True})
        assert r.status_code == 200
        body = r.json()
        assert body["ordinance"]["used"] is False
        # 법정상한 적용(조례 미반영)
        assert body["summary"]["basis"]["applied_limits"]["ordinance_far_percent"] is None

    def test_direct_effective_limits_apply_for_korean_zone(self):
        """부지분석 실효 한도는 한글 용도지역에서도 기본 2R 폴백 없이 직접 적용된다."""
        r = client.post("/api/v1/drawing/auto-design", json={
            **_BASE,
            "site_area_sqm": 12079,
            "zone_code": "자연녹지지역",
            "target_far_percent": 100,
            "target_bcr_percent": 20,
            "effective_far_pct": 80,
            "effective_bcr_pct": 20,
        })
        assert r.status_code == 200
        body = r.json()
        lim = body["summary"]["basis"]["applied_limits"]
        assert body["legal_limits"]["max_far_percent"] == 100
        assert lim["max_far_percent"] == 80
        assert lim["max_bcr_percent"] == 20
        assert lim["ordinance_far_percent"] == 80
        assert body["summary"]["far_percent"] <= 80 + 0.5

    def test_design_alternatives_receive_direct_effective_limits(self):
        """Top3 대안도 부지분석 실효 한도를 전 대안에 전파한다."""
        r = client.post("/api/v1/drawing/design-alternatives", json={
            **_BASE,
            "site_area_sqm": 12079,
            "zone_code": "자연녹지지역",
            "target_far_percent": 100,
            "target_bcr_percent": 20,
            "effective_far_pct": 80,
            "effective_bcr_pct": 20,
            "count": 3,
        })
        assert r.status_code == 200
        body = r.json()
        assert len(body["alternatives"]) == 3
        for alt in body["alternatives"]:
            lim = alt["summary"]["basis"]["applied_limits"]
            assert lim["max_far_percent"] == 80
            assert lim["max_bcr_percent"] == 20
            assert alt["summary"]["far_percent"] <= 80 + 0.5


class TestOrdinanceZoneMapping:
    """zone_code → OrdinanceService 한글 zone_type 매핑."""

    def test_code_to_zone_type(self):
        from apps.api.routers.drawing import _zone_type_for_ordinance
        assert _zone_type_for_ordinance("2R") == "제2종일반주거지역"
        assert _zone_type_for_ordinance("GC") == "일반상업지역"
        assert _zone_type_for_ordinance("QR") == "준주거지역"
        assert _zone_type_for_ordinance("자연녹지지역") == "자연녹지지역"
        assert _zone_type_for_ordinance("계획관리") == "계획관리지역"
        assert _zone_type_for_ordinance("ZZZ") is None  # 미지정 코드는 None(가짜 매핑 금지)

    async def test_korean_zone_type_flows_to_ordinance_lookup(self, monkeypatch):
        """한글 용도지역명 입력도 조례 조회 경로에서 누락되지 않는다."""
        from app.services.land_intelligence import ordinance_service
        from apps.api.routers import drawing

        seen: dict[str, str] = {}

        async def _fake(self, address, zone_type, **_kwargs):  # noqa: ANN001 — additive 파라미터 수용
            seen["zone_type"] = zone_type
            return {"effective_bcr": 20.0, "effective_far": 100.0, "source": "지자체 조례"}

        monkeypatch.setattr(ordinance_service.OrdinanceService, "get_ordinance_limits", _fake)
        out = await drawing._ordinance_limits(
            True, address="용인시 수지구 신봉동", zone_code="자연녹지지역",
        )
        assert seen["zone_type"] == "자연녹지지역"
        assert out["note"] in {
            "지자체 조례 실효 한도 적용(법정 이하)",
            "해당 지자체 조례가 법정상한을 더 제약하지 않음 — 법정상한 적용",
        }
