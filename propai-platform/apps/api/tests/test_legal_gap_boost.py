"""갭법규 보강(P0~P1) 테스트 — boostRoadmap 1~4단계.

검증 범위:
1단계: legal_reference_registry 신규 근거키(집합건물법·건축물분양법·환경영향평가법·소방·도로법·
       하수도법·소규모정비특례법·수도권정비계획법·학교용지/기부채납/국공유재산) verified 형식.
2단계: 연결 배선(land_share·floor_type·sales/suggest·scenario_simulator)의 legal_refs 가산.
3단계: special_parcel 규모·입지 임계 게이트(소방 PBD·도로법·하수도·소규모 환경영향평가).
4단계: regulation_monitor MONITORED_LAWS 확장 + '40개' 과장 교정(실수치).

원칙: 가산만(기존 응답 무손상)·verified URL만(pending은 정직)·무목업.
"""
from urllib.parse import quote, unquote

import pytest

from app.services.legal.legal_reference_registry import (
    LAW_GO_KR_BASE,
    get_legal_ref,
    get_legal_refs,
)

# 1단계: 신규 갭법규 근거키(전부 verified 딥링크 기대 — 루트 폴백 포함 url 보유).
GAP_KEYS = [
    # 집합건물법
    "condo_ownership", "condo_section_def", "land_use_right",
    "condo_management_body", "condo_seller_warranty",
    # 건축물분양법
    "building_sales_filing", "building_sales_guarantee",
    # 환경영향평가법
    "small_eia",
    # 소방·피난방화
    "fire_performance_design", "fire_prevention",
    "evacuation_stairs", "fire_compartment",
    # 도로법
    "road_abutting_zone", "road_connection_permit",
    # 하수도법
    "sewer_cause_charge", "private_sewage_facility",
    # 소규모정비특례법
    "small_housing_overview", "small_housing_road_project", "small_housing_sell_claim",
    # 수도권정비계획법
    "metro_overconcentration", "metro_congestion_charge",
    # 학교용지·기부채납·국공유재산
    "school_land_contribution", "school_land_special",
    "national_property_disposal", "public_property_disposal",
]

# 조문이 확정된(verified 딥링크) 신규 키 → (법령명, 제N조).
GAP_ARTICLE_CASES = {
    "condo_ownership": ("집합건물의 소유 및 관리에 관한 법률", "제1조"),
    "condo_section_def": ("집합건물의 소유 및 관리에 관한 법률", "제2조"),
    "land_use_right": ("집합건물의 소유 및 관리에 관한 법률", "제20조"),
    "condo_management_body": ("집합건물의 소유 및 관리에 관한 법률", "제23조"),
    "condo_seller_warranty": ("집합건물의 소유 및 관리에 관한 법률", "제9조"),
    "building_sales_filing": ("건축물의 분양에 관한 법률", "제5조"),  # ★분양신고=제5조(제4조는 '분양 시기 등')
    "building_sales_guarantee": ("건축물의 분양에 관한 법률", "제6조"),
    "small_eia": ("환경영향평가법", "제43조"),
    "fire_performance_design": ("소방시설 설치 및 관리에 관한 법률", "제8조"),
    "road_abutting_zone": ("도로법", "제40조"),
    "road_connection_permit": ("도로법", "제52조"),
    "sewer_cause_charge": ("하수도법", "제61조"),
    "private_sewage_facility": ("하수도법", "제34조"),
    "small_housing_road_project": ("빈집 및 소규모주택 정비에 관한 특례법", "제2조"),
    "small_housing_sell_claim": ("빈집 및 소규모주택 정비에 관한 특례법", "제35조"),
    "metro_overconcentration": ("수도권정비계획법", "제7조"),
    "metro_congestion_charge": ("수도권정비계획법", "제12조"),
    "school_land_contribution": ("국토의 계획 및 이용에 관한 법률", "제52조의2"),
}

# 루트 폴백(조문 미검증 — 조문 세그먼트 없음, url은 보유=verified).
GAP_ROOT_FALLBACK = {
    "fire_prevention": "화재의 예방 및 안전관리에 관한 법률",
    "evacuation_stairs": "건축물의 피난·방화구조 등의 기준에 관한 규칙",
    "fire_compartment": "건축물의 피난·방화구조 등의 기준에 관한 규칙",
    "small_housing_overview": "빈집 및 소규모주택 정비에 관한 특례법",
    "school_land_special": "학교용지 확보 등에 관한 특례법",
    "national_property_disposal": "국유재산법",
    "public_property_disposal": "공유재산 및 물품 관리법",
}


