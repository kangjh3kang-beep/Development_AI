"""ParcelGraph — 다필지 인접 그래프·articulation point(핵심필지)·N-1 시나리오(W2-5, 순수함수).

배경(v4.0 P2 실용 1차): 1·2차 실증에서 확정된 공백은 '다필지 조합 그 자체의 위상 구조'였다.
기존 3종 재료는 이미 있었다 —
  · upzoning_potential.py: adjacency_contiguous(bool|None) 를 *주입받기만* 하고 계산하지 않는다.
  · routers/auto_zoning.py:_parcel_adjacency: geometry 2개 이상일 때 union-find(거리<=6m 허용
    오차)로 '연결요소 수'만 낸다 — 어떤 필지가 인접에 핵심적인지(제거 시 끊기는지)는 모른다.
  · usable_area.py:simulate_exclusion: 필지 제외 시 면적 3계층 재정산(what-if)은 하지만
    '인접 위상'은 전혀 보지 않는다(순수 면적 집계).
이 모듈은 그 공백 — 그래프 구조(간선·연결성분·articulation point)와 도로접면 의존성 —
을 다룬다. networkx는 쓰지 않는다(요구사항 규모=필지 수십 개, 의존성 추가 없이 순수 파이썬
제거-재탐색 O(V·(V+E))로 충분 — 스파이크 결정, requirements 변경 없음).

무날조 원칙:
  · 간선(edge) = 두 필지 경계의 실제 접촉(shapely touches()+intersection 길이>0)만 인정한다.
    bbox(외접상자)만 겹치고 실제 도형이 이격돼 있으면 touches() 자체가 False라 간선을 만들지
    않는다. 점(코너) 접촉은 intersection 길이가 0이라 자동 제외된다(스침 배제).
  · geometry 가 없는 필지는 그래프에서 UNKNOWN 처리한다 — 있는 것처럼 간선을 지어내지 않는다
    (그 필지의 연결성분/articulation 판정은 산출하지 않고 'geometry 미확보' 로 명세한다).
  · road_frontage(도로접면)가 미상(None)인 필지는 '맹지 아님'으로 단정하지 않는다(landlocked
    판정은 True/False/None 3값 — 확정 정보가 없으면 None=미상).
  · critical_parcel_score 는 정성 등급(CRITICAL/IMPORTANT/NORMAL)이며 산식은 아래 _grade_parcel
    docstring 에 명시한다(가중치 날조 방지 — 코드가 곧 근거).

성능 가드: 필지 200개 초과 시 그래프 산출을 생략한다(status="skipped_large_set"). 제거-재탐색
  기반 N-1/articulation은 O(V²·(V+E)) 규모라 대량 배치(과거 5000행 배치 메모리 교훈)에는
  부적합 — 호출부가 소규모(수십 필지) 조합에서만 쓰는 것을 전제로 한다.
"""
from __future__ import annotations

from typing import Any

# 필지 수 상한 — 초과 시 그래프 생략(제거-재탐색 O(V²·(V+E)) 비용 보호).
MAX_PARCELS_FOR_GRAPH = 200

# 좌표 스냅 격자(도 단위, ~1cm) — 부동소수 연산 오차(예: 127.001+0.001 != 127.002)로 실제
# 맞닿은 두 필지가 touches() 판정에서 미세 중첩/미세 간격으로 새는 것을 흡수한다. 실제 물리적
# 이격(도로 등, 통상 수십cm~수m 이상)은 이 격자보다 훨씬 커서 영향받지 않는다(무날조 — 실측
# 간격을 지우는 게 아니라 좌표 표현 오차만 정규화).
_SNAP_GRID_DEG = 1e-7


def _parcel_id(p: dict, idx: int) -> str:
    """필지 식별자 — pnu 우선, 없으면 인덱스 폴백(입력 순서 내 유일성 보장)."""
    pnu = p.get("pnu")
    return str(pnu) if pnu not in (None, "") else f"__idx{idx}__"


def _area_sqm(p: dict) -> float | None:
    """필지 면적(㎡) — area_sqm/areaSqm/area 순 탐색. 미확보·비양수는 None(0 날조 금지)."""
    for key in ("area_sqm", "areaSqm", "area"):
        v = p.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return None


