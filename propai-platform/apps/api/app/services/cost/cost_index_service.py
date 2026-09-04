"""KOSIS 건설공사비지수(orgId=397 한국건설기술연구원, tblId=DT_39701_A003) — 시점보정 서비스.

기본형건축비·표준품셈 단가는 특정 시점(고시일·품셈 개정연도) 기준이라, 다른 시점 비교 시
건설공사비지수로 물가 시점보정(escalation)이 필요하다. ecos_service.py 패턴(모듈 캐시 +
lazy refresh + TTL + graceful 폴백)을 재사용한다.

무날조: 키 미설정/조회 실패/해당 시점 지수 미확보 시 factor=1.0·confidence='unavailable'로
정직 표기한다(임의 보정 금지). opt-in 소비처(unit_price_repository.get_price(escalate_to_current=True))
에서만 사용되며, 여기서 자동으로 값을 바꾸지 않는다(순수 조회 서비스).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

_HOST = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
_ORG_ID = "397"            # 한국건설기술연구원(KICT) 공사비원가관리센터
_TBL_ID = "DT_39701_A003"  # 건설공사비지수
_TIMEOUT = 12.0
_TTL_SEC = 24 * 3600  # 월 단위 지수라 staleness 무해 — 일 1회 캐시로 반복호출 절감

# 모듈 캐시: _refresh()가 채우고 escalation_factor()가 읽는다(ecos_service.py와 동일 패턴).
_CACHE: dict[str, Any] = {"series": None, "fetched_at": 0.0}

# 동일 시점(PRD_DE)에 여러 분류행이 있을 때 대표로 우선 채택할 분류명 힌트(총지수/전체).
_PREFERRED_CLASS_HINTS = ("총지수", "전체", "계")


def _kosis_key() -> str:
    """KOSIS 인증키 — 관리자 런타임 오버레이(os.environ) 우선, Settings 폴백(ecos_key() 관례)."""
    key = os.getenv("KOSIS_API_KEY")
    if key:
        return key.strip()
    try:
        from app.core.config import settings

        return (settings.KOSIS_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def kosis_ready() -> bool:
    return bool(_kosis_key())


async def _fetch_series(start_ym: str, end_ym: str) -> list[dict[str, Any]]:
    """DT_39701_A003 월별 지수 원본 행을 조회한다. 키 미설정/실패/비JSON 응답 시 빈 리스트."""
    key = _kosis_key()
    if not key:
        return []
    params = {
        "method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
        "orgId": _ORG_ID, "tblId": _TBL_ID,
        "itmId": "ALL", "objL1": "ALL",
        "prdSe": "M", "startPrdDe": start_ym, "endPrdDe": end_ym,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await asyncio.wait_for(client.get(_HOST, params=params), timeout=_TIMEOUT)
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "").lower()
            body = resp.text or ""
            if "json" not in ctype and body.lstrip()[:1] in ("<",):
                logger.warning("KOSIS 공사비지수 non-JSON 응답", ctype=ctype, head=body[:80])
                return []
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("KOSIS 공사비지수 조회 실패", err=str(e)[:150])
        return []
    if isinstance(data, dict):  # 오류 응답({"err":...}/{"RESULT":...} 등) — 정상은 list.
        logger.warning("KOSIS 공사비지수 오류응답", msg=str(data)[:150])
        return []
    if not isinstance(data, list):
        return []
    return data


async def _refresh(months_back: int = 36) -> list[dict[str, Any]]:
    now = datetime.now()
    end_ym = now.strftime("%Y%m")
    start_ym = (now - timedelta(days=months_back * 31)).strftime("%Y%m")
    rows = await _fetch_series(start_ym, end_ym)
    if rows:
        _CACHE["series"] = rows
        _CACHE["fetched_at"] = time.time()
    return rows


def _fresh() -> bool:
    return bool(_CACHE.get("series")) and (time.time() - _CACHE.get("fetched_at", 0.0)) < _TTL_SEC


async def _get_series() -> list[dict[str, Any]]:
    if _fresh():
        return _CACHE["series"]
    return await _refresh()


def _index_for_ym(rows: list[dict[str, Any]], ym: str) -> Optional[float]:
    """rows 중 PRD_DE==ym 인 행의 지수값(동일 시점 다중분류면 '총지수/전체/계' 행 우선)."""
    matches = [r for r in rows if str(r.get("PRD_DE", "")) == ym]
    if not matches:
        return None
    preferred = next(
        (r for r in matches if any(h in str(r.get("C1_NM", "")) for h in _PREFERRED_CLASS_HINTS)),
        None,
    )
    row = preferred or matches[0]
    try:
        return float(row.get("DT"))
    except (TypeError, ValueError):
        return None


async def escalation_factor(base_ym: str, target_ym: str | None = None) -> dict[str, Any]:
    """base_ym → target_ym(기본 최신월) 건설공사비지수 보정계수.

    반환: {factor, base_index, target_index, base_ym, target_ym, source, confidence, note}.
    지수 미가용(키 미설정/조회 실패/해당 월 미확보) 시 factor=1.0·confidence='unavailable'(무날조).
    """
    source = f"KOSIS 건설공사비지수({_TBL_ID})"
    rows = await _get_series()
    if not rows:
        return {
            "factor": 1.0, "base_index": None, "target_index": None,
            "base_ym": base_ym, "target_ym": target_ym,
            "source": source, "confidence": "unavailable",
            "note": "KOSIS 키 미설정 또는 조회 실패 — 보정 미적용(1.0)",
        }

    eff_target_ym = target_ym or max(
        (str(r.get("PRD_DE", "")) for r in rows if r.get("PRD_DE")), default=None
    )
    base_idx = _index_for_ym(rows, base_ym)
    target_idx = _index_for_ym(rows, eff_target_ym) if eff_target_ym else None
    if base_idx is None or target_idx is None or base_idx <= 0:
        return {
            "factor": 1.0, "base_index": base_idx, "target_index": target_idx,
            "base_ym": base_ym, "target_ym": eff_target_ym,
            "source": source, "confidence": "unavailable",
            "note": "해당 시점 지수 미확보 — 보정 미적용(1.0)",
        }

    factor = round(target_idx / base_idx, 6)
    return {
        "factor": factor, "base_index": base_idx, "target_index": target_idx,
        "base_ym": base_ym, "target_ym": eff_target_ym,
        "source": source, "confidence": "live",
        "note": f"{base_ym}→{eff_target_ym} 건설공사비지수 {base_idx}→{target_idx}(계수 {factor})",
    }
