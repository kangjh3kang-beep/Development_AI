"""§4-D A: 단면 구조상세 — 슬래브 철근배근(상/하부 주근·배력근)·콘크리트 피복.

기존 create_section_drawing_dxf은 층고·외형·해칭까지(철근 상세 전무). 본 작업은 옵셔널 rebar로
각 층 슬래브에 상/하부 주근 점(원)·배력근 선을 REBAR 레이어에 additive로 추가한다. 실무 구조
단면의 1단계(배근 표기). rebar=False(기본)면 기존 동작 완전 불변. 정직: 배근 간격은 표준 가정값
(구조계산 미연동 — 표기용).
"""

import io

import pytest

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치")

from app.services.cad.parametric_cad_service import ParametricCADService


@pytest.fixture()
def svc():
    return ParametricCADService()


def _read(b: bytes):
    return ezdxf.read(io.StringIO(b.decode("utf-8")))


class TestSectionRebar:

    def test_rebar_adds_rebar_layer_entities(self, svc):
        """rebar=True → REBAR 레이어에 철근 엔티티(원=주근 단면 / 선=배력근) 추가."""
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12, floor_count=3,
            basement_floors=0, rebar=True,
        )
        doc = _read(dxf)
        msp = doc.modelspace()
        rebar_circles = list(msp.query("CIRCLE[layer=='REBAR']"))
        rebar_lines = list(msp.query("LINE[layer=='REBAR']"))
        assert len(rebar_circles) > 0  # 주근 단면(원)
        assert len(rebar_lines) > 0     # 배력근/철근 선

    def test_rebar_scales_with_floors(self, svc):
        """층수↑ → 철근 엔티티↑(층별 슬래브 배근 — 결정론)."""
        def n(fc):
            doc = _read(svc.create_section_drawing_dxf(
                building_width_m=20, building_depth_m=12, floor_count=fc,
                basement_floors=0, rebar=True))
            return len(list(doc.modelspace().query("CIRCLE[layer=='REBAR']")))
        assert n(5) > n(2)

    def test_no_rebar_backward_compatible(self, svc):
        """rebar 미지정(기본 False) → REBAR 엔티티 없음(기존 동작 완전 불변)."""
        doc = _read(svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12, floor_count=3, basement_floors=0))
        assert len(list(doc.modelspace().query("CIRCLE[layer=='REBAR']"))) == 0
        # 기존 단면 선·HATCH는 유지
        assert len(list(doc.modelspace().query("LINE"))) > 0