class TestGapKeysRegistry:
    @pytest.mark.parametrize("key", GAP_KEYS)
    def test_gap_keys_exist(self, key):
        assert get_legal_ref(key) is not None, f"갭법규 키 누락: {key}"

    @pytest.mark.parametrize("key", GAP_KEYS)
    def test_gap_keys_verified_url(self, key):
        """모든 갭법규 키는 url 보유(루트 포함) → get_legal_refs에서 url_status='verified'."""
        rec = get_legal_refs([key])[0]
        assert rec["url_status"] == "verified", key
        prefix = f"{LAW_GO_KR_BASE}/{quote('법령')}/"
        assert rec["url"].startswith(prefix), key
        # 할루시네이션 링크 방지: 디코드에 % 없이 law.go.kr 한글주소.
        decoded = unquote(rec["url"])
        assert decoded.startswith("https://www.law.go.kr/")
        assert "%" not in decoded

    @pytest.mark.parametrize("key,law,article", [(k, v[0], v[1]) for k, v in GAP_ARTICLE_CASES.items()])
    def test_article_verified_mapping(self, key, law, article):
        ref = get_legal_ref(key)
        assert ref["law_name"] == law, key
        assert ref["article"] == article, key
        decoded = unquote(ref["url"])
        assert decoded == f"{LAW_GO_KR_BASE}/법령/{law.replace(' ', '')}/{article}", key

    @pytest.mark.parametrize("key,law", list(GAP_ROOT_FALLBACK.items()))
    def test_root_fallback(self, key, law):
        """조문 미검증 키는 루트 폴백(조문 세그먼트 없음) — 할루시네이션 조문 금지."""
        ref = get_legal_ref(key)
        assert ref["law_name"] == law, key
        assert ref["article"] == "", key
        # 레지스트리 _normalize_name은 공백·가운뎃점(·)을 제거(②-2 규칙).
        name_norm = law.replace(" ", "").replace("·", "")
        assert unquote(ref["url"]) == f"{LAW_GO_KR_BASE}/법령/{name_norm}", key

    def test_branch_article_preserved(self):
        """국토계획법 제52조의2(가지번호) 딥링크 보존."""
        ref = get_legal_ref("school_land_contribution")
        assert ref["article"] == "제52조의2"
        assert unquote(ref["url"]).endswith("제52조의2")


class TestWiringLegalRefs:
    """2단계: 연결 배선의 legal_refs 가산(전부 verified·기존 필드 무손상)."""

    def test_land_share_condo_refs(self):
        from app.services.land_intelligence.land_share_service import _condo_legal_refs

        refs = _condo_legal_refs()
        keys = [r["key"] for r in refs]
        assert "land_use_right" in keys and "condo_ownership" in keys
        assert all(r["url_status"] == "verified" for r in refs)

    def test_floor_type_refs(self):
        from app.services.cad.floor_type_generator import _floor_legal_refs

        refs = _floor_legal_refs()
        keys = [r["key"] for r in refs]
        assert "land_use_right" in keys and "parking_min" in keys
        assert all(r["url_status"] == "verified" for r in refs)

    def test_sales_suggest_refs(self):
        from app.services.sales.pricing.suggest import _sales_legal_refs

        refs = _sales_legal_refs()
        keys = [r["key"] for r in refs]
        assert "building_sales_filing" in keys and "building_sales_guarantee" in keys
        assert all(r["url_status"] == "verified" for r in refs)

    @pytest.mark.parametrize("scheme,expect", [
        ("가로주택정비사업", "small_housing_road_project"),
        ("소규모재건축사업", "small_housing_sell_claim"),
        ("모아주택/모아타운", "small_housing_overview"),
        ("재개발·재건축(정비사업)", "redev_impl"),
    ])
    def test_scenario_scheme_refs(self, scheme, expect):
        from app.services.development.scenario_simulator import _scheme_legal_refs

        refs = _scheme_legal_refs(scheme)
        keys = [r["key"] for r in refs]
        assert expect in keys, scheme
        assert all(r["url_status"] == "verified" for r in refs)

    def test_unmapped_scheme_returns_empty(self):
        from app.services.development.scenario_simulator import _scheme_legal_refs

        assert _scheme_legal_refs("존재하지않는방식") == []


