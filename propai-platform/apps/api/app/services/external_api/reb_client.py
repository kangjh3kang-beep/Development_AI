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
            y -= 1; m = 12
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
    if not region_sido:
        # ★**이중 가드다**(변이 «이 조건 무력화» → 생존 = 등가). 아래 루프의
        #   `region_sido not in row_region_names(row)` 도 빈 문자열을 **어떤 집합에서도 못 찾아**
        #   전 행을 건너뛴다(후보 집합은 빈 값을 담지 않는다). 그래서 이 조기 반환을 지워도
        #   결과가 같다 — **구멍이 아니라 의도된 이중 방어**다(§B-5: 사유를 코드에 적는다).
        #   그래도 남기는 이유: 「지역을 모르면 거부한다」는 계약을 **읽는 사람에게 보이게** 하기 위함.
        # ★★독립 리뷰 적발(R2 HIGH-F): 종전에는 `region_sido` 가 falsy 면 **필터가 통째로 꺼져**
        #   전 지역에서 «시점이 가장 늦은 행» 이 이겼다. 실측: `zzz없는지역` 이 **제주 9.9%** 를
        #   «R-ONE … 실측» 으로 받아 `desk_appraisal` 의 자본환원율로 채택됐다.
        #   형제 `rate_series_from_rows` 는 같은 상황에서 «전국» 으로 좁히는데 이 함수만
        #   «전 지역 무필터» 였다 — **같은 축을 두 함수가 반대로 처리**했다.
        #   ⇒ 지역을 모르면 **거부**한다(모름을 유효값으로 표현하지 않는다). 소비처는 각자
        #     문서화된 기본값으로 떨어지고, 그것은 정직하다.
        return None
    # ★★독립 리뷰 적발(HIGH-1 · 2026-09-08): 이 함수는 **같은 rows** 를 받는 형제인데
    #   정확일치 처방을 안 받고 있었다(`land_price.py` 가 `rate_series_from_rows` 와
    #   **나란히** 호출한다). 종전에 셋이 동시에 틀렸다:
    #     ① `CLS_FULLNM`(계층 경로) 부분문자열 — «경기» 가 `"경기>성남시"` 에 매칭돼
    #        **성남시 값 0.30 을 「경기」로 채택**했다(리뷰어 실측).
    #     ② `region_keys` 에 **`ITM_NM`** 이 있었다 — 지역이 **아닌** 필드로 지역을 판정.
    #        `ITM_NM="경기지수"` 행이 «경기» 로 잡혔다.
    #     ③ `and region_txt.strip()` — 지역 필드가 **빈 행은 필터를 통과**했다(per-row fail-open).
    #   ⇒ `row_region_name` 정확일치로 통일한다. 판정 규칙은 **한 자리**에 둔다.
    val_keys = ("DTA_VAL", "VALUE", "DATA_VALUE", "dtaVal")
    time_keys = ("WRTTIME_IDTFR_ID", "WRTTIME_DESC", "WRTTIME", "PRD_DE")
    best: tuple[str, float] | None = None
    tied: set[float] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if region_sido not in row_region_names(row):
            continue
        raw = next((row.get(k) for k in val_keys if row.get(k) not in (None, "")), None)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        tval = str(next((row.get(k) for k in time_keys if row.get(k) not in (None, "")), ""))
        if best is None or tval > best[0]:
            best = (tval, val)
            tied = {round(val, 6)}
        elif tval == best[0]:
            # ★같은 시점에 여러 행이 매칭됐다 — 값이 갈리면 **고를 근거가 없다**.
            tied.add(round(val, 6))
    if best is None:
        return None
    if len(tied) > 1:
        # ★★독립 리뷰 R3 HIGH-2(라이브 확증 2026-09-08): 후보 필드 집합으로 넓히면서
        #   **카디널리티 과매칭**이 생겼다. 주택매매가격지수·전월세전환율 표는 한 (지역, 시점)에
        #   **규모 구분 5행**이 있다(실측: `(서울, 202607)` → 5행). 종전 `tval >= best[0]` 은
        #   동률에서 **마지막 행이 이겨** 행 순서에 따라 5.4 / 6.6 / 7.9 가 나왔고,
        #   그 값이 보증금 환산 → NOI → 수익환원가액으로 흘러 화면에 «R-ONE 실측» 으로 찍혔다.
        #   ⇒ **모호하면 거부한다.** 소비처는 문서화된 기본값으로 떨어지고 그것을 `[기본]` 으로
        #     표기한다(정직). 값을 임의로 고르는 것보다 낫다.
        #   ★개선 여지: 표가 «전체» 같은 집계 행을 명시하면 그것을 고를 수 있다 — 다만 그 표기가
        #     표마다 같다는 근거가 없어(이 PR 이 배운 것) 지금은 거부한다.
        logger.info(
            "R-ONE 최신값 모호 — 같은 시점에 값이 다른 행이 여럿(거부)",
            region=region_sido, wrttime=best[0], values=sorted(tied),
        )
        return None
    return (round(best[1], 4), best[0])


