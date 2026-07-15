"""적산→수지 배선(P2) 회귀 테스트 — 공용 개산식 SSOT(overview_estimator).

배경(2026-07-15 수지·적산엔진 감사):
- 수지 공사비 = 순수 `연면적 × ₩/㎡`(구조유형·지하할증·조경 무반영),
  적산 estimate-overview = 자체 인라인 산식(구조계수+지하 30% 할증+조경 1.5%)
  → 같은 프로젝트의 공사비가 두 모듈에서 갈라짐(단절).
- QTO 총액은 골조 8공종만 커버해 시장 도급가의 ~1/3(실측) — 총액 기저로 쓰면
  ROI 날조 과대라 채택하지 않음(사용자 결정: 공용 개산식 봉합).

봉합 계약:
1. 공용 함수는 종전 라우터 인라인 산식과 byte 동일(연산 순서·int 절사 포함).
2. 수지 엔진: 층수·구조 미제공 시 종전 결과와 완전 동일(무회귀).
3. 층수·구조 제공 시 적산과 동일 산식으로 정밀화(분해·근거 포함).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.cost import router as cost_router
from app.services.auth.auth_service import get_current_user
from app.services.cost.overview_estimator import (
    STRUCT_COST_FACTOR,
    estimate_overview_direct_cost,
    split_gfa_below,
)
from app.services.feasibility.construction_cost_engine import (
    calculate_indirect_cost,
    calculate_total_construction_cost,
)
from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.modules.common.cost_blocks import compute_construction_cost


def _legacy_inline_direct(
    gfa: float, base_unit: float, structure_type: str,
    fa: int, fb: int, factor: float,
) -> dict[str, int]:
    """봉합 전 routers/cost.py estimate-overview의 인라인 산식 복제(회귀 기준선)."""
    unit = base_unit * STRUCT_COST_FACTOR.get(structure_type, 1.0)
    _fa, _fb, _bk = max(1, fa), max(0, fb), 1.2
    gfa_below = (gfa * (_fb * _bk) / (_fa + _fb * _bk)) if _fb > 0 else 0.0
    gfa_above = max(0.0, gfa - gfa_below)
    u = int(unit * factor)
    above = int(gfa_above * u)
    below = int(gfa_below * u * 1.3)
    landscape = int((above + below) * 0.015)
    return {"u": u, "above": above, "below": below,
            "landscape": landscape, "direct": above + below + landscape}


# ─────────────────────────────────────────────────────────────────────────────
# 1) 공용 함수 = 종전 인라인 산식 (byte 호환)
# ─────────────────────────────────────────────────────────────────────────────
class TestHelperMatchesLegacy:
    def test_all_scenarios_and_structures(self):
        cases = [
            (10_000.0, 2_400_000, "RC", 20, 2),
            (10_000.0, 2_400_000, "SRC", 35, 5),
            (8_000.0, 2_600_000, "철골", 15, 0),
            (3_000.0, 2_200_000, "목구조", 5, 1),
            (5_000.0, 2_400_000, "미등록구조", 10, 3),  # 미등록 → 1.0
        ]
        for gfa, base, st, fa, fb in cases:
            for factor in (0.92, 1.0, 1.12):
                legacy = _legacy_inline_direct(gfa, base, st, fa, fb, factor)
                ov = estimate_overview_direct_cost(
                    total_gfa_sqm=gfa, base_unit_cost_per_sqm=base,
                    structure_type=st, floor_count_above=fa,
                    floor_count_below=fb, scenario_factor=factor,
                )
                key = f"{st}/{fa}F/B{fb}/x{factor}"
                assert ov["unit_cost_per_sqm"] == legacy["u"], key
                assert ov["aboveground_won"] == legacy["above"], key
                assert ov["underground_won"] == legacy["below"], key
                assert ov["landscape_won"] == legacy["landscape"], key
                assert ov["direct_won"] == legacy["direct"], key

    def test_split_gfa_below_zero_basement(self):
        above, below = split_gfa_below(10_000.0, 20, 0)
        assert above == 10_000.0 and below == 0.0

    def test_hardcoded_golden_pin(self):
        """리뷰 R1-P3①: 계수표 드리프트 감지용 절대값 핀 — SSOT 계수가 바뀌면 여기서 터진다.

        (양변이 같은 STRUCT_COST_FACTOR를 참조하는 복제 대조는 계수 '값' 변경을 못 잡는다.
         SRC=1.15·지하할증 1.3·조경 1.5% 기준 수기 검산 원화를 고정.)
        """
        ov = estimate_overview_direct_cost(
            total_gfa_sqm=10_000.0, base_unit_cost_per_sqm=2_400_000,
            structure_type="SRC", floor_count_above=20, floor_count_below=2,
        )
        # u = int(2,400,000 × 1.15) = 2,760,000 / 지하 = 10,000×2.4/22.4 = 1,071.428…㎡
        assert ov["unit_cost_per_sqm"] == 2_760_000
        assert ov["aboveground_won"] == 24_642_857_142_857 // 1_000  # int(8,928.571…×2,760,000)
        assert ov["underground_won"] == int(10_000.0 * 2.4 / 22.4 * 2_760_000 * 1.3)
        assert ov["landscape_won"] == int((ov["aboveground_won"] + ov["underground_won"]) * 0.015)

    def test_basement_only_is_deferred(self):
        """리뷰 R1-P2: 지상층수 미상 + 지하만 제공 → 지하 분해 보류(과대계상 뇌관 차단)."""
        result = calculate_total_construction_cost(
            total_gfa_sqm=10_000.0, building_type="apartment", floor_count_below=3,
        )
        flat = int(10_000.0 * 2_400_000)
        # 지하 분해 없이 조경 1.5%만(구조 RC=1.0) — fa=1 폴백으로 지하 78% 배분되면 실패
        assert result["direct"]["total_direct_cost_won"] == flat + int(flat * 0.015)


# ─────────────────────────────────────────────────────────────────────────────
# 2) 수지 엔진 무회귀 — 채널 미제공 시 종전 `연면적 × ₩/㎡` 그대로
# ─────────────────────────────────────────────────────────────────────────────
class TestEngineBackwardCompat:
    def test_flat_path_unchanged(self):
        result = calculate_total_construction_cost(
            total_gfa_sqm=10_000.0, building_type="apartment",
        )
        direct = result["direct"]
        assert direct["total_direct_cost_won"] == int(10_000.0 * 2_400_000)
        assert "overview_breakdown" not in direct  # 정밀 경로 미발동
        # 간접비 15%(설계4+감리3+예비5+일반관리3)
        assert result["total_construction_cost_won"] == (
            direct["total_direct_cost_won"]
            + calculate_indirect_cost(direct_cost_won=direct["total_direct_cost_won"])["total_indirect_cost_won"]
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3) 수지 엔진 정밀 경로 — 적산과 동일 산식
# ─────────────────────────────────────────────────────────────────────────────
class TestEnginePrecisionPath:
    def test_basement_and_structure_applied(self):
        result = calculate_total_construction_cost(
            total_gfa_sqm=10_000.0, building_type="apartment",
            floor_count_above=20, floor_count_below=2, structure_type="SRC",
        )
        direct = result["direct"]
        legacy = _legacy_inline_direct(10_000.0, 2_400_000, "SRC", 20, 2, 1.0)
        assert direct["total_direct_cost_won"] == legacy["direct"]
        assert direct["overview_breakdown"]["underground_won"] == legacy["below"]
        assert "공용 개산식" in direct["basis"]

    def test_floors_only_no_basement_adds_landscape(self):
        """지상층수만 제공(지하 0) — 조경 1.5%만 가산(적산과 동일)."""
        result = calculate_total_construction_cost(
            total_gfa_sqm=10_000.0, building_type="apartment", floor_count_above=15,
        )
        flat = int(10_000.0 * 2_400_000)
        assert result["direct"]["total_direct_cost_won"] == flat + int(flat * 0.015)


# ─────────────────────────────────────────────────────────────────────────────
# 4) cost_blocks 채널 — ModuleInput.floors / params
# ─────────────────────────────────────────────────────────────────────────────
class TestCostBlocksChannels:
    def _inp(self, **overrides) -> ModuleInput:
        kwargs = dict(
            development_type="M06", total_land_area_sqm=2_000.0,
            official_price_per_sqm=3_000_000, total_gfa_sqm=10_000.0,
            building_type="apartment",
        )
        kwargs.update(overrides)
        return ModuleInput(**kwargs)

    def test_no_channels_flat_path(self):
        c = compute_construction_cost(self._inp())
        assert c["direct"]["total_direct_cost_won"] == int(10_000.0 * 2_400_000)
        assert "overview_breakdown" not in c["direct"]

    def test_params_channels_activate_precision(self):
        c = compute_construction_cost(self._inp(params={
            "floor_count_above": 20, "floor_count_below": 2, "structure_type": "SRC",
        }))
        legacy = _legacy_inline_direct(10_000.0, 2_400_000, "SRC", 20, 2, 1.0)
        assert c["direct"]["total_direct_cost_won"] == legacy["direct"]

    def test_module_input_floors_field(self):
        c = compute_construction_cost(self._inp(floors=15))
        flat = int(10_000.0 * 2_400_000)
        assert c["direct"]["total_direct_cost_won"] == flat + int(flat * 0.015)

    def test_override_still_wins(self):
        """정밀 채널과 무관하게 construction_cost_override_won이 최우선(기존 계약)."""
        c = compute_construction_cost(self._inp(params={
            "construction_cost_override_won": 77_000_000_000, "floor_count_below": 2,
        }))
        assert c["total_construction_cost_won"] == 77_000_000_000
        assert c["source"] == "cost_analysis_override"


# ─────────────────────────────────────────────────────────────────────────────
# 5) 적산 라우터 — 리팩토링 후 응답이 종전 산식과 동일
# ─────────────────────────────────────────────────────────────────────────────
class _User:
    id = "00000000-0000-0000-0000-000000000001"
    tenant_id = "00000000-0000-0000-0000-000000000002"
    role = "user"
    is_active = True


_app = FastAPI()
_app.include_router(cost_router)
_app.dependency_overrides[get_current_user] = lambda: _User()
_client = TestClient(_app)


class TestRouterByteCompat:
    def test_estimate_overview_totals_match_legacy(self):
        resp = _client.post("/api/v1/cost/estimate-overview", json={
            "building_type": "apartment", "structure_type": "SRC",
            "total_gfa_sqm": 10_000.0, "floor_count_above": 20, "floor_count_below": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        legacy = _legacy_inline_direct(10_000.0, 2_400_000, "SRC", 20, 2, 1.0)
        expected = data.get("expected", data)
        assert expected["direct_won"] == legacy["direct"]
        assert expected["underground_won"] == legacy["below"]
        ind = calculate_indirect_cost(direct_cost_won=legacy["direct"])
        assert expected["total_won"] == legacy["direct"] + ind["total_indirect_cost_won"]
