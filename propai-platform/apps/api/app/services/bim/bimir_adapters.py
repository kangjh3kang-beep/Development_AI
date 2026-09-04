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
from app.services.bim.ifc_generator_service import IfcGeneratorService
from app.services.cad.provenance import compute_input_hash

if TYPE_CHECKING:  # 타입 힌트 전용 — 런타임 import 회피(무거운 체인 차단)
    from app.services.cad.design_spec import DesignSpec as CadDesignSpec
    from app.services.design_ingest.design_spec import DesignSpec as IngestDesignSpec

# ── 매스 파생요소 기본 두께/치수(미러 상수) ──
# ifc_generator_service.IfcGeneratorService.generate 의 내부 상수와 '동일'해야 매스 파생 요소의
# 물량이 실제 IFC 산출과 일치한다(계약 미러). 아래 값들은 generator 코드에 박힌 리터럴을 그대로 복제.
_WALL_THICKNESS_M = 0.2      # 외벽 두께(generate wall_thickness_m 기본)
_SLAB_THICKNESS_M = 0.2      # 슬래브 두께(generate slab_thickness_m 기본)
_CORE_WALL_THICKNESS_M = 0.2  # 코어 외곽벽 두께(generate 내부 cwt)
_STAIR_THICKNESS_M = 0.15    # 계단참 슬래브 두께(generate 계단 압출 두께)
_PARTITION_THICKNESS_M = 0.15  # 세대 칸막이 두께(generate 내부 pwt)
_WINDOW_WIDTH_M = 1.5        # 창호 폭(generate win_w)
_WINDOW_HEIGHT_M = 1.2       # 창호 높이(generate win_h)
_WINDOW_SILL_M = 0.9         # 창호 하단 높이(generate sill)
_DOOR_WIDTH_M = 0.9          # 현관문 폭(generate door_w)
_DOOR_HEIGHT_M = 2.1         # 현관문 높이(generate door_h)


