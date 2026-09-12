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

# ★★값·시점 후보 키는 **한 자리**에 둔다(독립 리뷰 R9 MEDIUM-2 · 2026-09-09).
#   종전에는 두 추출기가 각자 튜플을 들고 있었고 **`WRTTIME_DESC` 가 한쪽에만** 있었다.
#   base 에서는 그 차이가 «출력 라벨» 수준이라 무해했는데, 이 PR 이 시점 키를
#   **그룹핑 + 「집계행 없는 시점 행 삭제」의 축**으로 승격시키면서 위험해졌다 —
#   `WRTTIME_DESC` 전용 표에서는 전 시점이 한 바구니가 되어 시점 구분이 사라진다(실측:
#   `rate_series` → `[('', 0.1), ('', 0.2), ('', 0.3)]` · `distinct_periods` 0).
#   ★어느 라이브 표가 `WRTTIME_DESC` 전용인지는 **미측정**이다 — 그래서 «무해하니 둔다» 가
#     아니라 **키를 합쳐 비대칭 자체를 없앤다**(드리프트할 자리를 남기지 않는다).
_VAL_KEYS = ("DTA_VAL", "VALUE", "DATA_VALUE", "dtaVal")
# ★★순서 교정(독립 리뷰 R10 MEDIUM · 2026-09-12): 통합하면서 `WRTTIME_DESC` 를 **2순위**로
#   넣었는데, 그것은 **설명형**(`"2024년 10월"`·`"'24년 7월"`)이라 정렬가능 키보다 앞에 두면
#   시계열이 **사전식으로 뒤섞이고**(10월이 1월보다 앞) `YYYY` 로 시작하지 않는 표기에선
#   **연도별 통계가 통째로 사라진다**(실측). 미측정 키를 정렬가능 키 앞에 두는 것은
#   «비대칭 제거» 가 아니라 위험 전파다. ⇒ **맨 뒤**로.
_TIME_KEYS = ("WRTTIME_IDTFR_ID", "WRTTIME", "PRD_DE", "WRTTIME_DESC")



def _period_of(row: dict[str, Any], time_keys: tuple[str, ...]) -> str:
    """행의 작성시점 문자열(없으면 빈 문자열)."""
    return str(next((row.get(k) for k in time_keys if row.get(k) not in (None, "")), ""))


def _has_usable_value(row: dict[str, Any], val_keys: tuple[str, ...]) -> bool:
    """그 행이 **쓸 수 있는 수치**를 담았는가(R-ONE 은 결측을 `'-'`·`''`·`None` 로 준다)."""
    raw = next((row.get(k) for k in val_keys if row.get(k) not in (None, "")), None)
    try:
        float(raw)
    except (TypeError, ValueError):
        return False
    return True


def narrow_to_period_aggregate(
    rows: list[dict[str, Any]], time_keys: tuple[str, ...],
    val_keys: tuple[str, ...] = _VAL_KEYS,
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
                                         = `(6.96, '2005')`).
                                       ★★«최신이 2005년» 이라 단정하지 마라(독립 리뷰 R8 F-4):
                                       그 300행은 `pIndex="1"` **단일 페이지**이고, 이 파일의
                                       형제 주석(`fetch_recent_monthly_rows`)이 이미
                                       *"A_2024_00903 등은 2005년~·지역블록·**오래된순**이라
                                       pSize로는 최신이 안 잡힘"* 이라고 적어 두었다.
                                       ⇒ 관측은 **«잘린 첫 페이지의 최댓값이 2005»** 이지
                                         «표의 최신이 2005» 가 아니다(§증거규율 1 — 관측≠추론).
                                       ★이 구분이 처방을 가른다: 「cycle 을 바꾼다」가 아니라
                                         **「시점 지정 조회(`fetch_recent_monthly_rows` 계열)를 쓴다」**
                                         가 옳을 수 있다(§29 — 없는 것을 만드는 것과 있는 것을
                                         안 쓴 것은 처방이 다르다). 정렬 방향은 **미측정**이다.
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
        # ★★독립 리뷰 R10 HIGH(2026-09-12): 종전엔 집계행이 **존재하기만 하면** 규모 행을
        #   통째로 버렸다. 그런데 R-ONE 은 결측을 `'-'`·`''`·`None` 로 준다 — 이 파일의
        #   `rate_series_scope` 독스트링이 *"결측을 `'-'` 로 주는 **흔한 형태**"* 라고
        #   **내가 직접 적어 둔 관측**이다. 그 한 셀 때문에:
        #     · `latest_value_from_rows` → 값 있는 규모 행이 지워져 **한 달 묵은 값**이
        #       「R-ONE 실측」으로 나갔다(실측: 집계행 값 `'-'` → `(5.4, '202606')`).
        #       ★내 테스트 이름이 못박은 계약(«구값을 최신인 척 내보내지 않는다»)을 **다시** 깼다.
        #     · `rate_series_from_rows` → 24개월 중 **한 달**만 결측이어도 그 시점이 통째로
        #       사라져 고유기간 23 → 누적계수 **None**(실측).
        #   ★계획서 §347 의 «좁히기가 실패하면 종전 거부로 되돌아가므로 거짓 값은 아니다» 가
        #     **반증됐다** — 좁히기가 «성공» 하고 거짓 값이 나온다.
        #   ⇒ **쓸 수 있는 값을 담은 집계행일 때만** 좁힌다. 아니면 그 시점은 원래 행을 유지하고
        #     호출부의 거부·건너뛰기가 받아 낸다(값을 지어내지 않는다).
        agg = [
            r for r in group
            if str(r.get("CLS_NM") or "").strip() == _AGGREGATE_CLS_NM
            and _has_usable_value(r, val_keys)
        ]
        out.extend(agg or group)
    return out


