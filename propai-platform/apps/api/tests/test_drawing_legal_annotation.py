"""§4-C 도면 법규주석 — audit findings를 SVG 배치도에 결정론 주석화.

8엔진 design_audit의 findings(`{check_id, engine, status, current, limit, ...}`)를
배치도 SVG에 시각화한다: 건물 footprint를 최악 status로 색칠(pass 녹/warning 황/fail 적),
법규 준수 범례(아이콘 ✓/⚠/✗·라벨·현재/한도), 정북일조 미달 표시. 존재하는 finding만
렌더(날조·가짜값 0). findings 미제공 시 기존 배치도와 동일(하위호환).
"""

import pytest

svgwrite = pytest.importorskip("svgwrite", reason="svgwrite 미설치 — SVG 테스트 스킵")

from app.services.drawing.svg_drawing_service import SVGDrawingService


@pytest.fixture()
def svc():
    return SVGDrawingService()


def _finding(check_id, engine, status, **kw):
    return {"check_id": check_id, "engine": engine, "status": status,
            "current": kw.get("current"), "limit": kw.get("limit"),
            "legal_refs": [], "improvement": kw.get("improvement"), **kw}


# 색상(svg_drawing_service와 동치) — 테스트가 색으로 status를 검증.
C_FAIL = "#d63031"
C_PASS = "#00b894"


class TestAnnotateSitePlan:

    def test_returns_svg_with_site_and_building(self, svc):
        """기본 — SVG 문자열 + 부지/건물 rect 포함."""
        svg = svc.annotate_site_plan(40, 30, 25, 12, setback_m=3.0, findings=[])
        assert isinstance(svg, str) and "<svg" in svg.lower()
        assert "rect" in svg

    def test_fail_finding_colors_footprint_red_and_legend(self, svc):
        """건폐율 초과(fail) → footprint 적색 + 범례에 ✗·현재/한도 표기."""
        findings = [_finding("rules8_건폐율", "rules8", "fail", current=65.0, limit=60.0)]
        svg = svc.annotate_site_plan(40, 30, 30, 20, findings=findings, verdict="부적합")
        assert C_FAIL in svg          # footprint/범례 적색
        assert "✗" in svg            # 위반 아이콘
        assert "65" in svg and "60" in svg  # 현재·한도 정직 표기

    def test_all_pass_colors_footprint_green(self, svc):
        """전 항목 pass → footprint 녹색 + ✓."""
        findings = [
            _finding("rules8_건폐율", "rules8", "pass", current=55.0, limit=60.0),
            _finding("rules8_용적률", "rules8", "pass", current=190.0, limit=200.0),
        ]
        svg = svc.annotate_site_plan(40, 30, 22, 12, findings=findings, verdict="적합")
        assert C_PASS in svg
        assert "✓" in svg

    def test_warning_uses_warning_icon(self, svc):
        """warning finding → ⚠ 아이콘(조건부)."""
        findings = [_finding("solar_정북일조", "solar", "warning",
                             current=1.5, limit=2.0, improvement="북측 이격 부족")]
        svg = svc.annotate_site_plan(40, 30, 25, 18, findings=findings, verdict="조건부적합")
        assert "⚠" in svg

    def test_sunlight_fail_draws_north_indicator(self, svc):
        """정북일조 fail → 북측 변에 적색 점선 표시 + '일조' 라벨(정북 사선 인지)."""
        findings = [_finding("solar_일조", "solar", "fail", current=1.0, limit=2.0)]
        svg = svc.annotate_site_plan(40, 30, 30, 22, findings=findings)
        assert "일조" in svg
        assert "stroke-dasharray" in svg or "stroke_dasharray" in svg or "dasharray" in svg

    def test_no_findings_is_backward_compatible(self, svc):
        """findings 미제공 → 가짜 ✓/✗ 없이 정상 SVG(하위호환 — 날조 금지)."""
        svg = svc.annotate_site_plan(40, 30, 25, 12)
        assert isinstance(svg, str) and "<svg" in svg.lower()
        assert "✓" not in svg and "✗" not in svg  # 판정 데이터 없으면 아이콘 미표기

    def test_only_present_findings_rendered(self, svc):
        """제공된 finding만 범례에 — 미제공 항목은 표기하지 않음(정직)."""
        findings = [_finding("rules8_용적률", "rules8", "fail", current=220.0, limit=200.0)]
        svg = svc.annotate_site_plan(40, 30, 28, 18, findings=findings)
        assert "용적률" in svg
        assert "주차" not in svg  # 제공 안 한 항목은 없어야

    def test_skipped_finding_not_counted_as_pass_or_fail(self, svc):
        """skipped/info finding은 ✓/✗로 단정하지 않음(판정불가 정직)."""
        findings = [_finding("design_review", "design_review", "skipped",
                             note="설계 건폐율·용적률 미입력")]
        svg = svc.annotate_site_plan(40, 30, 25, 12, findings=findings)
        # skipped만 있으면 footprint를 pass(녹)로 칠하지 않는다(AND — 회귀 포착 강화).
        assert C_PASS not in svg and "✓" not in svg and "✗" not in svg

    def test_real_solar_envelope_engine_draws_north_indicator(self, svc):
        """실 오케스트레이터 engine='solar_envelope' fail → 북측 점선·라벨 발화.

        (합성 engine='solar'가 아닌 실제 design_audit 엔진명으로 정북일조 표시를 검증 —
        필터가 'solar'만 매칭하면 실데이터에서 영구 미발화하는 dead-path를 막는다.)
        """
        findings = [_finding("solar_envelope", "solar_envelope", "fail",
                             current=1.0, limit=2.0)]
        svg = svc.annotate_site_plan(40, 30, 30, 22, findings=findings)
        assert "정북일조" in svg
        assert "stroke-dasharray" in svg or "dasharray" in svg

    def test_mixed_status_worst_is_fail(self, svc):
        """pass+warning+fail 혼합 → 최악(fail)으로 footprint 적색."""
        findings = [
            _finding("rules8_건폐율", "rules8", "pass", current=55.0, limit=60.0),
            _finding("solar_envelope", "solar_envelope", "warning", current=1.5, limit=2.0),
            _finding("rules8_용적률", "rules8", "fail", current=220.0, limit=200.0),
        ]
        svg = svc.annotate_site_plan(40, 30, 30, 20, findings=findings)
        assert C_FAIL in svg


