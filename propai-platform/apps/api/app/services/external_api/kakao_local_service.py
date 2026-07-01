"""Kakao Local(장소) API 연동 — 입지분석용 POI 인프라 인벤토리.

좌표(lat/lon) 중심 반경 내 카테고리별 시설(지하철·학교·병원·약국·마트·편의점·은행·
공공기관·문화시설·관광)을 정량 수집한다. Daum 우편번호 검색과 무관한 별개 API로,
입지분석의 인프라 조사에 효과적이다.

키: KAKAO_REST_API_KEY (secret_store가 앱 시작 시 os.environ 에 로드).
무목업: 키 미설정/조회 실패 시 정직하게 available=False·빈 결과(가짜 POI 생성 금지).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE = "https://dapi.kakao.com/v2/local/search/category.json"
_KEYWORD = "https://dapi.kakao.com/v2/local/search/keyword.json"
_NAVI = "https://apis-navi.kakaomobility.com/v1/directions"  # Kakao Mobility 자동차 길찾기

# 입지분석에 의미 있는 카테고리(코드: 라벨). Kakao Local category_group_code.
POI_CATEGORIES: list[tuple[str, str]] = [
    ("SW8", "지하철역"),
    ("SC4", "학교"),
    ("AC5", "학원"),
    ("HP8", "병원"),
    ("PM9", "약국"),
    ("MT1", "대형마트"),
    ("CS2", "편의점"),
    ("BK9", "은행"),
    ("PO3", "공공기관"),
    ("CT1", "문화시설"),  # 공연장·전시관·박물관 등 — 카카오 문화시설 카테고리
    ("AT4", "관광명소"),
    ("FD6", "음식점"),
    ("CE7", "카페"),
]

# ── 키워드 기반 POI 그룹(카카오 카테고리코드가 없는 광역 인프라) ──
#   누락 없는 광범위 수집 원칙: 대형관공서·백화점·터미널·기차역·고속도로IC·톨게이트·
#   체육관·골프장·공연장을 키워드 반경검색으로 보강한다. 선형(고속도로·순환도로)은
#   점 POI가 아니므로 '최근접 IC/톨게이트 거리'로 대표(가짜 점 POI 생성 금지).
#   각 그룹은 여러 키워드를 합산(중복 장소는 distance_m 기준 최근접 1건만 집계)한다.
#   키 형식: 그룹코드 -> (라벨, [키워드...]). 그룹코드는 카테고리코드와 충돌하지 않게 'KW_' 접두.
KEYWORD_POI_GROUPS: list[tuple[str, str, list[str]]] = [
    ("KW_GOVOFFICE", "대형 행정/의회", ["시청", "도청", "구청", "군청", "시의회", "도의회", "구의회"]),
    ("KW_DEPT", "백화점", ["백화점"]),
    # ※ 공원(PARK)은 라우터가 별도 키워드검색으로 이미 접근성 점수에 반영 — 중복 방지로 여기선 제외.
    ("KW_BUSTERMINAL", "버스터미널", ["버스터미널", "고속버스터미널"]),
    ("KW_TRAINSTATION", "기차역", ["기차역", "KTX역"]),
    ("KW_HIGHWAY_IC", "고속도로 IC", ["IC", "나들목", "분기점"]),  # 선형 도로 대표: 최근접 진출입로 거리
    ("KW_TOLLGATE", "톨게이트", ["톨게이트", "요금소"]),
    ("KW_GYM", "체육관", ["체육관", "실내체육관"]),
    ("KW_GOLF", "골프장", ["골프장", "컨트리클럽"]),
    ("KW_THEATER", "공연장", ["공연장", "콘서트홀"]),
]


def _rest_key() -> str:
    return (os.environ.get("KAKAO_REST_API_KEY") or "").strip()


class KakaoLocalService:
    """Kakao Local 장소 카테고리 검색."""

    async def category_search(
        self, lat: float, lon: float, code: str, radius: int = 1000, size: int = 15
    ) -> dict[str, Any] | None:
        """단일 카테고리 반경검색 → {count(전체), nearest_m, items[]}. 키없음/실패=None."""
        key = _rest_key()
        if not key:
            return None
        params = {
            "category_group_code": code,
            "x": str(lon), "y": str(lat),
            "radius": str(min(max(int(radius), 1), 20000)),  # Kakao 상한 20km
            "sort": "distance",
            "size": str(min(max(int(size), 1), 15)),
        }
        headers = {"Authorization": f"KakaoAK {key}"}
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                resp = await client.get(_BASE, params=params)
                if resp.status_code != 200:
                    logger.warning("KAKAO Local 비정상", code=code, status=resp.status_code)
                    return None
                data = resp.json()
                docs = data.get("documents", []) or []
                total = (data.get("meta", {}) or {}).get("total_count", len(docs))
                items = [
                    {
                        "name": d.get("place_name"),
                        "distance_m": int(d.get("distance") or 0) if str(d.get("distance") or "").isdigit() else None,
                        "category": d.get("category_name"),
                        "road_address": d.get("road_address_name") or d.get("address_name"),
                        "lat": float(d.get("y")) if d.get("y") else None,
                        "lon": float(d.get("x")) if d.get("x") else None,
                    }
                    for d in docs
                ]
                nearest = next((it["distance_m"] for it in items if it["distance_m"] is not None), None)
                return {"count": int(total), "nearest_m": nearest, "items": items}
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning("KAKAO Local 요청 실패", code=code, error=str(e))
            return None

    async def keyword_search(
        self, lat: float, lon: float, query: str, radius: int = 1000, size: int = 15
    ) -> dict[str, Any] | None:
        """키워드 반경검색 → {count, nearest_m, items}. 공원 등 카테고리코드 없는 시설용."""
        key = _rest_key()
        if not key:
            return None
        params = {
            "query": query, "x": str(lon), "y": str(lat),
            "radius": str(min(max(int(radius), 1), 20000)),
            "sort": "distance", "size": str(min(max(int(size), 1), 15)),
        }
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"Authorization": f"KakaoAK {key}"}) as client:
                resp = await client.get(_KEYWORD, params=params)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                docs = data.get("documents", []) or []
                total = (data.get("meta", {}) or {}).get("total_count", len(docs))
                items = [{
                    "name": d.get("place_name"),
                    "distance_m": int(d.get("distance")) if str(d.get("distance") or "").isdigit() else None,
                    "lat": float(d.get("y")) if d.get("y") else None,
                    "lon": float(d.get("x")) if d.get("x") else None,
                } for d in docs]
                nearest = next((it["distance_m"] for it in items if it["distance_m"] is not None), None)
                return {"count": int(total), "nearest_m": nearest, "items": items}
        except (httpx.TimeoutException, httpx.RequestError):
            return None

    async def driving_duration_sec(
        self, o_lat: float, o_lon: float, d_lat: float, d_lon: float
    ) -> dict[str, Any] | None:
        """Kakao Mobility 자동차 길찾기 → 실소요(초)·거리(m). 미가용(키/권한)=None(정직).

        ※도보 API는 공개 제공되지 않아 자동차 기준. 권한 미부여 시 None 폴백.
        """
        key = _rest_key()
        if not key:
            return None
        params = {"origin": f"{o_lon},{o_lat}", "destination": f"{d_lon},{d_lat}", "priority": "RECOMMEND"}
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"Authorization": f"KakaoAK {key}"}) as client:
                resp = await client.get(_NAVI, params=params)
                if resp.status_code != 200:
                    return None
                routes = (resp.json().get("routes") or [])
                if not routes:
                    return None
                summ = routes[0].get("summary") or {}
                return {"duration_sec": summ.get("duration"), "distance_m": summ.get("distance")}
        except (httpx.TimeoutException, httpx.RequestError):
            return None

    async def poi_inventory(
        self, lat: float, lon: float, radius: int = 1000,
        categories: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """좌표 반경 POI 인벤토리 — 카테고리별 {label, count, nearest_m, items}.

        키 미설정이면 available=False(무목업). 카테고리는 동시성 제한으로 병렬 조회.
        """
        if not _rest_key():
            return {"available": False, "reason": "KAKAO_REST_API_KEY 미설정 — 관리자 키 입력 필요", "categories": {}}

        cats = categories or POI_CATEGORIES
        sem = asyncio.Semaphore(6)

        async def _one(code: str, label: str):
            async with sem:
                r = await self.category_search(lat, lon, code, radius)
            return code, label, r

        results = await asyncio.gather(*[_one(c, l) for c, l in cats], return_exceptions=True)
        out: dict[str, Any] = {}
        for res in results:
            # return_exceptions=True는 CancelledError 등 BaseException도 반환할 수 있어 Exception보다 넓게 가드.
            if isinstance(res, BaseException) or res is None:
                continue
            code, label, r = res
            if r is None:
                out[code] = {"label": label, "count": 0, "nearest_m": None, "items": [], "unavailable": True}
            else:
                out[code] = {"label": label, **r}
        return {"available": True, "radius_m": radius, "center": {"lat": lat, "lon": lon}, "categories": out}

    async def keyword_group_inventory(
        self, lat: float, lon: float, radius: int = 1000,
        groups: list[tuple[str, str, list[str]]] | None = None,
    ) -> dict[str, Any]:
        """키워드 그룹 인벤토리 — 카테고리코드 없는 광역 인프라를 키워드 합산으로 수집.

        그룹별로 여러 키워드를 병렬 조회한 뒤, 같은 장소명은 최근접 1건만 남겨
        중복을 제거하고 {label, count(고유 장소 수), nearest_m, items}로 합산한다.
        키 미설정/조회 실패 그룹은 unavailable=True(가짜 POI 생성 금지).
        """
        grps = groups if groups is not None else KEYWORD_POI_GROUPS
        if not _rest_key():
            return {}
        sem = asyncio.Semaphore(6)

        async def _kw(query: str):
            async with sem:
                return await self.keyword_search(lat, lon, query, radius)

        # ★전 그룹의 모든 키워드를 한 번에 병렬 조회(그룹 간 직렬 제거 — 최대 그룹수만큼 누적되던
        #   라운드트립을 1회 배치로 평탄화). Semaphore(6)이 동시 호출 상한을 유지해 폭주를 막는다.
        flat = [(gi, q) for gi, (_c, _l, kws) in enumerate(grps) for q in kws]
        results = await asyncio.gather(*[_kw(q) for _gi, q in flat], return_exceptions=True)
        by_group: dict[int, list[Any]] = {}
        for (gi, _q), r in zip(flat, results):
            by_group.setdefault(gi, []).append(r)

        out: dict[str, Any] = {}
        for gi, (code, label, _keywords) in enumerate(grps):
            # 그룹 키워드 결과를 합치며 같은 장소는 가장 가까운 1건만 보존(중복 제거).
            merged: dict[str, dict[str, Any]] = {}
            any_ok = False
            for r in by_group.get(gi, []):
                if not isinstance(r, dict):
                    continue
                any_ok = True
                for it in r.get("items", []) or []:
                    nm = it.get("name") or ""
                    # 동명 다른 지점(예: 같은 체인 분점)을 1건으로 병합하지 않도록 근사좌표를 키에 포함.
                    key = f"{nm}@{round(float(it.get('lat') or 0), 4)},{round(float(it.get('lon') or 0), 4)}"
                    prev = merged.get(key)
                    if prev is None or (
                        it.get("distance_m") is not None
                        and (prev.get("distance_m") is None or it["distance_m"] < prev["distance_m"])
                    ):
                        merged[key] = it
            if not any_ok:
                out[code] = {"label": label, "count": 0, "nearest_m": None, "items": [], "unavailable": True}
                continue
            items = sorted(merged.values(), key=lambda x: (x.get("distance_m") is None, x.get("distance_m") or 0))
            nearest = next((it.get("distance_m") for it in items if it.get("distance_m") is not None), None)
            out[code] = {"label": label, "count": len(items), "nearest_m": nearest, "items": items[:15]}
        return out