def _far_pct(p: dict) -> float | None:
    """필지 실효 용적률(%) — effective_far_pct 우선, 없으면 _far_eff(라우터 보강 필드명) 폴백."""
    for key in ("effective_far_pct", "_far_eff", "far_eff_pct"):
        v = p.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _road_frontage(p: dict) -> bool | None:
    """도로접면 여부 — road_frontage 우선, 없으면 road_contact(access_basis 관례명) 폴백. 미상=None."""
    if "road_frontage" in p and p.get("road_frontage") is not None:
        return bool(p.get("road_frontage"))
    if "road_contact" in p and p.get("road_contact") is not None:
        return bool(p.get("road_contact"))
    return None


def _to_polygon(geom: Any) -> Any | None:
    """GeoJSON dict 또는 shapely 지오메트리 → buffer(0)로 유효화한 shapely 도형.

    파싱 실패·None 입력·빈 도형은 None(무날조 — 그래프에서 UNKNOWN 처리, 간선 생성 안 함).
    """
    if geom is None:
        return None
    try:
        from shapely.geometry import shape as shapely_shape
        from shapely.geometry.base import BaseGeometry

        if isinstance(geom, dict):
            poly = shapely_shape(geom)
        elif isinstance(geom, BaseGeometry):
            poly = geom
        else:
            return None
        fixed = poly.buffer(0)
        if fixed.is_empty:
            return None
        try:
            from shapely import set_precision

            fixed = set_precision(fixed, _SNAP_GRID_DEG)
        except Exception:  # noqa: BLE001 — 정밀도 스냅 실패해도 buffer(0) 결과로 계속 진행
            pass
        return None if fixed.is_empty else fixed
    except Exception:  # noqa: BLE001 — 형상 파싱 실패는 정직 None
        return None


def _looks_like_lonlat(poly: Any) -> bool:
    """좌표가 경위도(WGS84, ±180/±90) 범위인지 휴리스틱 판정 — 미터 근사환산 적용 여부 결정용."""
    try:
        minx, miny, maxx, maxy = poly.bounds
        return abs(minx) <= 180 and abs(maxx) <= 180 and abs(miny) <= 90 and abs(maxy) <= 90
    except Exception:  # noqa: BLE001
        return False


