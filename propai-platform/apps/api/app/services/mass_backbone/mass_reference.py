"""매스 레퍼런스 — 저장된 지역별 종류별 실측 매스를 '전형 규모' 레퍼런스로 제공.

유사건축물 추천·설계 자동생성이 "이 지역 같은 종류 건축물의 실측 전형 규모(건폐/용적/층수)"를
시드/참고로 쓰도록, mass_store.lookup_templates 위에 얇은 조회 헬퍼를 둔다.
★무목업: 저장 표본이 없거나 건폐/용적이 결측이면 None(가짜 전형 생성 금지)·provenance 동반.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mass_backbone.mass_aggregation import classify_building_type
from app.services.mass_backbone.mass_store import lookup_templates

# 사업유형명(feasibility DEVELOPMENT_TYPE_NAMES: 재개발·재건축·주상복합 등) → 매스 건축물종류.
# ★classify_building_type은 '건축물대장 주용도'용이라 사업유형명(재개발/일반분양/주상복합…)은 대부분
#   '기타'로 떨어져 0매칭(silent dead path)이 된다 → 사업유형을 결과 건축물종류로 먼저 매핑한다.
#   주거 개발(재개발·재건축·일반분양·주상복합·도시형생활주택 등)의 결과물은 공동주택(아파트) 매스.
_DEV_TYPE_TO_MASS: dict[str, str] = {
    "재개발": "공동주택", "재건축": "공동주택", "역세권개발": "공동주택",
    "지역주택조합": "공동주택", "임대협동조합": "공동주택", "일반분양": "공동주택",
    "주상복합": "공동주택", "도시형생활주택": "공동주택", "공공임대": "공동주택", "민간리츠": "공동주택",
    "오피스텔": "오피스텔", "지식산업센터": "지식산업센터",
    "단독주택": "단독주택", "전원주택": "단독주택", "타운하우스": "단독주택",
}


def _resolve_mass_type(label: str | None) -> str:
    """사업유형/주용도 라벨 → 매스 건축물종류. 사업유형 매핑 우선, 없으면 classify(대장 주용도) 폴백."""
    s = (label or "").strip()
    if not s:
        return "기타"
    for keyword, mass_type in _DEV_TYPE_TO_MASS.items():
        if keyword in s:
            return mass_type
    return classify_building_type(s)


async def get_mass_reference(
    db: AsyncSession,
    *,
    region: str | None,
    building_type_label: str | None,
) -> dict[str, Any] | None:
    """지역(시군구) + 사업유형 라벨 → 같은 종류 실측 전형 매스(중앙값) 1건. 없으면 None.

    building_type_label(예: '주상복합'·'오피스텔')을 _resolve_mass_type(사업유형 매핑→classify 폴백)으로
    매스 건축물종류로 변환해 조회하므로, 추천 유형명이 대장 주용도와 달라도 매칭된다. 건폐·용적 유효 행만 채택.
    """
    if not region:
        return None
    bt = _resolve_mass_type(building_type_label)   # 사업유형명→매스종류(주상복합·재개발 등도 매핑)
    rows = await lookup_templates(db, region=region, building_type=bt)  # 표본수 내림차순
    for row in rows:
        if (row.get("median_bcr_pct") or 0) > 0 and (row.get("median_far_pct") or 0) > 0:
            return {
                "region": region,
                "building_type": bt,
                "sample_count": row.get("sample_count"),
                "median_bcr_pct": row.get("median_bcr_pct"),
                "median_far_pct": row.get("median_far_pct"),
                "median_floors": row.get("median_floors"),
                "median_total_area_sqm": row.get("median_total_area_sqm"),
                "source": "mass_backbone(building_registry)",
                "note": "이 지역 같은 종류 건축물의 실측 중앙값(전형 규모) — 설계/사업성 참고용.",
            }
    return None
