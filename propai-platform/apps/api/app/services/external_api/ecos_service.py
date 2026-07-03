"""한국은행 ECOS(경제통계시스템) 클라이언트 — 기준금리·시장금리 실시간.

엔드포인트: GET https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/1/{N}/{STAT}/{CYCLE}/{START}/{END}/{ITEM}
- 기준금리: 722Y001 / 항목 0101000 / 월(M)  — 한국은행 기준금리(연%).
- 시장금리: 817Y002 / 일(D) — 국고채3년(010200000)·회사채AA-3년(010300000)·CD91일(010502000)·국고채10년(010210000).
키: ECOS_API_KEY(시크릿 스토어/.env, ecos.bok.or.kr 마이페이지 발급).

동기 소비(금융비 엔진 get_pf_rate)를 위해 **비동기 refresh()로 모듈 캐시를 채우고, 동기 base_rate()/get_rates()가 캐시를 읽는다.**
미설정/실패/캐시 콜드 시 None 반환 → 소비처가 하드코딩 폴백(graceful, 무날조). 값엔 as_of·source 근거를 함께 싣는다.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

_HOST = "https://ecos.bok.or.kr/api"
_TTL_SEC = 7 * 24 * 3600  # 기준금리는 월 단위라 며칠 staleness 무해 — 7일 캐시(startup 프리페치+재배포로 갱신)
_TIMEOUT = 12.0

# ── 통계표/항목 코드(ECOS 확정) ──
_BASE_STAT, _BASE_ITEM = "722Y001", "0101000"       # 한국은행 기준금리(월)
_MKT_STAT = "817Y002"                                # 시장금리(일)
_MKT_ITEMS = {
    "gov_bond_3y": "010200000",   # 국고채(3년)
    "gov_bond_10y": "010210000",  # 국고채(10년)
    "corp_bond_aa_3y": "010300000",  # 회사채(3년, AA-)
    "cd_91d": "010502000",        # CD(91일)
}

# 모듈 캐시: refresh()가 채우고 base_rate()/get_rates()가 읽는다.
_CACHE: dict[str, Any] = {"rates": None, "fetched_at": 0.0}


def ecos_key() -> str:
    """ECOS 인증키. 관리자 시크릿(os.environ 오버레이) 우선, 없으면 Settings."""
    key = os.getenv("ECOS_API_KEY")
    if key:
        return key.strip()
    try:
        from app.core.config import settings
        return (settings.ECOS_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def ecos_ready() -> bool:
    return bool(ecos_key())


def _to_decimal(data_value: str) -> Optional[float]:
    """ECOS DATA_VALUE(연%, 예 '2.5') → 소수(0.025). 파싱 실패시 None."""
    try:
        v = float(str(data_value).strip())
    except (TypeError, ValueError):
        return None
    return round(v / 100.0, 6)


async def _fetch_latest(
    client: httpx.AsyncClient, stat: str, item: str, cycle: str, start: str, end: str
) -> Optional[tuple[str, float]]:
    """StatisticSearch로 (start~end) 최근 100건 조회 후 마지막(=최신) 행 반환 → (TIME, decimal)."""
    url = f"{_HOST}/StatisticSearch/{ecos_key()}/json/kr/1/100/{stat}/{cycle}/{start}/{end}/{item}"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("ECOS 조회 실패", stat=stat, item=item, err=str(e)[:120])
        return None
    # 오류 응답({"RESULT":{"CODE":...}}) 방어
    if isinstance(data, dict) and "RESULT" in data and "StatisticSearch" not in data:
        logger.warning("ECOS 오류응답", stat=stat, msg=str(data.get("RESULT"))[:120])
        return None
    rows = (data.get("StatisticSearch") or {}).get("row", []) if isinstance(data, dict) else []
    if not rows:
        return None
    last = rows[-1]  # ECOS는 시점 오름차순 반환 → 마지막이 최신
    dec = _to_decimal(last.get("DATA_VALUE"))
    if dec is None:
        return None
    return str(last.get("TIME", "")), dec


async def refresh() -> Optional[dict[str, Any]]:
    """ECOS 실데이터로 모듈 캐시 갱신. 미설정/전부실패시 None(캐시 미변경)."""
    if not ecos_ready():
        logger.info("ECOS 키 미설정 — 실금리 미수집(하드코딩 폴백 유지)")
        return None
    now = datetime.now()
    m_start = (now - timedelta(days=730)).strftime("%Y%m")  # 최근 24개월(월)
    m_end = now.strftime("%Y%m")
    d_start = (now - timedelta(days=21)).strftime("%Y%m%d")  # 최근 3주(일)
    d_end = now.strftime("%Y%m%d")

    result: dict[str, Any] = {"source": "한국은행 ECOS(경제통계시스템)", "provenance": "ecos.bok.or.kr"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            base = await _fetch_latest(client, _BASE_STAT, _BASE_ITEM, "M", m_start, m_end)
            if base:
                result["base_rate"] = base[1]
                result["base_rate_as_of"] = base[0]
            market: dict[str, Any] = {}
            for name, item in _MKT_ITEMS.items():
                got = await _fetch_latest(client, _MKT_STAT, item, "D", d_start, d_end)
                if got:
                    market[name] = {"value": got[1], "as_of": got[0]}
            if market:
                result["market_rates"] = market
    except Exception as e:  # noqa: BLE001
        logger.warning("ECOS refresh 예외", err=str(e)[:150])

    if "base_rate" not in result and "market_rates" not in result:
        return None  # 아무것도 못 얻음 → 캐시 미변경(폴백 유지)
    _CACHE["rates"] = result
    _CACHE["fetched_at"] = time.time()
    logger.info(
        "ECOS 실금리 갱신",
        base_rate=result.get("base_rate"),
        base_as_of=result.get("base_rate_as_of"),
        market=list((result.get("market_rates") or {}).keys()),
    )
    return result


def _fresh() -> bool:
    return bool(_CACHE.get("rates")) and (time.time() - _CACHE.get("fetched_at", 0.0)) < _TTL_SEC


def get_rates() -> Optional[dict[str, Any]]:
    """동기 캐시 읽기 — 신선하면 {base_rate, market_rates, source, ...}, 아니면 None(폴백)."""
    return _CACHE.get("rates") if _fresh() else None


def base_rate() -> Optional[float]:
    """동기 — 캐시된 한국은행 기준금리(소수, 예 0.025). 콜드/미설정시 None."""
    r = get_rates()
    if r and isinstance(r.get("base_rate"), (int, float)):
        return float(r["base_rate"])
    return None


def base_rate_evidence() -> Optional[dict[str, Any]]:
    """근거 블록용 — {value, as_of, source} 또는 None."""
    r = get_rates()
    if not r or "base_rate" not in r:
        return None
    return {
        "value": r["base_rate"],
        "as_of": r.get("base_rate_as_of"),
        "source": r.get("source"),
        "provenance": r.get("provenance"),
    }
