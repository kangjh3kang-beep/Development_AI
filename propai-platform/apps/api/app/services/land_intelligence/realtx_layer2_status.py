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
    """신선도 — **미수집을 수치로 위장하지 않는다**."""
    if last_scanned_at is None:
        return {"last_scanned_at": None, "age_hours": None,
                "state": NEVER_SCANNED, "stale": None}
    age = now - last_scanned_at
    return {
        "last_scanned_at": last_scanned_at.isoformat(),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "state": "낡음" if age > timedelta(days=stale_after_days) else "정상",
        "stale": age > timedelta(days=stale_after_days),
    }


def detection_state(*, corrections_total: int, reobserved_rows: int, stored_rows: int) -> dict[str, Any]:
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

    ★한도는 **모른다**고 적는다. 절대 한도를 지어내면 다음 사람이 그것을 관측으로 읽는다.
      판정은 **기준선 대비 배수**로 낸다.
    """
    from app.tasks.realtx_sync_task import (
        DEFAULT_PROP_TYPES,
        RECENT_MONTHS,
        TAIL_MONTHS,
        TAIL_PROP_TYPES,
    )

    if targets is None:
        return {"targets": None, "daily_scopes": None, "weekly_tail_scopes": None,
                "weekly_avg_per_day": None, "baseline_targets": QUOTA_BASELINE_TARGETS,
                "vs_baseline": None, "limit": QUOTA_LIMIT_UNKNOWN, "state": NEVER_SCANNED}

    daily = targets * RECENT_MONTHS * len(DEFAULT_PROP_TYPES)
    tail = targets * (TAIL_MONTHS - RECENT_MONTHS) * len(TAIL_PROP_TYPES)
    weekly_avg = round((daily * 7 + tail) / 7, 1)
    ratio = round(targets / QUOTA_BASELINE_TARGETS, 2) if QUOTA_BASELINE_TARGETS else None
    return {
        "targets": targets,
        "daily_scopes": daily,
        "weekly_tail_scopes": tail,
        "weekly_avg_per_day": weekly_avg,
        "baseline_targets": QUOTA_BASELINE_TARGETS,
        "vs_baseline": ratio,
        # ★한도를 지어내지 않는다
        "limit": QUOTA_LIMIT_UNKNOWN,
        "state": ("재측정필요" if ratio is not None and ratio >= QUOTA_REVIEW_MULTIPLE
                  else "기준선범위"),
    }


_SQL_SCHEMA_PRESENT = "SELECT to_regclass('public.realtx_trades')"

_SQL_STORED = "SELECT count(*) FROM realtx_trades"
#: ★1초 여유 — 같은 트랜잭션 안 INSERT 는 `now()` 가 동일해 `>` 가 거짓이 된다.
_SQL_REOBSERVED = (
    "SELECT count(*) FROM realtx_trades WHERE updated_at > first_seen_at + interval '1 second'"
)
_SQL_CORRECTIONS = "SELECT count(*) FROM realtx_corrections"
_SQL_CORRECTIONS_BY_KIND = (
    "SELECT kind, count(*) FROM realtx_corrections GROUP BY kind ORDER BY count(*) DESC"
)
_SQL_LAST_SCAN_IN = (
    "SELECT max(last_scanned_at) FROM realtx_scan_state "
    "WHERE split_part(scope_key, '|', 3) = ANY(:months)"
)
_SQL_SCOPES = "SELECT count(*), count(*) FILTER (WHERE baseline_done) FROM realtx_scan_state"
#: 대상 시군구 — **scan_state 에서 파생**한다(스토어를 다시 훑지 않는다).
_SQL_TARGETS = "SELECT count(DISTINCT split_part(scope_key, '|', 2)) FROM realtx_scan_state"

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

    async def _scalar(sql: str, params: dict[str, Any] | None = None) -> Any:
        row = (await db.execute(text(sql), params or {})).first()
        return row[0] if row else None

    if await _scalar(_SQL_SCHEMA_PRESENT) is None:
        # 스키마 미생성 — 크론이 한 번도 안 돌았다. **0행과 다른 상태**다.
        return {
            "stored_rows": None, "reobserved_rows": None,
            "scopes": {"total": None, "baseline_done": None, "targets": None},
            "quota": quota_view(None),
            "corrections": {"total": None, "by_kind": {}},
            "detection": {"state": "미배포",
                          "meaning": ("2층 스키마가 아직 없다(lazy DDL) — "
                                      "수집 크론이 한 번도 돌지 않았다.")},
            "collection": {
                "recent": {"months": recent,
                           **freshness(None, now, STALE_RECENT_DAYS)},
                "tail": {"probe_month": tail_probe,
                         **freshness(None, now, STALE_TAIL_DAYS)},
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
    scopes_row = (await db.execute(text(_SQL_SCOPES))).first()
    scopes_total, scopes_baseline = (int(scopes_row[0]), int(scopes_row[1])) if scopes_row else (0, 0)
    targets = int(await _scalar(_SQL_TARGETS) or 0)

    last_recent = await _scalar(_SQL_LAST_SCAN_IN, {"months": recent})
    last_tail = await _scalar(_SQL_LAST_SCAN_IN, {"months": [tail_probe]})

    return {
        "stored_rows": stored,
        "reobserved_rows": reobserved,
        "scopes": {"total": scopes_total, "baseline_done": scopes_baseline,
                   "targets": targets},
        "quota": quota_view(targets),
        "corrections": {"total": corrections_total, "by_kind": by_kind},
        "detection": detection_state(
            corrections_total=corrections_total,
            reobserved_rows=reobserved,
            stored_rows=stored,
        ),
        "collection": {
            # 매일 도는 구간
            "recent": {"months": recent,
                       **freshness(last_recent, now, STALE_RECENT_DAYS)},
            # ★주 1회 도는 구간 — 가장 오래된 꼬리 달만이 이것을 증언한다
            "tail": {"probe_month": tail_probe,
                     **freshness(last_tail, now, STALE_TAIL_DAYS)},
        },
        "as_of": now.isoformat(),
    }
