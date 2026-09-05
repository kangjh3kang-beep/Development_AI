"""토지 실거래 기반 평당가 — ★**지목을 거르지 않으면 개발부지 가격이 아니다**.

## 왜 이 모듈이 지목 필터부터 시작하는가 (라이브 실측 2026-09-05)

MOLIT 토지 실거래를 **필터 없이** 집계하면 개발 가능 필지 가격이 아니라
**도로·임야 가격**이 나온다. 12개월 전수 실측:

    노원(11350) n=372   도로+임야 87%   전체중앙 1,082 ↔ 「대」 1,369   (+26%)
    강남(11680) n=658   도로 55%        전체중앙 2,000 ↔ 「대」 11,798  (+490%)
    분당(41135) n=553   임야 67%        전체중앙   156 ↔ 「대」 1,843   (+1085%)

★강남은 표본의 **55%가 도로**라 **전체 중앙값이 사실상 도로 가격**이다.
★★그대로 썼으면 토지비를 **최대 11배 과소평가**하고, 그 값이 총사업비·ROI·PF 한도로
  전파된다. **없는 것보다 나쁘다** — 그럴듯한 숫자로 조용히 틀리기 때문이다.

## 이 저장소가 이미 알고 있던 것

`app/services/verification/field_audit/invariants/market_methodology.py:18` 이
*«`_calc_land_prices` 에는 **실거래 산출 경로가 전무**»* 라고 적고 **상시 배지**로
표면화하고 있다. 이 모듈은 그 배지가 가리키는 결함을 메우려는 것이다.
★그 파일이 **기각한 접근**도 적어 뒀다 — *«무관한 **건물** 실거래 유무로 배지를 뒤집는»*
  방식. 그래서 여기서는 **토지 실거래만** 쓰고 지목으로 거른다.
"""
from __future__ import annotations

import logging
import statistics as _st
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_PYEONG_SQM = 3.3058

# ★개발 가능 지목. **목록이 아니라 판정 기준**이 근거다 — 건축법상 건축이 가능한 지목.
#   `잡종지`는 실무상 개발 전환이 흔해 포함하되, `대`와 **분리 계수**해 근거에 남긴다.
#   ★제외되는 것: 도로·임야·전·답·과수원·하천 — 실측에서 표본의 **70~87%** 를 차지한다.
_BUILDABLE_JIMOK: tuple[str, ...] = ("대", "잡종지")

# 표본 하한. 미달이면 **값을 내지 않는다**(공시지가 폴백이 살아야 한다).
# ★실측 표본: 노원 대 36 · 강남 대 184 · 분당 대 81 — 8은 셋 다 통과하는 보수적 하한.
_MIN_SAMPLES = 8

_MONTHS = 12


async def land_trade_price_per_pyeong(
    *, sigungu5: str, dong: str | None = None,
) -> dict[str, Any] | None:
    """개발 가능 지목의 토지 실거래 평당가(만원/평). 표본 미달이면 `None`.

    Returns:
        {'per_pyeong_10k', 'n', 'jimok_counts', 'scope', 'basis'} 또는 None.
        ★`None` 은 «값이 0» 이 아니라 **«말할 수 없다»** 다 — 호출부는 폴백해야 한다.
    """
    s5 = (sigungu5 or "").strip()
    if not (len(s5) == 5 and s5.isascii() and s5.isdigit()):
        # ★전각 숫자가 `isdigit()` 를 통과하는 함정을 이 저장소가 이미 기록했다.
        return None

    from apps.api.integrations.molit_client import MolitClient

    now = datetime.now(UTC)
    yms: list[str] = []
    y, mo = now.year, now.month
    for _ in range(_MONTHS):
        yms.append(f"{y:04d}{mo:02d}")
        mo -= 1
        if mo == 0:
            mo = 12
            y -= 1

    client = MolitClient()
    kept: list[float] = []
    kept_dong: list[float] = []
    jimok_counts: dict[str, int] = {}
    seen = 0

    for ym in yms:
        try:
            rows = await client.get_transactions(s5, ym, prop_type="land", num_rows=1000)
        except Exception as e:  # noqa: BLE001
            logger.warning("토지 실거래 조회 실패 %s/%s: %s", s5, ym, str(e)[:80])
            rows = []
        for r in rows or []:
            seen += 1
            jimok = str(r.get("jimok") or "").strip()
            jimok_counts[jimok or "?"] = jimok_counts.get(jimok or "?", 0) + 1
            if jimok not in _BUILDABLE_JIMOK:
                continue
            try:
                amt = float(r.get("price_10k_won") or 0)
                area = float(r.get("area_m2") or 0)
            except (TypeError, ValueError):
                continue
            if amt <= 0 or area <= 0:
                continue
            pp = amt / (area / _PYEONG_SQM)
            kept.append(pp)
            if dong and dong in str(r.get("dong") or ""):
                kept_dong.append(pp)

    # 동 표본이 충분하면 동을 쓰고, 아니면 시군구로 넓힌다(축을 근거에 명시한다).
    pool, scope = (kept_dong, f"{dong}") if len(kept_dong) >= _MIN_SAMPLES else (kept, "시군구")
    if len(pool) < _MIN_SAMPLES:
        logger.info("토지 실거래 표본 부족(%s건 · 수집 %s건) — 값을 내지 않는다", len(pool), seen)
        return None

    med = _st.median(pool)
    excluded = seen - len(kept)
    return {
        "per_pyeong_10k": round(med, 1),
        "n": len(pool),
        "scope": scope,
        "jimok_counts": dict(sorted(jimok_counts.items(), key=lambda kv: -kv[1])[:6]),
        "basis": (
            f"토지 실거래(MOLIT) {scope} 중앙값 {med:,.0f}만원/평"
            f"(개발가능 지목 {'·'.join(_BUILDABLE_JIMOK)} {len(pool)}건 · 최근 {_MONTHS}개월 · "
            f"수집 {seen}건 중 도로·임야 등 {excluded}건 제외)"
        ),
    }
