"""주변 실거래 지도 데이터 서비스.

대상 지번 중심좌표 + 반경 + 카테고리별(매매6·전월세4) 실거래를 건물단위로
그룹핑·집계하고, 각 건물을 카카오 로컬 지오코딩으로 좌표화하여 지도에 표시할
페이로드를 만든다.

- 실거래: 검증된 MolitClient(apis.data.go.kr/1613000) 재사용
- 지오코딩: 카카오 로컬 API(주소→좌표, 지번·도로명·키워드 모두 처리), Redis 캐시
- 성능: 카테고리별 그룹 상한 + 고유 쿼리 dedupe + 병렬(semaphore) + 7일 캐시
"""

import asyncio
import json
from datetime import datetime
from typing import Any

import httpx
import structlog

from apps.api.config import get_settings
from apps.api.integrations.molit_client import MolitClient

logger = structlog.get_logger(__name__)

_TRADE_TYPES = [
    ("apt", "아파트"),
    ("villa", "연립다세대"),
    ("house", "단독다가구"),
    ("officetel", "오피스텔"),
    ("land", "토지"),
    ("commercial", "상업업무용"),
]
_RENT_TYPES = [
    ("apt", "아파트"),
    ("villa", "연립다세대"),
    ("house", "단독다가구"),
    ("officetel", "오피스텔"),
]

_MAX_GROUPS_PER_CAT = 40  # 카테고리별 마커 상한(건물 수)
_GEOCODE_CONCURRENCY = 8
_KAKAO_ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
_KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


