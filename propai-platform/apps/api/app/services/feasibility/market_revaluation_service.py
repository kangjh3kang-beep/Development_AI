"""시장 재평가 엔진(F1) — 다중 시장가 출처를 신뢰도 가중으로 블렌딩.

단일 출처(regional_market_table)에 의존하던 분양가를, 여러 시장 신호를 신뢰도점수(0~100)로
가중 블렌딩해 "그때그때 현실을 반영한" 평당 분양가로 산출한다. 각 출처는 best-effort —
실패/희소하면 자동 제외되고 전체 신뢰도가 낮아진다(정직). 산출에는 timestamp가 붙어
분석원장(해시체인)에 가정버전으로 기록된다.

출처(현재):
  - regional   : 지역 시장표준 단가표(항상)
  - molit_real : MOLIT 실거래 최근 평균 평당가(있으면 — 가장 강한 시장신호)
확장 예정: 청약홈 분양가, AVM, 시세지수 추세.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_PYEONG = 3.3058


def _blend(sources: list[dict[str, Any]]) -> tuple[float, int]:
    """신뢰도×가중 평균으로 평당가·종합신뢰도 산출."""
    usable = [s for s in sources if s.get("price_per_pyeong") and s["price_per_pyeong"] > 0]
    if not usable:
        return 0.0, 0
    wsum = sum((s["confidence"] / 100.0) * s["weight"] for s in usable)
    if wsum <= 0:
        return 0.0, 0
    price = sum(s["price_per_pyeong"] * (s["confidence"] / 100.0) * s["weight"] for s in usable) / wsum
    # 종합신뢰도: 출처별 신뢰도의 가중평균 + 출처 다양성 보너스(최대 +10).
    base_conf = sum(s["confidence"] * s["weight"] for s in usable) / sum(s["weight"] for s in usable)
    diversity = min(10, (len(usable) - 1) * 6)
    return round(price), int(min(100, base_conf + diversity))


class MarketRevaluationService:
    """다중 출처 신뢰도 가중 시장 재평가."""

    async def revalue(self, *, address: str, building_type: str | None = None,
                      lawd_cd: str | None = None, land_area_sqm: float | None = None) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []

        # 1) 지역 시장표준 단가표(항상 시도)
        try:
            from app.services.feasibility.regional_pricing import get_regional_sale_price_per_pyeong
            rp = get_regional_sale_price_per_pyeong(address=address)
            if rp and rp > 0:
                sources.append({
                    "source": "regional", "label": "지역 시장표준",
                    "price_per_pyeong": float(rp), "confidence": 55, "weight": 0.35,
                    "count": None, "note": "지역·용도 표준단가",
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("revalue.regional_failed", error=str(e)[:120])

        # 2) MOLIT 실거래 최근 평균 평당가(있으면)
        try:
            molit = await self._molit_avg_per_pyeong(lawd_cd)
            if molit and molit["price_per_pyeong"] > 0:
                sources.append(molit)
        except Exception as e:  # noqa: BLE001
            logger.warning("revalue.molit_failed", error=str(e)[:120])

        price, confidence = _blend(sources)
        return {
            "price_per_pyeong": price,
            "confidence": confidence,
            "sources": sources,
            "blended_at": datetime.now().isoformat(timespec="seconds"),
            "available": price > 0,
        }

    async def _molit_avg_per_pyeong(self, lawd_cd: str | None) -> dict[str, Any] | None:
        """MOLIT 아파트 실거래 최근 평균 평당가(만원). lawd_cd 없으면 None."""
        lawd = (lawd_cd or "")[:5]
        if len(lawd) < 5:
            return None
        from apps.api.integrations.molit_client import MolitClient
        client = MolitClient()
        # 최근 3개월 수집
        now = datetime.now()
        yms = []
        y, m = now.year, now.month
        for _ in range(3):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
            yms.append(f"{y}{m:02d}")
        per_pyeong: list[float] = []
        for ym in yms:
            try:
                rows = await client.get_transactions(lawd, ym, prop_type="apt", num_rows=1000)
            except Exception:  # noqa: BLE001
                rows = []
            for r in rows:
                try:
                    price_10k = float(r.get("price_10k_won") or r.get("deal_amount") or 0)
                    area_m2 = float(r.get("area_m2") or r.get("exclusive_area") or 0)
                    if price_10k > 0 and area_m2 > 0:
                        # ★단위 통일: 만원/평 × 10,000 = 원/평 (지역표준이 원/평이라 일치시킴)
                        per_pyeong.append((price_10k / (area_m2 / _PYEONG)) * 10000)
                except Exception:  # noqa: BLE001
                    continue
        if not per_pyeong:
            return None
        # 이상치 절사(상하위 10%) 후 평균
        per_pyeong.sort()
        n = len(per_pyeong)
        trim = per_pyeong[int(n * 0.1): max(int(n * 0.1) + 1, int(n * 0.9))] or per_pyeong
        avg = sum(trim) / len(trim)
        cnt = len(per_pyeong)
        # 신뢰도: 거래건수·최근성 기반(많을수록↑, 최대 92)
        confidence = min(92, 50 + cnt)
        return {
            "source": "molit_real", "label": "MOLIT 실거래(최근3개월)",
            "price_per_pyeong": round(avg), "confidence": confidence, "weight": 0.65,
            "count": cnt, "note": f"아파트 실거래 {cnt}건 평균(상하위10% 절사)",
        }
