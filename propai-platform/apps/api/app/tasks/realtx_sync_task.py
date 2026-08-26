"""실거래 2층 주기 수집 — **파생된** 시군구만 태운다.

★왜 `etl_scheduled.run_etl_public_data` 에 붙이지 않았나
    그 함수는 시군구 **8개를 하드코딩**한다. 라이브 실측(2026-08-26)에서 그 목록은
    실사용 필지 **394개 중 4개(1.0%)** 만 덮었다. 저장을 거기 붙이면 **99% 가 안 담긴다.**
    → 모집단은 `realtx_store.derive_scan_targets` 가 `user_project_store` 에서 파생한다.

★쿼터
    MOLIT 키는 **G2B 와 같은 키**다(라이브 해시 일치 실측). G2B 는 2시간마다 태우므로
    이 태스크는 **하루 1회**만 돈다. `429/403` 은 **재시도하지 않는다** — 실패를
    "거래 0건"으로 기록하면 *"이 동네는 거래가 없었다"* 는 **거짓 사실**이 만들어진다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: **최근 창** — 매일 본다. 해제(`cdealType`)를 잡는 구간이다.
#:
#: ★해제는 **1개월부터 평평하다**(라이브 실측 2026-08-26 · 41465 apt · 노출별 해제율
#:   1개월 2.9% · 2개월 2.3% · 3개월 2.6% · 5개월 2.1% · 7개월 2.5%). 즉 해제는
#:   빨리 드러나므로 최근 3개월을 매일 보는 것으로 충분하다.
RECENT_MONTHS = 3

#: **꼬리 창** — 주 1회 본다. 등기일자(`rgstDate`)를 잡는 구간이다.
#:
#: ★★2026-08-27 — 종전 `DEFAULT_LOOKBACK_MONTHS = 3` 은 **등기의 절반을 구조적으로
#:   못 봤다.** 같은 시군구를 **노출 기간별로** 재니 기재율이 **시간의 함수**였다:
#:
#:       노출     1개월   2개월   3개월   5개월   7개월
#:       등기     5.4%   24.3%  **54.1%**  96.1%  97.4%
#:
#:   계약→등기 간격은 **완전 관측된 달**(202601 · 7개월 노출 · 표본 629)에서
#:   중앙 **72일** · p90 **103** · p95 **109** · 최대 **150**, **90일 초과가 23.5%** 다.
#:
#: ★**그리고 절단된 표본은 확신에 찬 오답을 준다.** 노출 1개월 달로 같은 지표를 재면
#:   *"90일 초과 0건(0.0%)"* 이 나온다. 우리가 저장한 3개월치만 봐도 같은 0% 가 나온다 —
#:   **창 자체가 관측을 자르기 때문**이다. 완전 관측된 옛 달을 따로 태우고서야 보였다.
#:   ★인계서의 *"등기 약 30% 기재"* 도 같은 이유로 무의미하다(나이를 안 밝힌 혼합 모집단).
#:
#: ★**이 상한(7)도 절단이다** — 5개월 96.1% → 7개월 97.4% 로 완만하지만 10·12개월은
#:   재지 않았다. 더 늘릴 근거가 생기면 늘려야 하고, **줄이면 등기를 다시 놓친다**.
TAIL_MONTHS = 7

#: 꼬리를 도는 요일(0=월). 매일 돌 필요가 없다 — 그 구간은 하루 단위로 변하지 않는다.
#: 쿼터 계산(실측 기준): 최근 36 스코프/일 + 꼬리 48 스코프/주 = 주간 평균 **약 43/일**.
TAIL_WEEKDAY = 2  # 수요일

#: 유형 — 토지는 지번이 100% 마스킹이지만 **법정동 단위 집계는 유효**하다(`#851` 실측).
DEFAULT_PROP_TYPES = ("apt", "land")

#: **꼬리 창을 도는 유형** — 등기를 **실제로 보고하는** 유형만.
#:
#: ★★꼬리 창은 오직 등기(`rgstDate`)를 잡으려고 존재한다. 그런데 **MOLIT 토지 API 는
#:   등기일자를 아예 주지 않는다.** 저장분 **전수** 실측(2026-08-26 · 4,898행):
#:
#:       유형    행      등기            해제
#:       apt   4,110    737(17.9%)      79(1.9%)
#:       land    788      **0(0.0%)**   49(6.2%)   ← 6개 시군구 **전부 0**
#:
#:   대조군으로 같은 조회에서 apt 는 나온다(노출별 28.6% · 12.8% · 3.8%). 즉 **조회기가
#:   죽은 것이 아니라 원천이 안 준다.**
#:   → 토지를 꼬리에 넣으면 **잡을 것이 없는 요청을 매주 24회** 낸다(순수 쿼터 낭비).
#:   ★토지의 신호는 **해제**이고(6.2% = apt 의 3배) 해제는 1개월부터 평평하므로
#:     **최근 3개월 창으로 충분**하다.
#:
#: ★이 값을 바꾸려면 **먼저 재라** — 원천이 토지 등기를 주기 시작하면 늘려야 한다.
TAIL_PROP_TYPES = ("apt",)


def recent_months(now: datetime, months: int) -> list[str]:
    """`YYYYMM` 목록(최신 우선). `now` 를 인자로 받아 **결정적**으로 만든다."""
    out, cursor = [], now
    for _ in range(max(1, months)):
        out.append(cursor.strftime("%Y%m"))
        cursor = cursor.replace(day=1) - timedelta(days=1)
    return out


def prop_types_for(deal_ym: str, recent: list[str]) -> tuple[str, ...]:
    """이 달에 어떤 유형을 조회할 것인가.

    최근 창은 전 유형, **꼬리 구간은 등기를 보고하는 유형만**(`TAIL_PROP_TYPES`).
    """
    return DEFAULT_PROP_TYPES if deal_ym in recent else TAIL_PROP_TYPES


def months_for(now: datetime) -> tuple[list[str], bool]:
    """이번 실행이 볼 `YYYYMM` 목록과 **꼬리를 포함했는지**.

    ★두 신호의 **시간상수가 다르다** — 해제는 1개월부터 평평하고(매일 봐야 잡는다),
      등기는 5개월에야 포화한다(매일 볼 필요가 없다). 하나의 창으로 둘을 덮으면
      등기에 맞춘 창이 **매일 불필요한 요청**을 내고, 해제에 맞춘 창이 **등기를 놓친다**.

    Returns:
        `(월 목록, 꼬리 포함 여부)` — `now` 만으로 결정된다(랜덤·전역상태 0).
    """
    include_tail = now.weekday() == TAIL_WEEKDAY
    span = TAIL_MONTHS if include_tail else RECENT_MONTHS
    return recent_months(now, span), include_tail


async def sync_realtx_trades(ctx: dict[str, Any]) -> dict[str, Any]:
    """파생된 시군구 × 최근 N개월 × 유형을 수집·저장하고 정정을 탐지한다."""
    from app.services.land_intelligence.realtx_store import (
        derive_scan_targets,  # 대상 0건이면 RealtxTargetsEmptyError 를 **전파**한다
        persist_scope,
    )
    from apps.api.database.session import AsyncSessionLocal
    from apps.api.integrations.molit_client import MolitClient

    _now = datetime.now(tz=UTC)
    months, tail_included = months_for(_now)
    recent = recent_months(_now, RECENT_MONTHS)

    async with AsyncSessionLocal() as db:
        # ★★2026-08-26 독립 리뷰 적발 — 종전엔 여기서 예외를 잡아 dict 로 돌려줬다.
        #   `realtx_store` 독스트링은 *"조용히 넘어가지 않고 죽는다"* 고 선언하는데,
        #   **arq 는 정상 반환을 성공으로 기록**하고 이 저장소에 job result 를 읽는
        #   코드가 **0건**이다(실측 · 대조군 arq 임포트 2건). 곧 선언과 동작이 어긋났다.
        #   → **전파한다.** arq 가 실패로 기록하고 재시도한다.
        targets = sorted(await derive_scan_targets(db))

        client = MolitClient()
        stats: dict[str, Any] = {
            "targets": len(targets), "months": len(months),
            # ★꼬리를 돌았는지 **결과에 남긴다** — 안 남기면 "오늘 등기를 봤나"를
            #   로그만 보고는 알 수 없고, 주간 실행이 조용히 멈춰도 드러나지 않는다.
            "tail_included": tail_included,
            # ★`submitted` 로 이름을 바꿨다 — 종전 `stored` 는 **투입 레코드 수**이지
            #   저장된 행 수가 아니다(멱등 upsert 라 기존 행 갱신이 섞인다).
            "submitted": 0, "corrections": 0,
            "fetch_errors": [], "persist_errors": [],
        }
        try:
            for lawd_cd in targets:
                for deal_ym in months:
                    for prop_type in prop_types_for(deal_ym, recent):
                        try:
                            records = await client.get_transactions(lawd_cd, deal_ym, prop_type=prop_type)
                        except Exception as exc:  # noqa: BLE001 — 사유를 실어 계속한다
                            # ★재시도하지 않는다(쿼터를 G2B 와 공유). 사유를 남기고 넘어간다.
                            stats["fetch_errors"].append(
                                {"lawd_cd": lawd_cd, "deal_ym": deal_ym,
                                 "prop_type": prop_type, "error": type(exc).__name__}
                            )
                            continue
                        try:
                            result = await persist_scope(
                                db, lawd_cd=lawd_cd, deal_ym=deal_ym,
                                prop_type=prop_type, records=records,
                            )
                        except Exception as exc:  # noqa: BLE001
                            # ★스코프 하나가 죽어도 나머지를 계속한다. 종전엔 무방비라
                            #   한 건의 DataError 가 **남은 전 시군구·월을 미수집**으로 만들고
                            #   stats 조차 반환되지 않았다. targets 가 정렬돼 있어 잘리는
                            #   부분이 **항상 같은 뒷부분**이라 계통적 손실이었다.
                            logger.error("실거래 저장 실패 lawd=%s ym=%s type=%s: %s",
                                         lawd_cd, deal_ym, prop_type, str(exc)[:200])
                            stats["persist_errors"].append(
                                {"lawd_cd": lawd_cd, "deal_ym": deal_ym,
                                 "prop_type": prop_type, "error": type(exc).__name__})
                            continue
                        stats["submitted"] += result["submitted"]
                        stats["corrections"] += len(result["corrections"])
        finally:
            await client.close()

    stats["status"] = "ok" if not stats["persist_errors"] else "partial"
    logger.info(
        "실거래 2층 수집 %s 시군구=%d 월=%d(꼬리=%s) 투입=%d 정정=%d 조회실패=%d 저장실패=%d",
        stats["status"], stats["targets"], stats["months"],
        "포함" if tail_included else "제외", stats["submitted"],
        stats["corrections"], len(stats["fetch_errors"]), len(stats["persist_errors"]),
    )
    return stats
