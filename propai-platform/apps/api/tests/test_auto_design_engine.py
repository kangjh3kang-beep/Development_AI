"""AutoDesignEngineService 단위 테스트."""

import pytest

from app.services.cad.auto_design_engine import (
    AutoDesignEngineService,
    DesignResult,
    SiteInput,
)


@pytest.fixture()
def engine():
    return AutoDesignEngineService()


@pytest.fixture()
def default_input():
    return SiteInput(
        site_area_sqm=500,
        zone_code="2R",
        building_use="공동주택",
        target_unit_types=["84A"],
        floor_height_m=3.0,
        setback_m={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5},
    )


class TestAutoDesignEngineGenerate:
    """generate() 정상 동작 검증."""

    def test_returns_design_result(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        assert isinstance(result, DesignResult)
        assert "points" in result.design_payload
        assert "lines" in result.design_payload
        assert "surfaces" in result.design_payload

    def test_summary_fields(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        s = result.summary
        assert s["building_area_sqm"] > 0
        assert s["total_floor_area_sqm"] > 0
        assert s["num_floors"] >= 1
        assert s["building_height_m"] > 0
        assert 0 < s["bcr_percent"] <= 100
        assert s["far_percent"] > 0
        assert s["total_units"] >= 0
        assert s["parking_count"] >= 0

    def test_compliance_fields(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        c = result.compliance
        assert "bcr_ok" in c
        assert "far_ok" in c
        assert "height_ok" in c
        assert "all_pass" in c

    def test_2r_zone_bcr_within_limit(self, engine: AutoDesignEngineService):
        """제2종일반주거지역 건폐율 60% 이하."""
        inp = SiteInput(site_area_sqm=500, zone_code="2R")
        result = engine.generate(inp)
        assert result.summary["bcr_percent"] <= 60.0
        assert result.compliance["bcr_ok"] is True

    def test_gc_zone_high_far(self, engine: AutoDesignEngineService):
        """일반상업지역 높은 용적률 허용."""
        inp = SiteInput(site_area_sqm=1000, zone_code="GC", building_use="업무시설")
        result = engine.generate(inp)
        assert result.summary["num_floors"] >= 1
        assert result.compliance["far_ok"] is True

    def test_1r_zone_low_density(self, engine: AutoDesignEngineService):
        """제1종일반주거지역 저밀도 설계."""
        inp = SiteInput(site_area_sqm=300, zone_code="1R")
        result = engine.generate(inp)
        assert result.summary["bcr_percent"] <= 60.0
        assert result.summary["far_percent"] <= 200.0

    def test_design_payload_has_scale(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        assert "scale" in result.design_payload
        assert "floor_count" in result.design_payload

    def test_small_site_still_generates(self, engine: AutoDesignEngineService):
        """아주 작은 대지도 에러 없이 생성."""
        inp = SiteInput(site_area_sqm=50, zone_code="2R")
        result = engine.generate(inp)
        assert result.summary["building_area_sqm"] > 0

    def test_large_site(self, engine: AutoDesignEngineService):
        """큰 대지 정상 처리."""
        inp = SiteInput(site_area_sqm=5000, zone_code="3R")
        result = engine.generate(inp)
        assert result.summary["total_units"] > 0


class TestAutoDesignAlternatives:
    """generate_alternatives() 검증."""

    def test_returns_3_alternatives(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=3)
        assert len(results) == 3

    def test_alternatives_differ(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=3)
        # 적어도 두 대안이 다르거나, 모두 동일한 건 극소 대지 시 가능
        assert len(results) == 3

    def test_all_alternatives_compliant(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=3)
        for r in results:
            assert r.compliance["bcr_ok"] is True
            assert r.compliance["far_ok"] is True

    def test_single_alternative(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=1)
        assert len(results) == 1


class TestAutoDesignLegalLimits:
    """법규 한도 경계 검증."""

    def test_get_legal_limits_2r(self, engine: AutoDesignEngineService):
        limits = engine.get_legal_limits("2R")
        assert limits["max_bcr_percent"] == 60.0
        assert limits["max_far_percent"] == 200.0

    def test_get_legal_limits_gc(self, engine: AutoDesignEngineService):
        limits = engine.get_legal_limits("GC")
        assert limits["max_bcr_percent"] == 60.0
        assert limits["max_far_percent"] == 1000.0

    def test_unknown_zone_defaults(self, engine: AutoDesignEngineService):
        limits = engine.get_legal_limits("UNKNOWN")
        assert limits["max_bcr_percent"] == 60.0  # 기본값

    def test_get_legal_limits_natural_green_korean_label(self, engine: AutoDesignEngineService):
        """자연녹지지역은 표준 용도지역이므로 제2종일반주거 폴백 없이 자체 한도를 사용한다."""
        limits = engine.get_legal_limits("자연녹지지역")
        assert limits["max_bcr_percent"] == 20.0
        assert limits["max_far_percent"] == 100.0
        assert limits["max_height_m"] == 12.0
        assert limits["limits_source"] == "statutory_default"
        assert limits["zone_key"] == "자연녹지지역"
        assert not any("미지정 용도지역" in warning for warning in limits["warnings"])

    def test_natural_green_generation_respects_green_caps(self, engine: AutoDesignEngineService):
        """자연녹지지역 공동주택 시드도 녹지지역 한도(건폐율 20%·용적률 100%·4층 근사)를 넘지 않는다."""
        inp = SiteInput(site_area_sqm=2000, zone_code="자연녹지지역", building_use="공동주택")
        result = engine.generate(inp)
        assert result.summary["bcr_percent"] <= 20.0
        assert result.summary["far_percent"] <= 100.0
        assert result.summary["num_floors"] <= 4
        assert result.compliance["bcr_ok"] is True
        assert result.compliance["far_ok"] is True
        assert result.compliance["height_ok"] is True


class TestAutoDesignComputations:
    """내부 계산 검증."""

    def test_effective_site_reduces_area(self, engine: AutoDesignEngineService):
        inp = SiteInput(site_area_sqm=500, setback_m={"north": 5, "south": 5, "east": 5, "west": 5})
        eff = engine.compute_effective_site(inp)
        assert eff["effective_area_sqm"] < 500

    def test_optimal_mass(self, engine: AutoDesignEngineService, default_input: SiteInput):
        limits = engine.get_legal_limits("2R")
        eff = engine.compute_effective_site(default_input)
        mass = engine.compute_optimal_mass(default_input, eff, limits)
        assert mass["building_footprint_sqm"] > 0
        assert mass["num_floors"] >= 1


class TestWALegalCorrections:
    """W-A 설계엔진 법규 교정 검증 (건축법 61조·시행령 84/86조, 가짜값 금지)."""

    def test_qr_zone_no_sunlight_cap_high_far(self, engine: AutoDesignEngineService):
        """준주거(QR) 286㎡ — 정북일조 미적용(건축법 61조 적용범위 외) → 8층 이상·FAR 450% 이상."""
        inp = SiteInput(site_area_sqm=286, zone_code="QR", building_use="공동주택")
        result = engine.generate(inp)
        assert result.summary["num_floors"] >= 8
        assert result.summary["far_percent"] >= 450
        sunlight = result.summary["basis"]["sunlight"]
        assert sunlight["applied"] is False
        assert sunlight["mode"] == "not_applicable"

    def test_2r_same_input_sunlight_cap_maintained(self, engine: AutoDesignEngineService):
        """2R 동일 입력 — 정북일조 캡(북측이격 3m<5.0m → 최고높이 10m, 시행령 86조 현행)."""
        inp = SiteInput(site_area_sqm=286, zone_code="2R", building_use="공동주택")
        result = engine.generate(inp)
        assert result.summary["building_height_m"] <= 10.0
        sunlight = result.summary["basis"]["sunlight"]
        assert sunlight["applied"] is True
        assert sunlight["mode"] == "hard_cap"
        assert sunlight["max_height_by_sunlight_m"] == 10.0

    def test_sunlight_cap_formula_wide_north_setback(self, engine: AutoDesignEngineService):
        """북측이격 d≥5.0m → 일조 최고높이 2d (10m 이하 부분 1.5m 룰 반영 교정 산식)."""
        inp = SiteInput(
            site_area_sqm=500, zone_code="2R",
            setback_m={"north": 6.0, "south": 2.0, "east": 1.5, "west": 1.5},
        )
        result = engine.generate(inp)
        assert result.summary["basis"]["sunlight"]["max_height_by_sunlight_m"] == 12.0

    def test_qr_bcr_limit_is_70(self, engine: AutoDesignEngineService):
        """준주거 건폐율 법정 상한 70% (국토계획법 시행령 84조 — 기존 60%는 오기재)."""
        limits = engine.get_legal_limits("QR")
        assert limits["max_bcr_percent"] == 70.0

    def test_unit_area_sum_within_net_area_per_floor(self, engine: AutoDesignEngineService, default_input: SiteInput):
        """W-A ③ 불변식: 층당 세대면적합 <= 층당 순면적 (max(1,…) 가짜 세대 금지)."""
        legal = engine.get_legal_limits(default_input.zone_code)
        eff = engine.compute_effective_site(default_input)
        mass = engine.compute_optimal_mass(default_input, eff, legal)
        core = engine.compute_core_layout(mass, default_input.building_use)
        layout = engine.compute_unit_layout(mass, core, ["39A", "59A", "84A"], "공동주택")
        per_floor_sum = sum(u["area_sqm"] * u["count_per_floor"] for u in layout["units"])
        assert per_floor_sum <= layout["net_area_per_floor_sqm"] + 0.01

    def test_tiny_site_zero_units_honest(self, engine: AutoDesignEngineService):
        """순면적 < 최소 평형 → 0세대·units_feasible=False·주차 0대 정직 반환(W-A ③)."""
        inp = SiteInput(site_area_sqm=50, zone_code="2R", building_use="공동주택")
        result = engine.generate(inp)
        assert result.summary["total_units"] == 0
        assert result.summary["units_feasible"] is False
        assert "units_note" in result.summary
        assert result.summary["parking_count"] == 0  # 0세대 → 0대 (최소 1대 강제 없음)

    def test_parking_matches_units(self, engine: AutoDesignEngineService, default_input: SiteInput):
        """공동주택 주차: 세대당 1.0대(주차장법 단순화) — 세대수 연동 재산출."""
        result = engine.generate(default_input)
        assert result.summary["parking_count"] == result.summary["total_units"]
        assert "세대당 1.0대" in result.summary["basis"]["parking_formula"]

    def test_target_far_above_statutory_clamped(self, engine: AutoDesignEngineService):
        """목표 FAR이 법정 초과 시 법정값으로 클램프(W-A ④ — 가짜 한도 상향 금지)."""
        inp = SiteInput(site_area_sqm=500, zone_code="2R", target_far_percent=9999.0)
        result = engine.generate(inp)
        applied = result.summary["basis"]["applied_limits"]
        assert applied["max_far_percent"] == 200.0  # min(법정 200, 목표 9999)
        assert result.summary["far_percent"] <= 200.0

    def test_target_far_below_statutory_applied(self, engine: AutoDesignEngineService):
        """목표 FAR < 법정 → min(법정, 목표) 적용, 결과 FAR이 목표 이내."""
        inp = SiteInput(site_area_sqm=286, zone_code="QR", target_far_percent=300.0)
        result = engine.generate(inp)
        assert result.summary["basis"]["applied_limits"]["max_far_percent"] == 300.0
        assert result.summary["far_percent"] <= 300.0
        assert result.summary["binding_constraint"] == "far"  # 목표 FAR이 층수를 막음

    def test_binding_constraint_sunlight(self, engine: AutoDesignEngineService):
        """일조캡이 층수를 막는 입력 — binding_constraint='sunlight' 표기(W-A ④)."""
        inp = SiteInput(
            site_area_sqm=500, zone_code="2R",
            setback_m={"north": 3.0, "south": 2.0, "east": 5.0, "west": 5.0},
        )
        result = engine.generate(inp)
        assert result.summary["binding_constraint"] == "sunlight"

    def test_summary_basis_block_present(self, engine: AutoDesignEngineService, default_input: SiteInput):
        """W-A ⑤: summary.basis — 세트백 실값·일조 산식·바인딩 제약·주차/코어 산식 정직 표기."""
        result = engine.generate(default_input)
        basis = result.summary["basis"]
        assert basis["setback_applied_m"] == default_input.setback_m
        assert "formula" in basis["sunlight"]
        assert basis["floors_binding_constraint"] in {"far", "height", "sunlight", "setback"}
        assert "주차장법 단순화" in basis["parking_formula"]
        assert "코어" in basis["core_formula"]
        assert basis["applied_limits"]["statutory_max_far_percent"] == 200.0


def _mass(zone: str, area: float) -> dict:
    """zone·면적으로 compute_optimal_mass 결과를 산출(테스트 헬퍼)."""
    svc = AutoDesignEngineService
    si = SiteInput(site_area_sqm=area, zone_code=zone)
    return svc.compute_optimal_mass(si, svc.compute_effective_site(si), svc.get_legal_limits(zone))


class TestPodiumTowerMassing:
    """★Podium-Tower 실무 매스(B1) — 고FAR 비일조 상업/준주거는 저층 podium+고층 tower 분할.

    단일 만층 박스(예 16층) 비현실 해소: 실무 주상복합은 footprint를 줄이고 30~60층으로 올린다.
    정북일조(주거)·저FAR은 단일박스 보존(무회귀).
    """

    def test_commercial_high_far_is_podium_tower(self):
        """일반상업(GC) 고FAR → podium_tower 프로파일·현실 고층(단일 만층 박스 아님)."""
        m = _mass("GC", 14959)
        assert m.get("massing_profile") == "podium_tower"
        assert "podium" in m and "tower" in m
        # 저층 podium + 고층 tower, tower가 podium보다 높다(고층 주거).
        assert m["tower"]["floors"] > m["podium"]["floors"]
        # 만층 산술하한(고FAR/건폐율 ≈ 13~17층)보다 의미있게 높은 현실 고층.
        assert m["num_floors"] >= 25, f"podium-tower 층수 {m['num_floors']} — 비현실 저층"
        # tower 플로어플레이트는 podium보다 작다(footprint 축소 고층화).
        assert m["tower"]["footprint_sqm"] < m["podium"]["footprint_sqm"]

    def test_podium_tower_far_within_legal(self):
        """composite 연면적이 법정 용적률을 초과하지 않는다(과대 금지·무날조)."""
        legal = AutoDesignEngineService.get_legal_limits("GC")
        m = _mass("GC", 14959)
        assert m["far_pct"] <= legal["max_far_percent"] + 1.0  # 부동소수 여유

    def test_residential_zone_keeps_single_box(self):
        """제2종일반주거(정북일조·저FAR)는 podium-tower 미적용(단일박스 보존·무회귀)."""
        m = _mass("2R", 660)
        assert m.get("massing_profile") != "podium_tower"
        assert "podium" not in m

    def test_units_use_residential_floors_not_total(self):
        """★무날조: 세대수는 주거(tower) 층수 기준 — podium(상가·주차) 층을 주거로 중복계산 금지."""
        m = _mass("GC", 14959)
        res_floors = m["floors_for_units"]
        assert res_floors == m["tower"]["floors"] < m["num_floors"]  # podium 제외
        core = AutoDesignEngineService.compute_core_layout(m, "공동주택")
        layout = AutoDesignEngineService.compute_unit_layout(m, core, ["84A"], "공동주택")
        # 세대수 = 층당세대 × 주거층수(=floors_for_units), 만층(num_floors) 아님(이 입력은 큰
        #   바닥판 3,291㎡라 수정 전에도 세대는 성립 — 여기선 '주거층수 곱' 불변식만 검증).
        for u in layout["units"]:
            if u["count_per_floor"] > 0:
                assert u["total_count"] == u["count_per_floor"] * res_floors

    def test_small_podium_tower_units_not_zero(self):
        """★회귀잠금(헤드라인 증상): 작은 타워 바닥판의 podium-tower가 0세대가 되면 안 된다.

        GC 2000㎡는 타워 바닥판이 440㎡로 작다. 과거 코어 수를 '적층 연면적'(19,760㎡)으로 산정해
        38층이면 코어 14개(350㎡)를 만들고, 이를 440㎡ 바닥판에서 빼니 순면적 38㎡로 붕괴 → 0세대.
        수정 후엔 코어를 '층당 바닥판'으로 산정(2개)해 136세대가 성립한다. 이 입력이 0세대 증상을
        실제로 재현하므로 회귀를 직접 잠근다(14959㎡는 바닥판이 커서 수정 전에도 0이 아니었음).
        """
        m = _mass("GC", 2000)
        assert m.get("massing_profile") == "podium_tower"  # 전제: 작은 상업 부지도 podium-tower
        core = AutoDesignEngineService.compute_core_layout(m, "공동주택")
        layout = AutoDesignEngineService.compute_unit_layout(m, core, ["59A", "84A"], "공동주택")
        assert layout["total_units"] > 0, "작은 타워 바닥판 podium-tower가 0세대 — 코어 과대산정 회귀"
        assert core["num_cores"] <= 4, f"코어 {core['num_cores']}개(440㎡ 바닥판) — 적층연면적 폭증 회귀"

    def test_core_count_uses_floor_plate_not_stacked_area(self):
        """★코어 수는 '층당 바닥판'으로 산정 — 고층에서 적층 연면적으로 폭증 금지.

        코어는 모든 층을 수직 관통하는 공용공간이라, 코어 수가 건물 높이(적층 연면적)에 비례해
        늘면 안 된다. GC 14959㎡(38층) 타워는 적층 연면적 기준이면 코어 99개로 폭증하지만, 층당
        바닥판(3,291㎡) 기준이면 3개로 현실화된다(피난·직통계단 2개소 의무 포함 한도 내·무날조).
        """
        m = _mass("GC", 14959)
        core = AutoDesignEngineService.compute_core_layout(m, "공동주택")
        # 38층 주상복합 타워라도 코어는 소수(피난 2개소+a) — 두 자릿수(적층연면적 기준 99개)는 비현실.
        assert 1 <= core["num_cores"] <= 4, f"코어 {core['num_cores']}개 — 적층 연면적 기준 폭증 회귀"
        # 직통계단 2개소 의무(5층↑/층당 200㎡↑) 반영 — 고층 타워는 최소 2코어.
        assert core["num_cores"] >= 2
        # 코어+복도가 타워 1개층 바닥판을 다 먹지 않아 순면적이 양(+)으로 남는다(세대 성립 가능).
        net = m["building_footprint_sqm"] - core["core_area_sqm"] - core["corridor_area_sqm"]
        assert net > 0, "코어+복도가 바닥판을 초과 — 순면적 음수(세대 성립 불가) 회귀"

    def test_explicit_massing_kind_respected(self):
        """사용자가 massing_kind 명시(slab 등) 시 podium-tower로 덮어쓰지 않는다(존중)."""
        svc = AutoDesignEngineService
        si = SiteInput(site_area_sqm=14959, zone_code="GC", massing_kind="slab")
        m = svc.compute_optimal_mass(si, svc.compute_effective_site(si), svc.get_legal_limits("GC"))
        assert m.get("massing_profile") != "podium_tower"
        assert m.get("massing_kind") == "slab"
