"""P-A.2 — 도면 자동해석 산출 → 법정 산정 입력(calc_targets) 자동구성.

면적표(outer_area)가 검출됐을 때만 산정 대상 자동 구성(날조 금지: 없으면 빈 + note).
제외 측정치는 area 보유 + 의미타입 확정(UNKNOWN 제외) 요소만(보수). 결정론(동일 입력 동일 출력).
"""
from __future__ import annotations

from app.contracts.drawing_extraction import DrawingExtraction


def build_calc_targets_from_drawing(ext: DrawingExtraction) -> tuple[list[dict], list[str]]:
    """도면 추출 → calc_targets dict 목록 + notes(자동구성 불가 사유 표면화)."""
    notes: list[str] = []
    if not ext.area_tables:
        return [], ["면적표(outer_area) 미검출 → 면적 자동산정 불가"]

    # area 보유 + 타입 확정(UNKNOWN 제외) 요소만 제외 측정치 후보(보수, 날조 금지).
    # length/depth/underground/accessory 동반 승계 — EAVE/BALCONY/PARKING 제외 정확 산정(미상=None 유지→HELD).
    excl = [
        {"semantic_type": e.semantic_hint, "area": e.area, "confidence": e.hint_strength,
         "length": e.length or 0.0, "depth": e.depth or 0.0,
         "underground": e.underground, "accessory": e.accessory}
        for e in ext.elements
        if e.area is not None and e.semantic_hint != "UNKNOWN"
    ]
    targets: list[dict] = []
    for at in ext.area_tables:
        outer = at.get("outer_area")
        if outer is None:
            notes.append(f"면적표({at.get('target')}): outer_area 없음 → skip")
            continue
        targets.append({
            "target": at.get("target", "building_area"),
            "payload": {"outer_area": float(outer)},
            "elements": excl,
        })
    return targets, notes
