"""침묵 폴백 정직화(P3) 회귀 테스트 — FAR 250%·공시지가 150만원/㎡ 가정치 표기.

배경(2026-07-15 수지·적산엔진 감사):
- `zone_limits.get("max_far_pct", 250)`: 용적률 상한 미확보 시 250% 가정치가 조용히
  들어가 FAR→GFA→세대수→매출→ROI 전 계단이 오염됨에도 어떤 표기도 없었다.
- `official_price_per_sqm or 1_500_000`: land_price_reliable 플래그는 있었으나
  표준 고지 문구가 없어 표시 표면이 문구를 자체 조립해야 했다.

봉합 계약(값 불변·표기 추가 — 무회귀):
1. 폴백 값 자체는 유지(랭킹 상대비교 유효) — 수치 회귀 0.
2. far_reliable / far_disclosure 신설(정답 기준선 = 같은 함수의 land_price_reliable·
   area_reliable/area_disclosure 관례 미러링).
3. land_price_disclosure 표준 문구 신설.
4. rough 오케스트레이터가 far 가정치를 degraded_notes로 정직 강등.
"""

from __future__ import annotations

import pytest

from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.land_intelligence import far_tier_service as far_tier_module
from app.services.land_intelligence import ordinance_service as ordinance_module
from app.services.zoning import auto_zoning_service as auto_zoning_module

pytestmark = pytest.mark.asyncio

ADDR = "서울특별시 강남구 역삼동 736"


def _zoning_result(*, with_far: bool = True, with_price: bool = True) -> dict:
    zone_limits = {"max_bcr_pct": 60}
    if with_far:
        zone_limits["max_far_pct"] = 250
    return {
        "zone_type": "제2종일반주거지역",
        "zone_limits": zone_limits,
        "land_area_sqm": 1000.0,
        "official_price_per_sqm": 3_000_000 if with_price else None,
        "special_districts": [],
        "land_category": "대",
    }


def _install_stubs(monkeypatch, zoning: dict, *, effective_far: float | None = 200.0):
    """AutoZoning·Ordinance·calc_effective_far 네트워크 차단 스텁."""

    async def _fake_analyze(self, address):
        return zoning

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):
        return {}

    def _fake_calc_effective_far(base, zone_type, land_area):
        if effective_far is None:
            raise RuntimeError("effective far unavailable")
        return {"effective_far_pct": effective_far, "effective_bcr_pct": 50.0, "far_basis": "테스트고정"}

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)
    monkeypatch.setattr(far_tier_module, "calc_effective_far", _fake_calc_effective_far)


# ─────────────────────────────────────────────────────────────────────────────
# 1) FAR 신뢰성 — 상한 확보 시 True·고지 없음(무회귀)
# ─────────────────────────────────────────────────────────────────────────────
async def test_far_reliable_when_zone_limits_present(monkeypatch):
    _install_stubs(monkeypatch, _zoning_result(with_far=True))
    out = await FeasibilityServiceV2().auto_recommend_top3(address=ADDR, land_area_sqm=1000.0, use_llm=False)
    assert out["far_reliable"] is True
    assert "far_disclosure" not in out
    assert out["recommendations"], "정상 경로 추천 산출(무회귀)"


# ─────────────────────────────────────────────────────────────────────────────
# 2) FAR 가정치 — 상한 미확보 시 False + 표준 고지, 값은 기존 폴백 유지
# ─────────────────────────────────────────────────────────────────────────────
async def test_far_fallback_disclosed(monkeypatch):
    # 실효 산정도 실패시켜 순수 250% 가정치 경로를 강제(폴백 값 무회귀 확인).
    _install_stubs(monkeypatch, _zoning_result(with_far=False), effective_far=None)
    out = await FeasibilityServiceV2().auto_recommend_top3(address=ADDR, land_area_sqm=1000.0, use_llm=False)
    assert out["far_reliable"] is False
    assert "250%" in out["far_disclosure"] and "가정치" in out["far_disclosure"]
    # 값 무회귀: 250 가정치가 그대로 라벨·산정에 사용(참고용 표기와 병행).
    assert out["legal_max_far_pct"] == 250
    assert out["recommendations"], "가정치 기반이어도 랭킹(상대비교)은 산출"


# ─────────────────────────────────────────────────────────────────────────────
# 3) 공시지가 가정단가 — 표준 고지 문구 신설(플래그는 기존 유지)
# ─────────────────────────────────────────────────────────────────────────────
async def test_land_price_fallback_disclosed(monkeypatch):
    _install_stubs(monkeypatch, _zoning_result(with_price=False))
    out = await FeasibilityServiceV2().auto_recommend_top3(address=ADDR, land_area_sqm=1000.0, use_llm=False)
    assert out["land_price_reliable"] is False
    assert "150만원" in out["land_price_disclosure"] and "참고용" in out["land_price_disclosure"]
    # 값 무회귀: ModuleInput에는 기존 1.5M 가정단가 그대로.
    assert out["recommendations"][0]["input_used"].official_price_per_sqm == 1_500_000


async def test_land_price_reliable_no_disclosure(monkeypatch):
    _install_stubs(monkeypatch, _zoning_result(with_price=True))
    out = await FeasibilityServiceV2().auto_recommend_top3(address=ADDR, land_area_sqm=1000.0, use_llm=False)
    assert out["land_price_reliable"] is True
    assert "land_price_disclosure" not in out


# ─────────────────────────────────────────────────────────────────────────────
# 4) rough 오케스트레이터 — far 가정치를 degraded_notes로 정직 강등
# ─────────────────────────────────────────────────────────────────────────────
async def test_rough_degrades_far_fallback(monkeypatch):
    from app.services.feasibility import rough_feasibility_orchestrator as orch

    _install_stubs(monkeypatch, _zoning_result(with_far=False), effective_far=None)

    async def _fake_recommend(self, **kwargs):
        # auto_recommend 결과 최소 형상 — far_reliable=False + 고지 포함.
        svc = FeasibilityServiceV2()
        inp = svc.build_module_input(
            dev_type="M06", site_area_sqm=1000.0, max_far_pct=250.0,
            region="서울", address=ADDR, equity_won=None, official_price_per_sqm=3_000_000,
        )
        rec = {"development_type": "M06", "type_name": "일반분양",
               "input_used": inp, "composite_score": 80.0}
        return {
            "address": ADDR, "zone_type": "제2종일반주거지역",
            "land_area_sqm": 1000.0, "effective_far_pct": 250.0,
            "recommendations": [rec], "all_results": [rec],
            "land_price_reliable": True, "area_reliable": True,
            "far_reliable": False,
            "far_disclosure": "용도지역 용적률 상한 미확보 — 250% 가정치 기준 산정(참고용).",
            "scenario_status": "actual",
        }

    monkeypatch.setattr(orch.FeasibilityServiceV2, "auto_recommend_top3", _fake_recommend)
    monkeypatch.setattr(orch, "_service", orch.FeasibilityServiceV2())

    async def _fake_integrated(parcels):
        return {"total_area_sqm": 1000.0, "dominant_zone": "제2종일반주거지역", "parcel_count": 1}

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)

    async def _fake_desk(**kwargs):
        return {"ok": False}

    monkeypatch.setattr(orch, "desk_appraisal", _fake_desk)

    out = await orch.build_rough_scenario(address=ADDR)
    assert any("250% 가정치" in n for n in out["degraded_notes"]), out["degraded_notes"]
