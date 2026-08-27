"""실거래 **2층 관측 표면** — 저장된 것을 처음으로 **읽는** 코드.

## 왜 이 파일이 필요했나

`#855`·`#860`·`#884` 가 2층(저장·정정탐지)을 만들었고 프로덕션에 **4,898행**이 쌓였다.
그런데 라이브 실측 2026-08-27T00:0xZ 기준 그 세 테이블을 **읽는 코드가 0건**이었다
(이름으로도 목적으로도 스윕 — `realtx_store` · `realtx_sync_task` · `apps/worker/main.py`
만 접근하고 전부 **쓰기**다). 즉 수집이 조용히 멈춰도, 정정이 쏟아져도 **아무도 모른다.**

`#884` 는 그 부채를 스스로 적어 두었다:

    ★부채: 진짜로 드러나게 하려면 realtx_scan_state 에 마지막 꼬리 실행 시각을 남기고
      *"8일 이상 낡음"* 을 판정하는 소비처가 필요하다(별건).

이 파일이 그 소비처다.

## ★가장 중요한 설계 — `corrections = 0` 을 **두 뜻으로 가른다**

인계서는 *"두 번째 실행이 정정 탐지의 진짜 시험이다. 0 이면 탐지가 죽은 것"* 이라고 적었다.
**그 문장은 두 번째 실행 이후에만 참이다.** 첫 실행 직후의 0 은 정상이다(baseline 억제).

둘을 섞으면 다음 사람이 **정상을 장애로**(또는 그 반대로) 읽는다. 그래서 판정을
**관측에서 파생**한다 — `realtx_trades` 는 upsert 때 `updated_at = now()` 를 찍고
`first_seen_at` 은 INSERT 때만 박히므로:

    updated_at > first_seen_at  ⟺  그 행이 **최소 한 번 재관측**됐다
                                    ⟺ 그 행에 대해 정정 탐지가 **실제로 돌 기회가 있었다**

라이브 실측(2026-08-27T00:0xZ): 재관측 행 **0 / 4,898**. 즉 현재의 `corrections = 0` 은
*"정정이 없었다"* 도 *"탐지가 죽었다"* 도 아니고 **"아직 한 번도 시험되지 않았다"** 이다.

★이 파생이 없으면 그 사실을 **말할 수 없다** — 그래서 이 모듈은 값을 세는 데서 멈추지 않고
  `detection_state` 를 낸다.

## ★「모름」을 유효값으로 표현하지 않는다

수집이 한 번도 안 돌았으면 신선도는 `"미수집"` 이다 — `999일 전` 같은 **그럴듯한 수**를
만들지 않는다. 면제·미조회를 유효값으로 그리면 그것이 **관측으로 읽힌다.**

## ★이 모듈이 **못 보는** 것

1. **꼬리 실행 이력이 1회분만 남는다.** `realtx_scan_state` 는 `last_scanned_at` 하나뿐이라
   *"지난 4주 중 몇 번 돌았나"* 는 **말할 수 없다**. 여기서는 *"마지막이 언제였나"* 까지다.
2. `updated_at > first_seen_at` 은 **재관측**을 말하지 정정을 말하지 않는다. 값이 안 변했으면
   재관측돼도 정정은 0이다 — 그것이 정상이다.
3. **정정률의 기대값은 미측정**이다. `해제 2.6%/월` 은 `#884` 가 **다른 모집단**(노출별
   해제율)에서 잰 값이라 여기에 그대로 대입하면 안 된다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

#: 최근 창이 낡았다고 볼 경계 — 크론이 **매일** 도므로 2일이면 최소 한 번은 건너뛴 것이다.
STALE_RECENT_DAYS = 2

#: 꼬리 창이 낡았다고 볼 경계 — 크론이 **주 1회** 도므로 8일이면 최소 한 번은 건너뛴 것이다.
#:
#: ★상한·하한을 **한 쌍으로** 본다(§D-19). 8일은 "주 1회 + 하루 여유"에서 나온 값이라
#:   `> 7` 이어야 의미가 있고, 무한대로 열어 두면 판정이 사라진다.
STALE_TAIL_DAYS = 8

#: 신선도를 말할 수 없는 상태. ★수치로 위장하지 않는다.
NEVER_SCANNED = "미수집"

#: ★마지막 수집이 **미래**다 — 시계 오차이거나 잘못된 행. **판정하지 않는다**(리뷰 M6).
CLOCK_ANOMALY = "시각이상"


def _tail_probe_month(now: datetime) -> str:
    """꼬리 실행을 **유일하게** 증언하는 달.

    ★왜 "꼬리 달 중 아무거나"가 아닌가: 달이 넘어가면 **최근 창에 있던 달이 꼬리로
      내려온다.** 그 달의 `last_scanned_at` 은 *최근 창으로서* 어제 찍힌 값일 수 있어,
      꼬리 실행이 6일간 멈췄어도 **"어제 돌았다"** 로 보인다(거짓 신선도).

    → **가장 오래된 꼬리 달** 하나만 본다. 그 달은 최근 창에 있었던 적이 없으므로
      그 값은 **오직 꼬리 실행만이** 갱신한다.
    """
    from app.tasks.realtx_sync_task import RECENT_MONTHS, TAIL_MONTHS, recent_months

    # 파생 — 상수를 손으로 옮겨 적지 않는다(옮겨 적으면 그 사본이 상한이 된다).
    assert TAIL_MONTHS > RECENT_MONTHS, "꼬리 구간이 비었다 — 이 프로브가 공허하다"
    return recent_months(now, TAIL_MONTHS)[-1]


def _recent_window(now: datetime) -> list[str]:
    from app.tasks.realtx_sync_task import RECENT_MONTHS, recent_months

    return recent_months(now, RECENT_MONTHS)


def freshness(last_scanned_at: datetime | None, now: datetime, stale_after_days: int) -> dict[str, Any]:
    """신선도 — **미수집을 수치로 위장하지 않는다**.

    ★★2026-08-27 독립 리뷰(M6): 종전엔 `last_scanned_at` 이 **미래**여도 `정상`(`stale=False`)
      이었고 `age_hours: -5.0` 이라는 **말이 안 되는 수를 관측처럼** 냈다. 「모름을 수치로
      위장하지 않는다」를 선언한 모듈이 **음수를 유효값으로** 낸 것이다.
      → 경계를 **양방향**으로 건다: 상한(낡음)만이 아니라 **하한(0)** 도 건다.
        미래 시각은 앱↔DB 시계 오차이거나 잘못된 행이므로 **판정하지 않는다**.
    """
    if last_scanned_at is None:
        return {"last_scanned_at": None, "age_hours": None,
                "state": NEVER_SCANNED, "stale": None}
    age = now - last_scanned_at
    if age < timedelta(0):
        return {"last_scanned_at": last_scanned_at.isoformat(),
                "age_hours": None,
                "state": CLOCK_ANOMALY, "stale": None}
    return {
        "last_scanned_at": last_scanned_at.isoformat(),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "state": "낡음" if age > timedelta(days=stale_after_days) else "정상",
        "stale": age > timedelta(days=stale_after_days),
    }


def detection_state(*, corrections_total: int, reobserved_rows: int, stored_rows: int,
                    state_lost: bool = False) -> dict[str, Any]:
    """★`corrections = 0` 이 무엇을 뜻하는지 **관측에서 파생**한다.

    | 저장 | 재관측 | 정정 | 판정 |
    |---|---|---|---|
    | 0 | – | – | `미수집` — 아직 아무것도 없다 |
    | >0 | **0** | 0 | ★`미시험` — 탐지가 **돌 기회가 없었다**(2회차 전) |
    | >0 | >0 | 0 | `관측됨_정정없음` — 재관측했는데 안 변했다(정상일 수 있다) |
    | >0 | >0 | >0 | `관측됨_정정있음` |
    | >0 | **0** | **>0** | ★`모순` — 재관측 없이 정정이 나왔다. 조회기나 계약을 의심하라 |

    ★가운데 두 줄을 가르는 것이 이 함수의 존재 이유다. 섞으면 **정상을 장애로**,
      혹은 **죽은 탐지를 정상으로** 읽는다.
    """
    if stored_rows <= 0:
        return {"state": "미수집",
                "meaning": "2층에 저장된 거래가 없다 — 수집부터 확인하라."}
    if reobserved_rows <= 0:
        if corrections_total > 0:
            return {"state": "모순",
                    "meaning": ("재관측된 행이 0인데 정정이 기록됐다 — "
                                "조회기나 upsert 계약을 의심하라.")}
        return {"state": "미시험",
                "meaning": ("정정 탐지가 **아직 한 번도 돌지 않았다**(재관측 행 0). "
                            "이 0 은 '정정 없음'이 아니다 — 2회차 수집 뒤에 다시 보라.")}
    if state_lost:
        # ★★2026-08-27 독립 리뷰(M1) — 재관측은 **필요조건이지 충분조건이 아니다.**
        #   `persist_scope` 는 baseline 실행에서도 **upsert 를 먼저 하고**(`updated_at`
        #   갱신) 그 뒤에 탐지를 억제한다. 그래서 `realtx_trades` 는 남고
        #   `realtx_scan_state` 만 잃은 상태(수동 정리·복구·부분 마이그레이션)에서
        #   재실행하면 **재관측 > 0 인데 탐지는 억제**된다.
        #   그때 종전 코드는 `관측됨_정정없음`("재관측했는데 안 변했다 — 정상일 수 있다")
        #   을 내서 **인계서가 밟은 오독의 정반대 방향**으로 같은 혼동을 만들었다.
        return {"state": "상태소실",
                "meaning": ("거래 행보다 스캔 상태가 적다 — baseline 이 다시 돌면서 "
                            "재관측은 일어났지만 **탐지는 억제**됐을 수 있다. "
                            "이 정정 수는 '탐지가 돌아서 나온 0' 이 아니다.")}
    if corrections_total <= 0:
        return {"state": "관측됨_정정없음",
                "meaning": f"{reobserved_rows}행을 재관측했고 바뀐 값이 없었다."}
    return {"state": "관측됨_정정있음",
            "meaning": f"{reobserved_rows}행 재관측 중 정정 {corrections_total}건."}


#: ★스키마 부재를 **조회 실패와 섞지 않는다.** 2층은 lazy DDL 이라 크론이 한 번도 안 돈
#:  환경에는 테이블 자체가 없다. 그때 500 을 내면 *"2층이 고장났다"* 로 읽히고, 예외를
#:  통째로 삼키면 *"깨끗하다"* 로 읽힌다 — 둘 다 거짓이다. **존재를 먼저 묻는다.**
def quota_view(targets: int | None) -> dict[str, Any]:
    """대상 시군구가 **무한히 늘 수 있다**는 부채(`#884` P-d)를 **관측 가능하게** 만든다.

    ★고치는 것이 아니라 **보이게** 하는 것이다. 상한을 걸어 대상을 잘라내면 그 사용자의
      지역이 **조용히 수집에서 빠진다** — 지금 결함보다 나쁘다. 그래서 자르지 않고 센다.

    ★한도는 **모른다**고 적는다(`limit`). 절대 한도를 지어내면 다음 사람이 그것을
      관측으로 읽는다. 판정은 **기준선 대비 배수**로 낸다.

    Args:
        targets: **현재** 수집 대상 시군구 수(`current_targets`). 파생 실패면 `None`.

    ★★2026-08-27 독립 리뷰(H3·M3) — 두 곳이 틀렸다:
      · 종전엔 `realtx_scan_state` 의 **누적** 시군구를 썼다. 그것은 수집 대상이 아니라
        *"한 번이라도 스캔된 적 있는"* 집합이라(저장소에 `DELETE FROM realtx_*` **0건**)
        사용자가 지역을 빼도 **영원히 안 줄고**, 그 위에 얹은 `재측정필요` 는
        **한 번 켜지면 안 꺼진다**.
      · 종전엔 `targets=0` 이 `None` 이 아니라는 이유로 산술 분기로 들어가
        `기준선범위`(= 정상)를 냈다. **「아직 아무것도 안 셌다」가 유효값 0 을 입은 것**이다.
    """
    from app.tasks.realtx_sync_task import (
        DEFAULT_PROP_TYPES,
        RECENT_MONTHS,
        TAIL_MONTHS,
        TAIL_PROP_TYPES,
    )

    if not targets:          # ★`None` 과 `0` 을 **함께** 판정 불가로 본다(리뷰 M3)
        return {"targets": targets, "daily_scopes": None, "weekly_tail_scopes": None,
                "weekly_avg_per_day": None, "baseline_targets": QUOTA_BASELINE_TARGETS,
                "vs_baseline": None, "limit": QUOTA_LIMIT_UNKNOWN,
                "state": NEVER_SCANNED if targets == 0 else UNDERIVABLE}

    daily = targets * RECENT_MONTHS * len(DEFAULT_PROP_TYPES)
    tail = targets * (TAIL_MONTHS - RECENT_MONTHS) * len(TAIL_PROP_TYPES)
    ratio = round(targets / QUOTA_BASELINE_TARGETS, 2) if QUOTA_BASELINE_TARGETS else None
    return {
        "targets": targets,
        "daily_scopes": daily,
        "weekly_tail_scopes": tail,
        "weekly_avg_per_day": round((daily * 7 + tail) / 7, 1),
        "baseline_targets": QUOTA_BASELINE_TARGETS,
        "vs_baseline": ratio,
        "limit": QUOTA_LIMIT_UNKNOWN,          # ★지어내지 않는다
        "state": ("재측정필요" if ratio is not None and ratio >= QUOTA_REVIEW_MULTIPLE
                  else "기준선범위"),
    }


async def current_targets(db: Any) -> int | None:
    """**현재** 수집 대상 시군구 수 — 수집기와 **같은 함수**로 파생한다.

    ★사본을 만들지 않는다. `derive_scan_targets` 가 곧 크론이 쓰는 모집단이므로 여기서
      따로 세면 **두 수가 조용히 갈린다**(리뷰 H3 가 지적한 것이 정확히 그것이다).

    ★파생이 0건이면 그 함수는 **예외를 던진다**(설계 — 조용한 0 금지). 여기는 읽기 전용
      표면이라 죽지 않고 `None`(판정 불가)을 준다 — 그러나 **0 으로 접지 않는다**.
      `0` 은 *"대상이 없다"* 는 관측이고 `None` 은 *"말할 수 없다"* 이다.
    """
    from app.services.land_intelligence.realtx_store import derive_scan_targets

    # ★★**세이브포인트 안에서** 부른다. 예외를 삼키는 것만으로는 부족하다 —
    #   실패한 조회가 **트랜잭션을 오염**시켜(`InFailedSQLTransactionError`) 그 뒤의
    #   모든 조회가 죽는다. 즉 `try/except` 가 **자기 실패는 숨기고 남의 조회를 죽인다**.
    #   ★이 결함은 실 Postgres 락이 **첫 실행에서** 잡았다(스텁은 트랜잭션이 없어 못 본다).
    try:
        async with db.begin_nested():
            return len(await derive_scan_targets(db))
    except Exception:  # noqa: BLE001 — 파생 실패는 판정 불가이지 0이 아니다
        return None


#: ★★2026-08-27 독립 리뷰(M2) — 종전엔 `to_regclass('public.realtx_trades')` 였다.
#:   `realtx_store._ensure_schema` 의 DDL 은 **스키마 무자격**(`CREATE TABLE IF NOT EXISTS
#:   realtx_trades`)이라 `search_path` 의 첫 스키마에 만들어진다. `public.` 을 못 박으면
#:   **테이블이 멀쩡한데 「미배포」** 가 나온다 — 이 분기가 막겠다고 선언한 그 거짓이다.
#:   → **무자격으로**(생산자와 같은 해석 규칙) 묻고, **3종 전부** 본다.
_LAYER2_TABLES: tuple[str, ...] = ("realtx_trades", "realtx_corrections", "realtx_scan_state")
_SQL_SCHEMA_PRESENT = (
    "SELECT count(*) FROM unnest(CAST(:tables AS text[])) AS t "
    "WHERE to_regclass(t) IS NOT NULL"
)

_SQL_STORED = "SELECT count(*) FROM realtx_trades"
#: ★1초 여유 — 같은 트랜잭션 안 INSERT 는 `now()` 가 동일해 `>` 가 거짓이 된다.
_SQL_REOBSERVED = (
    "SELECT count(*) FROM realtx_trades WHERE updated_at > first_seen_at + interval '1 second'"
)
_SQL_CORRECTIONS = "SELECT count(*) FROM realtx_corrections"
_SQL_CORRECTIONS_BY_KIND = (
    "SELECT kind, count(*) FROM realtx_corrections GROUP BY kind ORDER BY count(*) DESC"
)
#: ★★2026-08-27 독립 리뷰(H2) — 종전엔 `max(last_scanned_at)` **하나**였다.
#:
#:   이 모듈의 존재 이유는 *"수집이 조용히 멈춰도 아무도 모른다"* 를 깨는 것인데,
#:   `max()` 는 **스코프 36개 중 하나만 성공해도 「정상」** 이다. `realtx_sync_task` 는
#:   스코프별 실패에서 `continue` 하므로(그 스코프의 `scan_state` 는 갱신 안 됨)
#:   **5/6 시군구가 몇 주째 죽어도** 표면은 `stale: False` 를 냈다.
#:   → *"이 단언이 초록일 때 1/36 만 도는 수집도 초록인가"* 에 **예**였다.
#:
#: ★그래서 **분포**로 본다. 판정은 `max` 가 아니라 **`min`(최고령 스코프)** 으로 한다 —
#:   하나라도 낡았으면 낡은 것이다. `max` 는 참고로만 싣는다.
_SQL_LAST_SCAN_IN = (
    "SELECT max(last_scanned_at), min(last_scanned_at), count(*) "
    "FROM realtx_scan_state WHERE split_part(scope_key, '|', 3) = ANY(:months)"
)
_SQL_SCOPES = "SELECT count(*), count(*) FILTER (WHERE baseline_done) FROM realtx_scan_state"
#: ★★2026-08-27 독립 리뷰(H3) — 이것은 **수집 대상이 아니다.**
#:
#:   | | 이 SQL 이 세는 것 | 실제 수집이 쓰는 것 |
#:   |---|---|---|
#:   | 소스 | `realtx_scan_state` | `user_project_store.landSchedule` |
#:   | 시점 | **누적 · 영구** | **매 실행 재파생** |
#:   | 삭제 | `DELETE FROM realtx_*` 가 저장소에 **0건** | 사용자가 지우면 즉시 빠짐 |
#:
#:   즉 사용자가 지역을 빼도 이 수는 **영원히 안 줄고**, 오늘 추가된 지역은 크론이 돌기
#:   전까지 **안 잡힌다**. 상한도 하한도 아닌 **다른 집합**이다. 이 위에 쿼터 산술을
#:   얹으면 *"재측정필요"* 가 누적 이력 때문에 켜져 **영원히 안 꺼진다.**
#:   → 이름을 사실대로 바꾸고(`sigungu_ever_scanned`), **쿼터는 현재 대상에서** 낸다.
_SQL_SIGUNGU_EVER = "SELECT count(DISTINCT split_part(scope_key, '|', 2)) FROM realtx_scan_state"

#: 거래 행이 실제로 존재하는 스코프 수 — `realtx_scan_state` 와 대조해 **상태 소실**을 본다.
#: ★`persist_scope` 는 baseline 에서도 upsert 를 먼저 하므로, 상태만 잃으면
#:   **재관측은 일어나는데 탐지는 억제**된다(리뷰 M1).
_SQL_TRADE_SCOPES = (
    "SELECT count(*) FROM (SELECT DISTINCT prop_type, lawd_cd, deal_ym FROM realtx_trades) s"
)

#: 쿼터 산술의 **기준선** — 이 수치로 잰 날의 대상 시군구 수.
#:
#: ★라이브 실측 2026-08-26T19:10Z: 시군구 **6** → 하루 **36 스코프**(103.58초).
#:   `user_project_store` **3행**에서 파생됐다(사용자별 시군구 5·2·0).
QUOTA_BASELINE_TARGETS = 6

#: ★★**MOLIT 일일 쿼터의 실제 한도는 미측정이다.** 그러므로 여기서 한도를 **지어내지
#:   않는다** — 「모름」을 유효값으로 그리면 그것이 관측으로 읽힌다.
#:
#:   재 본 것(2026-08-27T00:0xZ · 보존된 로그 창): 진짜 HTTP 429 가 arq·api 모두 **0건**
#:   (양성 대조군 `status_code: 200` 1,003건 — 조회기 생존 확인). 즉 **현재 소비량에서는
#:   한도에 닿지 않는다**까지가 관측이고, 한도가 얼마인지는 **모른다**.
#:
#:   그래서 판정은 **절대 한도가 아니라 기준선 대비 배수**로 낸다 — 성장이 보이게 하되
#:   없는 한도를 단정하지 않는다.
QUOTA_LIMIT_UNKNOWN = "미측정"

#: 대상 파생 **자체가 실패**했다 — `0`(대상 없음)과 다르다(리뷰 M3).
UNDERIVABLE = "판정불가"

#: 기준선 대비 몇 배가 되면 사람이 봐야 하는가. ★임의값이 아니라 **재측정 트리거**다.
QUOTA_REVIEW_MULTIPLE = 5


async def build_layer2_status(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """2층이 살아 있는지, 무엇을 봤는지 — **읽기 전용**.

    ★`now` 를 인자로 받아 **결정적**으로 만든다(형제 `recent_months` 와 같은 계약).
    """
    from sqlalchemy import text

    now = now or datetime.now(tz=UTC)
    recent = _recent_window(now)
    tail_probe = _tail_probe_month(now)

    async def _row(sql: str, params: dict[str, Any] | None = None) -> Any:
        return (await db.execute(text(sql), params or {})).first()

    async def _scalar(sql: str, params: dict[str, Any] | None = None) -> Any:
        row = await _row(sql, params)
        return row[0] if row else None

    def _window(row: Any, stale_days: int) -> dict[str, Any]:
        """★`max` 가 아니라 **`min`(최고령 스코프)** 으로 판정한다(리뷰 H2).

        하나라도 낡았으면 낡은 것이다 — `max` 로 보면 36개 중 1개만 돌아도 「정상」이라
        **부분 정지가 원리적으로 탐지 불가**였다.
        """
        newest, oldest, scopes = (row[0], row[1], int(row[2] or 0)) if row else (None, None, 0)
        out = freshness(oldest, now, stale_days)
        out["newest_scanned_at"] = newest.isoformat() if newest else None
        out["scopes_in_window"] = scopes
        return out

    present = int(await _scalar(_SQL_SCHEMA_PRESENT, {"tables": list(_LAYER2_TABLES)}) or 0)
    if present < len(_LAYER2_TABLES):
        # 스키마 미생성 — 크론이 한 번도 안 돌았다. **0행과 다른 상태**다.
        return {
            "stored_rows": None, "reobserved_rows": None,
            "scopes": {"total": None, "baseline_done": None,
                       "sigungu_ever_scanned": None},
            "corrections": {"total": None, "by_kind": {}},
            "quota": quota_view(None),
            "detection": {
                "state": "미배포",
                "meaning": (
                    f"2층 스키마가 아직 없다(lazy DDL · {present}/{len(_LAYER2_TABLES)} 테이블) — "
                    "수집 크론이 한 번도 돌지 않았다."
                ),
            },
            "collection": {
                "recent": {"months": recent, **freshness(None, now, STALE_RECENT_DAYS)},
                "tail": {"probe_month": tail_probe, **freshness(None, now, STALE_TAIL_DAYS)},
            },
            "as_of": now.isoformat(),
        }

    stored = int(await _scalar(_SQL_STORED) or 0)
    reobserved = int(await _scalar(_SQL_REOBSERVED) or 0)
    corrections_total = int(await _scalar(_SQL_CORRECTIONS) or 0)
    by_kind = {
        r[0]: int(r[1])
        for r in (await db.execute(text(_SQL_CORRECTIONS_BY_KIND))).fetchall()
    }
    scopes_row = await _row(_SQL_SCOPES)
    scopes_total, scopes_baseline = (int(scopes_row[0]), int(scopes_row[1])) if scopes_row else (0, 0)
    sigungu_ever = int(await _scalar(_SQL_SIGUNGU_EVER) or 0)
    trade_scopes = int(await _scalar(_SQL_TRADE_SCOPES) or 0)
    targets = await current_targets(db)

    return {
        "stored_rows": stored,
        "reobserved_rows": reobserved,
        "scopes": {"total": scopes_total, "baseline_done": scopes_baseline,
                   # ★이름이 사실을 말한다 — 이것은 **수집 대상이 아니다**(리뷰 H3)
                   "sigungu_ever_scanned": sigungu_ever,
                   "trade_scopes": trade_scopes},
        "corrections": {"total": corrections_total, "by_kind": by_kind},
        "quota": quota_view(targets),
        "detection": detection_state(
            corrections_total=corrections_total,
            reobserved_rows=reobserved,
            stored_rows=stored,
            # ★거래에는 있는데 스캔 상태에 없는 스코프 = baseline 억제가 다시 걸릴 수 있다
            state_lost=trade_scopes > scopes_total,
        ),
        "collection": {
            # 매일 도는 구간
            "recent": {"months": recent,
                       **_window(await _row(_SQL_LAST_SCAN_IN, {"months": recent}),
                                 STALE_RECENT_DAYS)},
            # ★주 1회 도는 구간 — 가장 오래된 꼬리 달만이 이것을 증언한다
            "tail": {"probe_month": tail_probe,
                     **_window(await _row(_SQL_LAST_SCAN_IN, {"months": [tail_probe]}),
                               STALE_TAIL_DAYS)},
        },
        "as_of": now.isoformat(),
    }
