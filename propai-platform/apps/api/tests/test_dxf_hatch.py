"""§4-D #2: DXF 단면도에 재료 해칭(HATCH 엔티티) — 콘크리트(기초·슬래브) 패턴.

기존 단면도는 슬래브·벽을 선(LINE)으로만 그려 DXF에 HATCH 엔티티가 0건이었다(HATCH 레이어는
정의됐으나 add_hatch 미호출 — 감사 확인). 본 작업은 기초·층 슬래브에 콘크리트 해칭(ANSI31)을
additive로 추가한다(기존 선·치수 불변). AutoCAD에서 진짜 해칭으로 인식되는 실무 단면도 1단계.
"""

import io

import pytest

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")

from app.services.cad.parametric_cad_service import ParametricCADService


@pytest.fixture()
def svc():
    return ParametricCADService()


def _read(dxf_bytes: bytes):
    return ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8")))


class TestSectionHatch:

    def test_section_dxf_has_hatch_entities(self, svc):
        """단면도 DXF에 HATCH 엔티티가 존재(재료 해칭 — 기존 0건 해소)."""
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12, floor_count=3, basement_floors=1,
        )
        doc = _read(dxf)
        hatches = list(doc.modelspace().query("HATCH"))
        assert len(hatches) > 0

    def test_hatch_on_hatch_layer_with_pattern(self, svc):
        """해칭은 HATCH 레이어 + 패턴 채움(SOLID 아님 — 재료 표현)."""
        dxf = svc.create_section_drawing_dxf(
            building_width_m=18, building_depth_m=10, floor_count=2, basement_floors=0,
        )
        doc = _read(dxf)
        hatches = list(doc.modelspace().query("HATCH[layer=='HATCH']"))
        assert len(hatches) > 0
        # 적어도 하나는 패턴 채움(해치 패턴명 존재)
        assert any(h.dxf.solid_fill == 0 for h in hatches)

    def test_floor_count_scales_hatch(self, svc):
        """층수↑ → 슬래브 해칭↑(층별 슬래브에 콘크리트 해칭 — 결정론)."""
        h2 = len(_read(svc.create_section_drawing_dxf(
            building_width_m=18, building_depth_m=10, floor_count=2, basement_floors=0,
        )).modelspace().query("HATCH"))
        h5 = len(_read(svc.create_section_drawing_dxf(
            building_width_m=18, building_depth_m=10, floor_count=5, basement_floors=0,
        )).modelspace().query("HATCH"))
        assert h5 > h2

    def test_existing_lines_preserved(self, svc):
        """기존 LINE/치수는 그대로(additive — 해칭만 가산)."""
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12, floor_count=3, basement_floors=1,
        )
        doc = _read(dxf)
        assert len(list(doc.modelspace().query("LINE"))) > 0  # 단면 선 유지
