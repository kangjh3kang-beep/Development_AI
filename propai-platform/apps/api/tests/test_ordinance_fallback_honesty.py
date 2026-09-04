"""조례 폴백 confirmed 승격 정직화 회귀앵커 — 라이브 결함(2026-07-22, live-fix①).

라이브 그라운드 트루스(용인시 수지구 신봉동 56-19·자연녹지): /zoning/comprehensive에서
조례가 미해석(ordinance_service 3차 폴백 source="법정상한")되면, 법정상한 폴백값(100%)이
`far_basis_detail.조례값`에 `{far_pct: 100, confirmed: true}`로 승격되고
`zone_limits.ordinance_far_pct`도 채워져 프론트가 "② 조례 적용(지자체)" 카드를 확정(초록)
스타일로 오표시했다.

근본원인: land_info_service._collect_comprehensive_impl Phase 3가
ordinance_result["effective_far"/"effective_bcr"](법정상한 폴백에서도 항상 채워지는 값)를
source 확인 없이 무조건 zone_limits.ordinance_*_pct에 얹었다. 이 키를
legal_zone_limits._extract_ordinance_far의 zone_limits 형태(경로 2)가 "명시적 조례 신호"로
오인해 confirmed=True로 승격시켰다.

수정: (1) land_info_service — ordinance_result.source가 확정 조례 출처(_is_confirmed_
ordinance_source)일 때만 zone_limits.ordinance_*_pct를 채운다. (2) legal_zone_limits.
_extract_ordinance_far 경로2(zone_limits 형태) — 같은 zone_limits에 실린
ordinance_source가 폴백을 정직 고지하면(생산자가 실수로 값을 얹어도) 재차 걸러낸다
(공용 SSOT 게이트 — 전역 방어).

외부 API/네트워크 없이 monkeypatch 스텁으로 결정론 검증한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.land_intelligence.land_info_service import LandInfoService  # noqa: E402
from app.services.zoning.legal_zone_limits import _extract_ordinance_far  # noqa: E402


def _stub_land_service(monkeypatch, *, ordinance_result: dict):
    """LandInfoService의 외부 의존을 전부 스텁(네트워크 0회) — 용인시 수지구 자연녹지 시나리오."""
    svc = LandInfoService()

    async def _zoning(addr):
        return {
            "pnu": "PARITY-PNU-0001",
            "coordinates": {"lat": 37.3, "lng": 127.1},
            "zone_type": "자연녹지지역",
            "zone_source": "vworld_land_info",
            "zone_limits": {"max_bcr_pct": 20, "max_far_pct": 100},
            "special_districts": [],
            "warnings": [],
            "land_area_sqm": 500.0,
        }

    async def _none(*a, **k):
        return None

    async def _land_use(pnu):
        return []

    async def _ordinance(addr, zone, force_refresh=False, pnu=None, resolved_sigungu=None):
        return dict(ordinance_result)

    monkeypatch.setattr(svc.zoning, "analyze_by_address", _zoning)
    monkeypatch.setattr(svc, "_fetch_land_register", _none)
    monkeypatch.setattr(svc, "_fetch_land_use_plan", _land_use)
    monkeypatch.setattr(svc, "_fetch_official_price", _none)
    monkeypatch.setattr(svc, "_fetch_building_info", _none)
    monkeypatch.setattr(svc, "_fetch_land_characteristics", _none)
    monkeypatch.setattr(svc, "_fetch_building_detail", _none)
    monkeypatch.setattr(svc, "_fetch_nearby_transactions", _none)
    monkeypatch.setattr(svc, "_fetch_precise_road_width", _none)
    monkeypatch.setattr(svc, "_fetch_infrastructure", _none)
    monkeypatch.setattr(svc.ordinance, "get_ordinance_limits", _ordinance)
    return svc


# ── ① 조례 미해석 폴백 → confirmed 승격 금지(핵심 회귀: 용인 자연녹지) ──────────────

@pytest.mark.asyncio
async def test_statutory_fallback_not_promoted_to_confirmed(monkeypatch):
    """ordinance_service 3차 폴백(source='법정상한')이 조례확정으로 둔갑하지 않는다."""
    svc = _stub_land_service(
        monkeypatch,
        ordinance_result={
            "sido": "경기도", "sigungu": "용인시", "zone_type": "자연녹지지역",
            "national_bcr": 20.0, "national_far": 100.0,
            "ordinance_bcr": None, "ordinance_far": None,
            "effective_bcr": 20.0, "effective_far": 100.0,
            "source": "법정상한",
            "legal_basis": "국토의 계획 및 이용에 관한 법률 시행령 제84조, 제85조",
            "provenance": {"confidence": 0.60, "recheck_recommended": True},
        },
    )
    res = await svc._collect_comprehensive_impl("용인시 수지구 신봉동 56-19", pnu="PARITY-PNU-0001")

    # ★핵심 회귀: zone_limits에 폴백값이 '조례 확정' 신호(ordinance_*_pct)로 새지 않는다.
    zl = res["zone_limits"]
    assert "ordinance_far_pct" not in zl
    assert "ordinance_bcr_pct" not in zl
    assert zl["ordinance_source"] == "법정상한"  # 폴백 사실 자체는 정직 표기 유지

    eff = res["effective_far"]
    assert eff["ordinance_confirmed"] is False
    assert eff["far_basis_detail"]["조례값"] is None
    assert eff["far_basis_detail"]["조례확인필요"] is True
    # far_basis는 "조례 적용값"을 참칭하지 않는다(자연녹지는 구조상한(건폐×층수)이 최종
    # 근거로 덮어써 "구조상한(건폐율×층수)"가 되지만, 그 이전 계층에서도 조례 확정 문구는 없다).
    assert "조례 적용값" not in eff["far_basis"]
    assert eff["far_basis"] == "구조상한(건폐율×층수)"
    # 하류 오염 없음(구조상한 80%가 min으로 최종 실효를 누른다 — 수치는 그대로 정확).
    assert eff["effective_far_pct"] == 80.0


# ── ② 조례 실해석 시 confirmed=true 유지(과다강등 금지) ──────────────────────────

@pytest.mark.asyncio
async def test_real_ordinance_stays_confirmed(monkeypatch):
    """정적캐시/법제처API로 실제 조례가 확인되면 confirmed=True·수치 그대로 노출."""
    svc = _stub_land_service(
        monkeypatch,
        ordinance_result={
            "sido": "서울특별시", "sigungu": "서울특별시", "zone_type": "자연녹지지역",
            "national_bcr": 20.0, "national_far": 100.0,
            "ordinance_bcr": 20.0, "ordinance_far": 50.0,
            "effective_bcr": 20.0, "effective_far": 50.0,
            "source": "지자체 조례(정적캐시)",
            "legal_basis": "서울특별시 도시계획 조례",
        },
    )
    res = await svc._collect_comprehensive_impl("서울특별시 종로구 1-1", pnu="PARITY-PNU-0001")

    zl = res["zone_limits"]
    assert zl["ordinance_far_pct"] == 50.0
    assert zl["ordinance_bcr_pct"] == 20.0

    eff = res["effective_far"]
    assert eff["ordinance_confirmed"] is True
    assert eff["far_basis_detail"]["조례값"] is not None
    assert eff["far_basis_detail"]["조례값"]["far_pct"] == 50.0
    assert eff["far_basis_detail"]["조례값"]["confirmed"] is True


# ── ③ 공용 SSOT 게이트(legal_zone_limits._extract_ordinance_far) 단위 회귀 ────────

def test_extract_ordinance_far_zone_limits_dishonest_fallback_rejected():
    """생산자가 실수로 폴백값을 ordinance_*_pct에 얹어도, 같은 payload의 ordinance_source가
    폴백('법정상한')을 정직 고지하면 조례값으로 채택하지 않는다(전역 방어 게이트)."""
    r = _extract_ordinance_far({
        "zone_limits": {"ordinance_far_pct": 100, "ordinance_bcr_pct": 20, "ordinance_source": "법정상한"},
    })
    assert r["ord_far"] is None
    assert r["ord_bcr"] is None


def test_extract_ordinance_far_zone_limits_confirmed_source_accepted():
    """ordinance_source가 확정 조례 출처면 zone_limits 형태 명시 키를 그대로 채택(무회귀)."""
    r = _extract_ordinance_far({
        "zone_limits": {"ordinance_far_pct": 50, "ordinance_bcr_pct": 20, "ordinance_source": "지자체 조례(정적캐시)"},
    })
    assert r["ord_far"] == 50.0
    assert r["ord_bcr"] == 20.0


def test_extract_ordinance_far_zone_limits_no_source_key_backward_compat():
    """ordinance_source 키 자체가 없는 구버전 페이로드는 기존 계약대로 명시 키를 신뢰한다."""
    r = _extract_ordinance_far({"zone_limits": {"ordinance_far_pct": 50}})
    assert r["ord_far"] == 50.0
