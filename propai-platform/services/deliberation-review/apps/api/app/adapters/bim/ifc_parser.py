"""P1 — 경량 IFC(STEP/ISO-10303-21) 파서. 엔티티 행 → BimElement(타입+의미타입+이름+면적).

실 production은 ifcopenshell 권장이나, 여기선 무거운 dep 없이 STEP 텍스트를 정규식 파싱(테스트 가능).
IFC타입 → SemanticType 매핑은 보수적(명확한 것만), 모호/미매핑은 UNKNOWN(임의 단정 금지, INV-9).
이름 키워드(지하/발코니/주차 등)로 IFCSLAB/IFCSPACE 등 모호타입을 보조 정제.
"""
from __future__ import annotations

import re

from app.contracts.bim import BimElement, BimModel
from app.contracts.semantic_element import SemanticType

# IFC 엔티티: #12= IFCWALLSTANDARDCASE('guid',#5,'외벽-1',$,...);
_ENTITY_RE = re.compile(
    r"#\d+\s*=\s*(IFC[A-Z0-9]+)\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL
)
# 인자 내 첫 두 따옴표 문자열(guid, name 추정).
_STR_RE = re.compile(r"'((?:[^']|'')*)'")

# 명확한 타입만 매핑(나머지 UNKNOWN).
_TYPE_MAP = {
    "IFCWALL": SemanticType.EXT_WALL,
    "IFCWALLSTANDARDCASE": SemanticType.EXT_WALL,
    "IFCCURTAINWALL": SemanticType.EXT_WALL,
    "IFCSTAIR": SemanticType.CORE_STAIR,
    "IFCSTAIRFLIGHT": SemanticType.CORE_STAIR,
    "IFCROOF": SemanticType.EAVE,
}
# 이름 키워드로 모호타입(IFCSLAB/IFCSPACE/IFCBUILDINGELEMENTPROXY 등) 정제.
_NAME_HINTS = (
    ("지하", SemanticType.BASEMENT), ("basement", SemanticType.BASEMENT),
    ("발코니", SemanticType.BALCONY), ("balcon", SemanticType.BALCONY),
    ("주차", SemanticType.PARKING), ("parking", SemanticType.PARKING),
    ("필로티", SemanticType.PILOTIS), ("pilot", SemanticType.PILOTIS),
    ("처마", SemanticType.EAVE), ("eave", SemanticType.EAVE),
    ("대지경계", SemanticType.PLOT_BOUNDARY), ("건축선", SemanticType.BUILDING_LINE),
)


def _semantic_for(ifc_type: str, name: str | None) -> SemanticType:
    low = (name or "").lower()
    for kw, st in _NAME_HINTS:
        if kw in low:
            return st
    return _TYPE_MAP.get(ifc_type.upper(), SemanticType.UNKNOWN)


class IfcParser:
    def parse(self, ifc_text: str) -> BimModel:
        elements: list[BimElement] = []
        for m in _ENTITY_RE.finditer(ifc_text or ""):
            ifc_type = m.group(1).upper()
            if ifc_type in ("IFCPROJECT", "IFCOWNERHISTORY", "IFCQUANTITYAREA"):
                continue
            strings = _STR_RE.findall(m.group(2))
            guid = strings[0] if strings else None
            name = strings[1] if len(strings) > 1 else None
            elements.append(BimElement(
                ifc_type=ifc_type,
                semantic_type=_semantic_for(ifc_type, name),
                name=name,
                guid=guid,
            ))
        return BimModel(elements=elements, source="BIM")