class NearbyMapService:
    """주변 실거래 지도 페이로드 생성기."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.molit = MolitClient()
        self._kakao_key = getattr(self.settings, "kakao_client_id", "") or ""

    # ── 공개 진입점 ──
    async def build(
        self,
        address: str,
        lawd_cd: str,
        months: int = 3,
        radius_m: int = 1000,
        sigungu_hint: str = "",
    ) -> dict[str, Any]:
        ym_list = self._recent_months(months)

        # 1) 카테고리별 실거래 수집(병렬)
        trade_raw, rent_raw = await asyncio.gather(
            self._collect(self.molit.get_transactions, _TRADE_TYPES, lawd_cd, ym_list),
            self._collect(self.molit.get_rent_transactions, _RENT_TYPES, lawd_cd, ym_list),
        )

        # 2) 건물단위 그룹핑
        categories: dict[str, dict[str, Any]] = {}
        for tkey, tlabel in _TRADE_TYPES:
            categories[f"{tkey}_trade"] = self._group_trade(
                tkey, f"{tlabel} 매매", trade_raw.get(tkey, []), sigungu_hint
            )
        for tkey, tlabel in _RENT_TYPES:
            categories[f"{tkey}_rent"] = self._group_rent(
                tkey, f"{tlabel} 전월세", rent_raw.get(tkey, []), sigungu_hint
            )

        # 3) 고유 지오코딩 쿼리 수집 → dedupe → 병렬 지오코딩
        queries: set[str] = set()
        for cat in categories.values():
            for grp in cat["groups"]:
                queries.add(grp["_query"])
        coords = await self._geocode_many(sorted(queries))

        # 4) 좌표 주입 + 미해결 그룹 제거 + 정리
        center = coords.get(address.strip()) or await self._geocode_one(address.strip())
        for cat in categories.values():
            resolved = []
            for grp in cat["groups"]:
                c = coords.get(grp.pop("_query"))
                if c:
                    grp["lat"], grp["lon"] = c["lat"], c["lon"]
                    resolved.append(grp)
            cat["groups"] = resolved
            cat["count"] = sum(g["count"] for g in resolved)

        return {
            "center": center or {"lat": None, "lon": None, "address": address},
            "radius_m": radius_m,
            "lawd_cd": lawd_cd,
            "months": ym_list,
            "categories": categories,
        }

    # ── 수집 ──
    @staticmethod
    def _recent_months(months: int) -> list[str]:
        # 현재월은 신고지연으로 데이터가 거의 없음 → 직전월부터 수집
        now = datetime.now()
        y, m = now.year, now.month
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out = []
        for _ in range(months):
            out.append(f"{y}{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return out

    async def _collect(self, fetch, types, lawd_cd, ym_list) -> dict[str, list]:
        async def one(pt: str) -> tuple[str, list]:
            rows: list = []
            for ym in ym_list:
                try:
                    rows.extend(await fetch(lawd_cd, ym, prop_type=pt, num_rows=1000))
                except Exception as e:  # noqa: BLE001
                    logger.debug("실거래 수집 실패", pt=pt, ym=ym, err=str(e)[:60])
            return pt, rows

        results = await asyncio.gather(*[one(pt) for pt, _ in types])
        return dict(results)

    # ── 그룹핑 ──
    def _query_for(self, sigungu: str, dong: str, jibun: str, name: str) -> str:
        sgg = (sigungu or "").strip()
        if jibun:
            return f"{sgg} {dong} {jibun}".strip()
        if name:
            return f"{dong} {name}".strip()
        return f"{sgg} {dong}".strip()

    def _group_trade(self, type_key, label, rows, sigungu_hint) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = (r.get("building_name") or "").strip()
            jibun = (r.get("jibun") or "").strip()
            dong = (r.get("dong") or "").strip()
            sigungu = (r.get("sigungu") or sigungu_hint or "").strip()
            key = name or jibun or dong
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": name or (f"{dong} {jibun}".strip() or "물건"),
                "dong": dong, "jibun": jibun,
                "_query": self._query_for(sigungu, dong, jibun, name),
                "deals": [], "_prices": [], "_areas": [],
            })
            price = int(r.get("price_10k_won") or 0)
            area = float(r.get("area_m2") or 0)
            if price > 0:
                g["_prices"].append(price)
            if area > 0:
                g["_areas"].append(area)
            g["deals"].append({
                "price_10k_won": price, "area_m2": area,
                "floor": r.get("floor"), "deal_date": r.get("deal_date"),
            })
        return self._finalize(type_key, label, "trade", groups)

    def _group_rent(self, type_key, label, rows, sigungu_hint) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = (r.get("building_name") or "").strip()
            jibun = (r.get("jibun") or "").strip()
            dong = (r.get("dong") or "").strip()
            sigungu = (r.get("sigungu") or sigungu_hint or "").strip()
            key = name or jibun or dong
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": name or (f"{dong} {jibun}".strip() or "물건"),
                "dong": dong, "jibun": jibun,
                "_query": self._query_for(sigungu, dong, jibun, name),
                "deals": [], "_deposits": [], "_monthlies": [], "_areas": [],
            })
            dep = int(r.get("deposit_10k_won") or 0)
            mon = int(r.get("monthly_rent_10k_won") or 0)
            area = float(r.get("area_m2") or 0)
            if dep > 0:
                g["_deposits"].append(dep)
            if mon > 0:
                g["_monthlies"].append(mon)
            if area > 0:
                g["_areas"].append(area)
            g["deals"].append({
                "deposit_10k_won": dep, "monthly_rent_10k_won": mon,
                "area_m2": area, "floor": r.get("floor"), "deal_date": r.get("deal_date"),
            })
        return self._finalize(type_key, label, "rent", groups)

    def _finalize(self, type_key, label, kind, groups) -> dict[str, Any]:
        out = []
        for g in groups.values():
            cnt = len(g["deals"])
            areas = g.pop("_areas", [])
            g["count"] = cnt
            g["avg_area_m2"] = round(sum(areas) / len(areas), 1) if areas else 0
            if kind == "trade":
                p = g.pop("_prices", [])
                g["avg_price_10k"] = round(sum(p) / len(p)) if p else 0
                g["min_price_10k"] = min(p) if p else 0
                g["max_price_10k"] = max(p) if p else 0
            else:
                d = g.pop("_deposits", [])
                m = g.pop("_monthlies", [])
                g["avg_deposit_10k"] = round(sum(d) / len(d)) if d else 0
                g["avg_monthly_10k"] = round(sum(m) / len(m)) if m else 0
            g["deals"] = g["deals"][:10]
            out.append(g)
        # 거래 많은 순 정렬 + 상한
        out.sort(key=lambda x: x["count"], reverse=True)
        out = out[:_MAX_GROUPS_PER_CAT]
        return {"label": label, "type": type_key, "kind": kind,
                "count": sum(x["count"] for x in out), "groups": out}

    # ── 지오코딩(카카오 로컬 + Redis 캐시) ──
    async def _redis(self):
        try:
            import redis.asyncio as aioredis
            return aioredis.from_url(self.settings.redis_url)
        except Exception:
            return None

    async def _geocode_many(self, queries: list[str]) -> dict[str, dict]:
        if not queries or not self._kakao_key:
            return {}
        sem = asyncio.Semaphore(_GEOCODE_CONCURRENCY)
        async with httpx.AsyncClient(timeout=10.0) as client:
            async def run(q):
                async with sem:
                    return q, await self._geocode_one(q, client)
            pairs = await asyncio.gather(*[run(q) for q in queries])
        return {q: c for q, c in pairs if c}

    async def _geocode_one(self, query: str, client: httpx.AsyncClient | None = None) -> dict | None:
        if not query or not self._kakao_key:
            return None
        cache_key = f"kakao:geo:{query}"
        r = await self._redis()
        if r is not None:
            try:
                cached = await r.get(cache_key)
                if cached:
                    await r.aclose()
                    val = json.loads(cached)
                    return val or None
            except Exception:
                pass
        headers = {"Authorization": f"KakaoAK {self._kakao_key}"}
        own = client is None
        if own:
            client = httpx.AsyncClient(timeout=10.0)
        coord = None
        try:
            for url, key in ((_KAKAO_ADDR_URL, "address"), (_KAKAO_KEYWORD_URL, "keyword")):
                try:
                    resp = await client.get(url, params={"query": query}, headers=headers)
                    if resp.status_code != 200:
                        continue
                    docs = resp.json().get("documents") or []
                    if docs:
                        d = docs[0]
                        coord = {"lat": float(d["y"]), "lon": float(d["x"])}
                        break
                except Exception:
                    continue
        finally:
            if own:
                await client.aclose()
        if r is not None:
            try:
                await r.setex(cache_key, 604800, json.dumps(coord or {}))
                await r.aclose()
            except Exception:
                pass
        return coord
