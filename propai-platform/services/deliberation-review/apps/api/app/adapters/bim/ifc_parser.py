"""P1 — 경량 IFC(STEP/ISO-10303-21) 파서. 엔티티 행 → BimElement(타입+의미타입+이름+면적).

실 production은 ifcopenshell 권장이나, 여기선 무거운 dep 없이 STEP 텍스트를 정규식 파싱(테스트 가능).
IFC타입 → SemanticType 매핑은 보수적(명확한 것만), 모호/미매핑은 UNKNOWN(임의 단정 금지, INV-9).
이름 키워드(지하/발코니/주차 등)로 IFCSLAB/IFCSPACE 등 모호타입을 보조 정제.
"""
from __future__ import annotations

import re

from app.contracts.bim import BimElement, BimModel
from app.contracts.semantic_element import SemanticType

# IFC 엔티티: #12= IFCWALLSTANDARDCASE('guid',#5,'외벽-1',$,...); — ref·타입·인자 캡처.
_ENTITY_RE = re.compile(
    r"(#\d+)\s*=\s*(IFC[A-Z0-9]+)\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL
)
# 인자 내 첫 두 따옴표 문자열(guid, name 추정).
_STR_RE = re.compile(r"'((?:[^']|'')*)'")
# 엔티티 참조(#n). 정량 관계 결합용.
_REF_RE = re.compile(r"#\d+")
# 정량 그래프에서 BimElement로 만들지 않는 보조 엔티티.
_SKIP_TYPES = {
    "IFCPROJECT", "IFCOWNERHISTORY", "IFCQUANTITYAREA", "IFCQUANTITYLENGTH",
    "IFCELEMENTQUANTITY", "IFCRELDEFINESBYPROPERTIES",
}


def _first_real(args: str) -> float | None:
    """인자에서 첫 REAL 값(소수). #참조 정수는 제외(결정론)."""
    for m in re.finditer(r"(?<![#\w])-?\d+\.\d*", args):
        try:
            return float(m.group(0))
        except ValueError:
            continue
    return None

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
        # 1패스: 엔티티 수집 + 정량 그래프(IFCQUANTITYAREA/LENGTH → IFCELEMENTQUANTITY → IFCRELDEFINESBYPROPERTIES).
        entities = [(m.group(1), m.group(2).upper(), m.group(3))
                    for m in _ENTITY_RE.finditer(ifc_text or "")]
        area_q: dict[str, float] = {}     # quantity_ref → area 값
        length_q: dict[str, float] = {}   # quantity_ref → length 값
        elem_quant: dict[str, list[str]] = {}  # elementquantity_ref → [quantity_refs]
        rel: dict[str, str] = {}          # element_ref → elementquantity_ref(propset)
        for ref, typ, args in entities:
            if typ == "IFCQUANTITYAREA":
                v = _first_real(args)
                if v is not None:
                    area_q[ref] = v
            elif typ == "IFCQUANTITYLENGTH":
                v = _first_real(args)
                if v is not None:
                    length_q[ref] = v
            elif typ == "IFCELEMENTQUANTITY":
                elem_quant[ref] = _REF_RE.findall(args)
            elif typ == "IFCRELDEFINESBYPROPERTIES":
                refs = _REF_RE.findall(args)
                if len(refs) >= 2:  # 마지막=propset, 그 앞=관련 요소들
                    for er in refs[:-1]:
                        rel[er] = refs[-1]

        # 2패스: BimElement 생성 + 정량 결합(관계 따라 area/length 채움. 미연결은 None 유지=무음0).
        elements: list[BimElement] = []
        for ref, ifc_type, args in entities:
            if ifc_type in _SKIP_TYPES:
                continue
            strings = _STR_RE.findall(args)
            guid = strings[0] if strings else None
            name = strings[1] if len(strings) > 1 else None
            area = length = None
            propset = rel.get(ref)
            if propset and propset in elem_quant:
                for qref in elem_quant[propset]:
                    if area is None and qref in area_q:
                        area = area_q[qref]
                    if length is None and qref in length_q:
                        length = length_q[qref]
            elements.append(BimElement(
                ifc_type=ifc_type,
                semantic_type=_semantic_for(ifc_type, name),
                name=name,
                guid=guid,
                area=area,
                length=length,
            ))
        return BimModel(elements=elements, source="BIM")
