"""한국부동산원 R-ONE OpenAPI 클라이언트 — 지가변동률 실데이터.

엔드포인트: GET https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do
파라미터: KEY(인증키), STATBL_ID(통계표ID, 지가변동률), DTACYCLE_CD=MM(월), Type=json,
          (선택) WRTTIME_IDTFR_ID(작성시점), Start_INDEX/End_INDEX.
키: RONE_API_KEY(시크릿 스토어/.env), 통계표ID: RONE_LANDPRICE_STATBL_ID(env, 사용자 설정).
미설정/실패 시 None 반환 → land_price_index가 근사 테이블로 폴백(graceful).
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_HOST = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
_TBL_LIST_HOST = "https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do"


def reb_key() -> str:
    return (os.getenv("RONE_API_KEY") or os.getenv("REB_API_KEY") or "").strip()


def reb_statbl_id() -> str:
    return (os.getenv("RONE_LANDPRICE_STATBL_ID") or "").strip()


def reb_ready() -> bool:
    return bool(reb_key() and reb_statbl_id())


def _rows_from_payload(data: Any, row_block: str) -> list[dict[str, Any]]:
    """R-ONE 응답({block:[{head},{row:[...]}]} 또는 {row:[...]})에서 row 리스트 방어적 추출."""
    rows: list[dict[str, Any]] = []
    container = data.get(row_block) if isinstance(data, dict) else None
    if isinstance(container, list):
        for blk in container:
            if isinstance(blk, dict) and isinstance(blk.get("row"), list):
                return blk["row"]
    if isinstance(data, dict) and isinstance(data.get("row"), list):
        rows = data["row"]
    return rows


async def discover_statbl_ids(keyword: str = "지가변동", max_pages: int = 15) -> list[dict[str, Any]] | None:
    """통계표 목록(SttsApiTbl.do)에서 키워드 포함 통계표를 탐색해 후보(STATBL_ID·명) 반환."""
    key = reb_key()
    if not key:
        return None
    try:
        import httpx

        out: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            for page in range(1, max_pages + 1):
                params = {"KEY": key, "Type": "json", "pIndex": str(page), "pSize": "100"}
                r = await client.get(_TBL_LIST_HOST, params=params)
                r.raise_for_status()
                rows = _rows_from_payload(r.json(), "SttsApiTbl")
                if not rows:
                    break
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    name = " ".join(
                        str(row.get(k, "")) for k in ("STATBL_NM", "STAT_NM", "GRP_NM", "TBL_NM")
                    )
                    if keyword in name:
                        out.append({
                            "STATBL_ID": row.get("STATBL_ID") or row.get("TBL_ID"),
                            "STATBL_NM": row.get("STATBL_NM") or row.get("TBL_NM"),
                            "STAT_NM": row.get("STAT_NM"),
                            "DTACYCLE_CD": row.get("DTACYCLE_CD"),
                        })
                if len(rows) < 100:
                    break
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("R-ONE 통계표 목록 조회 실패", err=str(e)[:140])
        return None


async def fetch_statbl_rows(
    statbl_id: str, dtacycle: str = "MM", size: int = 240, wrttime: str | None = None
) -> list[dict[str, Any]] | None:
    """임의 통계표(STATBL_ID) 데이터 행을 원형 반환 — 범용 R-ONE 조회. 실패 시 None.

    wrttime 지정 시 해당 작성시점(YYYYMM/YYYY)만 조회(대용량 표에서 최근 시점만 효율 추출).
    """
    key = reb_key()
    if not key or not statbl_id:
        return None
    try:
        import httpx

        params = {
            "KEY": key, "STATBL_ID": statbl_id, "DTACYCLE_CD": dtacycle,
            "Type": "json", "pIndex": "1", "pSize": str(max(50, size)),
        }
        if wrttime:
            params["WRTTIME_IDTFR_ID"] = wrttime
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(_HOST, params=params)
            r.raise_for_status()
            data = r.json()
        return _rows_from_payload(data, "SttsApiTblData") or None
    except Exception as e:  # noqa: BLE001
        logger.warning("R-ONE 통계표 조회 실패", statbl=statbl_id, err=str(e)[:140])
        return None


# 월 지가변동률 최근행 캐시(대용량 표 반복조회 방지). 키=(statbl, 기준월), TTL 6h.
_LANDPRICE_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


async def fetch_recent_monthly_rows(statbl: str, months: int = 24) -> list[dict[str, Any]] | None:
    """대용량 월 통계표의 '최근 N개월' 행을 WRTTIME별 병렬 조회로 수집(각 호출=해당월 전 지역).

    A_2024_00903 등은 2005년~·지역블록·오래된순이라 pSize로는 최신이 안 잡힘 →
    최근 월(YYYYMM)을 직접 지정해 실시간 최신 데이터 확보. 6h 캐시."""
    if not statbl:
        return None
    import asyncio
    from datetime import datetime

    now = datetime.now()
    ym: list[str] = []
    y, m = now.year, now.month
    for _ in range(max(1, months) + 3):   # 공표 지연 고려 여유 +3개월
        m -= 1
        if m == 0:
            y -= 1
            m = 12
        ym.append(f"{y}{m:02d}")
    cache_key = f"{statbl}|{ym[0]}|{months}"
    hit = _LANDPRICE_CACHE.get(cache_key)
    if hit and (now.timestamp() - hit[0]) < 6 * 3600:
        return hit[1]

    async def _one(t: str) -> list[dict[str, Any]]:
        rows = await fetch_statbl_rows(statbl, "MM", size=400, wrttime=t)
        return rows or []

    results = await asyncio.gather(*[_one(t) for t in ym], return_exceptions=True)
    rows: list[dict[str, Any]] = []
    for res in results:
        if isinstance(res, list):
            rows.extend(res)
    if not rows:
        return None
    _LANDPRICE_CACHE[cache_key] = (now.timestamp(), rows)
    return rows


async def fetch_land_price_changes(months: int = 24) -> list[dict[str, Any]] | None:
    """지가변동률 '최근 N개월' 행(env STATBL_ID 기준). 미설정/실패 시 None."""
    statbl = reb_statbl_id()
    if not statbl:
        return None
    return await fetch_recent_monthly_rows(statbl, months)


def latest_value_from_rows(
    rows: list[dict[str, Any]], region_sido: str = ""
) -> tuple[float, str] | None:
    """월/분기 행에서 지역 매칭 최신 시점의 값(%)·작성시점을 반환. 값 필드 방어적 탐색."""
    if not rows:
        return None
    region_keys = ("CLS_NM", "CLS_FULLNM", "REGION_NM", "REGION", "ITM_NM")
    val_keys = ("DTA_VAL", "VALUE", "DATA_VALUE", "dtaVal")
    time_keys = ("WRTTIME_IDTFR_ID", "WRTTIME_DESC", "WRTTIME", "PRD_DE")
    best: tuple[str, float] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        region_txt = " ".join(str(row.get(k, "")) for k in region_keys)
        if region_sido and region_sido not in region_txt and region_txt.strip():
            continue
        raw = next((row.get(k) for k in val_keys if row.get(k) not in (None, "")), None)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        tval = str(next((row.get(k) for k in time_keys if row.get(k) not in (None, "")), ""))
        if best is None or tval >= best[0]:
            best = (tval, val)
    return (round(best[1], 4), best[0]) if best else None


def rate_series_from_rows(rows: list[dict[str, Any]], region_sido: str) -> list[tuple[str, float]]:
    """변동률(%) 시계열 [(YYYYMM, rate)] 추출 — ITM='변동률'만, 지역(sido→전국 폴백), 시점 오름차순."""
    if not rows:
        return []
    region_keys = ("CLS_NM", "CLS_FULLNM", "REGION_NM", "REGION")
    val_keys = ("DTA_VAL", "VALUE", "DATA_VALUE", "dtaVal")
    time_keys = ("WRTTIME_IDTFR_ID", "WRTTIME", "PRD_DE")

    def _collect(region_filter: str | None) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            itm = str(row.get("ITM_NM") or "")
            if itm and "변동" not in itm:   # '누계' 등 제외, 변동률만
                continue
            region_txt = " ".join(str(row.get(k, "")) for k in region_keys)
            if region_filter and region_filter not in region_txt:
                continue
            raw = next((row.get(k) for k in val_keys if row.get(k) not in (None, "")), None)
            try:
                rate = float(raw)
            except (TypeError, ValueError):
                continue
            tval = str(next((row.get(k) for k in time_keys if row.get(k) not in (None, "")), ""))
            out.append((tval, rate))
        return out

    series = _collect(region_sido) if region_sido else []
    if not series:
        series = _collect("전국") or _collect(None)
    series.sort(key=lambda x: x[0])
    return series


def cumulative_factor_from_rows(
    rows: list[dict[str, Any]], region_sido: str, months: int = 24
) -> float | None:
    """월별 지가변동률(%) → 지역 최근 N개월 누적 변동계수(∏(1+r/100))."""
    series = rate_series_from_rows(rows, region_sido)
    if not series:
        return None
    recent = series[-months:] if months > 0 else series
    factor = 1.0
    for _t, rate in recent:
        factor *= (1 + rate / 100.0)
    return round(factor, 4)


def trend_from_rows(rows: list[dict[str, Any]], region_sido: str, months: int = 24) -> dict[str, Any]:
    """월별·연도별 지가변동률 통계 — 최근 N개월 시계열 + 연도별 합계(연간 변동률 근사)."""
    series = rate_series_from_rows(rows, region_sido)
    if not series:
        return {}
    monthly = [{"period": t, "rate": round(r, 3)} for t, r in series[-months:]]
    yearly_map: dict[str, float] = {}
    for t, r in series:
        yr = t[:4]
        if len(yr) == 4 and yr.isdigit():
            yearly_map[yr] = yearly_map.get(yr, 0.0) + r   # 월 변동률 합 ≈ 연간 변동률
    yearly = [{"year": y, "rate": round(v, 2)} for y, v in sorted(yearly_map.items())][-10:]
    return {"monthly": monthly, "yearly": yearly}