def latest_value_from_rows(
    rows: list[dict[str, Any]], region_sido: str = "", *,
    itm_allow: tuple[str, ...] | None = None,
) -> tuple[float, str] | None:
    """월/분기 행에서 지역 매칭 최신 시점의 값(%)·작성시점을 반환. 값 필드 방어적 탐색.

    `itm_allow` — **호출자가 «무엇의 값을 원하는지» 선언한다**(기본 `None` = 종전 동작).

    ★왜 필요한가(2026-09-12 라이브 실측): 이 함수에는 항목 **카디널리티** 가드만 있었다 —
      한 시점에 `ITM_NM` 이 여럿이면 거부한다(아래 `_homogeneous`). 그런데 **단일 오항목**은
      «모호하지 않다» 는 이유로 **그대로 채택**된다. 실측:

          latest_value_from_rows([{ITM_NM:"투자수익률", CLS_NM:"서울", DTA_VAL:6.96, …}], "서울")
              → (6.96, '2005')   ★채택된다

      `commercial_cap_rate` 가 부르는 상업용 표(`A_2024_00683` 계열)는 `distinct_ITM_NM` 이
      **`['투자수익률']` 하나뿐**이라 정확히 이 경로를 탄다. 그리고 형제 모듈이 이미
      *"투자수익률 = 소득수익률 + 자본수익률이라 **cap rate 로 쓰면 산식이 틀린다**"* 라고
      적어 두었다 — **저장소가 아는 사실인데 강제하는 것이 없었다.**
      ⇒ «모호하면 거부» 만으로는 부족하다. **«무엇인지 모르면 채택하지 않는다»** 가 필요하다.

    ★형제 정합: `rate_series_from_rows` 는 처음부터 항목 필터(`변동률`)를 갖고 있었다.
      **같은 축의 처방을 형제 한쪽에만 걸어 두었던 것**을 여기서 맞춘다(전역 §D-20).

    ★선언하면 «혼재» 도 읽을 수 있다: 항목을 특정했으므로 더 이상 모호하지 않다.
      선언하지 않으면 종전 계약(혼재 → 거부)이 **그대로** 유지된다.
    """
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
    val_keys, time_keys = _VAL_KEYS, _TIME_KEYS

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
    _matched_raw = [
        row for row in rows if isinstance(row, dict) and region_sido in row_region_names(row)
    ]
    # ★항목 식별 가드 — 호출자가 선언한 항목만 남긴다(선언이 없으면 무동작).
    #   ★**시점 그룹화보다 먼저** 건다. 뒤에 걸면 «엉뚱한 항목이 섞였다» 는 이유로 혼재 거부가
    #     먼저 발화해, 선언한 항목이 그 시점에 **있는데도** 거부된다.
    if itm_allow is not None:
        _allow = {str(x).strip() for x in itm_allow}

        def _itm_ok(row: dict[str, Any]) -> bool:
            itm = str(row.get("ITM_NM") or "").strip()
            # ★**항목 표기가 없는 표는 통과**시킨다 — 형제 `rate_series_from_rows` 의 계약과 같다
            #   («itm 이 비면 통과»). 이 코드베이스는 `ITM_NM` 이 **없는 표를 명시적으로 전제**한다.
            #   ★★이것은 **의도된 면제**이고 **부채**다: 항목을 표기하지 않는 표에서는 이 가드가
            #     아무 일도 하지 않으므로 «무엇인지 모르면 채택하지 않는다» 가 그 표에는 미적용이다.
            #     그래도 이렇게 두는 이유 — 거부로 바꾸면 **정상 경로를 막는다**(위양성).
            #     실측: 그렇게 짰더니 기존 회귀 2건이 빨개졌고(`test_cap_rate_refuses_for_unknown_region`
            #     · `test_market_stats_carries_every_rone_backed_statistic`) **그 테스트들이 옳았다**.
            #   ⇒ 이 면제는 `test_itm_identity_guard_passes_rows_that_carry_no_item_label` 이 잠근다
            #     (죽은 면제가 되지 않도록 **양방향**으로).
            return (not itm) or itm in _allow

        _matched_raw = [r for r in _matched_raw if _itm_ok(r)]
    # ★★독립 리뷰 R8 F-2(2026-09-08) — **내가 만든 회귀**다. 이 함수에는 항목(ITM) 필터가
    #   **한 줄도 없는데** 집계행 좁히기를 붙였다. 그래서 집계행(`CLS_NM="전체"`)이 **다른 항목**
    #   (예: `지수`)이면 그것이 좁히기에서 이겨 **엉뚱한 항목의 값**이 채택된다. 실측:
    #       rows = [전체/지수 7.5, 40㎡이하/전월세전환율 5.4]  (같은 지역·같은 시점)
    #       base   → 5.4 / 7.5  ★**행 순서에 따라 뒤집힌다**(운이지 정답이 아니다)
    #       branch → 7.5 / 7.5  ★**일관되게 틀린다** — 안정적이라 더 안 보인다
    #   그 7.5 는 `jeonse_conv` 의 sane (2.0,12.0) 을 **통과해** 「전월세전환율(R-ONE 실측)」로
    #   보증금 환산 → NOI → 수익환원가액까지 흘러간다.
    #   ⇒ **항목 축이 섞인 시점은 「무엇의 값인지」 알 수 없다 — 그 시점을 통째로 제외한다.**
    #     (형제 `rate_series_from_rows` 는 항목 필터를 갖고 있어 이 문제가 없다. 여기만 없었다 —
    #      처방을 형제 한쪽에만 걸었던 것이다.)
    #   ★라이브 항목 구성이 **미측정인 표가 있으므로 거부 쪽이 안전하다**(값을 지어내지 않는다).
    #
    # ★★독립 리뷰 R9 HIGH-1/HIGH-2(2026-09-09) — 위 처방이 **두 곳에서 자기 계약을 어겼다**:
    #   (1) 혼재 시점을 `continue` 로 **건너뛰어** 더 오래된 시점이 이겼다. 실측:
    #         최신 202607 혼재 · 직전 202606 깨끗 → `(5.4, '202606')`
    #       그 구값이 `source="R-ONE"` · `basis="…실측"` 으로 화면·제출본에 나가고 **시점은
    #       어디에도 렌더되지 않는다**(`wrttime` 소비처 0). 그런데 이 함수의 형제 계약은
    #       `test_missing_aggregate_at_the_latest_period_rejects_not_returns_stale` —
    #       *"최신 시점에 집계행이 없으면 **거부**한다 — 구값을 최신인 척 내보내지 않는다"* 다.
    #       **같은 속성을 원인만 다르게 반대로 처리**했다. ⇒ **최신 시점이 혼재면 통째로 거부**한다.
    #   (2) `_items.discard("")` 때문에 **한쪽 ITM 이 비면** 혼재로 안 세어, 커밋 `4fdccbd17` 이
    #       «고쳤다» 고 선언한 그 회귀(`7.5 / 7.5`)가 **그대로 재현**됐다. 그리고 그 줄은
    #       **어느 방향으로도 안 잠겨** 있었다(변이 `discard` 제거 → SURVIVED).
    #       ★이 코드베이스는 `ITM_NM` 이 **없는 표를 명시적으로 전제**한다(`rate_series` 의
    #         «itm 이 비면 통과»). 그러니 «부재» 는 무시할 값이 아니라 **하나의 항목값**이다.
    #       ⇒ `discard("")` 를 지운다 — 부재도 항목으로 센다.
    _by_period: dict[str, list[dict[str, Any]]] = {}
    for row in _matched_raw:
        _by_period.setdefault(_period_of(row, time_keys), []).append(row)
    _latest_period = max(_by_period, default="")
    _homogeneous: list[dict[str, Any]] = []
    for _period, _grp in _by_period.items():
        # ★«부재» 도 하나의 항목값으로 센다(discard 하지 않는다 — R9 HIGH-2).
        _items = {str(r.get("ITM_NM") or "").strip() for r in _grp}
        if len(_items) > 1:
            logger.info(
                "R-ONE 최신값 항목 축 혼재 — 한 시점에 ITM_NM 이 여럿",
                region=region_sido, wrttime=_period, items=sorted(_items),
                latest=(_period == _latest_period),
            )
            if _period == _latest_period:
                # ★최신 시점을 못 읽으면 **구값을 최신인 척 내보내지 않는다**(형제 계약과 동일).
                return None
            continue
        _homogeneous.extend(_grp)
    matched = narrow_to_period_aggregate(_homogeneous, time_keys)

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
    val_keys, time_keys = _VAL_KEYS, _TIME_KEYS

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
            # ★★주석 정정(독립 리뷰 R3 MEDIUM-6): 종전 주석은 *"'누계' 등 제외"* 라 했지만
            #   `"누계변동률"` 은 `"변동"` 을 **포함해 통과한다** — 거짓 면역 주장이었다(§C-11).
            #   그러면 한 (지역,시점)에 «당월변동률»·«누계변동률» 두 행이 잡혀 시계열이 배로 늘고
            #   고유 기간이 모자라 `cumulative_factor` 가 **None** 으로 떨어진다(무고지 폴백).
            #   ★라이브 `distinct_ITM_NM` 은 표마다 다르다(지가변동률=«변동률» 1종 · 주택지수=«지수»)
            #     — **미측정 표가 있으므로** 이 필터를 좁히는 것은 별건으로 남긴다(그때 그 표를 재라).
            #   지금 보장하는 것은 «변동» 을 **포함하지 않는 항목은 제외» 뿐이다.
            # ★중복 판정 제거(독립 리뷰 R9 MEDIUM-1): 이 검사는 위 `candidates` 에 **이미 있다**.
            #   지역 축의 중복은 지웠는데 **항목 축은 두 자리로 남겼다** — 12줄 위에 내가
            #   «판정은 `candidates` 한 곳에만 둔다» 라고 써 둔 바로 그 함수에서.
            #   지금은 등가라 무해하지만, **중복은 변이를 눈멀게 한다**(한쪽만 바꾸면 다른 쪽이 막는다).
            #   실측: 루프 쪽만 무력화 → SURVIVED / `candidates` 쪽만 무력화 → CAUGHT.
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
            #
            # ★★중복 판정 제거(자기적용 변이 2026-09-09): R6 에서 지역 필터를 위 `candidates`
            #   목록으로 옮기면서 **여기 있던 같은 검사를 안 지웠다.** 기능상 무해했지만
            #   **변이 검증을 눈멀게 했다** — 한쪽만 바꾸면 다른 쪽이 막아 «등가» 로 나오고,
            #   그래서 «정확일치» 라는 이 함수의 핵심 계약이 **어느 쪽으로도 안 잠겨** 있었다
            #   (실측: `:391` 만 부분문자열로 약화 → `::VERDICT=SURVIVED`).
            #   ★이 파일이 스스로 «판정 규칙은 **한 자리**에 둔다» 고 적어 뒀는데 두 자리로 만들었다.
            #   ⇒ 판정은 `candidates` 한 곳에만 둔다.
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

    ★계층 경로(`CLS_FULLNM`·`GRP_FULLNM`)는 **넣지 않는다**.
      ★★단, **안전을 만드는 것은 이 배제가 아니다**(자기적용 변이 2026-09-09 — 「~가 보장한다」를
        태웠더니 내 귀속이 틀렸다). 방어는 **짝**이고, 두 변이가 **각각 등가**로 나왔다:
            후보 집합에 `CLS_FULLNM` 추가        → SURVIVED (정확일치라 `"광주"` ≠ `"광주>금호지구"`)
            정확일치 → 부분문자열로 약화         → SURVIVED (후보에 경로가 없다)
        **둘 다 무너져야** 원래 결함(«경기» 가 `"경기>수원시"` 에 매칭돼 산하 시군구가 통째로
        섞이던 것 — 이 PR 이 고친 그것)이 돌아온다.
      ⇒ 그래서 락은 다리가 아니라 **속성**을 본다:
        `test_a_region_that_merely_contains_the_sido_name_does_not_match`
        («「전남광주」는 「전남」이 아니다» — 어느 다리가 무너져도 빨개진다).
      ★경로를 계속 배제하는 이유는 **이중 방어**이자 의도 표시다 — 지우지 마라.

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
    #     값이 같으면(중복 표기) 한 번만 센다.
    #   ★★`months_counted`·`ambiguous_periods` 의 **소비처**(독립 리뷰 R8 F-1 — 종전엔 이 자리에
    #     «화면이 말하게 한다» 고 써 놓고 **읽는 쪽이 0** 이었다. 거짓 동작 주장이었다):
    #       · 화면  `DeskAppraisalReportClient.tsx` — 「값이 갈린 N개 시점 제외 — 부분 합계」·「6/12개월」
    #       · 제출본 `report/render/appraisal_adapter.py` — §5 «부분 합계입니다» 줄
    #       · 락    `test_pdf_reports_partial_yearly_and_non_timeseries` · 렌더 락 2건
    #   ★버리면 그 해 합계는 **작아진다** — 부풀림보다 덜 보이므로(「올해가 좀 느렸구나」) 반드시 말해야 한다.
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
