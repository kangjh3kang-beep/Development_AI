"""§4-D B/C: RCP(반사천장도)·MEP(설비도) 생성기.

기존 도면셋엔 RCP/MEP 생성기가 전무였다(감사 확인). 본 작업은 결정론 SVG 생성기를 추가한다 —
RCP: 천장 텍스 그리드 + 조명기구·디퓨저·스프링클러 배치. MEP: 급배기 덕트 간선 + 급수/오수 배관
경로. 정직: 라우팅·배치는 표준 그리드 기반 schematic(부하·사이징 미산 — 표기용).
"""

import pytest

svgwrite = pytest.importorskip("svgwrite", reason="svgwrite 미설치")

from app.services.drawing.svg_drawing_service import SVGDrawingService


@pytest.fixture()
def svc():
    return SVGDrawingService()


class TestRCP:

    def test_rcp_returns_svg(self, svc):
        """RCP SVG — 천장 그리드 + 조명·디퓨저 요소."""
        svg = svc.generate_rcp(20, 12)
        assert "<svg" in svg.lower()
        assert "조명" in svg and "디퓨저" in svg
        # 천장 그리드 선·기구 사각형
        assert svg.count("<line") > 4 or svg.count("<rect") > 4

    def test_rcp_scales_with_area(self, svc):
        """천장 면적↑ → 그리드/기구↑(결정론)."""
        big = svc.generate_rcp(40, 30)
        small = svc.generate_rcp(10, 8)
        assert big.count("<line") + big.count("<rect") > small.count("<line") + small.count("<rect")

    def test_rcp_has_sprinkler(self, svc):
        """스프링클러(소방) 기호 포함."""
        svg = svc.generate_rcp(20, 12)
        assert "스프링클러" in svg or "SP" in svg


class TestMEP:

    def test_mep_returns_svg(self, svc):
        """MEP SVG — 덕트 간선 + 급수/오수 배관."""
        svg = svc.generate_mep(20, 12)
        assert "<svg" in svg.lower()
        assert "덕트" in svg and ("급수" in svg or "배관" in svg)

    def test_mep_scales_with_area(self, svc):
        big = svc.generate_mep(40, 30)
        small = svc.generate_mep(10, 8)
        assert len(big) > len(small)

    def test_mep_honest_schematic_label(self, svc):
        """정직: schematic(부하/사이징 미산) 표기."""
        svg = svc.generate_mep(20, 12)
        assert "schematic" in svg.lower() or "개략" in svg


class TestDrawingSetIncludesRcpMep:

    def test_full_set_has_rcp_and_mep(self, svc):
        """전체 도면셋에 RCP(B-05)·MEP(B-06)이 포함된다."""
        drawings = svc.generate_full_drawing_set({
            "building_width_m": 30, "building_depth_m": 18, "floor_count": 5,
        })
        keys = " ".join(drawings.keys())
        assert "RCP" in keys or "B-05" in keys
        assert "MEP" in keys or "B-06" in keys