def _contact_length(a: Any, b: Any) -> float:
    """실접촉(경계) 길이 — touches()로 '접점 존재·내부 비중첩'을 먼저 확인한 뒤에만
    intersection 길이를 잰다. 점(코너) 접촉은 길이 0이라 호출부에서 자동 제외된다.
    bbox만 겹치고 실제 도형이 떨어져 있으면 touches() 자체가 False라 0.0을 반환한다.
    """
    try:
        if not a.touches(b):
            return 0.0
        inter = a.intersection(b)
        return float(inter.length or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _components(node_ids: list[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    """무방향 그래프 연결성분 — 순수 BFS(의존성 0)."""
    remaining = set(node_ids)
    comps: list[list[str]] = []
    while remaining:
        start = next(iter(remaining))
        stack = [start]
        comp: list[str] = []
        seen = {start}
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adjacency.get(cur, ()):
                if nb in remaining and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        remaining -= set(comp)
        comps.append(sorted(comp))
    return comps


def _articulation_points(node_ids: list[str], adjacency: dict[str, set[str]]) -> list[str]:
    """제거-재탐색 기반 articulation point(핵심필지) 판정 — O(V·(V+E)).

    v가 articulation point ⇔ v를 제거한 뒤(나머지 정점만으로) 연결성분 수가
    '전체 그래프(v 포함) 성분 수'보다 늘어난다. 이 일반형 판정식은 여러 연결성분이
    섞여 있어도(비인접 그룹 혼재) 정확하다 — v를 포함한 성분만 분리 가능성이 있고
    나머지 성분 수는 변하지 않기 때문(증명: 모듈 docstring 참조 불요 — 표준 성질).
    """
    base_count = len(_components(node_ids, adjacency))
    points: list[str] = []
    for v in node_ids:
        remaining = [x for x in node_ids if x != v]
        after_count = len(_components(remaining, adjacency))
        if after_count > base_count:
            points.append(v)
    return points


def _grade_parcel(
    is_articulation: bool,
    is_sole_frontage: bool,
    has_frontage_nonsole: bool,
    area_share: float | None,
    avg_share: float,
) -> tuple[float, str]:
    """critical_parcel_score 산식(명시) + 정성 등급.

    점수(정렬·표시용 보조 지표 — 등급 결정은 아래 규칙이 우선):
      score = 0.5·I(articulation) + 0.35·I(sole_frontage) + 0.15·area_share(0~1, 미상=0)

    등급 규칙(정성, 임계값 날조 금지 — 명시적 불리언 게이트):
      CRITICAL  — articulation point 이거나(제거 시 그룹 분리) 자기 그룹 내 '유일한'
                  도로접면 필지(제거 시 그룹 전체 맹지화 직결)인 경우.
      IMPORTANT — CRITICAL 아니지만, (a) 자기 그룹 평균 면적지분보다 큰 면적을 차지하거나
                  (b) 도로접면을 보유(단, 유일하지 않음 — 다른 접면 필지 존재)한 경우.
      NORMAL    — 그 외(제거해도 그룹 연결·접면·규모에 두드러진 영향 없음).
    """
    share = area_share or 0.0
    score = 0.5 * (1.0 if is_articulation else 0.0) + 0.35 * (1.0 if is_sole_frontage else 0.0) + 0.15 * share
    if is_articulation or is_sole_frontage:
        grade = "CRITICAL"
    elif (area_share is not None and area_share > avg_share) or has_frontage_nonsole:
        grade = "IMPORTANT"
    else:
        grade = "NORMAL"
    return round(score, 4), grade


def build_parcel_graph(parcels: list[dict[str, Any]] | None) -> dict[str, Any]:
    """다필지 인접 그래프 + articulation point + 도로접면 의존 + N-1 시나리오(순수함수·외부콜 0).

    parcels: [{pnu, geometry(GeoJSON dict|shapely 도형), road_frontage: bool|None,
               area_sqm: float|None, effective_far_pct: float|None}, ...]

    반환: {status, parcel_count, ids, geometry_unknown_pnus, edges, adjacency,
           connected_components, component_count, articulation_points,
           road_dependency, critical_parcels, critical_scores, n_minus_1,
           warnings, basis}
    """
    items = list(parcels or [])
    n_total = len(items)
    warnings: list[str] = []

    if n_total > MAX_PARCELS_FOR_GRAPH:
        return {
            "status": "skipped_large_set",
            "parcel_count": n_total,
            "note": (
                f"{n_total}개 필지가 상한({MAX_PARCELS_FOR_GRAPH})을 초과해 인접 그래프 산출을 "
                "생략합니다(제거-재탐색 연산 비용 보호 — 대량 배치는 분할 호출 필요)."
            ),
            "basis": f"성능 가드 — parcel_count > {MAX_PARCELS_FOR_GRAPH}",
        }

    if n_total == 0:
        return {
            "status": "empty",
            "parcel_count": 0,
            "ids": [], "geometry_unknown_pnus": [], "edges": [], "adjacency": {},
            "connected_components": [], "component_count": 0, "articulation_points": [],
            "road_dependency": {"frontage_pnus": [], "frontage_unknown_pnus": [],
                                 "landlocked_pnus": [], "unknown_landlocked_pnus": [],
                                 "access_path": {}},
            "critical_parcels": {"CRITICAL": [], "IMPORTANT": [], "NORMAL": []},
            "critical_scores": {},
            "n_minus_1": {},
            "warnings": [], "basis": "입력 필지 없음",
        }

    ids = [_parcel_id(p, i) for i, p in enumerate(items)]
    polys = {ids[i]: _to_polygon(items[i].get("geometry")) for i in range(n_total)}
    areas = {ids[i]: _area_sqm(items[i]) for i in range(n_total)}
    fars = {ids[i]: _far_pct(items[i]) for i in range(n_total)}
    frontage = {ids[i]: _road_frontage(items[i]) for i in range(n_total)}

    known_ids = [i for i in ids if polys[i] is not None]
    unknown_ids = [i for i in ids if polys[i] is None]
    if unknown_ids:
        warnings.append(
            f"{len(unknown_ids)}개 필지의 형상(geometry)이 없어 인접 그래프에서 제외했습니다"
            "(간선 날조 금지 — 해당 필지는 UNKNOWN으로 표기)."
        )

    # ── 1) 간선(edge) 판정 — 실접촉(touches + intersection 길이>0)만 인정 ──
    edges: list[dict[str, Any]] = []
    adjacency: dict[str, set[str]] = {i: set() for i in known_ids}
    for a_idx in range(len(known_ids)):
        for b_idx in range(a_idx + 1, len(known_ids)):
            a_id, b_id = known_ids[a_idx], known_ids[b_idx]
            length = _contact_length(polys[a_id], polys[b_id])
            if length > 0:
                adjacency[a_id].add(b_id)
                adjacency[b_id].add(a_id)
                edge: dict[str, Any] = {"a": a_id, "b": b_id, "contact_length": round(length, 6)}
                if _looks_like_lonlat(polys[a_id]):
                    import math

                    lat = (polys[a_id].centroid.y + polys[b_id].centroid.y) / 2
                    m_per_deg = 111_000 * math.cos(math.radians(lat))
                    edge["contact_length_m_approx"] = round(length * m_per_deg, 1)
                edges.append(edge)

    # ── 2) 연결성분·articulation point ──
    components = _components(known_ids, adjacency)
    articulation = _articulation_points(known_ids, adjacency)
    articulation_set = set(articulation)
    comp_of: dict[str, int] = {}
    for c_idx, comp in enumerate(components):
        for pid in comp:
            comp_of[pid] = c_idx

    # ── 3) 도로접면 의존 — 그룹(연결성분) 단위 접면 상태 + 필지별 최단 접경로 ──
    frontage_true = {i for i in ids if frontage.get(i) is True}
    frontage_unknown = {i for i in ids if frontage.get(i) is None}

    comp_status: dict[int, str] = {}  # "has_frontage" | "confirmed_landlocked" | "unknown"
    for c_idx, comp in enumerate(components):
        flags = [frontage.get(m) for m in comp]
        if any(f is True for f in flags):
            comp_status[c_idx] = "has_frontage"
        elif all(f is False for f in flags):
            comp_status[c_idx] = "confirmed_landlocked"
        else:
            comp_status[c_idx] = "unknown"

    def _access_path_for(target: str, comp: list[str]) -> list[str] | None:
        """target에서 그룹 내 도로접면 필지까지의 최단(hop) 경로 — 다중소스 BFS."""
        sources = [m for m in comp if frontage.get(m) is True]
        if not sources:
            return None
        adj_local = adjacency
        parent: dict[str, str | None] = {s: None for s in sources}
        queue = list(sources)
        qi = 0
        found = target in parent
        while qi < len(queue) and not found:
            cur = queue[qi]
            qi += 1
            for nb in adj_local.get(cur, ()):
                if nb not in parent:
                    parent[nb] = cur
                    if nb == target:
                        found = True
                        break
                    queue.append(nb)
        if target not in parent:
            return None
        path = [target]
        node = target
        while parent.get(node) is not None:
            node = parent[node]
            path.append(node)
        path.reverse()
        return path

    access_path: dict[str, list[str] | None] = {}
    landlocked: dict[str, bool | None] = {}
    for i in ids:
        if frontage.get(i) is True:
            access_path[i] = [i]
            landlocked[i] = False
            continue
        if i not in comp_of:  # geometry 미확보 — 그래프 판정 불가
            access_path[i] = None
            landlocked[i] = None
            continue
        status = comp_status[comp_of[i]]
        if status == "has_frontage":
            access_path[i] = _access_path_for(i, components[comp_of[i]])
            landlocked[i] = access_path[i] is None  # 이론상 같은 성분이면 항상 경로 존재
        elif status == "confirmed_landlocked":
            access_path[i] = None
            landlocked[i] = True
        else:
            access_path[i] = None
            landlocked[i] = None

    road_dependency = {
        "frontage_pnus": sorted(frontage_true),
        "frontage_unknown_pnus": sorted(frontage_unknown),
        "landlocked_pnus": sorted(k for k, v in landlocked.items() if v is True),
        "unknown_landlocked_pnus": sorted(k for k, v in landlocked.items() if v is None),
        "access_path": access_path,
        "basis": (
            "그룹(연결성분) 내 최소 1필지가 도로접면(True)이면 나머지는 인접 경유로 접근 가능(맹지 "
            "아님)으로 판정한다. 그룹 전원이 명시적 False면 확정 맹지, True 없이 미상(None)이 섞이면 "
            "확정하지 않고 미상 처리한다(과대낙관 금지)."
        ),
    }

    # ── 4) 필지별 critical_parcel_score + 등급 ──
    total_known_area = sum(a for a in (areas.get(i) for i in ids) if a is not None) or 0.0
    comp_avg_share: dict[int, float] = {}
    sole_frontage_of: dict[int, str | None] = {}
    for c_idx, comp in enumerate(components):
        comp_avg_share[c_idx] = 1.0 / len(comp) if comp else 0.0
        members_with_frontage = [m for m in comp if frontage.get(m) is True]
        sole_frontage_of[c_idx] = members_with_frontage[0] if len(members_with_frontage) == 1 and len(comp) >= 2 else None

    critical_scores: dict[str, dict[str, Any]] = {}
    critical_parcels: dict[str, list[str]] = {"CRITICAL": [], "IMPORTANT": [], "NORMAL": []}
    for i in ids:
        area_share = (areas[i] / total_known_area) if (areas[i] is not None and total_known_area > 0) else None
        is_articulation = i in articulation_set
        c_idx = comp_of.get(i)
        is_sole_frontage = (c_idx is not None) and (sole_frontage_of.get(c_idx) == i)
        has_frontage_nonsole = frontage.get(i) is True and not is_sole_frontage
        avg_share = comp_avg_share.get(c_idx, 0.0) if c_idx is not None else 0.0
        score, grade = _grade_parcel(is_articulation, is_sole_frontage, has_frontage_nonsole, area_share, avg_share)
        critical_scores[i] = {
            "score": score, "grade": grade, "is_articulation": is_articulation,
            "is_sole_frontage": is_sole_frontage, "area_share": round(area_share, 4) if area_share is not None else None,
        }
        critical_parcels[grade].append(i)

    # ── 5) N-1 시나리오 — 필지별 제거 시 연결성·면적·실효한도(면적가중 근사) delta ──
    baseline_comp_count = len(components)
    total_area_all = sum(a for a in (areas.get(i) for i in ids) if a is not None) or 0.0

    def _blended_far(subset_ids: list[str]) -> float | None:
        pairs = [(areas[i], fars[i]) for i in subset_ids if areas.get(i) is not None and fars.get(i) is not None]
        area_sum = sum(a for a, _ in pairs)
        if not pairs or area_sum <= 0:
            return None
        return sum(a * f for a, f in pairs) / area_sum

    blended_before = _blended_far(ids)

    n_minus_1: dict[str, dict[str, Any]] = {}
    for r in ids:
        others = [i for i in ids if i != r]
        remaining_area = sum(a for a in (areas.get(i) for i in others) if a is not None) if others else 0.0
        area_delta = (remaining_area - total_area_all) if (areas.get(r) is not None or total_area_all) else None
        blended_after = _blended_far(others) if others else None
        far_delta = (blended_after - blended_before) if (blended_after is not None and blended_before is not None) else None

        if r not in comp_of:
            # geometry 미확보 필지 — 그래프에 애초 포함 안 됨(연결성 영향 판단 불가, 미상 정직 표기).
            n_minus_1[r] = {
                "remains_connected": None, "components_after": None,
                "remaining_area_sqm": round(remaining_area, 2) if others else 0.0,
                "area_delta_sqm": round(area_delta, 2) if area_delta is not None else None,
                "effective_far_pct_before": round(blended_before, 1) if blended_before is not None else None,
                "effective_far_pct_after": round(blended_after, 1) if blended_after is not None else None,
                "effective_far_pct_delta": round(far_delta, 1) if far_delta is not None else None,
                "newly_landlocked_pnus": None,
                "note": "형상(geometry) 미확보 필지 — 연결성 영향은 판단 불가(미상)입니다.",
            }
            continue

        remaining_known = [i for i in known_ids if i != r]
        if not remaining_known:
            n_minus_1[r] = {
                "remains_connected": None, "components_after": 0,
                "remaining_area_sqm": round(remaining_area, 2) if others else 0.0,
                "area_delta_sqm": round(area_delta, 2) if area_delta is not None else None,
                "effective_far_pct_before": round(blended_before, 1) if blended_before is not None else None,
                "effective_far_pct_after": round(blended_after, 1) if blended_after is not None else None,
                "effective_far_pct_delta": round(far_delta, 1) if far_delta is not None else None,
                "newly_landlocked_pnus": None,
                "note": "제거 후 형상 확보 필지가 남지 않아 연결성 판단이 성립하지 않습니다.",
            }
            continue

        sub_adjacency = {i: {nb for nb in adjacency.get(i, ()) if nb != r} for i in remaining_known}
        sub_components = _components(remaining_known, sub_adjacency)
        after_count = len(sub_components)
        remains_connected = after_count <= baseline_comp_count

        # 새로 맹지화되는 필지 — 제거 전 landlocked!=True 였다가 제거 후 True로 바뀌는 필지만.
        sub_comp_of: dict[str, int] = {}
        for c_idx, comp in enumerate(sub_components):
            for pid in comp:
                sub_comp_of[pid] = c_idx
        sub_comp_status: dict[int, str] = {}
        for c_idx, comp in enumerate(sub_components):
            flags = [frontage.get(m) for m in comp]
            if any(f is True for f in flags):
                sub_comp_status[c_idx] = "has_frontage"
            elif all(f is False for f in flags):
                sub_comp_status[c_idx] = "confirmed_landlocked"
            else:
                sub_comp_status[c_idx] = "unknown"

        newly_landlocked: list[str] = []
        for i in remaining_known:
            if frontage.get(i) is True:
                continue  # 자체 접면 보유 — 맹지화 대상 아님
            was_landlocked = landlocked.get(i)
            status_after = sub_comp_status[sub_comp_of[i]]
            is_landlocked_after = status_after == "confirmed_landlocked"
            if is_landlocked_after and was_landlocked is not True:
                newly_landlocked.append(i)

        n_minus_1[r] = {
            "remains_connected": remains_connected,
            "components_after": after_count,
            "remaining_area_sqm": round(remaining_area, 2) if others else 0.0,
            "area_delta_sqm": round(area_delta, 2) if area_delta is not None else None,
            "effective_far_pct_before": round(blended_before, 1) if blended_before is not None else None,
            "effective_far_pct_after": round(blended_after, 1) if blended_after is not None else None,
            "effective_far_pct_delta": round(far_delta, 1) if far_delta is not None else None,
            "newly_landlocked_pnus": sorted(newly_landlocked),
        }

    return {
        "status": "ok",
        "parcel_count": n_total,
        "ids": ids,
        "geometry_unknown_pnus": unknown_ids,
        "edges": edges,
        "adjacency": {i: sorted(adjacency[i]) for i in known_ids},
        "connected_components": components,
        "component_count": len(components),
        "articulation_points": sorted(articulation),
        "road_dependency": road_dependency,
        "critical_parcels": critical_parcels,
        "critical_scores": critical_scores,
        "n_minus_1": n_minus_1,
        "warnings": warnings,
        "basis": (
            "간선=경계 실접촉(shapely touches+intersection 길이>0, bbox 스침·코너 접촉 제외). "
            "articulation point=제거-재탐색(O(V·(V+E)))으로 연결성분 증가 여부 판정. "
            "critical_parcel_score 산식은 _grade_parcel 참조(articulation·유일접면·면적지분 가중)."
        ),
    }
