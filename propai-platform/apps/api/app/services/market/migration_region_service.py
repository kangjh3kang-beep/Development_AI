"""권역 인구이동망 지도 레이어 — 대상 시군구가 속한 '시도(광역)' 하위 시군구 경계(GeoJSON)
+ 시군구별 순이동(KOSIS) → 순이동 발산(diverging) 코로플레스 데이터.

배경(PR#210 후속): KOSIS「시군구별 이동자수」는 대상 시군구의 순이동만 주고 'OD 출발지'는
미제공 → 방향 화살표(흐름도)는 불가. 대신 대상 시군구 + 같은 시도의 주변 시군구(권역)의
순이동을 발산 코로플레스로 표시한다(전출초과=red, 전입초과=blue, 0=중립, 무자료=회색).

흐름(인구밀도 스택 재사용 — 재구현 금지):
1. 대상 주소(bcode) → 법정동 시도(앞2자리) → KOSTAT 시도코드(SgisClient._LAWD_TO_KOSTAT_SIDO 재사용).
2. 그 시도 하위 '시군구' 경계(boundary/hadmarea.geojson, low_search=1) 조회 — ★UTM-K(EPSG:5179).
   (인구밀도는 시군구→행정동을 받지만, 여기선 시도→시군구로 한 단계 위에서 받는다.)
3. KOSIS 전국 시군구 순이동을 '한 번에' 조회(get_migration_region_map) — 시군구 수만큼 중복호출 금지.
4. 각 시군구 경계에 순이동 조인(코드 우선→이름 폴백). 대상 시군구는 is_target 강조.
5. _reproject_5179_to_4326(인구밀도와 동일 헬퍼) 재사용해 WGS84 features + legend(min/max/max_abs) 반환.

무자료/무키/실패는 정직 표기(data_source=unavailable + reason, 가짜 순이동 금지).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

# 인구밀도 레이어의 재투영 헬퍼·변환기·상수를 그대로 재사용(중복 구현 금지).
from app.services.market.population_density_service import (
    _BOUNDARY_YEARS,
    _SGIS_BASE,
    _reproject_5179_to_4326,
    build_utmk_to_wgs84_transformer,
)
from apps.api.integrations.kosis_client import KosisClient
from apps.api.integrations.sgis_client import SgisClient

logger = structlog.get_logger(__name__)


def _norm(s: str | None) -> str:
    return (s or "").strip()


def _is_target(name: str | None, region_name: str | None) -> bool:
    """경계 시군구명이 대상 시군구(주소에서 추출)인지 판정(강조용, 비핵심).

    통합시 자치구 표기차(예: SGIS '장안구' vs 주소 '수원시 장안구')를 흡수하려고
    양방향 endswith 도 허용한다. 정확 일치가 우선.
    """
    n, r = _norm(name), _norm(region_name)
    if not n or not r:
        return False
    return n == r or n.endswith(r) or r.endswith(n)


class MigrationRegionService:
    """SGIS 시도→시군구 경계 + KOSIS 시군구 순이동 → 순이동 발산 코로플레스 features."""

    def __init__(self) -> None:
        self._sgis = SgisClient()
        self._kosis = KosisClient()

    async def build_migration_region(
        self, *, bcode: str | None, region_name: str | None = None, year: str | None = None,
    ) -> dict[str, Any]:
        year = year or str(datetime.now().year)

        # ── 무키 즉시 정직 폴백(외부콜 0) ──
        # KOSIS 키가 없으면 순이동 자체를 받을 수 없다 → 경계만 그려도 색을 채울 수 없으므로
        # 바로 unavailable(외부 호출 없이). dev(무키) 환경의 정직 경로.
        if not self._kosis._kosis_key():
            return {"data_source": "unavailable", "reason": "KOSIS 인증키 미설정 — 순이동 데이터 없음",
                    "features": [], "legend": {"min_net": 0, "max_net": 0, "max_abs": 0}}
        token = await self._sgis.get_access_token()
        if not token:
            return {"data_source": "unavailable", "reason": "SGIS 인증키 미설정/토큰 실패",
                    "features": [], "legend": {"min_net": 0, "max_net": 0, "max_abs": 0}}

        lawd_sido = (bcode or "")[:2]
        sido = SgisClient._LAWD_TO_KOSTAT_SIDO.get(lawd_sido, lawd_sido)
        if not sido or len(sido) < 2:
            return {"data_source": "unavailable", "reason": "시도코드 미해석(주소/bcode 확인)",
                    "features": [], "legend": {"min_net": 0, "max_net": 0, "max_abs": 0}}

        # ── 경계(시도→시군구) + KOSIS 전국 순이동을 병렬 조회 ──
        # 두 외부 호출은 서로 독립이라 asyncio.gather 로 동시에 받는다(지연 최소화).
        boundaries, mig = await asyncio.gather(
            self._fetch_sigungu_boundaries(token, sido),
            self._kosis.get_migration_region_map(year),
        )
        if not boundaries:
            return {"data_source": "unavailable", "reason": "SGIS 시군구 경계 무자료",
                    "features": [], "legend": {"min_net": 0, "max_net": 0, "max_abs": 0},
                    "sido": sido}
        if mig.get("data_source") != "live":
            # KOSIS 순이동을 못 받으면(폴백/무자료) 색을 채울 실데이터가 없다 → 정직 미표시.
            return {"data_source": mig.get("data_source") or "unavailable",
                    "reason": mig.get("note") or "KOSIS 순이동 데이터 없음",
                    "features": [], "legend": {"min_net": 0, "max_net": 0, "max_abs": 0},
                    "sido": sido}

        by_code = mig.get("by_code") or {}
        by_name = mig.get("by_name") or {}

        # 좌표 변환기(UTM-K→WGS84, 공용 헬퍼). pyproj 미설치 시 정직 폴백(500 방지).
        tf = build_utmk_to_wgs84_transformer()
        if tf is None:
            return {"data_source": "unavailable", "reason": "좌표 변환기(pyproj) 미설치",
                    "features": [], "legend": {"min_net": 0, "max_net": 0, "max_abs": 0},
                    "sido": sido}

        feats: list[dict[str, Any]] = []
        target_hit = False
        for b in boundaries:
            props = b.get("properties") or {}
            adm_cd = str(props.get("adm_cd") or "")
            name = _norm(props.get("adm_nm")) or adm_cd
            geom = b.get("geometry") or {}

            # 조인: KOSIS 코드(C1)==경계 adm_cd 우선(코드 체계 일치 시 충돌 없음),
            #      실패하면 '유일한' 시군구명으로 폴백(동일명 중복은 by_name 에서 이미 제외됨).
            rec = by_code.get(adm_cd) or by_name.get(name)
            net = rec.get("net_migration") if rec else None
            inflow = rec.get("total_inflow") if rec else None
            outflow = rec.get("total_outflow") if rec else None

            is_target = _is_target(name, region_name)
            if is_target:
                target_hit = True

            try:
                wgs_coords = _reproject_5179_to_4326(geom.get("coordinates"), tf)
            except Exception:  # noqa: BLE001
                continue  # 변환 실패 시군구는 제외(가짜좌표 금지)
            feats.append({
                "adm_cd": adm_cd,
                "name": name,
                "geometry": {"type": geom.get("type"), "coordinates": wgs_coords},
                # 순이동(명). 무자료=None → 프론트 회색(가짜값 없음).
                "net_migration": net,
                "total_inflow": inflow,
                "total_outflow": outflow,
                "is_target": is_target,
            })

        nets = [f["net_migration"] for f in feats if f.get("net_migration") is not None]
        if nets:
            min_net, max_net = min(nets), max(nets)
            max_abs = max(abs(min_net), abs(max_net))
        else:
            min_net = max_net = max_abs = 0
        legend = {"min_net": min_net, "max_net": max_net, "max_abs": max_abs}

        return {
            "data_source": "live",
            "sido": sido,
            "year": mig.get("year") or year,
            "count": len(feats),
            "matched": len(nets),
            "target_region": region_name,
            "target_found": target_hit,
            "features": feats,
            "legend": legend,
            "note": ("SGIS 시군구 경계(UTM-K→WGS84)+KOSIS 시군구별 이동자수 순이동. "
                     "발산 코로플레스(전출초과=적·전입초과=청·0=중립). 무자료 시군구는 회색."),
        }

    async def _fetch_sigungu_boundaries(self, token: str, sido: str) -> list[dict]:
        """시도(2자리) 하위 '시군구' 경계(GeoJSON features, UTM-K). 수록연도 폴백.

        인구밀도의 _fetch_boundaries 와 동일한 hadmarea.geojson·low_search 패턴이되,
        adm_cd 를 시군구가 아닌 '시도'로 넣어 한 단계 위(시군구)를 받는다.
        """
        async with httpx.AsyncClient(timeout=20, base_url=_SGIS_BASE) as c:
            for yr in _BOUNDARY_YEARS:
                try:
                    r = await c.get("/OpenAPI3/boundary/hadmarea.geojson", params={
                        "accessToken": token, "year": yr, "adm_cd": sido, "low_search": "1",
                    })
                    g = r.json()
                    feats = g.get("features") or []
                    if feats:
                        return feats
                except Exception as e:  # noqa: BLE001
                    logger.debug("SGIS 시군구 경계 조회 실패", year=yr, err=str(e)[:80])
        return []