def rate_series_from_rows(
    rows: list[dict[str, Any]], region_sido: str, *, _no_fallback: bool = False,
) -> list[tuple[str, float]]:
    """변동률(%) 시계열 [(YYYYMM, rate)] 추출 — ITM='변동률'만, 지역(sido→전국 폴백), 시점 오름차순."""
    if not rows:
        return []
    val_keys = ("DTA_VAL", "VALUE", "DATA_VALUE", "dtaVal")
    time_keys = ("WRTTIME_IDTFR_ID", "WRTTIME", "PRD_DE")

    def _collect(region_filter: str | None) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            itm = str(row.get("ITM_NM") or "")
            # ★★주석 정정(독립 리뷰 R3 MEDIUM-6): 종전 주석은 *"'누계' 등 제외"* 라 했지만
            #   `"누계변동률"` 은 `"변동"` 을 **포함해 통과한다** — 거짓 면역 주장이었다(§C-11).
            #   그러면 한 (지역,시점)에 «당월변동률»·«누계변동률» 두 행이 잡혀 시계열이 배로 늘고
            #   고유 기간이 모자라 `cumulative_factor` 가 **None** 으로 떨어진다(무고지 폴백).
            #   ★라이브 `distinct_ITM_NM` 은 표마다 다르다(지가변동률=«변동률» 1종 · 주택지수=«지수»)
            #     — **미측정 표가 있으므로** 이 필터를 좁히는 것은 별건으로 남긴다(그때 그 표를 재라).
            #   지금 보장하는 것은 «변동» 을 **포함하지 않는 항목은 제외» 뿐이다.
            if itm and "변동" not in itm:
                continue
            # ★★시도 행은 **정확일치**로 고른다(2026-09-08). 종전에는 `region_filter not in
            #   region_txt` 였는데 `region_txt` 에 `CLS_FULLNM`(**계층 경로**)이 섞여 있어
            #   `"경기"` 가 **경기 산하 모든 시군구·동**에 매칭됐다.
            #
            #   ★라이브 실측(`/land-price/rone-test` — 저장소가 그 용도로 갖고 있던 진단 경로):
            #     · `CLS_NM` 은 **축약형 시도명**(`"전남"`) — 시도 행이 **정확일치로 실재**한다
            #     · `CLS_FULLNM` 은 계층 경로(`"전남광주>전남"` · `"부산>중구"` ·
            #       `"제주>제주시>일도일동"`) — 한 표에 시도·시군구·**동**이 섞여 있다
            #   그래서 부분문자열 매칭은 **같은 달의 수십 개 하위지역**을 한 시계열로 모았고,
            #   소비처는 그것을 「그 지역 24개월」로 읽어 ∏(1+r/100) 로 곱했다
            #   (라이브: 경기 `yearly 2024 = +80.68%` — 월 최대 0.267%로는 물리적으로 불가).
            if region_filter and region_filter not in row_region_names(row):
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
    if _no_fallback:
        # ★scope 판정용 — 폴백 없이 «그 지역 시계열이 실재하는가» 만 답한다.
        series.sort(key=lambda x: x[0])
        return series
    if not series:
        # ★★fail-open 제거(2026-09-08). 종전에는 `_collect("전국") or _collect(None)` 이었고
        #   그 **`_collect(None)` 이 fail-open** 이었다 — 지역 필터가 안 맞으면 **모든 지역**을
        #   돌려주고, 소비처는 그것을 「그 지역 24개월」로 읽었다.
        #
        #   ★라이브 실측(2026-09-08): `zzz없는지역` 이 누적계수 **1.047** 을 냈다.
        #     같은 값을 **정식 명칭 `경상남도`** 도 냈다(축약형 `경남` 은 판정 거부로 `None`).
        #     ⇒ **존재하지 않는 지역이 확신 있는 답을 내고, 진짜 지역은 거부**되고 있었다.
        #     그 1.047 은 「R-ONE 지가변동률 **실데이터**」로 라벨링돼 감정평가 단가에 곱해졌다.
        #
        #   ★종전에 못 고친 이유는 «원시 행의 지역 필드 표기를 확인하지 못해서» 였다.
        #     이제 실측했다(`/land-price/rone-test` — 저장소가 그 용도로 이미 갖고 있던 진단
        #     엔드포인트다): `CLS_NM` 은 **축약형**(`"전남"`) · `CLS_FULLNM` 은 **계층 경로**
        #     (`"전남광주>전남"`) · 한 표에 시도·시군구·**동**이 섞여 있다.
        #
        #   ⇒ **전 지역 혼합(`_collect(None)`)은 더 이상 돌려주지 않는다.** 남기는 폴백은
        #     **실제 「전국」 행**뿐이고, 그것은 `rate_series_scope` 가 «전국» 이라고 **말한다**.
        #     둘 다 없으면 **빈 시계열**을 돌려준다 — 소비처의 판정 거부가 발화하게(모름을
        #     유효값으로 표현하지 않는다).
        #
        #   ★★종전 주석은 «남은 소비처: trend_from_rows · rate_series_scope ·
        #     land_price_index.monthly_rate_series_async» 라고 적었다. **재측정했다**
        #     (독립 리뷰 MEDIUM-4 — 자기 라벨을 승계하지 않는다):
        #     `monthly_rate_series_async` 는 **호출부 0건**이다(저장소 전수 — 정의와 계획서
        #     언급뿐). base 시점부터 이미 죽어 있었다 — 그 주석은 **틀린 사실**을 실어 날랐다.
        #     실사용 소비처는 `trend_from_rows`(차트) · `rate_series_scope`(라벨) 둘이다.
        series = _collect("전국")
    series.sort(key=lambda x: x[0])
    return series


