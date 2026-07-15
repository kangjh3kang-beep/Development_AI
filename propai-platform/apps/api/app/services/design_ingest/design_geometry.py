"""기하 SSOT(DesignGeometry) — 하향식 자동설계의 단일 기하 정본(m 단위).

문제(OMC 감사 확정): 편집기·2D·3D·평면이 각자 스칼라로 따로 그려 SSOT가 없고,
평면 폴리곤 생성기(unit_plan_generator.generate_unit_plan)는 rooms/boundaries/openings
실폴리곤을 보유하나 compose가 호출하지 않아(D3 최대단절) 평형 '개수'까지만 알았다.

본 모듈은 그 두 단절을 메운다(전부 additive·기존 블록 재사용·신규 최소):
 1) DesignGeometry — site/mass/dongs/floors/cores/units[].plan/provenance를 하나의
    정본으로 묶는다. units[].plan은 generate_unit_plan 반환 형식을 **그대로** 재사용한다
    (신규 평면 스키마 정의 금지).
 2) 평면 브리지 — compose() 결과 unit_breakdown(평형 type/area/count)을 받아 평형별로
    generate_unit_plan을 호출해 rooms/boundaries/openings 실폴리곤을 적재한다.
 3) 소형 3종 — orientation_from_polygon(향)·core_type_for_units(코어형)·allowed_uses(허용용도).
 4) LLM 부지맞춤 조정층 — 결정론 평면 위에 LLM 미세조정 패스(opt-in·검증게이트).

무날조: 미확정·미가용은 None/정직표기. 최종 책임은 건축사(AI 보조 초안).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.cad.unit_plan_generator import (
    MAX_UNIT_AREA_SQM,
    MIN_UNIT_AREA_SQM,
    UNIT_CORE_TYPES,
    UNIT_RULE_TABLE,
    _band_for,
    generate_unit_plan,
)

logger = logging.getLogger(__name__)

# 평면 브리지 기본 베이수 — 49~114 전 밴드가 보유한 유일한 공통 베이(49는 2/3, 114는 3/4).
_DEFAULT_BAYS = 3
# 좌표 음수 허용 오차(라운딩 노이즈) — 0 미만이라도 -1cm까지는 0으로 본다.
_COORD_EPS = 0.01


# ─────────────────────────────────────────────────────────────────────────────
# 1. 기하 SSOT 스키마(m 단위 정본)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DesignGeometry:
    """하향식 자동설계의 단일 기하 정본(m 단위).

    site:  부지(폴리곤·폭/깊이·향). mass: compute_optimal_mass 출력 그대로(+north_step_profile).
    dongs: 동별 배치 사각형(compose placement.blocks 그대로). floors: 층 프로파일(층수·층고).
    cores: 코어 배치(compute_core_layout 그대로). units: 평형별 {type,area,plan}(plan은
    generate_unit_plan 반환 형식 그대로 — 신규 정의 금지). provenance: 출처·정직고지.
    """

    site: dict[str, Any] = field(default_factory=dict)
    mass: dict[str, Any] = field(default_factory=dict)
    dongs: list[dict[str, Any]] = field(default_factory=list)
    floors: list[dict[str, Any]] = field(default_factory=list)
    cores: list[dict[str, Any]] = field(default_factory=list)
    units: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# 2. 신규 소형 3종
# ─────────────────────────────────────────────────────────────────────────────
def orientation_from_polygon(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """필지 폴리곤(GeoJSON)의 최장변 방위각 → 건물 주 입면이 향하는 방위(정남=0·서=+).

    최장변(전면도로/장축)에 평행하게 건물을 앉히면 그 법선(정면)이 주 채광면이 된다.
    경위도(EPSG:4326)를 중심위도 기준 등거리 근사로 미터 변환 후 최장 변의 각도를 구하고,
    그 법선을 solar_placement_service의 방위 규약(정남=0·동=−90·서=+90·북=±180)으로 환산한다.
    geometry 없음/계산불가면 None(무날조). dims_from_polygon과 인접한 결정론 기하 함수.
    """
    if not geometry:
        return None
    try:
        from shapely.geometry import shape

        geom = shape(geometry)
        if geom.is_empty:
            return None
        poly = geom if geom.geom_type == "Polygon" else getattr(geom, "convex_hull", geom)
        coords = list(poly.exterior.coords) if hasattr(poly, "exterior") else []
        if len(coords) < 2:
            return None
        minx, miny, maxx, maxy = poly.bounds
        lat0 = (miny + maxy) / 2.0
        m_per_deg_lat = 110540.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
        # 미터 평면 좌표(동=+x, 북=+y)에서 최장 변 탐색.
        pts = [((x - minx) * m_per_deg_lon, (y - miny) * m_per_deg_lat) for x, y in coords]
        best_len = -1.0
        best_dx = best_dy = 0.0
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:], strict=False):
            dx, dy = x1 - x0, y1 - y0
            seg = math.hypot(dx, dy)
            if seg > best_len:
                best_len, best_dx, best_dy = seg, dx, dy
        if best_len <= 0:
            return None
        # 최장변 방향각(동=0·북=90, 수학각). 입면 법선 = 변에 수직.
        edge_deg = math.degrees(math.atan2(best_dy, best_dx))
        normal_math_deg = edge_deg - 90.0  # 변의 한쪽 법선(수학각: 동=0·북=90)
        # 방위(정남=0·서=+) = 90 − 수학각, 그리고 -180~180 정규화. 남향 쪽을 채택(법선 둘 중
        # |facing|이 작은 쪽 = 더 남향). 두 법선은 180° 차이.
        cand = []
        for nrm in (normal_math_deg, normal_math_deg + 180.0):
            facing = ((90.0 - nrm) + 180.0) % 360.0 - 180.0
            cand.append(facing)
        facing = min(cand, key=lambda f: abs(f))
        # 8방위 라벨.
        names = [(-180, "북"), (-135, "북서"), (-90, "서"), (-45, "남서"), (0, "남"),
                 (45, "남동"), (90, "동"), (135, "북동"), (180, "북")]
        label = min(names, key=lambda nv: abs(nv[0] - facing))[1]
        return {
            "facing_deg": round(facing, 1),
            "facing_label": label,
            "longest_edge_m": round(best_len, 2),
            "basis": "필지 폴리곤 최장변 평행 배치 가정 — 주 입면 법선 방위(정남=0·서=+)",
        }
    except Exception as e:  # noqa: BLE001
        logger.info("orientation_from_polygon 산출 생략: %s", str(e)[:120])
        return None


def core_type_for_units(units_per_core: int | None) -> str:
    """코어당 세대수 → 코어형(unit_plan_generator UNIT_CORE_TYPES enum). 결정론·실무 통념.

    2호 이하=계단실형(코어당 2세대 직결), 3호 이상=복도형(편/중복도), 5호 초과(고밀)=타워형.
    미상이면 계단실형(국내 분양 공동주택 표준·보수). 반환은 항상 UNIT_CORE_TYPES 내 값.
    """
    n = int(units_per_core) if isinstance(units_per_core, (int, float)) and units_per_core else 0  # noqa: RUF046
    if n <= 2:
        core = "계단실형"
    elif n <= 5:
        core = "복도형"
    else:
        core = "타워형"
    # UNIT_CORE_TYPES 계약 보증(드리프트 가드).
    return core if core in UNIT_CORE_TYPES else UNIT_CORE_TYPES[0]


# ★국토계획법 시행령 별표(별표2~22) 용도지역별 허용 건축물 — 확인된 대표 양허 항목만 수록(무날조).
#   미확정 용도지역/세부 단서(지구단위·조례 강화)는 None·정직고지. 코드(2R 등)·한글명 모두 매핑.
#   양허(positive list) 방식 — 목록에 있으면 '일반적으로 허용', 없으면 '확인 필요'(불허 단정 금지).
ALLOWED_USES_BY_ZONE: dict[str, list[str]] = {
    # 전용주거 — 단독·공동주택 중심(상가·업무는 원칙 불허).
    "제1종전용주거지역": ["단독주택", "제1종근린생활시설"],
    "제2종전용주거지역": ["단독주택", "공동주택", "제1종근린생활시설"],
    # 일반주거 — 공동주택 허용 폭 확대(종별 규모·층수 차등은 별도).
    "제1종일반주거지역": ["단독주택", "공동주택", "제1종근린생활시설", "제2종근린생활시설"],
    "제2종일반주거지역": ["단독주택", "공동주택", "제1종근린생활시설", "제2종근린생활시설", "오피스텔"],
    "제3종일반주거지역": ["단독주택", "공동주택", "제1종근린생활시설", "제2종근린생활시설", "오피스텔", "업무시설"],
    # 준주거 — 주거+상업 혼합.
    "준주거지역": ["공동주택", "오피스텔", "제1종근린생활시설", "제2종근린생활시설", "판매시설", "업무시설"],
    # 상업 — 상가·업무·주상복합 중심.
    "일반상업지역": ["공동주택", "오피스텔", "판매시설", "업무시설", "숙박시설", "제1종근린생활시설", "제2종근린생활시설"],
    "근린상업지역": ["공동주택", "오피스텔", "판매시설", "업무시설", "제1종근린생활시설", "제2종근린생활시설"],
    # 공업 — 공장·물류·지원시설(주거는 제한적).
    "준공업지역": ["공장", "물류시설", "지식산업센터", "제1종근린생활시설", "제2종근린생활시설", "업무시설"],
}
# zone_code → 한글명 별칭(site_context_from_zone 코드 경로 호환).
# ★프론트 정본(apps/web/lib/kr-building-regulations.ts _LABEL_TO_CODE)이 실제 발행하는
#   코드는 일반상업=GC·준공업=QI다 — 과거 표기(CC/SI)는 하위호환으로 함께 유지.
#   (PR#282 리뷰 적발: 2종 발산으로 GC/QI 리졸브가 무음 no-op이었음)
_ZONE_CODE_ALIAS: dict[str, str] = {
    "1R": "제1종일반주거지역", "2R": "제2종일반주거지역", "3R": "제3종일반주거지역",
    "QR": "준주거지역", "CC": "일반상업지역", "GC": "일반상업지역",
    "NC": "근린상업지역", "SI": "준공업지역", "QI": "준공업지역",
}


def allowed_uses(zone_type: str | None) -> list[str] | None:
    """용도지역(한글명 또는 코드) → 허용 건축물 용도 목록(별표 확인분). 미확정이면 None(무날조).

    양허 방식: 목록은 '일반적으로 허용'되는 대표 용도이며, 목록에 없다고 불허로 단정하지 않는다
    (지구단위·조례·세부 단서는 별도 확인). 미인식 용도지역은 None — 무근거 폴백 금지(정직).
    """
    if not zone_type:
        return None
    key = str(zone_type).replace(" ", "").strip()
    if key in ALLOWED_USES_BY_ZONE:
        return list(ALLOWED_USES_BY_ZONE[key])
    alias = _ZONE_CODE_ALIAS.get(key)
    if alias and alias in ALLOWED_USES_BY_ZONE:
        return list(ALLOWED_USES_BY_ZONE[alias])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. 평면 브리지(D3 해소·핵심) — compose 평형 개수 → generate_unit_plan 실폴리곤
# ─────────────────────────────────────────────────────────────────────────────
def _bays_for_band(band: str) -> int:
    """밴드별 유효 베이 — 기본 3베이, 룰 테이블에 없으면 그 밴드의 최소 보유 베이로 폴백."""
    if (band, _DEFAULT_BAYS) in UNIT_RULE_TABLE:
        return _DEFAULT_BAYS
    supported = sorted(b for (bd, b) in UNIT_RULE_TABLE if bd == band)
    return supported[0] if supported else _DEFAULT_BAYS


def build_unit_plans(unit_breakdown: list[dict] | None, core_type: str | None = None) -> list[dict]:
    """평형 분해(type/area/count) → 평형별 generate_unit_plan 호출 → units[].plan 적재.

    compose가 평형 '개수'까지만 알던 것을 평면 '기하'(rooms/boundaries/openings)까지 산출한다.
    각 평형의 전용면적(area_sqm)이 generate_unit_plan 지원범위(MIN~MAX) 밖이거나 룰 미보유면
    그 평형은 plan=None(정직 — 가짜 평면 금지)로 적재하고 사유를 남긴다.

    반환: [{type, area_sqm, count, plan(generate_unit_plan as_dict|None), plan_error}]
    """
    if not unit_breakdown:
        return []
    ct = core_type if core_type in UNIT_CORE_TYPES else None
    out: list[dict] = []
    for u in unit_breakdown:
        area = u.get("area_sqm")
        utype = u.get("type")
        count = u.get("total_count") or u.get("count") or u.get("count_per_floor")
        entry: dict[str, Any] = {
            "type": utype, "area_sqm": area, "count": count, "plan": None, "plan_error": None,
        }
        try:
            a = float(area) if area is not None else None
        except (TypeError, ValueError):
            a = None
        if a is None or not (MIN_UNIT_AREA_SQM <= a <= MAX_UNIT_AREA_SQM):
            entry["plan_error"] = (
                f"평형 면적 {area} 미상/범위밖({MIN_UNIT_AREA_SQM}~{MAX_UNIT_AREA_SQM}㎡) — 평면 생략"
            )
            out.append(entry)
            continue
        band = _band_for(a)
        bays = _bays_for_band(band)
        # 평형별 코어형: 호출자 지정 우선, 미상이면 면적 밴드로 결정(소형=계단실/대형=복도).
        unit_core = ct or ("복도형" if band in ("84", "114") else "계단실형")
        try:
            plan = generate_unit_plan(a, bays, core_type=unit_core)
            entry["plan"] = plan.as_dict()
            entry["bays"] = bays
            entry["core_type"] = unit_core
        except ValueError as e:
            entry["plan_error"] = str(e)[:160]
        out.append(entry)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 4. LLM 부지맞춤 유기적 조정층(검증게이트·RLVR: LLM proposes / rules verify)
# ─────────────────────────────────────────────────────────────────────────────
def _polys_overlap(a: dict, b: dict) -> bool:
    """두 사각형 실(室)이 면적상 겹치는지(축정렬 AABB) — 미세 접촉(1cm)은 허용."""
    eps = 0.01
    ax0, ay0 = float(a.get("x", 0)), float(a.get("y", 0))
    ax1, ay1 = ax0 + float(a.get("w", 0)), ay0 + float(a.get("h", 0))
    bx0, by0 = float(b.get("x", 0)), float(b.get("y", 0))
    bx1, by1 = bx0 + float(b.get("w", 0)), by0 + float(b.get("h", 0))
    return (ax0 < bx1 - eps and bx0 < ax1 - eps and ay0 < by1 - eps and by0 < ay1 - eps)


def verify_adjusted_plan(
    original_plan: dict, adjusted_rooms: list[dict] | None, *, area_sqm: float
) -> dict:
    """LLM 조정안(rooms)을 결정론 룰로 재검증(RLVR 검증게이트). 위반 시 폐기→원안 폴백.

    검증 항목(할루시네이션·비현실 거부):
      - 형식: rooms 리스트·각 실 x/y/w/h 숫자·음수/과대 거부.
      - 무중첩: 실 간 면적 중첩 금지(AABB).
      - 최소면적: 각 실 면적 ≥ 1.0㎡(0/음수 가짜 실 금지).
      - 면적합 ≤ 전용(원안 본체 면적의 +5% 허용) — 전용면적 부풀리기 금지.
    반환: {ok, rooms(통과 시 조정안·실패 시 원안), violations, fell_back}
    """
    orig_rooms = original_plan.get("rooms") or []
    body_w = float(original_plan.get("body_width_m") or 0.0)
    body_d = float(original_plan.get("body_depth_m") or 0.0)
    envelope = body_w * body_d if (body_w > 0 and body_d > 0) else float(area_sqm or 0.0)
    violations: list[str] = []

    if not isinstance(adjusted_rooms, list) or not adjusted_rooms:
        return {"ok": False, "rooms": orig_rooms, "violations": ["조정안 rooms 없음/형식오류"],
                "fell_back": True}

    cleaned: list[dict] = []
    for i, r in enumerate(adjusted_rooms):
        if not isinstance(r, dict):
            violations.append(f"room[{i}] 형식오류")
            break
        vals = [r.get(k) for k in ("x", "y", "w", "h")]
        if not all(isinstance(v, (int, float)) for v in vals):
            violations.append(f"room[{i}] 좌표 비숫자")
            break
        x, y, w, h = (float(v) for v in vals if isinstance(v, (int, float)))
        if w <= 0 or h <= 0 or x < -_COORD_EPS or y < -_COORD_EPS:
            violations.append(f"room[{i}] 음수/0 치수(거부)")
            break
        if w * h < 1.0:
            violations.append(f"room[{i}] 최소면적 미달(<1㎡)")
            break
        if envelope > 0 and (x + w > body_w * 1.05 + 0.5 or y + h > body_d * 1.05 + 0.5) and body_w > 0:
            violations.append(f"room[{i}] 본체 envelope 초과(과대)")
            break
        cleaned.append({"name": r.get("name", f"실{i+1}"), "x": x, "y": y, "w": w, "h": h})

    if violations:
        return {"ok": False, "rooms": orig_rooms, "violations": violations, "fell_back": True}

    # 무중첩.
    for i in range(len(cleaned)):
        for j in range(i + 1, len(cleaned)):
            if _polys_overlap(cleaned[i], cleaned[j]):
                violations.append(f"room[{i}]·room[{j}] 중첩(거부)")
                break
        if violations:
            break
    # 면적합 ≤ 전용(원안 본체) +5%.
    total_area = sum(r["w"] * r["h"] for r in cleaned)
    if envelope > 0 and total_area > envelope * 1.05 + 0.5:
        violations.append(
            f"실 면적합 {total_area:.1f}㎡ > 전용 envelope {envelope:.1f}㎡(+5%) — 부풀리기 거부"
        )

    if violations:
        return {"ok": False, "rooms": orig_rooms, "violations": violations, "fell_back": True}
    return {"ok": True, "rooms": cleaned, "violations": [], "fell_back": False}


async def llm_adjust_unit_plan(
    unit_entry: dict,
    *,
    site_context: dict,
    similar_seeds: list[dict] | None = None,
) -> dict | None:
    """결정론 평면(unit_entry.plan) 위 LLM 부지맞춤 미세조정 패스(opt-in·best-effort·검증게이트).

    입력: 결정론 layout(plan.rooms) + 부지 맥락(형상·향·접도·인접) + 검색된 유사 시드평면.
    출력: 부지맞춤 조정 제안(실 비례·인접·동선 미세조정) — 단, ★결정론 룰(verify_adjusted_plan)로
    재검증해 위반 시 폐기→결정론 원안 폴백(가짜 통과 금지). BaseInterpreter 단일경유(get_llm)로
    LLM 인프라를 재사용한다(신규 인프라 금지). LLM 미가용/실패/검증실패는 정직표기 후 원안 유지.

    반환: {applied(bool), rooms, verification, note} 또는 None(plan 없음 — 조정 대상 부재).
    """
    plan = unit_entry.get("plan")
    if not plan or not plan.get("rooms"):
        return None
    area_sqm = float(plan.get("unit_area_sqm") or unit_entry.get("area_sqm") or 0.0)
    try:
        adjusted_rooms = await _llm_propose_rooms(plan, site_context, similar_seeds or [])
    except Exception as e:  # noqa: BLE001 — LLM 실패가 생성 결과를 깨면 안 됨
        logger.info("LLM 평면 조정 생략: %s", str(e)[:120])
        return {
            "applied": False, "rooms": plan["rooms"], "verification": None,
            "note": "LLM 조정 미가용 — 결정론 원안 유지(정직)",
        }
    if adjusted_rooms is None:
        return {
            "applied": False, "rooms": plan["rooms"], "verification": None,
            "note": "LLM 조정안 없음 — 결정론 원안 유지(정직)",
        }
    gate = verify_adjusted_plan(plan, adjusted_rooms, area_sqm=area_sqm)
    return {
        "applied": gate["ok"],
        "rooms": gate["rooms"],
        "verification": {"passed": gate["ok"], "violations": gate["violations"],
                         "fell_back": gate["fell_back"]},
        "note": ("LLM 부지맞춤 조정 적용(결정론 룰 검증 통과·AI 보조 초안)" if gate["ok"]
                 else "LLM 조정안 검증 실패 — 결정론 원안 폴백(가짜 통과 금지·정직)"),
    }


async def _llm_propose_rooms(
    plan: dict, site_context: dict, similar_seeds: list[dict]
) -> list[dict] | None:
    """LLM에 결정론 평면+부지맥락+유사시드를 주고 조정 rooms(JSON)를 제안받는다(best-effort).

    BaseInterpreter._get_llm(get_llm 단일경유)로 LLM을 얻어 1회 호출한다. JSON 파싱 실패·빈
    응답·형식오류는 None(호출자 폴백). 신규 LLM 인프라를 만들지 않는다(기존 재사용).
    """
    import json

    from app.services.ai.base_interpreter import BaseInterpreter

    rooms = plan.get("rooms") or []
    seeds_brief = [
        {"rooms": [{"name": r.get("name"), "w": r.get("w"), "h": r.get("h")}
                   for r in (s.get("rooms") or [])[:8]]}
        for s in similar_seeds[:2] if isinstance(s, dict)
    ]
    payload = {
        "deterministic_plan": {
            "unit_area_sqm": plan.get("unit_area_sqm"),
            "body_width_m": plan.get("body_width_m"),
            "body_depth_m": plan.get("body_depth_m"),
            "rooms": rooms,
        },
        "site_context": site_context,
        "similar_seed_plans": seeds_brief,
    }
    system = (
        "당신은 한국 공동주택 평면 설계 보조 AI입니다. 결정론 엔진이 만든 단위세대 평면(rooms)을 "
        "부지 맥락(형상·향·접도·인접)과 유사 사례를 참고해 '실 비례·동선·인접'만 미세조정합니다. "
        "규칙: ① 전용면적 본체(body_width×body_depth) envelope를 넘지 마세요 ② 실 간 겹치지 "
        "마세요 ③ 실 개수·이름은 보존(미세 치수 조정만) ④ 음수/0 치수 금지. "
        "반드시 JSON만 출력하세요: {\"rooms\":[{\"name\":...,\"x\":..,\"y\":..,\"w\":..,\"h\":..}]}"
    )
    user = (
        "다음 결정론 평면을 부지맞춤 미세조정한 rooms를 JSON으로만 반환하세요.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    helper = BaseInterpreter()
    helper.max_tokens = 2048
    llm = helper._get_llm()
    from langchain_core.messages import HumanMessage, SystemMessage

    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    text = getattr(resp, "content", None)
    if isinstance(text, list):  # 일부 provider는 content가 블록 리스트
        text = "".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in text)
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    # 코드펜스 제거 후 첫 JSON 오브젝트 파싱(관대).
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):] if "{" in s else s
    try:
        start, end = s.find("{"), s.rfind("}")
        obj = json.loads(s[start:end + 1]) if start >= 0 and end > start else None
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    out = obj.get("rooms")
    return out if isinstance(out, list) and out else None


# ─────────────────────────────────────────────────────────────────────────────
# 5. 기하 SSOT 어셈블러 — compose 추천후보 + 부지요약 → DesignGeometry 단일 정본
# ─────────────────────────────────────────────────────────────────────────────
def _cores_from_mass(mass: dict, building_use: str) -> list[dict]:
    """1동 매스 기준 코어 배치(compute_core_layout 정본 재사용·DRY). 산출불가면 []."""
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService

        if not all(mass.get(k) for k in ("building_width_m", "building_depth_m", "num_floors")):
            return []
        m = dict(mass)
        m.setdefault(
            "total_floor_area_sqm",
            float(m["building_width_m"]) * float(m["building_depth_m"]) * float(m["num_floors"]),
        )
        core = AutoDesignEngineService.compute_core_layout(
            m, building_use, corridor_type="double", fire_resistant=True
        )
        positions = core.get("core_positions") or []
        return [{
            "num_cores": core.get("num_cores"),
            "corridor_width_m": core.get("corridor_width_m"),
            "corridor_type": core.get("corridor_type"),
            "core_positions": positions,
        }]
    except Exception as e:  # noqa: BLE001 — 코어 산출 실패는 cores=[](평가 비차단·정직)
        logger.info("design_geometry 코어 산출 생략: %s", str(e)[:120])
        return []


def build_design_geometry(
    candidate: dict | None,
    site_summary: dict,
    *,
    mass: dict | None = None,
    site_geometry: dict | None = None,
    building_use: str = "공동주택",
) -> DesignGeometry:
    """compose 추천 후보 + 부지요약(+선택 mass·필지 폴리곤)을 단일 기하 정본으로 조립한다.

    - site: 부지면적·향(orientation_from_polygon·있을 때)·치수.
    - mass: compute_optimal_mass 출력(있으면 그대로) + north_step_profile. 없으면 후보 추정으로 근사.
    - dongs: compose placement.blocks(동별 배치 사각형) 그대로 재사용(신규 정의 금지).
    - floors: 층수·층고 단순 프로파일.
    - cores: 1동 매스 기준 compute_core_layout(정본 재사용).
    - units: 평형별 {type,area,plan} — build_unit_plans 평면 브리지(generate_unit_plan 그대로).

    무날조: 미상은 None/빈 리스트, 결측 사유는 provenance.notes에 정직 기록.
    """
    cand = candidate or {}
    notes: list[str] = []

    # ── site ──
    area = site_summary.get("area_sqm")
    orientation = orientation_from_polygon(site_geometry)
    if site_geometry and orientation is None:
        notes.append("필지 폴리곤 향 산출 실패 — 향 미상(정직)")
    placement = cand.get("placement") or {}
    site_dims = placement.get("site") if isinstance(placement, dict) else None
    site_block: dict[str, Any] = {
        "area_sqm": area,
        "polygon": site_geometry,
        "width_m": (site_dims or {}).get("w"),
        "depth_m": (site_dims or {}).get("d"),
        "orientation": orientation,
    }

    # ── mass ──
    mass_block: dict[str, Any] = dict(mass) if mass else {}
    if not mass_block:
        est_floors = cand.get("estimated_floors")
        gfa = cand.get("estimated_gfa_sqm")
        bldg = placement.get("building") if isinstance(placement, dict) else None
        if isinstance(bldg, dict) and bldg.get("w") and bldg.get("d"):
            mass_block = {
                "building_width_m": bldg["w"], "building_depth_m": bldg["d"],
                "num_floors": est_floors, "total_floor_area_sqm": gfa,
            }
            notes.append("매스는 배치 폴리곤·추정 층수 기준 근사(/mass 미주입)")
        elif est_floors:
            notes.append("매스 폭/깊이 미상 — 층수만 반영(정직)")
            mass_block = {"num_floors": est_floors, "total_floor_area_sqm": gfa}

    # ── dongs / floors ──
    dongs = list(placement.get("blocks") or []) if isinstance(placement, dict) else []
    nf = mass_block.get("num_floors") or cand.get("estimated_floors")
    fh = mass_block.get("floor_height_m") or 3.0
    floors: list[dict[str, Any]] = []
    if isinstance(nf, (int, float)) and nf > 0:
        floors = [{"floor": i + 1, "floor_height_m": fh, "elevation_m": round(i * fh, 2)}
                  for i in range(int(nf))]

    # ── cores ──
    cores = _cores_from_mass(mass_block, building_use) if mass_block else []
    # unit_plan 코어형(계단실/복도/타워)은 corridor_type(double/single)이 아니라 코어당 세대수로 추정.
    units_total = cand.get("estimated_units")
    n_cores = (cores[0].get("num_cores") if cores else None) or 1
    units_per_core = (units_total / (n_cores * int(nf or 1))) if (units_total and nf) else None
    unit_core_type = core_type_for_units(units_per_core)

    # ── units[].plan(평면 브리지·D3 해소) ──
    units = build_unit_plans(cand.get("unit_breakdown"), core_type=unit_core_type)
    if cand.get("unit_breakdown") and not any(u.get("plan") for u in units):
        notes.append("평형 평면 전건 생략 — 평형 면적 범위밖/룰 미보유(정직)")

    return DesignGeometry(
        site=site_block,
        mass=mass_block,
        dongs=dongs,
        floors=floors,
        cores=cores,
        units=units,
        provenance={
            "engine": "design_ingest.design_geometry",
            "unit": "m",
            "disclaimer": "AI 보조 초안 — 기하 SSOT(매스·배치·평면). 최종 책임은 건축사.",
            "reused": ["compute_optimal_mass", "compose.placement",
                       "compute_core_layout", "generate_unit_plan"],
            "unit_core_type": unit_core_type,
            "notes": notes,
        },
    )