class TestSpecialParcelRegulationLayer:
    """3단계: 규모·입지 임계 게이트(소방 PBD·도로법·하수도·소규모 환경영향평가)."""

    def test_ordinary_parcel_still_none(self):
        """일상 부지(주거·중규모·도로접함)는 특이 없음(None) — 과탐 0(회귀 가드)."""
        from app.services.zoning.special_parcel import detect_special_parcel

        ok = {"land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 800,
              "road_contact": True, "road_width_m": 8, "special_districts": []}
        assert detect_special_parcel(ok) is None

    def test_fire_performance_threshold(self):
        from app.services.zoning.special_parcel import detect_special_parcel

        big = {"land_category": "대", "zone_type": "일반상업지역",
               "total_floor_area_sqm": 250000, "road_contact": True, "road_width_m": 20}
        r = detect_special_parcel(big)
        assert r is not None
        cats = [f["category"] for f in r["factors"]]
        assert any("성능위주설계" in c for c in cats)
        fire = next(f for f in r["factors"] if "성능위주설계" in f["category"])
        assert any("소방시설" in b for b in fire["legal_basis"])

    def test_fire_below_threshold_not_flagged(self):
        """임계 미만(소규모)은 소방 PBD 미탐(과탐 방지)."""
        from app.services.zoning.special_parcel import detect_special_parcel

        small = {"land_category": "대", "zone_type": "일반상업지역",
                 "total_floor_area_sqm": 5000, "floors": 5,
                 "road_contact": True, "road_width_m": 20}
        r = detect_special_parcel(small)
        if r:
            assert not any("성능위주설계" in f["category"] for f in r["factors"])

    def test_road_law_abutting_zone(self):
        from app.services.zoning.special_parcel import detect_special_parcel

        rd = {"land_category": "대", "zone_type": "계획관리지역", "area_sqm": 1000,
              "special_districts": ["일반국도 접도구역"],
              "road_contact": True, "road_width_m": 10}
        r = detect_special_parcel(rd)
        assert r is not None
        assert any("도로법" in f["category"] for f in r["factors"])

    def test_small_eia_threshold(self):
        from app.services.zoning.special_parcel import detect_special_parcel

        eia = {"land_category": "임야", "zone_type": "계획관리지역", "area_sqm": 20000,
               "road_contact": True, "road_width_m": 8}
        r = detect_special_parcel(eia)
        assert r is not None
        assert any("환경영향평가" in f["category"] for f in r["factors"])

    def test_sewer_signal(self):
        from app.services.zoning.special_parcel import detect_special_parcel

        sw = {"land_category": "대", "zone_type": "계획관리지역", "area_sqm": 1000,
              "in_sewer_service_area": False, "road_contact": True, "road_width_m": 8}
        r = detect_special_parcel(sw)
        assert r is not None
        assert any("하수도" in f["category"] for f in r["factors"])

    def test_new_factors_carry_resolution(self):
        """신규 요인도 resolvable/resolution_paths를 보유(정직 고지 정합)."""
        from app.services.zoning.special_parcel import detect_special_parcel

        rd = {"land_category": "대", "zone_type": "계획관리지역", "area_sqm": 1000,
              "special_districts": ["일반국도 접도구역"],
              "road_contact": True, "road_width_m": 10}
        r = detect_special_parcel(rd)
        road = next(f for f in r["factors"] if "도로법" in f["category"])
        assert road.get("resolvable") in ("YES", "CONDITIONAL", "NO")
        assert road.get("resolution_paths")


class TestRegulationMonitorBoost:
    """4단계: MONITORED_LAWS 확장 + '40개' 과장 교정."""

    def test_count_is_real_not_forty(self):
        from app.services.regulation_monitor.regulation_monitor import (
            MONITORED_LAW_COUNT, MONITORED_LAWS,
        )

        assert MONITORED_LAW_COUNT == len(MONITORED_LAWS)
        assert MONITORED_LAW_COUNT != 40  # 과장 '40개' 제거
        assert MONITORED_LAW_COUNT >= 7   # 기존 6개 대비 확장

    def test_no_forty_in_docstring(self):
        from app.services.regulation_monitor.regulation_monitor import RegulationMonitorService

        RegulationMonitorService()  # __init__이 docstring 플레이스홀더를 실수치로 치환
        assert "40개" not in (RegulationMonitorService.__doc__ or "")

    def test_pollable_only_has_real_ids(self):
        """ID 미확보 법령은 폴링 불가(pollable=False) — 가짜 ID 호출 금지(무목업)."""
        from app.services.regulation_monitor.regulation_monitor import (
            POLLABLE_LAW_COUNT, RegulationMonitorService,
        )

        ch = RegulationMonitorService().check_for_changes()
        pollable = [c for c in ch if c["pollable"]]
        assert len(pollable) == POLLABLE_LAW_COUNT
        assert all(c["law_id"] for c in pollable)
        # ID 미확보 항목은 law_id=None으로 정직 표기.
        assert all(c["law_id"] is None for c in ch if not c["pollable"])

    def test_real_estate_laws_present(self):
        """부동산개발 직결 법령(정비·소규모정비·집합건물·분양) 포함."""
        from app.services.regulation_monitor.regulation_monitor import MONITORED_LAWS

        names = {law["name"] for law in MONITORED_LAWS}
        for expected in ("도시 및 주거환경정비법", "빈집 및 소규모주택 정비에 관한 특례법",
                         "집합건물의 소유 및 관리에 관한 법률", "건축물의 분양에 관한 법률",
                         "환경영향평가법", "도로법"):
            assert expected in names, expected

    def test_assess_impact_invariant(self):
        """가산 후에도 changes_detected == len(changes) 불변(기존 계약 보존)."""
        from app.services.regulation_monitor.regulation_monitor import RegulationMonitorService

        m = RegulationMonitorService()
        ch = m.check_for_changes()
        imp = m.assess_impact({"project_id": "P1"}, ch)
        assert imp["changes_detected"] == len(ch)
        assert len(ch) >= 1
