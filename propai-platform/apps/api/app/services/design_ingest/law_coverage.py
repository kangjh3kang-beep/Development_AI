"""설계생성 단계 ↔ 법규 연결성(coverage) 매핑·검증.

부동산개발·건축 전 과정의 각 단계에 적용되는 법규(legal_reference_registry 키)를 매핑하고,
모든 매핑 키가 레지스트리에 실재(연결)하는지 검증한다. 누락·오타·할루시네이션 키를 전수 적발.
URL은 직접 조립하지 않고 get_legal_refs()만 사용(레지스트리 단일 출처).
"""

from __future__ import annotations

from app.services.legal.legal_reference_registry import get_legal_ref, get_legal_refs

# 설계생성 단계(도메인) → 적용 법규 키(legal_reference_registry). 전수조사 결과 반영.
DESIGN_LAW_MAP: dict[str, list[str]] = {
    "zoning": [  # 용도지역·건폐/용적·구역·지구
        "zone_use", "bcr_law", "far_law", "bcr_limit", "far_limit",
        "district_unit_plan", "ordinance_bcr", "ordinance_far", "greenbelt",
        "land_use_regulation", "urban_renewal_promotion", "transit_oriented",
        "land_dev_promotion", "industrial_site",
    ],
    "permit": [  # 인허가·정비·기부채납·문화유산
        "building_permit", "use_permission", "zone_use",
        "redev_impl", "redev_mgmt", "small_housing_redev", "urban_dev_replot",
        "urban_regeneration", "public_facility_contribution", "cultural_heritage",
    ],
    "design": [  # 설계(건폐/용적/일조/공지/피난/구조/소방/녹색/경관)
        "bldg_bcr", "bldg_far", "daylight_height", "daylight_height_dec",
        "site_open_space", "evacuation", "structure_safety",
        "fire_safety", "fire_prevention", "fire_evac_structure",
        "green_building", "energy_efficiency", "zeb_certification", "landscape_review",
    ],
    "parking": ["parking_min", "parking_min_dec"],
    "environment": ["env_impact", "disaster_impact", "traffic_impact", "buried_heritage"],
    "construction": ["construction_industry", "construction_tech"],  # 시공·감리
    "land": [  # 토지(전용허가·공시지가·감정평가·보상·지적)
        "farmland_conversion", "forest_conversion", "official_land_price", "appraisal",
        "land_compensation", "cadastral", "state_property", "public_property",
    ],
    "feasibility": [  # 사업성·부담금·가액
        "development_levy", "reconstruction_levy", "appraisal", "official_land_price",
        "land_compensation",
    ],
    "sales_rights": [  # 분양·구분소유·대지권·관리·임대·거래
        "housing_approval", "housing_price_cap", "condo_ownership",
        "condo_reconstruction", "condo_management", "land_right_registration",
        "realtx_report", "public_housing", "apartment_management",
        "private_rental", "apartment_sales",
    ],
    "tax": [
        "acquisition_tax", "capital_gains_tax", "comprehensive_property_tax",
        "reconstruction_levy", "local_education_tax", "stamp_tax",
    ],
    "developer": ["developer_registration"],
}


def verify_coverage() -> dict:
    """매핑된 모든 법규 키가 레지스트리에 연결(실재)하는지 전수 검증.

    Returns: {ok, total_keys, resolved, unresolved:[{domain,key}], by_domain:{...}}
    unresolved가 비어야 '전 단계 법규 연결 완결'.
    """
    unresolved: list[dict] = []
    by_domain: dict[str, dict] = {}
    total = resolved = 0
    for domain, keys in DESIGN_LAW_MAP.items():
        dom_resolved = 0
        for key in keys:
            total += 1
            if get_legal_ref(key) is not None:
                resolved += 1
                dom_resolved += 1
            else:
                unresolved.append({"domain": domain, "key": key})
        by_domain[domain] = {"keys": len(keys), "resolved": dom_resolved}
    return {
        "ok": not unresolved,
        "total_keys": total,
        "resolved": resolved,
        "unresolved": unresolved,
        "by_domain": by_domain,
    }


def laws_for(domain: str, *, sigungu: str | None = None) -> list[dict]:
    """단계(도메인)에 적용되는 법규 레코드 목록(근거·링크·url_status). get_legal_refs 단일 출처."""
    return get_legal_refs(DESIGN_LAW_MAP.get(domain, []), sigungu=sigungu)


def all_referenced_laws(*, sigungu: str | None = None) -> list[dict]:
    """전 단계에서 참조하는 법규(중복 제거) 레코드 — '전수 참조 목록'."""
    seen: set[str] = set()
    ordered_keys: list[str] = []
    for keys in DESIGN_LAW_MAP.values():
        for k in keys:
            if k not in seen:
                seen.add(k)
                ordered_keys.append(k)
    return get_legal_refs(ordered_keys, sigungu=sigungu)
