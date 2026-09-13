"""R-ONE 부동산통계정보 인제스션 레이어 — 다종 통계 단일 출처화.

지가변동률(reb_client) 외 주택가격지수 변동률·상업용 소득수익률(cap rate)·전월세전환율을
통계표(STATBL_ID)별로 조회해 시점수정·수익환원법에 실데이터를 주입한다.

설계 원칙(할루시네이션 방지):
 - STATBL_ID는 env(RONE_*_STATBL_ID)로 명시 설정하거나 키워드 자동탐색(rone-status).
 - 값은 sane-range 검증을 통과할 때만 채택, 아니면 기존 근사값으로 graceful 폴백.
 - 모든 반환값에 source('R-ONE' | '근사')를 명시해 출처 투명성 보장.

각 모듈이 각자 추정/하드코딩하던 시세·수익률·시점보정을 본 레이어로 단일화한다.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _sido_of(address: str) -> str:
    from app.services.land_intelligence.land_price_index import _sido_of as _s
    return _s(address)


# 통계표 레지스트리: env STATBL_ID 키 + 수록주기 + 탐색 키워드 + 합리적 값 범위
_STAT_REGISTRY = {
    "housing": {
        "env": "RONE_HOUSING_STATBL_ID", "cycle": "MM",
        "keyword": "주택종합 매매가격지수", "kind": "rate",  # 월 변동률 누적
    },
    "commercial_yield": {
        "env": "RONE_COMMYIELD_STATBL_ID", "cycle": "QQ",
        # ★MINOR-2(독립 리뷰): 이 `keyword` 는 **프로덕션 소비처가 0**인데(레지스트리에서 읽는
        #   코드 없음 · `/rone-status` 는 인자를 받는다) 다음 사람이 «이 표를 찾으라» 로 읽는다.
        #   `_CAP_RATE_ITM`(소득수익률)과 어긋나므로 함께 고친다.
        "keyword": "상업용부동산 소득수익률", "kind": "level",  # 최신 수익률(%)
        "sane": (1.0, 12.0),
    },
    "jeonse_conv": {
        "env": "RONE_JEONSE_CONV_STATBL_ID", "cycle": "MM",
        "keyword": "전월세전환율", "kind": "level",
        "sane": (2.0, 12.0),
    },
}

# ★자본환원율(cap rate)인 항목 — **하나의 자리**에 둔다(소비처가 이 이름을 복사하지 않게).
#   자본환원율 = 순영업소득 / 가치 = **소득수익률**이다. `투자수익률`(= 소득수익률 + 자본수익률)은
#   자본이득을 포함하므로 **cap rate 가 아니다** — 같은 파일 `commercial_cap_rate` 독스트링 참조.
#   ★재측정 명령(휘발성 — 값이 아니라 이것이 정본). ★★**프로덕션이 태우는 주기로 잰다**:
#       GET /api/v1/land-price/rone-test?statbl_id=<RONE_COMMYIELD_STATBL_ID>&cycle=QQ
#       ★독립 적대 리뷰 MEDIUM-3 — 초판은 `cycle=YY` 를 적었는데 **프로덕션은 `"QQ"` 리터럴**을
#         쓴다(아래 `fetch_statbl_rows(statbl, "QQ", …)`). YY 로 재면 «항목이 있으니 값을 낼 수
#         있다» 가 나오지만 **프로덕션 경로는 여전히 0행**이다 — 「내가 방금 잰 것이 사용자가
#         실제로 쓰는 그것인가」에 걸린다.
#       ⇒ 판정은 **두 조건의 곱**이다: ①그 주기에 행이 있는가 ②`distinct_ITM_NM` 에 아래 항목이 있는가.
#       ★그리고 `/rone-test` 의 `latest_value_(레벨형)` 은 **항목 필터 없이** 계산하므로
#         그 값이 보인다고 프로덕션이 채택한다는 뜻이 아니다(진단 ≠ 산출).
_CAP_RATE_ITM: tuple[str, ...] = ("소득수익률",)


def _statbl(kind: str) -> str:
    reg = _STAT_REGISTRY.get(kind, {})
    return (os.getenv(reg.get("env", "")) or "").strip()


async def housing_time_adjust(address: str = "") -> dict[str, Any] | None:
    """주택매매가격지수 월 변동률 누적 → 건물/주택 시점수정계수. 미설정/비정상 시 None."""
    statbl = _statbl("housing")
    if not statbl:
        return None
    try:
        from app.services.external_api.reb_client import (
            cumulative_factor_from_rows,
            fetch_statbl_rows,
        )
        rows = await fetch_statbl_rows(statbl, "MM", size=480)
        if not rows:
            return None
        sido = _sido_of(address)
        f = cumulative_factor_from_rows(rows, sido)
        if f and 0.5 < f < 2.0:  # sane: 24개월 누적이 ±100% 이내
            # ★★독립 리뷰 R2 HIGH-B: 이 형제도 «요청 지역이 아니어도 R-ONE 이라고 단정» 하고
            #   있었다. 실측에서 `zzz없는지역` 과 `경상남도` 가 **바이트 동일한 답**을 받았다 —
            #   PR 제목 그 자체가 형제에 살아 있었다. 라벨은 `land_price_index` 와 **같은 규칙**을 쓴다.
            from app.services.external_api.reb_client import rate_series_scope

            scope = rate_series_scope(rows, sido)
            if sido and scope == sido:
                return {"factor": f, "source": "R-ONE", "scope": scope,
                        "basis": f"주택매매가격지수 누적 변동({sido})"}
            # ★`source` 는 "R-ONE" 유지 — 프론트가 정확일치로 렌더한다(R2 MEDIUM-3).
            #   정직성은 `scope` + `basis` 가 나른다.
            return {"factor": f, "source": "R-ONE", "scope": scope,
                    "basis": (f"주택매매가격지수 누적 변동 — {scope} 범위 값"
                              f"(요청 지역{f' {sido}' if sido else ''}의 시계열이 없어 대체 · "
                              f"해당 지역 실데이터가 아닙니다)")}
    except Exception:  # noqa: BLE001
        pass
    return None


async def commercial_cap_rate(address: str = "") -> dict[str, Any] | None:
    """상업용부동산 **소득수익률** 최신값 → 자본환원율(cap rate). 비정상 시 None.

    ★★2026-09-12 — R10 이 «(소득수익률)» 표기를 **뺀** 근거는 *"어떤 코드도 `ITM_NM` 을 고르지
      않는다"* 였다. **이 PR 이 그 전제를 뒤집었다**(`_CAP_RATE_ITM` 으로 고른다) — 그러므로
      표기를 **되돌린다.** 전제가 바뀌었는데 그 위에 선 문장을 그대로 두면 거짓이 된다.
      투자수익률 = 소득수익률 + 자본수익률이라 **cap rate 로 쓰면 산식이 틀린다.**
    ★★독립 적대 리뷰 MAJOR-2 — 초판은 **성공 경로에서도 라벨이 거짓**이었다: 값은 소득수익률인데
      `basis` 가 «상업용부동산 **투자수익률** 실측» 이라고 말했고, 그 문자열이 제출 PDF
      (`report/render/appraisal_adapter.py:200`)와 화면에 그대로 인쇄됐다.
      ⇒ `basis` 를 **`_CAP_RATE_ITM` 에서 파생**시킨다(손으로 적은 문자열은 다음번에 또 갈린다).
    """
    statbl = _statbl("commercial_yield")
    if not statbl:
        return None
    try:
        from app.services.external_api.reb_client import (
            fetch_statbl_rows,
            latest_value_from_rows,
        )
        rows = await fetch_statbl_rows(statbl, "QQ", size=120)
        if not rows:
            return None
        # ★항목을 **선언**한다 — «무엇인지 모르면 채택하지 않는다».
        #   바로 위 독스트링이 *"투자수익률 = 소득수익률 + 자본수익률이라 cap rate 로 쓰면
        #   산식이 틀린다"* 고 적어 두었는데, 그것을 **강제하는 것이 한 줄도 없었다**
        #   (전역 §30 — 주석에 쓴 동작 주장은 그 자체가 검증 대상이다).
        #   ★라이브 실측(2026-09-12): 설정된 표는 `distinct_ITM_NM = ['투자수익률']` 하나뿐이라
        #     선언 없이는 그 값이 **그대로 자본환원율로 채택**된다(단일 항목은 «모호하지 않다»).
        res = latest_value_from_rows(rows, _sido_of(address), itm_allow=_CAP_RATE_ITM)
        if not res:
            return None
        val, wrttime = res
        lo, hi = _STAT_REGISTRY["commercial_yield"]["sane"]
        if lo <= val <= hi:
            return {"cap_rate": round(val / 100.0, 4), "pct": val,
                    "wrttime": wrttime, "source": "R-ONE",
                    # ★손으로 적지 않는다 — 선언한 항목에서 **파생**한다(MAJOR-2).
                    "basis": f"상업용부동산 {'·'.join(_CAP_RATE_ITM)} 실측"}
    except Exception as e:  # noqa: BLE001
        logger.warning("REB 조회 실패: %s", str(e)[:160])
    return None


async def jeonse_conversion_rate(address: str = "") -> dict[str, Any] | None:
    """전월세전환율 최신값(연 %) → 보증금↔월세 환산율. 비정상 시 None."""
    statbl = _statbl("jeonse_conv")
    if not statbl:
        return None
    try:
        from app.services.external_api.reb_client import (
            fetch_statbl_rows,
            latest_value_from_rows,
        )
        rows = await fetch_statbl_rows(statbl, "MM", size=120)
        if not rows:
            return None
        res = latest_value_from_rows(rows, _sido_of(address))
        if not res:
            return None
        val, wrttime = res
        lo, hi = _STAT_REGISTRY["jeonse_conv"]["sane"]
        if lo <= val <= hi:
            return {"rate": round(val / 100.0, 4), "pct": val,
                    "wrttime": wrttime, "source": "R-ONE",
                    "basis": "전월세전환율 실측"}
    except Exception as e:  # noqa: BLE001
        logger.warning("REB 조회 실패: %s", str(e)[:160])
    return None


async def land_price_trend(address: str = "") -> dict[str, Any] | None:
    """월별·연도별 지가변동률 통계 시계열(최근 24개월 + 연도별). 미가용 시 None."""
    from app.services.external_api.reb_client import fetch_land_price_changes, trend_from_rows
    rows = await fetch_land_price_changes(months=36)
    if not rows:
        return None
    sido = _sido_of(address)
    t = trend_from_rows(rows, sido, months=24)
    if not t:
        return None
    # ★★2026-09-07 — **범위와 고유 기간 수를 함께 싣는다.**
    #   화면이 이 시계열을 조건 없이 「R-ONE 실데이터」라고 라벨링했는데, 실측하니
    #   기간 고유가 **1개**(전부 202607)였다 — 24개월이 아니라 **같은 달의 24개 지역**.
    #   값만 주면 소비처가 라벨을 지어낸다. **무엇인지를 값과 함께** 준다.
    from app.services.external_api.reb_client import distinct_period_count, rate_series_from_rows, rate_series_scope
    # ★★2026-09-07 독립 리뷰 적발(CRITICAL-2) — 종전엔 `distinct_periods` 를
    #   **36개월 전체 fetch** 위에서 세고 배지는 `>= 24` 로 판단했다. 그런데 판정 거부
    #   (`cumulative_factor_from_rows`)는 **마지막 24개 원소** 위에서 센다. **축이 달랐다.**
    #   실측(17지역 × 36개월 = 612행, 지역 필터 불일치):
    #       distinct_periods(전체) = 36  → is_time_series **True** → 배지 안 뜸
    #       cumulative_factor      = None(같은 데이터를 «못 믿는다»고 거부)
    #       차트 monthly 기간 고유수 = **2 / 24**   ← 사용자가 보는 것은 이쪽
    #   **두 지표가 같은 데이터에 반대로 답했다.** → **같은 창**에서 센다.
    _MONTHS = 24
    series = rate_series_from_rows(rows, sido)
    window = series[-_MONTHS:] if _MONTHS > 0 else series
    t["scope"] = rate_series_scope(rows, sido)
    t["distinct_periods"] = distinct_period_count(window)
    t["requested_months"] = _MONTHS
    # 시계열로 쓸 수 있는가 — **판정 거부와 같은 기준**이다(두 지표가 갈리지 않게).
    t["is_time_series"] = t["distinct_periods"] >= _MONTHS
    # ★차트가 그리는 것과 이 판정이 같은 것을 보는지 확인 가능하게 함께 싣는다.
    t["chart_distinct_periods"] = distinct_period_count(
        [(str(m.get("period") or ""), 0.0) for m in (t.get("monthly") or [])])
    return t


async def get_market_stats(address: str = "", base_year: int | None = None) -> dict[str, Any]:
    """지역 부동산 시장 통계 묶음(시점수정·cap rate·전환율) — 모세혈관 주입용 단일 출처.

    각 항목은 R-ONE 실데이터 가용 시 채택, 아니면 None(호출측이 근사 폴백).
    """
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async

    # ★시점수정 기준연도는 호출자가 정한다(2026-08-22).
    #   종전엔 base_year 를 안 넘겨 기본값 2025 에 의존했다. 유일한 소비처인
    #   desk_appraisal 은 **공시연도(2026)** 기준으로 따로 시점수정하고 있어,
    #   같은 함수 안에서 두 시점수정이 **서로 다른 기준연도**를 쓰고 있었다.
    #   land_time_adjust 는 아직 소비처가 없지만(응답 '출처 투명화'용), 값이 실려 나가는 한
    #   틀린 기준으로 두면 나중에 쓰는 쪽이 그대로 오독한다.
    land_ta = await time_adjust_factor_async(address, base_year) if base_year is not None \
        else await time_adjust_factor_async(address)
    housing = await housing_time_adjust(address)
    cap = await commercial_cap_rate(address)
    jeonse = await jeonse_conversion_rate(address)
    trend = await land_price_trend(address)          # 월별·연도별 지가변동률 추이
    _region = _sido_of(address)
    return {
        "region": _region or "전국",
        # ★★독립 리뷰 R5 LOW-1(2026-09-08): 주소에서 시·도를 **해석하지 못했는데** `region` 이
        #   `"전국"` 으로 채워지면, 프론트의 «`scope != region` 이면 대체값» 판정이 `전국 == 전국`
        #   이라 **조용히 침묵**한다. 그때 정직성을 나르는 것은 백엔드 산문 하나뿐인데,
        #   프론트는 «백엔드 문구를 안 믿어도 성립한다» 고 선언한다 — 그 선언이 이 경우 깨졌다.
        #   ⇒ **해석 여부를 기계 필드로 분리**한다(모름을 유효값으로 표현하지 않는다).
        #     `region` 자체는 기존 소비처 계약이라 바꾸지 않는다.
        "region_resolved": bool(_region),
        "land_time_adjust": land_ta,                 # 토지 시점수정(지가변동률)
        "land_price_trend": trend,                   # 월별/연도별 통계분석(시계열)
        "housing_time_adjust": housing,              # 건물/주택 시점수정(주택가격지수)
        "cap_rate": cap,                             # 상업용 투자수익률(자본환원율)
        "jeonse_conversion_rate": jeonse,            # 전월세전환율
        "rone_available": any([
            (land_ta or {}).get("source") == "R-ONE", housing, cap, jeonse, trend,
        ]),
    }
