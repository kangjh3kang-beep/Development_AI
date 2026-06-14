"""§4-C 후속 #3: 상세 평면도에 법규 findings 주석 — 피난동선 강조 + 법규 범례.

기존 generate_detailed_floor_plan은 기하(벽/문/창/코어/세대)만 렌더하고 findings를 받지 않았다.
본 작업은 옵셔널 findings를 받아 ① 복도를 피난동선으로 적색 점선 강조 ② 법규 범례(✓/⚠/✗·라벨)를
추가한다(배치도 annotate_site_plan 패턴 이식). findings 미제공 시 기존 동작 완전 불변(하위호환).
"""

import pytest

svgwrite = pytest.importorskip("svgwrite", reason="svgwrite 미설치 — SVG 테스트 스킵")

from app.services.drawing.svg_drawing_service import SVGDrawingService


@pytest.fixture()
def svc():
    return SVGDrawingService()


def _f(check_id, engine, status, **kw):
    return {"check_id": check_id, "engine": engine, "status": status,
            "current": kw.get("current"), "limit": kw.get("limit")}


class TestFloorPlanAnnotation:

    def test_findings_legend_rendered(self, svc):
        """fail finding → 범례에 ✗·라벨(건폐율)."""
        svg = svc.generate_detailed_floor_plan(
            30, 15, findings=[_f("rules8_건폐율", "rules8", "fail", current=65, limit=60)])
        assert "✗" in svg and "건폐율" in svg

    def test_evacuation_route_highlighted(self, svc):
        """피난(grammar) finding → 복도를 피난동선으로 적색 점선 강조 + 라벨."""
        svg = svc.generate_detailed_floor_plan(
            30, 15, findings=[_f("grammar_피난", "grammar", "warning")])
        assert "피난동선" in svg
        assert "stroke-dasharray" in svg or "dasharray" in svg

    def test_no_findings_backward_compatible(self, svc):
        """findings 미제공 → 아이콘·피난동선 라벨 없음(기존 동작 완전 불변)."""
        svg = svc.generate_detailed_floor_plan(30, 15)
        assert "✗" not in svg and "✓" not in svg
        assert "피난동선" not in svg

    def test_skipped_not_counted(self, svc):
        """skipped finding만 → ✓/✗ 단정 없음(정직)."""
        svg = svc.generate_detailed_floor_plan(
            30, 15, findings=[_f("design_review", "design_review", "skipped")])
        assert "✗" not in svg and "✓" not in svg

    def test_returns_valid_svg(self, svc):
        """findings 있어도 유효 SVG·기존 요소(rect/line) 유지."""
        svg = svc.generate_detailed_floor_plan(
            30, 15, findings=[_f("rules8_용적률", "rules8", "pass", current=180, limit=200)])
        assert "<svg" in svg.lower() and ("rect" in svg or "line" in svg)
        assert "✓" in svg and "용적률" in svg
