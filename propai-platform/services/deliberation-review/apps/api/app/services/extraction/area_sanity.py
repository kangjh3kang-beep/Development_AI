"""INC-6 — 도면 추출 area sanity 게이트(환각/모순 면적 무검증 승계 차단).

비전(VLLM)이 답한 area는 1차출처가 아니므로 산정 입력으로 무비판 승계하면 환각 면적이 FAR/건축면적을
왜곡한다(무음 오판). 결정론 부등식으로 (1)제외 area 합 ≤ 외곽면적, (2)단일 제외 area/외곽 ≤ 상한(param)을
검사해 위반을 note로 표면화한다(드롭 금지 — 무음0). 임계는 param 주입(INV-3).
"""
from __future__ import annotations

from app.core.parameters import param


def area_sanity_notes(outer_area: float, excl_elements: list[dict]) -> list[str]:
    """제외 측정치 sanity 위반을 note 목록으로 반환(요소는 변형/드롭하지 않음 — 표면화만)."""
    notes: list[str] = []
    if not outer_area or outer_area <= 0:
        return notes
    ratio_max = float(param("area_ratio_max"))
    total_excl = sum(float(e["area"]) for e in excl_elements if e.get("area"))
    if total_excl > outer_area:
        notes.append(
            f"⚠️ area_sanity: 제외 area 합 {round(total_excl, 1)} > 외곽면적 {round(outer_area, 1)} "
            "— 모순(도면 추출 오류 의심), 산정 신뢰 제한")
    for e in excl_elements:
        a = e.get("area")
        if a and (float(a) / outer_area) > ratio_max:
            notes.append(
                f"⚠️ area_sanity: 단일 제외 area {round(float(a), 1)}/외곽 {round(outer_area, 1)}="
                f"{round(float(a) / outer_area, 2)} > 상한 {ratio_max} — 비전 추출 환각 의심(확인 필요)")
    return notes