class TestFindingLabel:
    """_finding_label — check_id/engine에서 표시 라벨(multi-word 엔진 포함)."""

    def test_multiword_engine_label(self):
        from app.services.drawing.svg_drawing_service import _finding_label
        # check_id==engine(접미사 없음) → 엔진 라벨(깨진 영문 'envelope' 금지)
        assert _finding_label({"check_id": "solar_envelope", "engine": "solar_envelope"}) == "정북일조"
        # 'engine_타입' → 타입 접미사
        assert _finding_label({"check_id": "design_review_건폐율", "engine": "design_review"}) == "건폐율"
        assert _finding_label({"check_id": "rules8_용적률", "engine": "rules8"}) == "용적률"
        # 단일 단어 엔진(접미사 없음) → 엔진 라벨
        assert _finding_label({"check_id": "rules8", "engine": "rules8"}) == "법규"

    def test_solar_envelope_legend_label_not_broken(self, svc):
        """범례에 'envelope' 같은 깨진 영문이 아니라 '정북일조'가 표기된다."""
        findings = [_finding("solar_envelope", "solar_envelope", "fail", current=1.0, limit=2.0)]
        svg = svc.annotate_site_plan(40, 30, 30, 22, findings=findings)
        assert "정북일조" in svg
        assert "envelope" not in svg


# ── 라우터: POST /drawing/annotated-site-plan (DB-free) ──

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers.drawing import router as drawing_router

_app = FastAPI()
_app.include_router(drawing_router, prefix="/api/v1/drawing")
client = TestClient(_app)


class TestAnnotatedSitePlanRoute:
    """순수 결정론 산출 — 인증·DB 없이 findings를 받아 주석 도면 SVG 반환."""

    def test_returns_annotated_svg(self):
        r = client.post("/api/v1/drawing/annotated-site-plan", json={
            "site_width_m": 40, "site_depth_m": 30,
            "building_width_m": 28, "building_depth_m": 18, "setback_m": 3.0,
            "findings": [{"check_id": "rules8_건폐율", "engine": "rules8",
                          "status": "fail", "current": 65.0, "limit": 60.0}],
            "verdict": "부적합",
        })
        assert r.status_code == 200
        assert "image/svg+xml" in r.headers["content-type"]
        assert "✗" in r.text and "건폐율" in r.text and "부적합" in r.text

    def test_no_findings_backward_compatible(self):
        r = client.post("/api/v1/drawing/annotated-site-plan", json={
            "site_width_m": 40, "site_depth_m": 30,
            "building_width_m": 25, "building_depth_m": 12,
        })
        assert r.status_code == 200
        assert "<svg" in r.text.lower()
        assert "✓" not in r.text and "✗" not in r.text
