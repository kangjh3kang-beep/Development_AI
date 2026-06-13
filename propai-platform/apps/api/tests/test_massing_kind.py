"""매스 형상(massing_kind) 결정론 변형 — opt-in·additive.

기존 동작(None=자동)은 불변, 명시 시 형상별 종횡비·플로어플레이트로 매스 재산출.
판상(slab)·타워(tower)·ㄱ자(lshape)·중정(court). LLM 0(결정론).
"""

import pytest

from app.services.cad.auto_design_engine import (
    MASSING_FORMS,
    AutoDesignEngineService,
    SiteInput,
)


@pytest.fixture()
def engine() -> AutoDesignEngineService:
    return AutoDesignEngineService()


def _inp(massing_kind: str | None = None) -> SiteInput:
    # 형상이 클램프되지 않고 실제로 매스를 구동하도록 충분히 큰 대지.
    return SiteInput(
        site_area_sqm=4000,
        zone_code="2R",
        building_use="공동주택",
        target_unit_types=["84A"],
        floor_height_m=3.0,
        setback_m={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5},
        massing_kind=massing_kind,
    )


class TestMassingKind:
    def test_default_none_is_auto(self, engine: AutoDesignEngineService):
        """massing_kind 미지정 시 출처는 'auto'(대지 종횡비 기반) — 하위호환."""
        s = engine.generate(_inp(None)).summary
        assert s["massing_kind"] == "auto"
        assert s["massing_label"] == "자동(대지비율)"
        assert s["building_area_sqm"] > 0

    def test_explicit_kind_propagates(self, engine: AutoDesignEngineService):
        s = engine.generate(_inp("tower")).summary
        assert s["massing_kind"] == "tower"
        assert s["massing_label"] == MASSING_FORMS["tower"]["label"]

    def test_tower_smaller_plate_taller_than_slab(self, engine: AutoDesignEngineService):
        """타워형은 작은 플로어플레이트 → 건축면적↓·층수↑ (결정론)."""
        slab = engine.generate(_inp("slab")).summary
        tower = engine.generate(_inp("tower")).summary
        assert tower["building_area_sqm"] < slab["building_area_sqm"]
        assert tower["num_floors"] >= slab["num_floors"]

    def test_slab_is_wide_and_shallow(self, engine: AutoDesignEngineService):
        """판상형: 전면 폭 ≥ 깊이(넓고 얕은 매스)."""
        slab = engine.generate(_inp("slab")).summary
        assert slab["building_width_m"] >= slab["building_depth_m"]

    def test_unknown_kind_falls_back_to_auto(self, engine: AutoDesignEngineService):
        """미정의 형상 문자열은 자동으로 폴백 — 예외·가짜값 없음(정직)."""
        s = engine.generate(_inp("nonsense")).summary
        assert s["massing_kind"] == "auto"
        assert s["building_area_sqm"] > 0

    @pytest.mark.parametrize("kind", list(MASSING_FORMS.keys()))
    def test_all_forms_produce_valid_mass(self, engine: AutoDesignEngineService, kind: str):
        """정의된 4개 형상 모두 양수 면적·층수 산출(법규 한도 내)."""
        s = engine.generate(_inp(kind)).summary
        assert s["building_area_sqm"] > 0
        assert s["num_floors"] >= 1
        assert s["bcr_percent"] <= 100
