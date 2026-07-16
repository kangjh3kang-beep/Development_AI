"""/regulations 워크플로우 배선 검증 — WP-R1(실효FAR)·R2(법규링크)·R3(구획도 parity).

라이브 지적(용인 신봉동 자연녹지)의 회귀를 잠근다:
- 자연녹지 실효 용적률은 법정 100%가 아니라 구조상한 80%(건폐20%×4층)여야 한다.
- 상위법령 §77/§78·개별 규제 지역지구별 법령칩·높이 4층 근거칩이 배선돼야 한다.
- 응답에 parcels_used(실제 사용 필지 목록)가 echo돼 구획도가 단일 권위목록을 소비한다.

외부 API 없이 collect_comprehensive만 모킹(순수 서비스 로직 검증). use_llm/with_senior=False.
"""
from unittest.mock import AsyncMock, patch

from app.services.regulation.regulation_analysis_service import RegulationAnalysisService


def _natural_green_comp() -> dict:
    """자연녹지 부지 comp(collect_comprehensive 반환 형태) — effective_far는 far_tier SSOT값(80)."""
    return {
        "zone_type": "자연녹지지역",
        "zone_type_secondary": "",
        "pnu": "4146310300100560016",
        "coordinates": {"lat": 37.3, "lng": 127.1},
        "land_area_sqm": 1161.0,
        "land_register": {"area_sqm": 1161.0, "land_category": "전"},
        "land_characteristics": {},
        "land_use_plan": {"districts": ["자연녹지지역", "상대보호구역", "비행안전제5구역", "토지거래계약허가구역"]},
        "special_districts": [],
        # ★zone_limits엔 effective_far_pct 키가 없다(법정 100%만) — _limits가 법정으로 폴백하던 지점.
        "zone_limits": {"max_bcr_pct": 20, "max_far_pct": 100},
        "local_ordinance": {},
        # far_tier_service.calc_effective_far SSOT 산출값(구조상한 반영 80%).
        "effective_far": {
            "effective_far_pct": 80.0,
            "effective_bcr_pct": 20.0,
            "structural_cap_pct": 80.0,
            "floor_cap": 4,
            "floor_cap_basis": "국토계획법 시행령 별표17(자연녹지지역) 두문 — 4층 이하",
            "far_basis": "구조상한(건폐율×층수)",
        },
    }


async def _analyze_natural_green():
    with patch(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
        new=AsyncMock(return_value=_natural_green_comp()),
    ):
        return await RegulationAnalysisService().analyze(
            "경기도 용인시 수지구 신봉동 56-16", pnu=None, use_llm=False, with_senior=False,
        )


async def test_natural_green_effective_far_is_structural_cap_80_not_legal_100():
    """WP-R1: 자연녹지 실효 용적률 = 80%(구조상한). 법정 100%를 '실효'로 오표기하지 않는다."""
    res = await _analyze_natural_green()
    far = res["limits"]["far"]
    assert far["legal"] == 100, "법정 상한은 100% 그대로"
    assert far["effective"] == 80.0, f"실효는 구조상한 80%여야 함(발산 봉합) — got {far['effective']}"
    bcr = res["limits"]["bcr"]
    assert bcr["effective"] == 20.0


async def test_natural_green_effective_far_passthrough_and_evidence():
    """WP-R1: effective_far 통과키 + evidence 구조상한 트레이스(green_zone_floor_cap 근거키)."""
    res = await _analyze_natural_green()
    eff = res.get("effective_far")
    assert eff and eff["structural_cap_pct"] == 80.0 and eff["floor_cap"] == 4
    labels = {e.get("label") for e in res.get("evidence") or []}
    assert "구조상한 실효 용적률" in labels, "근거패널에 구조상한 트레이스가 있어야 함"
    struct = next(e for e in res["evidence"] if e["label"] == "구조상한 실효 용적률")
    assert struct["value"] == "80%" and struct["legal_ref_key"] == "green_zone_floor_cap"


async def test_natural_green_height_card_has_floor_cap_legal_ref():
    """WP-R2: 높이 카드에 녹지 층수상한(별표15~17) 원문링크 칩이 배선된다."""
    res = await _analyze_natural_green()
    ref = res["limits"]["height"].get("legal_ref")
    assert ref and ref.get("law_name") and ref.get("key") == "green_zone_floor_cap"
    assert ref.get("url_status") in ("verified", "pending")


async def test_upper_law_level_has_bcr_far_law_links():
    """WP-R2: 상위법령 레벨에 §77(bcr_law)·§78(far_law) 법령칩이 부착된다(현재 미배선 봉합)."""
    res = await _analyze_natural_green()
    upper = next(lv for lv in res["hierarchy"] if lv["level"] == "상위법령")
    keys = {r.get("key") for r in (upper.get("legal_refs") or [])}
    assert {"bcr_law", "far_law"} <= keys, f"§77/§78 링크가 있어야 함 — got {keys}"
    # 녹지 층수제한 zone이므로 구조상한 근거키도 함께.
    assert "green_zone_floor_cap" in keys


async def test_district_level_has_per_district_legal_refs():
    """WP-R2: 개별 적용 규제·지구·구역 레벨이 지역지구별 규제법령집을 부착한다(현재 [] 봉합)."""
    res = await _analyze_natural_green()
    dist_level = next(lv for lv in res["hierarchy"] if lv["level"] == "개별 적용 규제·지구·구역")
    refs = dist_level.get("legal_refs") or []
    keys = {r.get("key") for r in refs}
    # 상대보호구역→교육환경보호법, 비행안전→군사기지법, 토지거래→거래신고법.
    assert "edu_env_protection" in keys, "상대보호구역 법령칩"
    assert "military_protection_zone" in keys, "비행안전구역→군사기지법 칩"
    assert "realtx_report" in keys, "토지거래허가→부동산거래신고법 칩"


async def test_parcels_used_echo_single_parcel():
    """WP-R3: 단일 필지도 parcels_used로 해결된 주소·PNU를 echo(구획도 단일 권위목록)."""
    res = await _analyze_natural_green()
    used = res.get("parcels_used")
    assert isinstance(used, list) and len(used) == 1
    assert used[0]["address"] == "경기도 용인시 수지구 신봉동 56-16"
    assert used[0]["pnu"] == "4146310300100560016"


async def test_parcels_used_echo_multiparcel():
    """WP-R3: 다필지(2필지↑)면 전달된 필지 목록을 그대로 echo한다."""
    rows = [
        {"address": "신봉동 56-16", "area_sqm": 1161.0, "zone_type": "자연녹지지역", "pnu": "PNU1"},
        {"address": "신봉동 56-17", "area_sqm": 900.0, "zone_type": "자연녹지지역", "pnu": "PNU2"},
    ]
    with patch(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
        new=AsyncMock(return_value=_natural_green_comp()),
    ):
        res = await RegulationAnalysisService().analyze(
            "신봉동 56-16", pnu=None, use_llm=False, with_senior=False, parcels=rows,
        )
    used = res.get("parcels_used")
    assert [p["address"] for p in used] == ["신봉동 56-16", "신봉동 56-17"]
    assert [p["pnu"] for p in used] == ["PNU1", "PNU2"]
