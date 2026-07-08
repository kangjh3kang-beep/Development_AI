import sys
import re

# Load explain refs
sys.path.insert(0, "services/deliberation-review/apps/api")
from app.services.explain.legal_refs import _REFS

# Read registry content
with open("apps/api/app/services/legal/legal_reference_registry.py", "r", encoding="utf-8") as f:
    content = f.read()

# We'll just generate the code for _ALIASES instead! Wait, if we add them to LEGAL_REFERENCES, we keep their summaries.
# But "정본 SSOT" means we should not duplicate.
# For example, "건축법§61" is exactly "daylight_height" (제61조).
# It's better to add them as ALIASES.
alias_map = {
    "국토계획법§36": "zone_use",
    "국토계획법§77": "bcr_law",
    "국토계획법§78": "far_law",
    "국토계획법§84": "zone_use", # approx
    "국토계획법시행령§84": "bcr_limit",
    "국토계획법시행령§85": "far_limit",
    "국토계획법§52": "district_unit_plan",
    "도시정비법": "urban_redevelopment",
    "서울도시계획조례§55": "ordinance_far",
    "서울도시계획조례§54": "ordinance_bcr",
    "건축법§6": "building_permit",
    "건축법§61": "daylight_height",
    "건축법시행령§86": "daylight_height_dec",
    "건축법시행령§119": "daylight_height_dec",
    "건축법§60": "daylight_height",
    "경관법§9": "landscape_review",
    "주차장법시행규칙§6": "parking_min_dec",
    "국토계획법시행령": "bcr_limit",
    "국토계획법": "zone_use",
    "건축법시행령": "daylight_height_dec",
    "건축법": "daylight_height",
    "기부채납": "public_facility_contribution",
    "집합건물법": "condo_ownership",
    "주택법": "housing_approval",
    "공동주택관리법": "apartment_management",
    "도시개발법": "urban_dev_replot",
    "소규모주택정비법": "small_housing_overview",
    "환경영향평가법": "env_impact",
    "교통영향평가": "traffic_impact",
    "재해영향평가": "disaster_impact",
    "소방시설법": "fire_safety",
    "감정평가법": "appraisal",
    "개발이익환수법": "development_levy",
    "농지법": "farmland_conversion",
    "산지관리법": "forest_conversion",
    "문화유산법": "cultural_heritage",
    "매장유산법": "buried_heritage",
    "국유재산법": "state_property",
    "공유재산법": "public_property",
    "도시정비법시행령": "redev_mgmt",
    "토지보상법": "land_compensation",
    "공시지가법": "official_land_price",
    "주차장법": "parking_min",
    "주차장법시행령": "parking_min_dec",
    "피난방화규칙": "evacuation_stairs",
    "경관법": "landscape_review",
    "토지이용규제기본법": "land_use_regulation",
    "국토계획법시행규칙": "zone_use",
    "개발제한구역법": "greenbelt",
    "공원녹지법": "district_unit_plan",
    "도로법": "road_abutting_zone",
    "건축물분양법": "apartment_sales",
    "건축설비기준규칙": "structure_safety",
    "건축구조기준규칙": "structure_safety",
    "도시재정비촉진법": "urban_renewal_promotion",
    "도시재생법": "urban_regeneration",
    "택지개발촉진법": "land_dev_promotion",
    "공공주택특별법": "public_housing",
    "산업입지법": "industrial_site",
    "역세권개발법": "transit_oriented",
    "수도권정비계획법": "metro_overconcentration",
    "군사기지법": "daylight_height",
    "공항시설법": "daylight_height",
    "하수도법": "sewer_cause_charge",
    "수도법": "sewer_cause_charge",
    "국토기본법": "district_unit_plan",
}

missing_keys = [
    "서울한시완화2025",
    "서울역세권활성화조례",
    "서울청년안심주택조례§2",
    "서울사전협상조례",
    "입지규제최소구역지침"
]

print("Alias map size:", len(alias_map))
