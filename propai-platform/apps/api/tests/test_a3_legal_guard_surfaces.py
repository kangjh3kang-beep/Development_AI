"""★A-3(배선 P1 — 법정초과 경량 가드 확산·G8) 표면별 배선 회귀 테스트.

comprehensive_analysis_service.analyze()의 P0-3 핫패스 가드(check_against_legal)가
hotpath_guard.apply_legal_hotpath_guard로 공용화된 뒤, 아래 4개 표면에 additive로
확산 배선되었는지 검증한다(각 표면: 오염값 주입 → integrity_warnings 존재,
정상값 → 부재/빈 배열).

  1) rough_feasibility_orchestrator.build_rough_scenario — effective_far 사용부
  2) precheck_service.run_instant_precheck — 실효율 카드(legal_limits.applied_*_pct)
  3) routers/auto_zoning.analyze_zoning (/zoning/analyze) — effective_far_tier
  4) routers/auto_zoning.integrated_analysis (/zoning/integrated-analysis) — blended 실효율

무네트워크·무행: 각 표면의 외부 호출(AutoZoningService·OrdinanceService·
SiteAnalysisInterpreter·FeasibilityServiceV2.auto_recommend_top3 등)은 monkeypatch로
대역한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# 1) rough_feasibility_orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def test_rough_orchestrator_flags_legal_excess(monkeypatch):
    from app.services.feasibility import rough_feasibility_orchestrator as orch

    async def _fake_integrated(parcels):
        return None

    async def _fake_auto(**kwargs):
        return {
            "address": "경기도 용인시 처인구 어딘가", "zone_type": "자연녹지지역",
            "land_area_sqm": 1000.0, "effective_far_pct": 139.6,  # 자연녹지 법정100% 초과(근거없음)
            "recommendations": [], "all_results": [],
            "honest_disclosure": "특이부지 등으로 후보 미생성.",
        }

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="경기도 용인시 처인구 어딘가")
    assert out["integrity_warnings"], "법정초과(자연녹지 139.6%)가 적발되지 않음"
    assert any(i["severity"] == "high" for i in out["integrity_warnings"])


async def test_rough_orchestrator_no_warning_within_legal_limit(monkeypatch):
    from app.services.feasibility import rough_feasibility_orchestrator as orch

    async def _fake_integrated(parcels):
        return None

    async def _fake_auto(**kwargs):
        return {
            "address": "경기도 용인시 처인구 어딘가", "zone_type": "자연녹지지역",
            "land_area_sqm": 1000.0, "effective_far_pct": 80.0,  # 법정 100% 이내
            "recommendations": [], "all_results": [],
            "honest_disclosure": "특이부지 등으로 후보 미생성.",
        }

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)

    out = await orch.build_rough_scenario(address="경기도 용인시 처인구 어딘가")
    assert out["integrity_warnings"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 2) precheck_service.run_instant_precheck
# ─────────────────────────────────────────────────────────────────────────────

def _precheck_stub_zoning(monkeypatch):
    import app.services.precheck.precheck_service as svc

    async def _fake_analyze(self, address):
        return {
            "zone_type": "자연녹지지역", "pnu": "4146025021100010000",
            "land_area_sqm": 1000.0, "land_category": "대",
            "special_districts": [], "official_price_per_sqm": 1_000_000,
        }

    monkeypatch.setattr(svc.AutoZoningService, "analyze_by_address", _fake_analyze, raising=True)
    return svc


async def test_precheck_flags_legal_excess(monkeypatch):
    svc = _precheck_stub_zoning(monkeypatch)

    async def _fake_legal_limits(zone_type, address=None, pnu=None):
        return {
            "bcr_pct": 20, "far_pct": 100, "height_m": None,
            "source": "국토의 계획 및 이용에 관한 법률 제78조", "zone_type": "자연녹지지역",
            "applied_bcr_pct": 35.8, "applied_far_pct": 139.6,  # 실효율 카드 — 근거없는 초과
            "ordinance_confirmed": False,
        }

    monkeypatch.setattr(svc, "_legal_limits", _fake_legal_limits)

    resp = await svc.run_instant_precheck(address="경기도 용인시 처인구 어딘가")
    assert resp["ok"] is True
    assert resp["integrity_warnings"], "법정초과(자연녹지 139.6%)가 적발되지 않음"
    assert any(i["severity"] == "high" for i in resp["integrity_warnings"])
    # 값은 클램프하지 않음(무날조) — legal_limits.applied_far_pct 그대로.
    assert resp["legal_limits"]["applied_far_pct"] == 139.6
    assert resp["legal_limits"]["confidence"] == "degraded"


async def test_precheck_no_warning_within_legal_limit(monkeypatch):
    svc = _precheck_stub_zoning(monkeypatch)

    async def _fake_legal_limits(zone_type, address=None, pnu=None):
        return {
            "bcr_pct": 20, "far_pct": 100, "height_m": None,
            "source": "국토의 계획 및 이용에 관한 법률 제78조", "zone_type": "자연녹지지역",
            "applied_bcr_pct": 20.0, "applied_far_pct": 100.0,  # 법정 이내
            "ordinance_confirmed": False,
        }

    monkeypatch.setattr(svc, "_legal_limits", _fake_legal_limits)

    resp = await svc.run_instant_precheck(address="경기도 용인시 처인구 어딘가")
    assert resp["ok"] is True
    assert resp["integrity_warnings"] == []
    assert "confidence" not in resp["legal_limits"]


# ─────────────────────────────────────────────────────────────────────────────
# 3) routers/auto_zoning.analyze_zoning (/zoning/analyze)
# ─────────────────────────────────────────────────────────────────────────────

async def test_zoning_analyze_flags_legal_excess(monkeypatch):
    import apps.api.routers.auto_zoning as az
    from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
    from app.services.land_intelligence import far_tier_service
    from app.services.land_intelligence.ordinance_service import OrdinanceService

    async def _fake_analyze(self, address):
        return {
            "address": address, "pnu": "4146025021100010000",
            "zone_type": "자연녹지지역",
            "zone_limits": {"max_bcr_pct": 20, "max_far_pct": 100,
                            "legal_basis": "국토의 계획 및 이용에 관한 법률 제78조"},
            "land_area_sqm": 1000.0, "land_category": "대",
            "official_price_per_sqm": 1_000_000, "special_districts": [], "warnings": [],
        }

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):
        return {}  # 조례 미확인(법정상한 폴백) — 무근거 초과 시나리오 유지

    def _fake_calc_effective_far(base, zone_type, land_area):
        return {"effective_far_pct": 139.6, "effective_bcr_pct": 35.8, "far_basis": None}

    def _fake_calc_upzoning(base, zone_type, land_area, a, b):
        return {}

    async def _fake_interp(self, data):
        return {}  # LLM 무호출(무네트워크) — 구조화 결과만 검증

    monkeypatch.setattr(az.AutoZoningService, "analyze_by_address", _fake_analyze, raising=True)
    monkeypatch.setattr(OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True)
    monkeypatch.setattr(far_tier_service, "calc_effective_far", _fake_calc_effective_far)
    monkeypatch.setattr(far_tier_service, "calc_upzoning", _fake_calc_upzoning)
    monkeypatch.setattr(SiteAnalysisInterpreter, "generate_interpretation", _fake_interp, raising=True)

    req = az.ZoningAnalyzeRequest(address="경기도 용인시 처인구 어딘가")
    result = await az.analyze_zoning(req)

    assert result.get("integrity_warnings"), "법정초과(자연녹지 139.6%)가 적발되지 않음"
    assert any(i["severity"] == "high" for i in result["integrity_warnings"])


# ─────────────────────────────────────────────────────────────────────────────
# 4) routers/auto_zoning.integrated_analysis (/zoning/integrated-analysis)
# ─────────────────────────────────────────────────────────────────────────────

async def test_integrated_analysis_flags_legal_excess(monkeypatch):
    import apps.api.routers.auto_zoning as az
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
    from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

    async def _passthrough_enrich(self, items, with_building=True):
        return [dict(p) for p in items]

    async def _noop_enrich_effective(enriched):
        return None

    async def _fake_top3(self, **kwargs):
        return {"recommendations": [], "all_results": []}

    monkeypatch.setattr(ParcelExcelService, "enrich_parcel_list", _passthrough_enrich)
    monkeypatch.setattr(az, "_enrich_effective_and_special", _noop_enrich_effective)
    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)

    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 1000, "_far_eff": 139.6, "_bcr_eff": 35.8,
         "_far_legal": 100, "_bcr_legal": 20, "_far_basis": None},
        {"pnu": "P-B", "address": "B", "land_category": "대", "zone_type": "자연녹지지역",
         "area_sqm": 1000, "_far_eff": 139.6, "_bcr_eff": 35.8,
         "_far_legal": 100, "_bcr_legal": 20, "_far_basis": None},
    ]
    req = az.IntegratedAnalysisRequest(parcels=parcels, use_llm=False)
    result = await az.integrated_analysis(req)

    assert result.get("integrity_warnings"), "통합(면적가중) 법정초과가 적발되지 않음"
    assert any(i["severity"] == "high" for i in result["integrity_warnings"])
    # 값은 그대로(무날조) — blended_far_eff_pct는 클램프되지 않는다.
    assert result["integrated"]["blended_far_eff_pct"] == 139.6


# ─────────────────────────────────────────────────────────────────────────────
# ★QA MEDIUM 수정 회귀 — 혼합 용도지역 블렌드를 dominant 단일 zone 법정상한과 비교하면
# 정당한 혼합 부지도 오탐(false "high")한다. legal_far_pct/legal_bcr_pct override(같은
# 면적가중 법정 블렌드와 비교)로 오탐은 사라지고 진짜 오염은 여전히 검출되는지 검증한다.
# ─────────────────────────────────────────────────────────────────────────────

async def _run_integrated_analysis(monkeypatch, parcels):
    import apps.api.routers.auto_zoning as az
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
    from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

    async def _passthrough_enrich(self, items, with_building=True):
        return [dict(p) for p in items]

    async def _noop_enrich_effective(enriched):
        return None

    async def _fake_top3(self, **kwargs):
        return {"recommendations": [], "all_results": []}

    monkeypatch.setattr(ParcelExcelService, "enrich_parcel_list", _passthrough_enrich)
    monkeypatch.setattr(az, "_enrich_effective_and_special", _noop_enrich_effective)
    monkeypatch.setattr(FeasibilityServiceV2, "auto_recommend_top3", _fake_top3)

    req = az.IntegratedAnalysisRequest(parcels=parcels, use_llm=False)
    return await az.integrated_analysis(req)


async def test_integrated_analysis_mixed_zone_no_false_positive(monkeypatch):
    """정당한 혼합 용도지역 블렌드 — 각 필지는 자기 zone 법정상한 이내(초과 없음)이나,
    면적가중 블렌드(291.7%)는 dominant(제2종일반주거지역, 법정 250%) 단일 상한을 넘는다.
    dominant 단일 상한과 비교하면 오탐(false "high")하지만, 같은 면적가중 법정 블렌드
    (blended_far_legal_pct)와 비교하면 eff블렌드==legal블렌드라 초과가 아니다(오탐 없음).

    제2종일반주거지역(법정 far 250%) 1000㎡ + 준주거지역(법정 far 500%) 200㎡:
      blended_far_eff = blended_far_legal = (1000*250+200*500)/1200 = 291.7%(반올림)
      dominant(제2종일반주거지역) 단일 법정상한 250% < 291.7% → 구법(단일zone 비교)이면 오탐.
    """
    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대", "zone_type": "제2종일반주거지역",
         "area_sqm": 1000, "_far_eff": 250, "_bcr_eff": 60,
         "_far_legal": 250, "_bcr_legal": 60, "_far_basis": None},
        {"pnu": "P-B", "address": "B", "land_category": "대", "zone_type": "준주거지역",
         "area_sqm": 200, "_far_eff": 500, "_bcr_eff": 70,
         "_far_legal": 500, "_bcr_legal": 70, "_far_basis": None},
    ]
    result = await _run_integrated_analysis(monkeypatch, parcels)

    assert result["dominant_zone"] == "제2종일반주거지역"
    assert result["integrated"]["blended_far_eff_pct"] == 291.7
    assert result["integrated"]["blended_far_legal_pct"] == 291.7
    assert result.get("integrity_warnings") == [], (
        "정당한 혼합용도 블렌드(eff==legal 블렌드)가 dominant 단일 상한 비교로 오탐됨"
    )
    assert "confidence" not in result["integrated"]


async def test_integrated_analysis_mixed_zone_still_flags_real_contamination(monkeypatch):
    """블렌드 override 적용 후에도 진짜 오염(eff블렌드>legal블렌드)은 여전히 검출된다.

    준주거 필지의 실효 용적률이 자기 zone 법정상한(500%)마저 초과한 700%로 오염된 경우:
      blended_far_eff = (1000*250+200*700)/1200 = 325.0%
      blended_far_legal = (1000*250+200*500)/1200 = 291.7%
      325.0 > 291.7(+0.5 허용) → 법정 블렌드 기준으로도 여전히 초과 검출(늑대소년 아님).
    """
    parcels = [
        {"pnu": "P-A", "address": "A", "land_category": "대", "zone_type": "제2종일반주거지역",
         "area_sqm": 1000, "_far_eff": 250, "_bcr_eff": 60,
         "_far_legal": 250, "_bcr_legal": 60, "_far_basis": None},
        {"pnu": "P-B", "address": "B", "land_category": "대", "zone_type": "준주거지역",
         "area_sqm": 200, "_far_eff": 700, "_bcr_eff": 70,  # 자기 zone 법정(500%)마저 초과(오염)
         "_far_legal": 500, "_bcr_legal": 70, "_far_basis": None},
    ]
    result = await _run_integrated_analysis(monkeypatch, parcels)

    assert result["integrated"]["blended_far_eff_pct"] == 325.0
    assert result["integrated"]["blended_far_legal_pct"] == 291.7
    assert result.get("integrity_warnings"), "진짜 오염(eff블렌드>legal블렌드)이 적발되지 않음"
    assert any(i["severity"] == "high" for i in result["integrity_warnings"])
    assert result["integrated"]["confidence"] == "degraded"
