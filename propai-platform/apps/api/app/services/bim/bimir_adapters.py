"""구 DesignSpec 2벌 + 매스 dict → propai.bimir/1.0(BimModel) 어댑터 (WP-D · P11).

왜 어댑터가 '두 벌+매스'로 셋인가(쉬운 설명):
- 설계 입력이 이형(異形) 타입 두 벌이라(cad=pydantic·design_ingest=dataclass) 각각 다른 어댑터가
  필요하다. 두 벌 중 어느 것도 삭제하지 않고(수렴만) BimIR로 사상한다.
- 여기에 IFC 생성이 실제로 소비하는 '매스 dict'(폭·깊이·층수·코어…)까지 BimIR로 담아, 소비처
  전환(ifc_generator_service)이 BimIR 하나만 보게 만든다.

★손실 0 계약: 어느 어댑터도 원본 필드를 버리지 않는다. 원본 전체를 model.extras에 '그대로'
  보존한다(cad=model_dump·ingest=asdict·mass=원본 dict). 하류가 쓰기 좋게 일부 필드는
  attributes/elements로도 승격하지만, 손실 0의 근거는 언제나 extras의 원본 사본이다.

★결정론: design_input_hash·element_id·지문이 전부 입력에서 파생된다(uuid4/시각/랜덤 0). 같은
  설계를 3번 넣어도 산출 IR이 바이트까지 동일하다(수용 게이트).

★무거운 의존성 0: DesignSpec 클래스를 모듈 상단에서 import하지 않는다(오리 타이핑 + TYPE_CHECKING).
  cad 어댑터는 spec.model_dump()·spec_input_hash, ingest 어댑터는 asdict(spec)·spec.content_hash()로
  값을 읽어, cad의 무거운 커널 import 체인을 이 모듈에 끌어들이지 않는다.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import TYPE_CHECKING, Any

from app.services.bim.bimir_schema import (
    BimCategory,
    BimElement,
    BimModel,
    make_element,
)
from app.services.cad.provenance import compute_input_hash

if TYPE_CHECKING:  # 타입 힌트 전용 — 런타임 import 회피(무거운 체인 차단)
    from app.services.cad.design_spec import DesignSpec as CadDesignSpec
    from app.services.design_ingest.design_spec import DesignSpec as IngestDesignSpec

# ── 매스 파생요소 기본 두께(미러 상수) ──
# ifc_generator_service.IfcGeneratorService.generate 의 wall_thickness_m/slab_thickness_m 기본값과
# '동일'해야 매스 파생 SLAB/WALL 요소의 물량이 실제 IFC 산출과 일치한다(계약 미러).
_WALL_THICKNESS_M = 0.2
_SLAB_THICKNESS_M = 0.2


# ─────────────────────────────────────────────────────────────────────────────
# 1) cad DesignSpec(pydantic·설계 의도 입력) → BimModel
# ─────────────────────────────────────────────────────────────────────────────
def bimir_from_cad_design_spec(spec: CadDesignSpec) -> BimModel:
    """cad/design_spec.py DesignSpec(pydantic) → BimModel.

    원본 전체를 extras['cad_design_spec']에 보존(손실 0). 의도 필드는 attributes로, 대지/건물은
    SITE/BUILDING 요소로 승격한다. 설계 기하(폭·깊이 등)는 커널이 만드는 것이라 아직 없다 —
    여기서는 '의도'만 담는다(무날조).
    """
    dump: dict[str, Any] = spec.model_dump()
    design_input_hash = compute_input_hash(dump)

    # 손실 0의 근거: 원본 전체 사본.
    extras = {"cad_design_spec": dump}

    # 하류 소비 편의: 모델 수준 설계 속성(원본 값 그대로 — 변형 금지).
    attributes: dict[str, Any] = {
        "zone_code": dump.get("zone_code"),
        "building_use": dump.get("building_use"),
        "priority": dump.get("priority"),
        "corridor_width_m": dump.get("corridor_width_m"),
        "target_far_percent": dump.get("target_far_percent"),
        "target_bcr_percent": dump.get("target_bcr_percent"),
        "effective_far_percent": dump.get("effective_far_percent"),
        "effective_bcr_percent": dump.get("effective_bcr_percent"),
        "ordinance_far_percent": dump.get("ordinance_far_percent"),
        "ordinance_bcr_percent": dump.get("ordinance_bcr_percent"),
        "massing_kind": dump.get("massing_kind"),
    }

    elements: list[BimElement] = []
    # 대지(SITE) — 면적만 확정.
    elements.append(
        make_element(
            design_input_hash=design_input_hash,
            element_path="site",
            category=BimCategory.SITE,
            name="대지",
            geometry={"site_area_sqm": dump.get("site_area_sqm")},
        )
    )
    # 건물(BUILDING) — 층수/층고/이격/목표세대 등 의도.
    elements.append(
        make_element(
            design_input_hash=design_input_hash,
            element_path="building",
            category=BimCategory.BUILDING,
            name="건물",
            geometry={
                "num_floors": dump.get("num_floors"),
                "floor_height_m": dump.get("floor_height_m"),
                "building_use": dump.get("building_use"),
                "target_units": dump.get("target_units"),
                "target_unit_types": dump.get("target_unit_types"),
                "setback_m": dump.get("setback_m"),
                "unit_grammar": dump.get("unit_grammar"),
                "massing_kind": dump.get("massing_kind"),
            },
        )
    )

    return BimModel(
        source_kind="cad_design_spec",
        design_input_hash=design_input_hash,
        project_name=None,
        attributes=attributes,
        elements=elements,
        extras=extras,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2) design_ingest DesignSpec(dataclass·도면 파싱 결과) → BimModel
# ─────────────────────────────────────────────────────────────────────────────
def bimir_from_ingest_design_spec(spec: IngestDesignSpec) -> BimModel:
    """design_ingest/design_spec.py DesignSpec(dataclass) → BimModel.

    원본 전체를 extras['design_ingest_design_spec']에 보존(손실 0). 룸은 SPACE 요소로, 집계값은
    BUILDING 요소로 승격한다. design_input_hash는 원본이 이미 가진 결정적 content_hash를 재사용한다.
    """
    dump: dict[str, Any] = dataclasses.asdict(spec)
    # 원본이 이미 결정적 content_hash를 제공 — 재발명 없이 재사용(멱등 계약 일치).
    design_input_hash = spec.content_hash()

    extras = {"design_ingest_design_spec": dump}

    attributes: dict[str, Any] = {
        "source_format": dump.get("source_format"),
        "drawing_type": dump.get("drawing_type"),
        "title": dump.get("title"),
        "total_area_sqm": dump.get("total_area_sqm"),
        "floor_count": dump.get("floor_count"),
        "unit_count": dump.get("unit_count"),
        "parking_count": dump.get("parking_count"),
        "layers": dump.get("layers"),
        "dimensions": dump.get("dimensions"),
        "raw_summary": dump.get("raw_summary"),
        "meta": dump.get("meta"),
    }

    elements: list[BimElement] = []
    # 건물(BUILDING) — 집계값(면적/층/세대/주차).
    elements.append(
        make_element(
            design_input_hash=design_input_hash,
            element_path="building",
            category=BimCategory.BUILDING,
            name=dump.get("title"),
            geometry={
                "total_area_sqm": dump.get("total_area_sqm"),
                "floor_count": dump.get("floor_count"),
                "unit_count": dump.get("unit_count"),
                "parking_count": dump.get("parking_count"),
            },
        )
    )
    # 룸(SPACE) — 파싱된 공간 목록(순서 보존 → 결정적 element_path).
    rooms = dump.get("rooms") or []
    for idx, room in enumerate(rooms):
        elements.append(
            make_element(
                design_input_hash=design_input_hash,
                element_path=f"space[{idx}]",
                category=BimCategory.SPACE,
                name=room.get("name"),
                geometry={"area_sqm": room.get("area_sqm")},
            )
        )

    return BimModel(
        source_kind="design_ingest",
        design_input_hash=design_input_hash,
        project_name=dump.get("title"),
        attributes=attributes,
        elements=elements,
        extras=extras,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3) 매스 dict(IFC 생성 입력) ↔ BimModel  — 소비처 전환(ifc_generator)의 계약 운반체
# ─────────────────────────────────────────────────────────────────────────────
def bimir_from_mass(mass: dict[str, Any]) -> BimModel:
    """AutoDesignEngine 매스 dict → BimModel.

    BUILDING 요소의 geometry에 매스 '전체'를 그대로 담는다(mass_from_bimir가 이걸 되읽어 왕복 무손실).
    추가로 층/슬래브/외벽을 파생요소로 열거한다(부가·서술적 — 왕복 진실원천이 아니라 IR 풍부화용).
    파생요소의 물량 수식은 ifc_generator_service의 BaseQuantities 수식을 미러한다(가짜값 0).

    ★왕복 계약: mass_from_bimir(bimir_from_mass(mass)) == mass (정규화 동일). 그래서 BimIR 경로가
      기존 매스 경로와 '동일 IFC'를 낸다(구조 동등성).
    """
    src = dict(mass)  # 원본 훼손 방지
    design_input_hash = compute_input_hash(src)

    bw = float(src.get("building_width_m", 10.0))
    bd = float(src.get("building_depth_m", 10.0))
    n = int(src.get("num_floors", 5))
    fh = float(src.get("floor_height_m", 3.0))
    wt = _WALL_THICKNESS_M
    st = _SLAB_THICKNESS_M

    elements: list[BimElement] = []
    # BUILDING — 매스 전체 보존(왕복 진실원천).
    elements.append(
        make_element(
            design_input_hash=design_input_hash,
            element_path="building",
            category=BimCategory.BUILDING,
            name="건물",
            geometry=src,
        )
    )

    # 파생 envelope 요소(부가): 층·바닥슬래브·외벽 4면. 수식은 ifc_generator와 미러.
    for i in range(max(1, n)):
        elev = i * fh
        elements.append(
            make_element(
                design_input_hash=design_input_hash,
                element_path=f"storey[{i}]",
                category=BimCategory.STOREY,
                name=f"{i + 1}F",
                storey_index=i,
                geometry={"elevation_m": elev},
            )
        )
        elements.append(
            make_element(
                design_input_hash=design_input_hash,
                element_path=f"storey[{i}]/slab",
                category=BimCategory.SLAB,
                name=f"{i + 1}F-Slab",
                storey_index=i,
                geometry={"width_m": bw, "depth_m": bd, "thickness_m": st},
                quantities={
                    "NetArea": bw * bd,
                    "NetVolume": bw * bd * st,
                    "Perimeter": 2 * (bw + bd),
                },
            )
        )
        # 외벽 4면 — S/N 길이=bw, W/E 길이=bd (generator._make_perimeter_walls 미러).
        for side, wall_len in (("S", bw), ("N", bw), ("W", bd), ("E", bd)):
            elements.append(
                make_element(
                    design_input_hash=design_input_hash,
                    element_path=f"storey[{i}]/wall/{side}",
                    category=BimCategory.WALL,
                    name=f"{i + 1}F-Wall-{side}",
                    storey_index=i,
                    geometry={"side": side, "length_m": wall_len, "height_m": fh, "thickness_m": wt},
                    quantities={
                        "Length": wall_len,
                        "NetSideArea": wall_len * fh,
                        "NetVolume": wall_len * wt * fh,
                    },
                )
            )

    return BimModel(
        source_kind="mass_geometry",
        design_input_hash=design_input_hash,
        project_name=None,
        attributes={"building_width_m": bw, "building_depth_m": bd, "num_floors": n, "floor_height_m": fh},
        elements=elements,
        extras={"mass_geometry": copy.deepcopy(src)},  # ★독립사본 — geometry와 별칭 공유 금지(교차오염 방지)
    )


def mass_from_bimir(model: BimModel) -> dict[str, Any]:
    """BimModel → 매스 dict(IFC 생성 입력) 복원 — BUILDING 요소 geometry가 진실원천.

    BUILDING 요소가 없으면 extras['mass_geometry'] 보존본으로 폴백한다(정직·손실 0).
    """
    for e in model.elements:
        if e.category == BimCategory.BUILDING:
            return copy.deepcopy(e.geometry)  # ★깊은 복사 — 반환본 변이가 IR로 역류하지 않게
    return copy.deepcopy(model.extras.get("mass_geometry", {}))
