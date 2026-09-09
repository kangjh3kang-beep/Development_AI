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


# ★규모 구분 표의 **집계 행** 표기(라이브 실측 2026-09-08 — 주택매매가격지수 442/442 조합에
#   정확히 1행). 이 표기가 없는 표에서는 아래 좁히기가 무동작이므로 안전하다.
_AGGREGATE_CLS_NM = "전체"


def _period_of(row: dict[str, Any], time_keys: tuple[str, ...]) -> str:
    """행의 작성시점 문자열(없으면 빈 문자열)."""
    return str(next((row.get(k) for k in time_keys if row.get(k) not in (None, "")), ""))


def narrow_to_period_aggregate(
    rows: list[dict[str, Any]], time_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    """(시점)별로 집계행(`CLS_NM == "전체"`)이 있으면 **그 시점은 집계행만** 남긴다.

    ★★공용 헬퍼다(독립 리뷰 R5 HIGH-3). 종전에는 이 좁히기가 `latest_value_from_rows`
      **한 함수 안**에만 있었고, 같은 표 모양을 받는 형제 `rate_series_from_rows` 에는 없었다.
      그 결과 규모 구분 5행 표에서 시계열이 **5배**로 늘고, `trend_from_rows` 의 연간 합계가
      실제 6.0% 대신 **30.0%** 로 찍혔다(리뷰어 실측). 이 PR 의 표제 결함
      («경기 yearly 2024 = +80.68%»)과 **같은 산수**다 — 처방을 한 자리에만 넣은 것이 원인이다.
      ⇒ 판정을 **한 곳**에 두고 두 추출기가 함께 쓴다(저장소 §전역 전파방지).

    ★★**시점 단위**로 판정한다(독립 리뷰 R5 MEDIUM-2). 표 전체에 걸쳐 한 번에 거르면,
      최신 시점에만 집계행이 없을 때 그 시점 행이 **통째로 사라져** 한 달 묵은 값이 조용히
      «최신» 인 척 반환된다(실측: base 는 그 경우 거부했는데 좁히기가 `(5.0, '202607')` 을 냈다).
      시점별로 판정하면 집계행 없는 시점은 **원래 행을 그대로** 유지하고, 값이 갈리면
      호출부의 카디널리티 거부가 받아 낸다.

    ★집계 표기가 없는 표에서는 **무동작**이다 — 이제 **재서** 말한다(독립 리뷰 R6 요구 ③).
      종전 주석은 «무동작이므로 안전하다» 고 단정하면서 근거로는 **상업용수익률 표 하나**만
      제시했다(단정의 모집단 ≠ 근거의 모집단 — §27-c). 라이브 실측 2026-09-08:

        A_2024_00903 지가변동률 (MM) : `CLS_NM="전체"` **0건 / 5,000행 표본**(전량 10,400)
                                       `CLS_NM` 은 지역명(`시지역`·`군지역`·`중구`·`가오동`…)
                                       `distinct_ITM_NM` = `['변동률']`
        A_2024_00683 상업용수익률(YY): `CLS_NM` 이 **혼재**다 — 시도명 **24건**(`서울` 4 · `부산` 4 ·
                                       `대구` 4 · `인천`/`광주`/`대전`/`울산` 각 3, `CLS_FULLNM` 도
                                       같은 시도명) + 나머지는 **상권명**(`강남`·`광복동`·`금호지구`…).
                                       ⇒ **시도 선택은 된다**(실측 `latest_value_from_rows(rows,"서울")`
                                         = `(6.96, '2005')`). 다만 최신 시점이 **2005년**이다.
        A_2024_00615 주택지수  (MM) : `CLS_NM` 은 **규모 구분** — 여기서만 좁히기가 동작한다

      ★그래도 «전 표에서 무동작» 은 아니다 — **미측정 표가 있다**(전월세전환율은 서버 시크릿이라
        직접 못 쟀고, 이번 세션에 라이브로 재서 남긴 모양이 주택지수와 같다는 것만 근거다).
        구조적 안전장치는 따로 있다: `region_sido` 는 시도 축약키(또는 `"전국"`)라 `"전체"` 와
        **절대 같아질 수 없으므로**, 지역명이 `CLS_NM` 에 오는 표에서 정당한 행을 버릴 수 없다.
    """
    by_period: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        # ★공개 함수라 세 번째 소비처가 생길 수 있다 — 현재 두 호출부는 각자 걸러 넘기지만
        #   여기서 한 번 더 본다(독립 리뷰 R6 LOW-3). 없으면 `_period_of` 가 터진다.
        if not isinstance(row, dict):
            continue
        by_period.setdefault(_period_of(row, time_keys), []).append(row)
    out: list[dict[str, Any]] = []
    for group in by_period.values():
        agg = [r for r in group if str(r.get("CLS_NM") or "").strip() == _AGGREGATE_CLS_NM]
        out.extend(agg or group)
    return out


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

    # ★★독립 리뷰 R4 HIGH-3(2026-09-08): 종전 처방(«모호하면 거부»)은 **증상에 걸려 있었다**.
    #   카디널리티를 만드는 것은 «여러 지역이 섞였다» 가 아니라 **규모 구분 축**이고, 그 표들은
    #   집계 행을 스스로 갖고 있다. 라이브 실측(주택매매가격지수 `A_2024_00615` · 전 2,210행):
    #     · `(GRP_NM=서울, 202607)` → 5행 = `전체` / `40㎡이하` / `40㎡초과 60㎡이하` /
    #       `60㎡초과 85㎡이하` / `85㎡초과` — 값이 100.66 / 100.34 / 101.11 / 102.25 / 105.22
    #     · 그 응답 안의 **(지역,시점) 조합 442개 전부**에 `CLS_NM="전체"` 가 **정확히 1행**(예외 0)
    #   ★★그 «전부» 의 조건(독립 리뷰 R5 MEDIUM-5 — 조건 없는 단정은 참일 때도 검증 불가다):
    #     ① 그것은 **한 표**(`A_2024_00615`)의 관측이다. 다른 표에 일반화한 것이 아니다.
    #     ② 그것은 **`pIndex="1"` 단일 페이지** 위의 전수다(이 클라이언트는 페이징을 안 한다).
    #        내 census 는 2,210행 = 442 × 5 로 그 표를 덮었지만, 프로덕션은 `size=480` 으로
    #        부르므로 **약 22%** 만 본다. 어느 22% 인지는 API 정렬에 달렸고 **그 정렬은 미측정**이다
    #        (형제 주석이 `A_2024_00903` 에 대해 «오래된순» 이라고 이미 적어 두었다).
    #     ⇒ 그래서 좁히기는 «집계행이 **있을 때만**» 걸고, 없으면 그 시점은 원래 행을 유지해
    #       카디널리티 거부가 받아 내게 했다. 페이지가 잘려도 **거짓 값이 아니라 거부**가 된다.
    #   ⇒ 집계 행이 **실제로 있을 때만** 그 행으로 좁힌다. 거부는 그대로 **뒤에 남긴다**
    #     (집계 표기가 없는 표에서는 좁히기가 무동작이고, 그때 거부가 받아 낸다).
    #   ★없는 표기를 가정하지 않는다 — 상업용수익률 표는 `CLS_NM` 이 **상권명**이라 `전체` 가
    #     없고, 그 표에서는 이 좁히기가 아무 일도 하지 않는다(실측: `distinct_CLS_NM` =
    #     `강남`·`광복동`·`금호지구`… — 규모 구분이 아니다).
    matched = narrow_to_period_aggregate(
        [row for row in rows if isinstance(row, dict) and region_sido in row_region_names(row)],
        time_keys,
    )

    best: tuple[str, float] | None = None
    # ★이 초기화는 **읽히지 않는다**(기계 변이 «줄삭제» 생존 = 등가 · 2026-09-08).
    #   `tied` 는 아래에서 `best` 와 **항상 같은 분기에서 함께** 대입되고, 끝까지 `best is
    #   None` 이면 그전에 반환한다. 남기는 이유는 타입과 의도를 읽는 사람에게 보이기 위함이다
    #   — 구멍이 아니라 방어이므로 여기 적어 둔다(변이 점수 부풀리기 방지).
    tied: set[float] = set()
    for row in matched:
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
        #   ★★2026-09-08 갱신 — 이 자리는 이제 **최후 방어**다. 위에서 집계 행(`전체`)이 있으면
        #     그것으로 좁히므로, 여기까지 오는 것은 «집계 표기가 없는 표에서 여러 행이 같은 시점에
        #     서로 다른 값을 내는» 경우뿐이다. 그때는 여전히 **고를 근거가 없어** 거부한다.
        #     (종전 주석은 «표기가 표마다 같다는 근거가 없어 지금은 거부한다» 였다 — 그 근거를
        #      라이브로 재서 얻었으므로 좁히기를 앞에 넣었고, 이 문장은 그에 맞춰 고쳤다.)
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
        # ★★형제에도 같은 좁히기를 적용한다(독립 리뷰 R5 HIGH-3). 안 하면 규모 구분 5행 표에서
        #   시계열이 5배가 되고 `trend_from_rows` 의 연간 합계가 그대로 5배로 찍힌다.
        #
        # ★★★적용 **지점**을 형제와 맞춘다(독립 리뷰 R6 HIGH-1 · 2026-09-08).
        #   R5 대응에서 이 좁히기를 **전 행**에 걸었는데, `latest_value_from_rows` 는
        #   **지역 필터 뒤**에 건다. 그래서 한 시점에 **다른 지역**이 집계행을 가지면
        #   집계행이 없는 지역의 행이 그 시점에서 **통째로 삭제**됐다. 실측:
        #       rows = [서울/전체 0.5, 서울/40㎡이하 0.7, 경기/시군구계 0.3] (모두 202607)
        #       latest_value_from_rows(rows,"경기") = (0.3, '202607')   ← 유일행, 모호하지 않다
        #       rate_series_from_rows(rows,"경기")  = []                ← 같은 행이 사라졌다
        #       rate_series_scope(rows,"경기")      = "미상(지역 필터 불일치 — 전체 행)"
        #   ★«함수를 공유했다» 가 «축을 공유했다» 를 뜻하지 않는다 — 공용 헬퍼로 뺀 그 커밋이
        #     바로 그 착각을 했다. 좁히기는 **(지역, 시점)** 단위여야 한다.
        #   ★항목(ITM) 필터도 좁히기 **앞**에 둔다 — 집계행이 다른 항목에만 있으면
        #     쓸 행이 그 이유로 지워질 수 있다(좁히기는 «실제로 쓸 행» 위에서만 판정해야 한다).
        candidates = [
            r for r in rows
            if isinstance(r, dict)
            and not (str(r.get("ITM_NM") or "") and "변동" not in str(r.get("ITM_NM") or ""))
            and (not region_filter or region_filter in row_region_names(r))
        ]
        for row in narrow_to_period_aggregate(candidates, time_keys):
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
        상업용수익률(A_2024_00683) CLS_NM="서울"      GRP_NM=null   CLS_FULLNM="서울"
          ★★전사 오류 정정(독립 리뷰 R7 M-2 · 라이브 재측정 2026-09-08): 종전 이 줄은
            `CLS_NM="서울"` 에 `CLS_FULLNM="광주>금호지구"` 를 **짝지어** 적어 두었다. 실제로는
            **다른 두 행**이다 — 시도 행은 `CLS_NM`·`CLS_FULLNM` 이 **둘 다 `"서울"`** 이고,
            `"광주>금호지구"` 는 `CLS_NM="금호지구"` 인 **상권 행**의 경로다.
            그 짝지음이 같은 파일 안 다른 주석과 모순을 만들었고, 그 모순 위에서 내가
            «시도 선택 불가» 라는 **거짓 부채**를 xfail 로 남겼다(§C-10 — 주석의 근거도 검증 대상).

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
    """행 묶음에 그 지역 **이름**이 있는가(값·항목은 보지 않는다).

    ★★프로덕션 소비처 **0건**이다(독립 리뷰 R6 LOW-1 · `grep -rn "_has_region"` 전수 실측).
      R2 HIGH-A 대응에서 `rate_series_scope` 가 «이름이 있는가» → «시계열이 실제로 나오는가»
      (`rate_series_from_rows(..., _no_fallback=True)`)로 갈아타며 유일한 소비처가 사라졌다.
    ★지우지 않고 남기는 이유를 **여기 적는다**(참조 0건 함수는 다음 리뷰가 반드시 의심한다):
      이제 **테스트 대조군 전용**이다 — «이름은 있는데 시계열은 없다» 는 두 축의 차이를
      두 테스트가 이것으로 만든다(폴백 분기 · 공허 방지 선단언). 그 차이가 R2 HIGH-A 결함의
      본체라, 대조군을 없애면 그 락이 무엇을 보는지 흐려진다.
    ★**프로덕션 판정에 쓰지 마라** — 이름의 존재는 값의 존재를 함의하지 않는다.
    """
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

    # ★★독립 리뷰 R7 HIGH-1(2026-09-08) — **처방을 한 창에만 걸었다.**
    #   `cumulative_factor_from_rows` 는 «고유 기간이 모자라면 거부» 를 갖고 `is_time_series` 는
    #   **최근 24개월 창**에서 판정하는데, `yearly` 는 **시계열 전체**를 그냥 더했다. 그래서
    #   좁히기가 무동작인 시점(집계행이 없는 표·구간)이 창 **밖**에 있으면 그 해의 막대만
    #   조용히 배수로 부풀고 **배지는 꺼져 있다**. 실측(집계행 없는 2024 + 있는 2025~26):
    #       최근24 고유기간 = 24 → is_time_series **True**(배지 꺼짐) · 누적계수 1.1272(정답)
    #       yearly = [2024: **12.0**, 2025: 6.0, 2026: 6.0]   ← 정답은 각 연 6.0
    #   이 PR 의 표제 결함(«경기 yearly 2024 = +80.68%»)과 **같은 산수**다.
    #   ⇒ 형제(`latest_value_from_rows`)가 이미 가진 규율을 여기에도 건다:
    #     **같은 시점에 값이 갈리면 고를 근거가 없다 — 합치지 말고 그 시점을 버린다.**
    #     값이 같으면(중복 표기) 한 번만 센다. 버린 시점 수를 함께 실어 화면이 말하게 한다.
    by_period: dict[str, set[float]] = {}
    order: list[str] = []
    for t, r in series:
        if t not in by_period:
            by_period[t] = set()
            order.append(t)
        by_period[t].add(round(r, 6))
    collapsed: list[tuple[str, float]] = []
    dropped: list[str] = []
    for t in order:
        vals = by_period[t]
        if len(vals) == 1:
            collapsed.append((t, next(iter(vals))))
        else:
            dropped.append(t)
    if dropped:
        logger.info(
            "R-ONE 지가변동률 시점 모호 — 같은 시점에 값이 다른 행이 여럿(해당 시점 제외)",
            region=region_sido or "전체", dropped=len(dropped), sample=sorted(dropped)[:3],
        )
    if not collapsed:
        return {}

    monthly = [{"period": t, "rate": round(r, 3)} for t, r in collapsed[-months:]]
    yearly_map: dict[str, float] = {}
    yearly_n: dict[str, int] = {}
    for t, r in collapsed:
        yr = t[:4]
        if len(yr) == 4 and yr.isdigit():
            yearly_map[yr] = yearly_map.get(yr, 0.0) + r   # 월 변동률 합 ≈ 연간 변동률
            yearly_n[yr] = yearly_n.get(yr, 0) + 1
    # ★`months_counted` 를 함께 싣는다 — 「연간」이라 쓰면서 실제로 몇 달을 더했는지 말하지 않으면
    #   부분 합계가 연간 값인 척한다(모름을 유효값으로 표현하지 않는다).
    yearly = [
        {"year": y, "rate": round(v, 2), "months_counted": yearly_n.get(y, 0)}
        for y, v in sorted(yearly_map.items())
    ][-10:]
    return {"monthly": monthly, "yearly": yearly, "ambiguous_periods": len(dropped)}
