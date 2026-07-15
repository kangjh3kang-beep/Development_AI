"""2026-07-15 수지·적산엔진 감사 후속 스윕(PR-A) 회귀 테스트.

대상 3.5건:
1. far 가정치 고지 문구 SSOT(far_fallback) — 수지 추천·solar 매스 경로 문장 통일.
2. solar_envelope: 미매칭 용도지역 200% 보수 가정치의 assumptions 정직 전파(값 무회귀).
3. /feasibility/export-excel 인증 부착(무인증 전체 재계산 차단).
4. bid_analyzer 구조계수: 물량계수 혼용 → 비용계수 SSOT(STRUCT_COST_FACTOR) 별칭.
※ project_pipeline은 재검증 결과 E7 채널(assumed_fields·data_quality)로 기존 방어
   확인 — 무수정(943 폴백은 AutoZoning이 max_far_pct를 항상 채워 도달 불가).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.land_intelligence.far_fallback import far_fallback_disclosure


# ─────────────────────────────────────────────────────────────────────────────
# 1) 문구 SSOT
# ─────────────────────────────────────────────────────────────────────────────
class TestFarFallbackDisclosure:
    def test_format_contains_pct_and_honesty_markers(self):
        for pct, label in ((250, "250%"), (200, "200%")):
            msg = far_fallback_disclosure(pct)
            assert label in msg and "가정치" in msg and "참고용" in msg

    def test_snapshot_pins_exact_p3_sentence(self):
        """리뷰 R1-P2: 전체 문자열 스냅샷 — 헬퍼 문구가 표류하면 프론트 배너 텍스트가
        조용히 바뀌므로 P3(PR#292) 원문 전문을 고정한다(부분문자열 테스트의 사각 보완)."""
        assert far_fallback_disclosure(250) == (
            "용도지역 용적률 상한 미확보 — 250% 가정치 기준 산정(참고용). "
            "GFA·세대수·매출·ROI 전 수치가 가정치 기반이므로 용도지역 확정 후 재산정이 필요합니다."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2) solar_envelope — 미매칭 용도지역 가정치 정직 전파
# ─────────────────────────────────────────────────────────────────────────────
class TestSolarEnvelopeFarAssumption:
    def _run(self, zone: str) -> dict:
        from app.services.site_score.solar_envelope_service import compute_buildable_envelope

        return compute_buildable_envelope(
            land_area_sqm=1000.0, zone=zone,
            land_width_m=25.0, land_depth_m=40.0,
        )

    def test_unmatched_zone_discloses_200_assumption(self):
        out = self._run("존재하지않는특수지역")
        assert "error" not in out
        notes = out.get("assumptions") or []
        assert any("200% 가정치" in n for n in notes), notes
        # 값 무회귀: 보수 가정치 200%가 그대로 산정에 사용.
        assert out["far_pct"] == 200.0

    def test_matched_zone_no_assumption_note(self):
        out = self._run("제2종일반주거지역")
        notes = out.get("assumptions") or []
        assert not any("가정치 기준 산정" in n for n in notes), notes

    def test_explicit_far_limit_suppresses_note(self):
        """호출자가 상한을 명시하면 미매칭 용도지역이어도 가정치 고지 없음(실입력 존중)."""
        from app.services.site_score.solar_envelope_service import compute_buildable_envelope

        out = compute_buildable_envelope(
            land_area_sqm=1000.0, zone="존재하지않는특수지역",
            land_width_m=25.0, land_depth_m=40.0, far_limit_pct=180.0,
        )
        notes = out.get("assumptions") or []
        assert not any("가정치 기준 산정" in n for n in notes), notes


# ─────────────────────────────────────────────────────────────────────────────
# 3) export-excel 인증
# ─────────────────────────────────────────────────────────────────────────────
class TestExportExcelAuth:
    def _client(self, with_auth: bool) -> TestClient:
        from app.routers.v2_feasibility import router
        from app.services.auth.auth_service import get_current_user

        app = FastAPI()
        app.include_router(router)
        if with_auth:
            class _User:
                id = "00000000-0000-0000-0000-000000000001"
                tenant_id = "00000000-0000-0000-0000-000000000002"
                role = "user"
                is_active = True

            app.dependency_overrides[get_current_user] = lambda: _User()
        return TestClient(app)

    _BODY = {
        "development_type": "M06",
        "total_land_area_sqm": 1000.0,
        "official_price_per_sqm": 3_000_000,
        "total_gfa_sqm": 2000.0,
        "avg_sale_price_per_pyeong": 15_000_000,
        "avg_area_pyeong": 34.0,
        "total_households": 30,
    }

    def test_unauthenticated_rejected(self):
        resp = self._client(with_auth=False).post("/api/v2/feasibility/export-excel", json=self._BODY)
        assert resp.status_code in (401, 403), resp.status_code

    def test_authenticated_returns_binary(self):
        resp = self._client(with_auth=True).post("/api/v2/feasibility/export-excel", json=self._BODY)
        assert resp.status_code == 200
        assert "spreadsheet" in resp.headers["content-type"] or "csv" in resp.headers["content-type"]


# ─────────────────────────────────────────────────────────────────────────────
# 4) bid_analyzer 구조계수 — 비용계수 SSOT
# ─────────────────────────────────────────────────────────────────────────────
class TestBidAnalyzerStructFactor:
    def test_alias_is_cost_factor_ssot(self):
        from app.services.ai_services.bid_analyzer import _STRUCTURE_FACTORS
        from app.services.cost.overview_estimator import STRUCT_COST_FACTOR

        assert _STRUCTURE_FACTORS is STRUCT_COST_FACTOR  # 값 이원화 금지(동일 객체)

    def test_quantity_factor_confusion_corrected(self):
        """물량계수(PC 0.92·목구조 0.70) 혼용 교정 — 비용계수(0.95·0.85) 채택."""
        from app.services.ai_services.bid_analyzer import _STRUCTURE_FACTORS

        assert _STRUCTURE_FACTORS["PC"] == 0.95
        assert _STRUCTURE_FACTORS["목구조"] == 0.85
        assert _STRUCTURE_FACTORS["RC"] == 1.0 and _STRUCTURE_FACTORS["SRC"] == 1.15
