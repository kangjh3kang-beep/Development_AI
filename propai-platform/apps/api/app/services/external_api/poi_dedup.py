"""학교 POI 모학교 병합(dedup) 헬퍼 — 입지분석 학교 카운트의 단일 진실원천(SSOT).

★근본원인(실증): 종합분석 입지점수가 학교 POI를 **과카운트**했다. kakao_local·VWORLD가
category/keyword 검색 결과를 이름병합 없이 raw append해, 대보초등학교 1곳이 본교·운동장·
병설유치원·체육관·분교 등 부속시설로 5개교로 집계돼 입지점수(학군 보너스)를 부풀렸다.

이 모듈은 "학교 POI 목록 → 고유 모학교 목록"의 단일 진실원천이다. 그간 kakao_local_service·
land_info_service·comprehensive_analysis_service·site_score_service가 각자 raw `len(schools)`로
과카운트하던 것을 여기로 수렴시켜, 한 곳(dedup 로직)을 고치면 전 소비처가 따라오게 한다
(전역 전파방지 — CLAUDE.md 버그정책 '공용화 수정').

병합 계약(둘 다 충족해야 병합):
  (1) **정규화 모학교명 동일** — 부속·분교 접미를 제거해 얻은 '모학교명'이 같아야 한다.
  (2) **좌표 근접**(반경 radius_m 이내) — 좌표가 한쪽이라도 없으면 (2)는 생략하고 모학교명만으로
      병합(land_info schools는 distance_m만 있고 좌표가 없다). POI 목록은 이미 반경검색(≤1~2km)
      결과라 같은 모학교명이면 사실상 동일 학교다.

★오탐 차단(계획 W1-2): 이름 다른 실제 학교(예 '대보초' vs '구룡포초')는 근접해도 병합하지
  않는다(모학교명 일치 필수). **근접만으로는 절대 병합하지 않는다.** 학교 토큰이 없어 모학교명을
  못 얻은 이름은 정규화명 그대로 두어 고유 취급(모르는 것을 함부로 합치지 않는다).

계산 로직 없음 — 문자열 정규화 + 좌표거리 비교만(import 부작용·I/O·LLM 호출 없음, pure).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

_WS = re.compile(r"\s+")

# 학교 유형 코어 토큰(집합 — 튜플 순서 무관). mother_school_name은 이름에서 **가장 우측(최종)**
# 코어에서 절단해 '모학교명'을 얻는다. 예: '대보초등학교병설유치원'→'대보초등학교'(부속 제거),
# '서울교육대학교부설초등학교'→그대로(부설초는 모대학과 별개교 → 최종코어 '초등학교'로 분리).
# (어떤 _ATTACH_TOKENS도 코어를 부분문자열로 포함하지 않아 부속 뒤에서 코어 오인식 없음.)
_SCHOOL_CORE: tuple[str, ...] = (
    "초등학교", "중학교", "고등학교", "특수학교", "대학교",
)

# 축약형(초/중/고) → 정규형. 코어 토큰이 없을 때만(예 '대보초 분교') 폴백 적용.
_SCHOOL_CORE_ABBR: tuple[tuple[str, str], ...] = (
    ("초", "초등학교"), ("중", "중학교"), ("고", "고등학교"),
)

# 부속/분교/지점 접미 토큰 — 모학교명 뒤에 붙는다. 축약형 폴백의 안전가드로도 쓴다
# (이 토큰이 뒤따를 때만 '초/중/고' 축약을 학교로 인정 → 일반 지명의 '고'·'중' 오탐 방지).
_ATTACH_TOKENS: tuple[str, ...] = (
    "병설유치원", "병설", "분교", "분실", "운동장", "대운동장", "체육관", "강당",
    "후문", "정문", "별관", "본관", "신관", "구관", "주차장", "급식소", "도서관", "기숙사",
)

# 좌표 근접 병합 기본 반경(m). 부속시설·분교는 통상 본교와 수백 m 이내.
_DEFAULT_RADIUS_M = 250.0


def mother_school_name(name: str | None) -> str:
    """학교 POI 이름 → 모학교명(부속·분교 접미 제거). 학교 토큰 미검출 시 정규화명 그대로.

    예: '대보초등학교 운동장'·'대보초등학교병설유치원'·'대보초등학교 구만분교'·'대보초 분교'
        → 모두 '대보초등학교'. '구룡포초등학교' → '구룡포초등학교'(다른 학교, 병합 안 함).
    """
    if not name:
        return ""
    n = _WS.sub("", str(name))
    # 1) 정규 코어 토큰: **가장 우측(최종)** 코어에서 잘라 모학교명 확정(그 뒤 부속·분교 제거).
    #    최초가 아니라 최종을 쓰는 이유 — '서울교육대학교부설초등학교'는 모대학과 행정상 별개교이므로
    #    최종코어 '초등학교'에서 절단해 그대로 보존한다. 최초코어 '대학교'에서 자르면 '서울교육대학교'로
    #    붕괴해 모대학과 과병합되는 회귀(정답 2 → 오답 1). 부속(운동장·병설유치원·분교)은 코어 뒤
    #    접미라 최종코어가 그 부속 앞이므로 그대로 잘려나간다(대보초 5→1 무회귀).
    best_i = -1
    best_core = ""
    for core in _SCHOOL_CORE:
        i = n.rfind(core)
        if i > best_i:
            best_i, best_core = i, core
    if best_i >= 0:
        return n[:best_i] + best_core
    # 2) 축약형 폴백(코어 없음): '초/중/고' 뒤가 부속토큰이거나 문자열 끝일 때만 학교로 인정.
    for abbr, full in _SCHOOL_CORE_ABBR:
        i = n.find(abbr)
        if i < 0:
            continue
        rest = n[i + len(abbr):]
        if rest == "" or any(rest.startswith(t) for t in _ATTACH_TOKENS):
            return n[:i] + full
    # 3) 학교 토큰 미검출 — 정규화명 그대로(오병합 방지: 알 수 없으면 고유 취급).
    return n


def _coord(poi: Any) -> tuple[float, float] | None:
    """POI에서 (위도, 경도) 추출 — lat/lon 우선, 없으면 y/x(카카오·fixture 규약: x=경도, y=위도)."""
    if not isinstance(poi, dict):
        return None
    lat = poi.get("lat")
    lon = poi.get("lon")
    if lat is None and lon is None:
        lat, lon = poi.get("y"), poi.get("x")
    if lat is None or lon is None:
        return None
    try:
        return (float(lat), float(lon))
    except (TypeError, ValueError):
        return None


def _dist_of(poi: Any) -> float | None:
    """POI의 distance_m(숫자) — 대표(최근접) 선정용. 없으면 None."""
    if not isinstance(poi, dict):
        return None
    d = poi.get("distance_m")
    if d is None:
        return None
    try:
        return float(d)
    except (TypeError, ValueError):
        return None


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """두 (위도, 경도) 사이 대권거리(m)."""
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def dedup_school_cluster(
    pois: Iterable[Any] | None, *, radius_m: float = _DEFAULT_RADIUS_M
) -> list[Any]:
    """학교 POI 목록 → 고유 '모학교' 대표 목록(부속시설·분교 병합).

    병합 조건: 정규화 모학교명 동일 AND 좌표 근접(반경 radius_m). 좌표가 한쪽이라도 없으면
    모학교명만으로 병합(land_info schools엔 좌표가 없다). 이름 불일치는 절대 병합하지 않으며,
    근접만으로도 병합하지 않는다(오탐 차단). 대표는 각 클러스터의 최근접(distance_m 최소) POI,
    반환 순서는 입력 첫 등장 순서(카카오는 거리순이라 첫 클러스터가 최근접 학교).

    멱등: 이미 dedup된(모학교 1개씩) 목록을 다시 넣어도 동일 목록을 돌려준다.
    """
    clusters: list[dict[str, Any]] = []  # {"key", "coord", "rep", "rep_dist"}
    for poi in pois or []:
        name = poi.get("name") if isinstance(poi, dict) else None
        key = mother_school_name(name)
        coord = _coord(poi)
        dist = _dist_of(poi)
        target: dict[str, Any] | None = None
        for c in clusters:
            if c["key"] != key:
                continue  # 이름 불일치 → 별개(오탐 차단: 근접해도 병합 안 함)
            if coord is not None and c["coord"] is not None:
                if _haversine_m(coord, c["coord"]) > radius_m:
                    continue  # 같은 이름이나 반경 밖 → 보수적으로 별개
            target = c
            break
        if target is None:
            clusters.append({"key": key, "coord": coord, "rep": poi, "rep_dist": dist})
            continue
        # 최근접을 대표로 승격 + 좌표 없던 클러스터가 좌표를 확보하도록 갱신.
        if dist is not None and (target["rep_dist"] is None or dist < target["rep_dist"]):
            target["rep"], target["rep_dist"] = poi, dist
        if target["coord"] is None and coord is not None:
            target["coord"] = coord
    return [c["rep"] for c in clusters]


def school_cluster_count(pois: Iterable[Any] | None, *, radius_m: float = _DEFAULT_RADIUS_M) -> int:
    """고유 모학교 수(= dedup_school_cluster 길이). 소비처가 카운트만 필요할 때의 편의 API."""
    return len(dedup_school_cluster(pois, radius_m=radius_m))