def rate_series_scope(rows: list[dict[str, Any]], region_sido: str) -> str:
    """시계열이 **어느 범위**에서 나왔는지 — 소비처가 라벨을 거짓으로 쓰지 않게.

    ★★독립 리뷰 적발(R2 HIGH-A): 종전에는 `_has_region`(지역 **만** 본다)으로 판정했는데,
      시계열을 실제로 만드는 `_collect` 는 지역 + `ITM_NM` 에 "변동" 포함 + `DTA_VAL` 이
      **숫자로 파싱될 것**까지 본다. 그래서 «그 지역 행이 있다» 와 «그 지역 시계열이 있다» 가
      갈렸다 — R-ONE 이 결측을 `'-'` 로 주는 흔한 형태에서 **행은 있는데 시계열이 없어**
      전국으로 폴백하면서 scope 는 «경남» 이라고 말했고, 그 라벨이 감정평가 문서에 찍혔다.
      ⇒ **시계열을 만든 그 필터로 판정한다.** 판정과 산출을 갈라 두면 반드시 다시 갈린다.
    """
    if region_sido and rate_series_from_rows(rows, region_sido, _no_fallback=True):
        return region_sido
    if rate_series_from_rows(rows, "전국", _no_fallback=True):
        return "전국"
    return "미상(지역 필터 불일치 — 전체 행)"