def _mirror_unit_widths(
    inner_w: float,
    zone_depth: float,
    unit_sequence: list[dict[str, Any]] | None,
    unit_width_m: float,
) -> list[float]:
    """세대 폭 리스트 산출 — IfcGeneratorService._unit_widths 를 '직접 재사용'(진짜 SSOT).

    ★리뷰 반영(MEDIUM — 미러↔generator 발산 방지): 수식을 이 파일에 복제하지 않는다. 복제하면
    한쪽만 고치는 순간 발산하므로, generator의 정적메서드를 그대로 호출해 수식을 하나로
    수렴시킨다(전역 전파방지 — CLAUDE.md 버그수정 정책). 나머지 파생요소(코어·계단·창·칸막이·
    문의 좌표·존재조건) 수식은 generator 루프 본문에 IFC 엔티티 생성과 인터리브되어 있어
    이번 세션에서 안전하게 분리 추출하기엔 회귀 리스크가 크다 — 대신
    tests/test_bimir_consumers.py::test_derived_elements_no_divergence_from_real_generator_ifc
    가 실제 생성기 IFC의 BaseQuantities를 파싱해 미러 산출과 교차검증하는 발산 감지 안전망이다.
    """
    return IfcGeneratorService._unit_widths(inner_w, zone_depth, unit_sequence, unit_width_m)


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
    추가로 층/슬래브/외벽에 더해 코어(COLUMN)·계단(STAIR)·창(WINDOW)·세대칸막이(PARTITION)·문(DOOR)까지
    파생요소로 열거한다(부가·서술적 — 왕복 진실원천이 아니라 IR 풍부화용).

    ★정직한 커버리지 범위(과장 금지 — 리뷰 반영): 파생요소의 '존재조건'(층 조건·개수·클램프
      bw/bd/n/fh)과 '대표 물량'(BaseQuantities 중 면적/체적/길이 등 핵심 스칼라)은
      ifc_generator_service.generate 의 수식을 미러해 정상 입력 범위에서 일치한다 —
      tests/test_bimir_consumers.py 의 발산 감지 테스트가 실제 생성기 IFC의 BaseQuantities를
      파싱해 이를 교차검증한다. 단 일부 부수 스칼라(예: 벽/슬래브 두께를 나타내는 개별 "Width"
      quantity)와 Pset_WallCommon(LoadBearing/IsExternal)은 geometry 필드로는 보존하되 미러
      quantities dict·property set에는 담지 않는다 — "실제 IFC와 완전 동일"이 아니라 "핵심 물량
      항목 미러"다.
    ★왕복 계약: mass_from_bimir(bimir_from_mass(mass)) == mass (정규화 동일). 그래서 BimIR 경로가
      기존 매스 경로와 '동일 IFC'를 낸다(구조 동등성). 파생요소를 늘려도 왕복 진실원천은 BUILDING
      geometry 한 곳뿐이라 왕복은 불변(파생은 읽기 전용 서술) — 클램프는 파생요소 계산에만 적용되고
      BUILDING geometry·extras에 보존되는 원본 src는 클램프되지 않는다.
    ★element_path 인덱스 규율: 층(i)·코어(ci)·창/칸막이/문(면·순번) 인덱스로 결정적 경로를 만든다 —
      같은 매스를 재생성하면 경로·element_id가 불변, 요소 삽입/재정렬 시에는 인덱스가 변한다(정직 표기).
    ★비-슬래브만 열거: generator의 복도/발코니(IfcSlab)는 파생하지 않는다 — SLAB 범주를 '층 바닥'
      의미로 유지하기 위함(코어·계단·창·칸막이·문 5군만 미러). 잔여는 후속 세션 범위.
    """
    src = dict(mass)  # 원본 훼손 방지
    design_input_hash = compute_input_hash(src)

    # ★클램프 정합(리뷰 LOW): generator.generate()의 bw=max(...,1.0)·bd=max(...,1.0)·
    #   n=max(...,1)·fh=max(...,2.0)와 동일 적용 — 퇴화 입력(0/음수/극단값)에서도 파생요소
    #   좌표·물량이 실제 IFC 산출과 발산하지 않는다. BUILDING geometry·extras에 보존되는
    #   원본 src는 이 클램프와 무관(왕복 무손실 유지 — 아래 elements[0].geometry=src 참고).
    bw = max(float(src.get("building_width_m", 10.0)), 1.0)
    bd = max(float(src.get("building_depth_m", 10.0)), 1.0)
    n = max(int(src.get("num_floors", 5)), 1)
    fh = max(float(src.get("floor_height_m", 3.0)), 2.0)
    wt = _WALL_THICKNESS_M
    st = _SLAB_THICKNESS_M
    # 파생요소 존재조건 입력(generate 인자와 동일 키·기본값) — 0/False는 '없음' 게이트(값 손실 아님:
    # 원본 전체는 BUILDING geometry·extras에 보존됨).
    cores = src.get("core_positions")
    core_size = float(src.get("core_size_m", 5.0))
    corridor_width_m = float(src.get("corridor_width_m", 0.0))
    windows_per_side = int(src.get("windows_per_side", 0))
    unit_width_m = float(src.get("unit_width_m", 0.0))
    unit_sequence = src.get("unit_sequence")
    unit_doors = bool(src.get("unit_doors", False))

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
    # n은 위에서 이미 max(...,1) 클램프됨(generator와 동일) — 여기서 재클램프 불필요.
    for i in range(n):
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

        # ── 코어(COLUMN 외곽벽 4면) + 계단(STAIR 2참) — generator cores 블록 미러 ──
        # 코어는 전 층 산출(generator도 층 조건 없음). 위치는 generate와 동일하게 클램프.
        if cores:
            cs = core_size
            cwt = _CORE_WALL_THICKNESS_M
            for ci, c in enumerate(cores):
                cx = float(c.get("x", bw / 2)) - cs / 2
                cy = float(c.get("y", bd / 2)) - cs / 2
                cx = max(wt, min(cx, bw - cs - wt))
                cy = max(wt, min(cy, bd - cs - wt))
                core_walls = (
                    (cx, cy, cs, cwt),                # 하
                    (cx, cy + cs - cwt, cs, cwt),     # 상
                    (cx, cy, cwt, cs),                # 좌
                    (cx + cs - cwt, cy, cwt, cs),     # 우
                )
                for wpi, (wx, wy, ww, wd) in enumerate(core_walls):
                    elements.append(
                        make_element(
                            design_input_hash=design_input_hash,
                            element_path=f"storey[{i}]/core[{ci}]/wall[{wpi}]",
                            category=BimCategory.COLUMN,
                            name=f"{i + 1}F-CoreWall-{ci + 1}-{wpi}",
                            storey_index=i,
                            geometry={"x": wx, "y": wy, "width_m": ww, "depth_m": wd, "height_m": fh},
                            quantities={
                                "Length": fh,
                                "CrossSectionArea": ww * wd,
                                "NetVolume": ww * wd * fh,
                            },
                        )
                    )
                # 계단참 2개(half-flight) — 코어 내부를 가로지르는 얇은 슬래브.
                inset = cwt + 0.05
                half_w = (cs - 2 * inset) / 2
                for sp in range(2):
                    sx = cx + inset + sp * half_w
                    st_z = sp * (fh / 2)
                    st_w = half_w - 0.05
                    st_d = cs - 2 * inset
                    elements.append(
                        make_element(
                            design_input_hash=design_input_hash,
                            element_path=f"storey[{i}]/core[{ci}]/stair[{sp}]",
                            category=BimCategory.STAIR,
                            name=f"{i + 1}F-Stair-{ci + 1}-{sp}",
                            storey_index=i,
                            geometry={
                                "x": sx, "y": cy + inset, "width_m": st_w, "depth_m": st_d,
                                "thickness_m": _STAIR_THICKNESS_M, "elevation_offset_m": st_z,
                            },
                            quantities={
                                "Length": st_d,
                                "GrossArea": st_w * st_d,
                                "NetVolume": st_w * st_d * _STAIR_THICKNESS_M,
                            },
                        )
                    )

        # ── 창호(WINDOW) — generator windows 블록 미러: 1층 제외(i>0), 정면(F)/배면(B) 등간격 ──
        if windows_per_side > 0 and i > 0:
            win_w, win_h, sill = _WINDOW_WIDTH_M, _WINDOW_HEIGHT_M, _WINDOW_SILL_M
            step = bw / (windows_per_side + 1)
            for side_y, side in ((0.0, "F"), (bd - wt, "B")):
                for wj in range(windows_per_side):
                    wx = step * (wj + 1) - win_w / 2
                    wx = max(wt, min(wx, bw - win_w - wt))
                    elements.append(
                        make_element(
                            design_input_hash=design_input_hash,
                            element_path=f"storey[{i}]/window/{side}[{wj}]",
                            category=BimCategory.WINDOW,
                            name=f"{i + 1}F-Win-{side}{wj + 1}",
                            storey_index=i,
                            geometry={
                                "side": side, "x": wx, "y": side_y,
                                "width_m": win_w, "height_m": win_h, "sill_m": sill,
                            },
                            quantities={"Width": win_w, "Height": win_h, "Area": win_w * win_h},
                        )
                    )

        # ── 세대칸막이(PARTITION) + 현관문(DOOR) — generator units 블록 미러: 1층 제외(i>0) ──
        if (unit_width_m > 0 or unit_sequence) and i > 0:
            pwt = _PARTITION_THICKNESS_M
            inner_w = bw - 2 * wt
            cw = min(corridor_width_m, bd) if corridor_width_m > 0 else 0.0
            corr_y0 = (bd - cw) / 2
            corr_y1 = corr_y0 + cw
            part_h = fh - st  # generator: fh - slab_thickness_m
            zones = (
                ("F", wt, max(wt, corr_y0)),
                ("B", min(bd - wt, corr_y1), bd - wt),
            )
            for face, zy0, zy1 in zones:
                zd = zy1 - zy0
                if zd <= 0.3:
                    continue
                widths = _mirror_unit_widths(inner_w, zd, unit_sequence, unit_width_m)
                cursor = wt
                for ui, uw in enumerate(widths):
                    # 세대 사이 칸막이(첫 세대 앞은 외벽이라 생략 — ui>0).
                    if ui > 0:
                        elements.append(
                            make_element(
                                design_input_hash=design_input_hash,
                                element_path=f"storey[{i}]/partition/{face}[{ui}]",
                                category=BimCategory.PARTITION,
                                name=f"{i + 1}F-Part-{face}-{ui}",
                                storey_index=i,
                                geometry={
                                    "face": face, "x": cursor - pwt / 2, "y": zy0,
                                    "length_m": zd, "height_m": part_h, "thickness_m": pwt,
                                },
                                quantities={
                                    "Length": zd,
                                    "Height": part_h,
                                    "NetSideArea": zd * part_h,
                                    "NetVolume": pwt * zd * part_h,
                                },
                            )
                        )
                    # 현관문 — 복도 있을 때만(generator: unit_doors and cw>0).
                    if unit_doors and cw > 0:
                        door_w, door_h = _DOOR_WIDTH_M, _DOOR_HEIGHT_M
                        door_y = zy1 if face == "F" else zy0 - wt
                        dx = cursor + uw / 2 - door_w / 2
                        elements.append(
                            make_element(
                                design_input_hash=design_input_hash,
                                element_path=f"storey[{i}]/door/{face}[{ui}]",
                                category=BimCategory.DOOR,
                                name=f"{i + 1}F-Door-{face}-{ui}",
                                storey_index=i,
                                geometry={
                                    "face": face, "x": dx, "y": door_y,
                                    "width_m": door_w, "height_m": door_h,
                                },
                                quantities={"Width": door_w, "Height": door_h, "Area": door_w * door_h},
                            )
                        )
                    cursor += uw

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
