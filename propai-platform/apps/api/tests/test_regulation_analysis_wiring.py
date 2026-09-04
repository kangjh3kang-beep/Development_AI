"""/regulations 워크플로우 배선 검증 — WP-R1(실효FAR)·R2(법규링크)·R3(구획도 parity).

라이브 지적(용인 신봉동 자연녹지)의 회귀를 잠근다:
- 자연녹지 실효 용적률은 법정 100%가 아니라 구조상한 80%(건폐20%×4층)여야 한다.
- 상위법령 §77/§78·개별 규제 지역지구별 법령칩·높이 4층 근거칩이 배선돼야 한다.
- 응답에 parcels_used(실제 사용 필지 목록)가 echo돼 구획도가 단일 권위목록을 소비한다.
- ★적대리뷰(PR#333 REVISE) HIGH: 다필지 혼합(면적가중 blended effective)에 대표(첫)필지의
  구조상한(structural_cap_pct/floor_cap)을 그대로 얹으면 "실효 건폐율 40%(blended) × 4층(대표)
  = 80%(대표)" 같은 산술 거짓이 재유입된다 — 다필지 혼합은 구조상한 상세를 미표시해야 한다.
- ★층수클램프가 없는 zone(제2종일반주거 등)은 구조상한이 실효치를 낮추지 않아야 한다(250% 유지).

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


async def test_mixed_multiparcel_no_bogus_structural_cap_row():
    """★적대리뷰 HIGH: 자연녹지(대표)+제2종일반주거 혼합 다필지는 blended bcr/far가 헤드라인이고,
    대표필지 전용 구조상한(structural_cap_pct=80·floor_cap=4)을 그 옆에 노출하면 "실효 건폐율
    40%(blended) × 4층(대표) = 80%(대표)"(40×4=160≠80) 같은 가시적 산술 거짓이 된다.
    다필지 혼합(integrated 성공) 시엔 구조상한 evidence 행·passthrough 필드·높이칩을 미표시해야 한다.
    """
    rows = [
        {"address": "신봉동 56-16", "area_sqm": 1161.0, "zone_type": "자연녹지지역", "pnu": "PNU1"},
        {"address": "신봉동 56-17", "area_sqm": 900.0, "zone_type": "제2종일반주거지역", "pnu": "PNU2"},
    ]
    blended = {
        "parcel_count": 2,
        "total_area_sqm": 2061.0,
        "dominant_zone": "자연녹지지역",
        "blended_far_eff_pct": 139.6,
        "blended_bcr_eff_pct": 40.0,
    }
    with (
        patch(
            "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
            new=AsyncMock(return_value=_natural_green_comp()),
        ),
        patch(
            "app.services.land_intelligence.comprehensive_analysis_service."
            "ComprehensiveAnalysisService._integrated_context",
            new=AsyncMock(return_value=blended),
        ),
    ):
        res = await RegulationAnalysisService().analyze(
            "신봉동 56-16", pnu=None, use_llm=False, with_senior=False, parcels=rows,
        )

    # 헤드라인은 blended(면적가중) 값이어야 함 — 대표필지 단독값(80/20)이 아니라.
    assert res["limits"]["bcr"]["effective"] == 40.0
    assert res["limits"]["far"]["effective"] == 139.6

    # 구조상한 evidence 행이 없어야 함(대표필지 전용 값 재유입 금지).
    labels = {e.get("label") for e in res.get("evidence") or []}
    assert "구조상한 실효 용적률" not in labels, f"다필지 혼합에 대표필지 구조상한 행이 새면 안 됨 — {labels}"

    # passthrough의 구조상한 상세 필드도 None(헤드라인만 유지, 대표필지 근거는 생략).
    eff = res.get("effective_far")
    assert eff is not None
    assert eff["effective_far_pct"] == 139.6 and eff["effective_bcr_pct"] == 40.0
    assert eff["structural_cap_pct"] is None
    assert eff["floor_cap"] is None
    assert eff["floor_cap_basis"] is None
    assert eff["far_basis"] is None

    # 높이카드 층수상한 근거칩도 대표필지 전용이라 미표시.
    assert res["limits"]["height"].get("legal_ref") is None

    # 상위법령 legal_refs에도 green_zone_floor_cap(대표필지 근거)이 섞이면 안 됨.
    upper = next(lv for lv in res["hierarchy"] if lv["level"] == "상위법령")
    keys = {r.get("key") for r in (upper.get("legal_refs") or [])}
    assert "green_zone_floor_cap" not in keys


async def test_no_floor_cap_zone_keeps_full_effective_far_250():
    """★적대리뷰 HIGH 반증테스트: 제2종일반주거(층수클램프 없음)는 구조상한이 실효치를 낮추지
    않는다 — far_tier_service._structural_cap_for가 (None,None,None)을 반환하는 zone은 실효
    용적률이 법정/조례 그대로(250%) 유지돼야 한다(자연녹지만 테스트하던 이전 커버리지 갭 봉합).
    """
    comp = {
        "zone_type": "제2종일반주거지역",
        "zone_type_secondary": "",
        "pnu": "PNU-JUGEO",
        "coordinates": {"lat": 37.4, "lng": 127.0},
        "land_area_sqm": 800.0,
        "land_register": {"area_sqm": 800.0, "land_category": "대"},
        "land_characteristics": {},
        "land_use_plan": {"districts": ["제2종일반주거지역"]},
        "special_districts": [],
        "zone_limits": {"max_bcr_pct": 60, "max_far_pct": 250},
        "local_ordinance": {},
        # far_tier_service.calc_effective_far SSOT 산출값 — 층수제한 없음(구조상한 미적용).
        "effective_far": {
            "effective_far_pct": 250.0,
            "effective_bcr_pct": 60.0,
            "structural_cap_pct": None,
            "floor_cap": None,
            "floor_cap_basis": None,
            "far_basis": "법정/조례",
        },
    }
    with patch(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
        new=AsyncMock(return_value=comp),
    ):
        res = await RegulationAnalysisService().analyze(
            "서울시 어딘가 100-1", pnu=None, use_llm=False, with_senior=False,
        )

    far = res["limits"]["far"]
    assert far["legal"] == 250, "법정 상한 250% 그대로"
    assert far["effective"] == 250.0, f"층수제한 없는 zone은 실효가 낮아지면 안 됨 — got {far['effective']}"
    # 구조상한 evidence 행도 없어야 함(floor_cap 자체가 없으므로).
    labels = {e.get("label") for e in res.get("evidence") or []}
    assert "구조상한 실효 용적률" not in labels
    assert res["limits"]["height"].get("legal_ref") is None


# ── 근거체인 절단 수정(2026-07-19) — 동질존 다필지 구조상한 근거 표면화 핀 ──

def _integrated(zone_mix, far=80.0, bcr=20.0):
    return {
        "total_area_sqm": 12079.0, "parcel_count": len(zone_mix) + 10,
        "dominant_zone": zone_mix[0]["zone"], "zone_mix": zone_mix,
        "blended_far_eff_pct": far, "blended_bcr_eff_pct": bcr,
    }


async def _analyze_multi(zone_mix):
    parcels = [{"address": f"신봉동 56-{i}", "area_sqm": 100.0, "zone_type": zone_mix[0]["zone"]}
               for i in range(2)]
    with patch(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
        new=AsyncMock(return_value=_natural_green_comp()),
    ), patch(
        "app.services.land_intelligence.comprehensive_analysis_service.ComprehensiveAnalysisService._integrated_context",
        new=AsyncMock(return_value=_integrated(zone_mix)),
    ):
        return await RegulationAnalysisService().analyze(
            "경기도 용인시 수지구 신봉동 56-16", pnu=None, use_llm=False,
            with_senior=False, parcels=parcels,
        )


async def test_uniform_multi_parcel_surfaces_structural_basis():
    """★동질존 다필지(12필지 전부 자연녹지)는 구조상한 근거를 표면화한다.

    종전: not integrated 가드가 동질존까지 숨겨 far.effective=80이 무근거 하드코딩처럼
    보였다(AI 검증 '근거 미명시' 경고·라이브 신고). 동질존은 blended=단일존 실효치라
    구조상한(건폐20%×4층=80%)·별표17 근거가 전체 집합에 유효 — 산술 거짓 불성립.
    """
    res = await _analyze_multi([{"zone": "자연녹지지역", "area_sqm": 12079.0, "share_pct": 100.0}])
    far = res["limits"]["far"]
    assert far["effective"] == 80.0
    assert far.get("effective_basis"), "동질존 다필지엔 실효 산정 근거가 표면화되어야 함"
    hgt = res["limits"]["height"]
    assert hgt.get("basis"), "높이 근거(별표17 층수상한)가 표면화되어야 함"
    assert hgt.get("legal_ref", {}).get("key") == "green_zone_floor_cap"


async def test_mixed_multi_parcel_keeps_basis_hidden():
    """혼합존 다필지는 기존 가드 보존 — 대표필지 근거를 blended 옆에 노출하면 산술 거짓."""
    res = await _analyze_multi([
        {"zone": "자연녹지지역", "area_sqm": 8000.0, "share_pct": 66.0},
        {"zone": "제2종일반주거지역", "area_sqm": 4079.0, "share_pct": 34.0},
    ])
    assert not res["limits"]["far"].get("effective_basis"), "혼합존은 근거 미표시(정직)가 계약"


async def test_single_parcel_far_effective_basis_additive():
    """단일필지도 far.effective_basis 신설 필드가 실린다(additive — AI 검증 근거 확인용)."""
    res = await _analyze_natural_green()
    assert res["limits"]["far"].get("effective_basis"), "단일필지 실효 근거 표면화"


async def test_uniform_but_divergent_blended_hides_basis():
    """★R1 하드닝 — 동질존이어도 blended(19%×4=76)≠대표 구조상한(80)이면 미표시(산술 거짓 방지).

    시군구 상이 조례로 필지별 BCR이 갈리는 좁은 케이스 — 표시하면 evidence가
    "실효 건폐율 19% × 4층 = 80%" 같은 가시적 거짓을 만든다. ε(0.5%p) 밖이면 숨김이 정직.
    """
    zone_mix = [{"zone": "자연녹지지역", "area_sqm": 12079.0, "share_pct": 100.0}]
    parcels = [{"address": f"신봉동 56-{i}", "area_sqm": 100.0, "zone_type": "자연녹지지역"}
               for i in range(2)]
    with patch(
        "app.services.land_intelligence.land_info_service.LandInfoService.collect_comprehensive",
        new=AsyncMock(return_value=_natural_green_comp()),
    ), patch(
        "app.services.land_intelligence.comprehensive_analysis_service.ComprehensiveAnalysisService._integrated_context",
        new=AsyncMock(return_value=_integrated(zone_mix, far=76.0, bcr=19.0)),
    ):
        res = await RegulationAnalysisService().analyze(
            "경기도 용인시 수지구 신봉동 56-16", pnu=None, use_llm=False,
            with_senior=False, parcels=parcels,
        )
    assert not res["limits"]["far"].get("effective_basis"), "발산 동질존은 근거 미표시(ε 가드)"