def row_region_names(row: dict[str, Any]) -> set[str]:
    """행이 **지역으로 주장하는 이름들**(계층 경로는 제외한 정확값 집합).

    ★★어느 필드가 지역인지는 **통계표마다 다르다**(2026-09-08 라이브 실측 — 독립 리뷰 R2 HIGH-E
      가 지목한 미측정 전제를 재서 확인했다). 한 표의 모양을 보편이라 가정하면 다른 표에서
      **조용히 0건**이 된다:

        지가변동률(A_2024_00903)   CLS_NM="전남"   GRP_NM=null     CLS_FULLNM="전남광주>전남"
        전월세전환율(T2411631…)     CLS_NM="전체"   GRP_NM="서울"   ← ★지역은 GRP_NM 이다
                                   (CLS_NM 은 **규모 구분**: 전체·40㎡이하·60㎡초과 85㎡이하…)
        상업용수익률(A_2024_00683) CLS_NM="서울"                   CLS_FULLNM="광주>금호지구"

      ⇒ 후보 필드의 **정확값 집합**을 돌려주고, 소비처는 «찾는 시도명이 그 집합에 있는가» 로
        판정한다. 규모 구분(`"40㎡이하"`)은 시도명과 **절대 같아질 수 없으므로** 안전하다.

    ★계층 경로(`CLS_FULLNM`·`GRP_FULLNM`)는 **넣지 않는다** — `"경기>수원시"` 가 «경기» 에
      매칭돼 산하 시군구가 통째로 섞이던 것이 이 PR 이 고친 결함이다.

    ★**설명된 생존**(변이 «계층 경로를 후보에 추가» → SURVIVED): 이 설계는 **정확값 비교**라
      `"경기>수원시" != "경기"` 이므로 계층 경로를 넣어도 **시도명 판정이 바뀌지 않는다**
      (실측 4행 전수: 판정 차이 **0/4**). 즉 **등가 변이**이지 구멍이 아니다.
      ⇒ 그래도 넣지 않는 이유는 «부분문자열로 되돌아갈 때 즉시 새는 재료» 를 남기지 않기 위함이다.
    """
    if not isinstance(row, dict):
        return set()
    return {
        v for v in (str(row.get(k) or "").strip() for k in ("CLS_NM", "GRP_NM", "REGION_NM", "REGION"))
        if v
    }


def row_region_name(row: dict[str, Any]) -> str:
    """표시·디버깅용 대표 이름(후보 중 하나). **판정에는 `row_region_names` 를 쓴다.**"""
    for k in ("CLS_NM", "GRP_NM", "REGION_NM", "REGION"):
        v = str(row.get(k) or "").strip() if isinstance(row, dict) else ""
        if v:
            return v
    return ""


def _has_region(rows: list[dict[str, Any]], needle: str) -> bool:
    """그 지역의 행이 **정확일치**로 실재하는가(계층 경로 경유 과매칭 금지)."""
    return any(needle in row_region_names(row) for row in rows or [])


def distinct_period_count(series: list[tuple[str, float]]) -> int:
    """시계열의 **고유 기간 수**. 지역이 섞이면 같은 기간이 반복된다."""
    return len({t for t, _ in series if t})


def cumulative_factor_from_rows(
    rows: list[dict[str, Any]], region_sido: str, months: int = 24
) -> float | None:
    """월별 지가변동률(%) → 지역 최근 N개월 누적 변동계수(∏(1+r/100))."""
    series = rate_series_from_rows(rows, region_sido)
    if not series:
        return None
    recent = series[-months:] if months > 0 else series
    # ★★**판정 거부** — 요청한 개월 수만큼 **고유 기간**이 없으면 누적계수를 만들지 않는다.
    #   같은 달의 여러 지역을 곱하면 «24개월 누적»이 아니라 **지역 개수만큼의 거듭제곱**이다.
    #   실측(2026-09-07): 고유 기간 **1개**인 24행으로 1.0414 를 만들어 토지가액을
    #   근거 없이 +4.14% 부풀렸다. **하는 척하느니 안 하는 것이 옳다** —
    #   None 을 돌려주면 `land_price_index` 가 근사테이블로 폴백하고 그 출처를 밝힌다.
    if months > 0 and distinct_period_count(recent) < months:
        return None
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
