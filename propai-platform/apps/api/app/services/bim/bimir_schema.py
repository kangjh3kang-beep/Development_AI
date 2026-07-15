"""propai.bimir/1.0 — 단일 BIM 중간표현(IR) 계약 (WP-D · P11).

무엇을 푸는가(쉬운 설명):
- 지금까지 설계 산출물은 서로 다른 두 벌의 DesignSpec으로 흩어져 있었다:
  · cad/design_spec.py (pydantic) = 설계 '의도 입력'(대지면적·용도지역·층수·이격 등)
  · design_ingest/design_spec.py (dataclass) = 업로드 도면 '파싱 결과'(룸·레이어·치수)
  여기에 IFC 생성이 소비하는 '매스 dict'(폭·깊이·층수·코어…)까지 3갈래라, IFC·glb·QTO·
  뷰어가 각기 다른 모양을 받아 계약이 없었다(P11 갭).
- BimIR은 이 셋을 담을 수 있는 '하나의 정규 계약'이다. 요소(element)마다 결정적 id·범주·
  지문(fingerprint)을 붙여, 같은 설계를 다시 만들어도 id가 변하지 않게 한다(멱등·재현).

★결정론(수용 게이트): 같은 설계 입력을 3번 만들어도 element_id·fingerprint·직렬화 JSON이
  '바이트까지' 동일해야 한다. 그래서 이 파일의 생성 경로에는 datetime.now()/uuid4()/random을
  절대 쓰지 않는다 — 모든 값은 입력에서 결정적으로 파생한다(uuid5).

★element_id 파생식(스키마에 박제 — 감사·재현용):
    element_id = uuid5(BIMIR_NAMESPACE, f"{design_input_hash}|{element_path}|{fingerprint}")
  · design_input_hash: 설계 입력(핑거프린트)의 sha256 — 같은 설계면 같은 값.
  · element_path: 모델 내 결정적 경로(예: 'storey[2]/wall/S') — ★재생성 불변이지만 인덱스
    파생이라 요소 삽입/재정렬 시에는 변한다. 편집 안정(stable) id는 P12 merge 트랙 범위.
  · fingerprint: 요소 자신의 지문(범주+기하+소속층의 정규화 sha256).
  랜덤/시각 기반(uuid4·UUIDv7)을 쓰지 않고 위 파생으로 UUID 포맷을 충족하면서 결정성을 지킨다.

★범위(세션 1/4~5): 계약·범주·id·지문·ownership '예약'까지만. element-level 3-way merge는
  P12 Revit(BLOCKED_INPUT) 트랙이라 여기서 구현하지 않는다(ownership 필드는 자리만 잡는다).

신규 무거운 의존성 0: pydantic + 기존 provenance 순수 헬퍼(hashlib/json)만 쓴다.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.services.cad.provenance import (
    canonical_json,
    normalize_fingerprint,
    sha256_hex,
)

# IR 버전 문자열 — 모든 BimModel 헤더에 박제(계약 식별자·불변).
IR_VERSION = "propai.bimir/1.0"

# ── element_id 파생 상수(미러 상수 계약 — 절대 변경 금지) ──
# 이 네임스페이스를 바꾸면 '모든' element_id가 바뀌어 하류(캐시·머지·영속)가 전부 깨진다.
# 값의 유래(문서화·재현 가능): uuid5(uuid.NAMESPACE_URL, "propai.bimir/1.0/element-namespace").
BIMIR_NAMESPACE = uuid.UUID("0941506d-9123-5a1c-8d5e-14768501734a")

# element_id 파생식의 사람이 읽는 문서(계약 문자열 — 테스트가 이 상수를 검증한다).
ELEMENT_ID_DERIVATION = (
    "uuid5(BIMIR_NAMESPACE, '{design_input_hash}|{element_path}|{fingerprint}')"
)


class BimCategory(StrEnum):
    """category v1 — 14종 정규 BIM 요소 범주(명세 A7 사상).

    각 범주는 특정 IFC 클래스에 1:1 사상한다(CATEGORY_IFC_CLASS 단일출처). 'unknown'은
    범주를 결정할 수 없을 때의 정직 폴백이다(무날조 — 억지 범주를 지어내지 않는다).

    ★StrEnum: 값이 곧 문자열("site" 등)이라 JSON 직렬화가 결정적이고, UP042(str+Enum 이중상속)
      경고도 피한다.
    """

    SITE = "site"            # IfcSite — 대지/필지
    BUILDING = "building"    # IfcBuilding — 건물
    STOREY = "storey"        # IfcBuildingStorey — 층
    SPACE = "space"          # IfcSpace — 실(룸)
    SLAB = "slab"            # IfcSlab — 슬래브(바닥/복도)
    WALL = "wall"            # IfcWall — 외벽
    PARTITION = "partition"  # IfcWallStandardCase — 세대 칸막이(내벽)
    COLUMN = "column"        # IfcColumn — 기둥/코어벽
    BEAM = "beam"            # IfcBeam — 보 (예약 — 현행 생성기 미산출)
    STAIR = "stair"          # IfcStair — 계단/경사로
    DOOR = "door"            # IfcDoor — 문(개구부)
    WINDOW = "window"        # IfcWindow — 창(개구부)
    ROOF = "roof"            # IfcRoof — 지붕 (예약 — 현행 생성기 미산출)
    UNKNOWN = "unknown"      # 정직 폴백 — 범주 판정 불가


# 범주 → IFC 클래스 단일출처(미러 상수). 어댑터·소비처가 같은 사상을 공유한다.
# (14종 전건 사상 — 테스트가 키 집합=BimCategory 전건 일치를 검증한다.)
CATEGORY_IFC_CLASS: dict[BimCategory, str] = {
    BimCategory.SITE: "IfcSite",
    BimCategory.BUILDING: "IfcBuilding",
    BimCategory.STOREY: "IfcBuildingStorey",
    BimCategory.SPACE: "IfcSpace",
    BimCategory.SLAB: "IfcSlab",
    BimCategory.WALL: "IfcWall",
    BimCategory.PARTITION: "IfcWallStandardCase",
    BimCategory.COLUMN: "IfcColumn",
    BimCategory.BEAM: "IfcBeam",
    BimCategory.STAIR: "IfcStair",
    BimCategory.DOOR: "IfcDoor",
    BimCategory.WINDOW: "IfcWindow",
    BimCategory.ROOF: "IfcRoof",
    BimCategory.UNKNOWN: "IfcBuildingElementProxy",
}


def ifc_class_for(category: BimCategory) -> str:
    """범주 → IFC 클래스명(미상 범주는 프록시로 정직 폴백)."""
    return CATEGORY_IFC_CLASS.get(category, "IfcBuildingElementProxy")


class BimElementOwnership(BaseModel):
    """요소 소유권/출처 — P12 Revit(BLOCKED_INPUT) element-level 3-way merge 트랙용 '예약' 블록.

    ★세션 1/4~5에서는 자리만 잡고 소비하지 않는다(merge 로직 구현 금지). 값은 전부 기본 None —
      직렬화에는 항상 포함되어(예약 필드 계약), 하류 스키마가 미리 이 자리를 인지하게 한다.
    """

    model_config = {"extra": "forbid"}

    owner_track: str | None = None      # 소유 주체(예: 'revit'|'propai') — 예약
    base_version: str | None = None     # 3-way merge 기준 버전 — 예약
    origin_kind: str | None = None      # 최초 출처(생성/임포트) — 예약
    locked: bool | None = None          # 편집 잠금 — 예약


class BimElement(BaseModel):
    """BIM 요소 1건 — 결정적 id + 범주 + 지문 + (예약)소유권 + 손실 0 extras."""

    model_config = {"extra": "forbid"}

    element_id: str                 # uuid5 파생(결정적) — ELEMENT_ID_DERIVATION 참고
    element_path: str               # 결정적 경로 — 재생성 불변·삽입/재정렬 시 변동(P12 merge 트랙 참조)
    category: BimCategory
    fingerprint: str                # 지문(sha256) — 범주+소속층+기하의 결정적 해시
    name: str | None = None
    storey_index: int | None = None  # 소속 층(0-base) — None=비층요소(site/building)
    geometry: dict[str, Any] = Field(default_factory=dict)      # 치수/배치 파라미터(원본 보존·손실 0)
    quantities: dict[str, float] = Field(default_factory=dict)  # 물량(면적/체적/길이 등)
    ownership: BimElementOwnership = Field(default_factory=BimElementOwnership)
    extras: dict[str, Any] = Field(default_factory=dict)        # 원본 미사상 필드 손실 0 보존


class BimModel(BaseModel):
    """propai.bimir/1.0 단일 IR — 헤더 + 모델속성 + 요소목록.

    extras / attributes에는 원본(DesignSpec·mass) 값을 손실 없이 보존한다 — 어떤 어댑터도
    필드를 버리지 않는다(손실 0 계약). source_kind로 어느 원본에서 왔는지 표기한다(무날조).
    """

    model_config = {"extra": "forbid"}

    ir_version: str = IR_VERSION
    source_kind: str                 # 유래: 'cad_design_spec'|'design_ingest'|'mass_geometry'
    design_input_hash: str           # 입력 결정 핑거프린트 해시(같은 설계면 같은 값)
    project_name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)  # 모델 수준 속성(zone_code 등 원본 보존)
    elements: list[BimElement] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)      # 모델 수준 손실 0 보존

    def to_canonical_json(self) -> str:
        """결정적 정규 JSON 직렬화(키 정렬·공백 제거) — 바이트 동일성 비교의 단일 기준.

        model_dump(mode="json")로 enum→문자열·중첩모델→dict로 낮춘 뒤, provenance.canonical_json
        (sort_keys)로 정규화한다 → 같은 모델이면 언제 직렬화해도 바이트까지 동일.
        """
        return canonical_json(self.model_dump(mode="json"))

    def element_ids(self) -> list[str]:
        """요소 element_id 목록(등장 순서) — 결정성 게이트 비교용."""
        return [e.element_id for e in self.elements]


def compute_fingerprint(
    *,
    category: BimCategory,
    geometry: dict[str, Any] | None,
    storey_index: int | None,
) -> str:
    """요소 지문(sha256) — 범주+소속층+기하를 정규화해 해시한다.

    ★수치 정규화(normalize_fingerprint): int/float·미세 부동소수 차이를 같은 값으로 본다
      (20 == 20.0). name은 지문에서 제외한다 — 이름엔 표시용 인덱스가 섞여 정체와 무관하다
      (정체 유일성은 element_path가 담당).
    """
    payload = {
        "category": category.value,
        "storey_index": storey_index,
        "geometry": {} if geometry is None else geometry,
    }
    return sha256_hex(canonical_json(normalize_fingerprint(payload)))


def derive_element_id(design_input_hash: str, element_path: str, fingerprint: str) -> str:
    """element_id 결정적 파생 — uuid5(BIMIR_NAMESPACE, 'hash|path|fingerprint').

    ★결정론: 입력·경로·지문이 같으면 언제 만들어도 같은 UUID(랜덤/시각 요소 0).
    """
    seed = f"{design_input_hash}|{element_path}|{fingerprint}"
    return str(uuid.uuid5(BIMIR_NAMESPACE, seed))


def make_element(
    *,
    design_input_hash: str,
    element_path: str,
    category: BimCategory,
    name: str | None = None,
    storey_index: int | None = None,
    geometry: dict[str, Any] | None = None,
    quantities: dict[str, float] | None = None,
    extras: dict[str, Any] | None = None,
) -> BimElement:
    """BimElement 결정적 생성 헬퍼 — 지문·element_id를 입력에서 파생한다.

    ★0-falsy 금지: geometry/quantities/extras는 'is None'으로만 비운다(값 0·빈 문자열을
      실수로 버리지 않게). 원본 값은 그대로 보존한다(손실 0 — 반올림/정규화는 지문 계산에만 적용).
    """
    geo: dict[str, Any] = {} if geometry is None else dict(geometry)
    fp = compute_fingerprint(category=category, geometry=geo, storey_index=storey_index)
    return BimElement(
        element_id=derive_element_id(design_input_hash, element_path, fp),
        element_path=element_path,
        category=category,
        fingerprint=fp,
        name=name,
        storey_index=storey_index,
        geometry=geo,
        quantities={} if quantities is None else dict(quantities),
        extras={} if extras is None else dict(extras),
    )
