"""매스 레퍼런스 → 설계 자동생성 시드 — 지역 실측 전형규모를 AutoDesignEngine 목표강도로 변환.

get_mass_reference(지역·종류 실측 중앙값)를 설계엔진 SiteInput의 target_far_percent/target_bcr_percent로
바꿔, 법정 최대 설계 외에 '이 지역 실측 전형' 설계안을 생성하는 시드로 쓴다.
★엔진이 min(법정, 목표)로 클램프하므로 실측이 법정보다 높아도 가짜 상향이 안 되고, 실측<법정이면
  지역 전형(저밀·실거주 규모) 설계안이 결정론으로 산출된다. 무목업: 유효 매스 없으면 None(시드 미적용).
"""

from __future__ import annotations

from typing import Any


def mass_seed_targets(mass_ref: dict[str, Any] | None) -> dict[str, Any] | None:
    """매스 레퍼런스 → 설계엔진 목표강도 dict. 건폐·용적이 모두 유효(>0)할 때만, 아니면 None.

    반환 = {target_far_percent, target_bcr_percent, target_floors, building_type, sample_count, source}.
    """
    if not mass_ref:
        return None
    far = mass_ref.get("median_far_pct")
    bcr = mass_ref.get("median_bcr_pct")
    if not (isinstance(far, (int, float)) and far > 0 and isinstance(bcr, (int, float)) and bcr > 0):
        return None  # 결측/0이면 시드 없이 법정 최대만(가짜 전형 금지)
    return {
        "target_far_percent": float(far),
        "target_bcr_percent": float(bcr),
        "target_floors": mass_ref.get("median_floors"),
        "building_type": mass_ref.get("building_type"),
        "sample_count": mass_ref.get("sample_count"),
        "source": "mass_backbone(building_registry)",
    }
