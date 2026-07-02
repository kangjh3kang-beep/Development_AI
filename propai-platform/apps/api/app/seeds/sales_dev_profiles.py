"""v62 분양관리 — 개발형식(development_type) 기본 프로필 + 분양가 구성 기본값 시드.

프로비저닝(Part3)에서 현장 development_type 에 맞는 프로필 + 구성 기본값을 적재한다.
기본형건축비 단가는 regulation_change_log 연계로 최신 국토부 고시값을 주입(하드코딩 금지).
"""

DEV_TYPE_DEFAULTS = {
    "APT": {
        "sale_method": "SUBSCRIPTION", "unit_price_basis": "PER_UNIT",
        "area_basis": {"primary": "supply", "areas": ["exclusive", "supply"]},
        "vat_policy": {"taxable": "build_over_85"}, "naming_rule": {"unit": "dong_ho"},
    },
    "OFFICETEL": {
        "sale_method": "OPEN", "unit_price_basis": "PER_UNIT",
        "area_basis": {"primary": "contract", "areas": ["exclusive", "contract"]},
        "vat_policy": {"taxable": "build"}, "naming_rule": {"unit": "ho"},
    },
    "KNOWLEDGE_CENTER": {
        "sale_method": "OPEN", "unit_price_basis": "PER_AREA",
        "area_basis": {"primary": "supply", "areas": ["exclusive", "supply"]},
        "vat_policy": {"taxable": "build"}, "naming_rule": {"unit": "ho"},
        "attributes": {"features": ["drive_in", "support_facility"]},
    },
    "HOTEL": {
        "sale_method": "OPEN", "unit_price_basis": "PER_UNIT",
        "area_basis": {"primary": "contract", "areas": ["exclusive", "contract"]},
        "vat_policy": {"taxable": "build"}, "naming_rule": {"unit": "room"},
        "attributes": {"operator": True, "yield_note": True},
    },
    "RETAIL": {
        "sale_method": "OPEN", "unit_price_basis": "PER_AREA",
        "area_basis": {"primary": "contract", "areas": ["exclusive", "contract"]},
        "vat_policy": {"taxable": "build"}, "naming_rule": {"unit": "store"},
        "attributes": {"floor_weight": "high", "md": True},
    },
}

# 분양가 구성 기본 항목: 토지비(LAND)/건축비(BUILD). CUSTOM(업무대행비)은 운영자 추가.
COMPOSITION_DEFAULTS = [
    {"component_type": "LAND", "label": "토지비(택지비)", "basis": "RATE", "value": 0, "vat_applicable": False},
    {"component_type": "BUILD", "label": "건축비(기본형건축비+가산비)", "basis": "RATE",
     "value": 0, "vat_applicable": True},
]
