"""효과기가 **실제로 발화했는가** — 선언(`effector_reach`) × 실측(`platform_events`).

## 왜 이 파일이 생겼나 (2026-08-27)

`effector_reach.py` 는 자기 값어치를 이렇게 적어 뒀다:

> 이 표의 값어치는 **닿지 않는 것을 닿지 않는다고 적는 데** 있다.

옳다. 그런데 **거울상이 빠져 있다** — *"발화하지 않는 것을 발화하지 않는다고 적기"*.
`reach` 는 "이 효과기가 동작하면 어디까지 닿는가"이지 **"동작한 적이 있는가"** 가 아니다.
그래서 표만 읽은 사람은 `threshold_relax` 를 보고 *"제품에 닿는 효과기가 살아 있다"* 고
읽는데, 실제로는 며칠째 조용할 수 있고 **그 사실을 알 방법이 없었다.**

## 라이브 실측 — ★**휴면 시간은 적지 않는다. 여기서 다시 재라.**

    await firing_status(db)     # 이 모듈의 함수. 발화수·최신시각·휴면 판정을 지금 값으로 낸다.

★**왜 값을 지웠나 (2026-09-13)**: 종전엔 이 자리에 *"★66시간 휴면"* 이 적혀 있었는데
  2026-09-12 재측정에서 **약 447시간**이었다. ***"넣으면 낡는다"고 경고하는 이 파일 안에서
  그 경고가 그대로 실현됐다.*** 발화수·시각은 스냅샷이라 아래처럼 **기준을 달아** 남기고,
  **거기서 계산되는 「휴면 N시간」은 지운다** — 그것이 낡는 유일한 칸이었다.

    [스냅샷 · 168 propai-api-8001 · DB now 2026-09-12T14:27:08Z · 측정 sid=7af9eaa2]
    threshold_autotune   SELF      441건   최신 2026-08-06T23:46Z
    threshold_relax      PRODUCT    47건   최신 2026-08-24T18:50Z
    circuit_observe      NONE       30건   최신 2026-07-24T11:55Z
    cache_warm           NONE        6건   최신 2026-09-04T17:34Z
    feature_toggle       SELF        0건   ★한 번도 발화한 적 없음
    stale_reanalysis     NONE        0건   ★한 번도 발화한 적 없음
    prompt_ab_adopt      NONE        0건   ★한 번도 발화한 적 없음
    ★대조군: `heal*` 이벤트 타입 전수 = [('heal_action', 524)] — 0건이 매체 오측정이 아니다.

★**양성 대조군**: L1 액션인 `threshold_autotune` 이 441건으로 잡혔다 —
`_emit_l1_event` 도 `event_type='heal_action'` 으로 쓰므로(`feature_flags.py` 실측)
L0·L1 이 **같은 매체**에 있다. 따라서 위 0건은 매체를 잘못 잰 결과가 아니다.

## 이 파일이 하지 않는 것

**고치지 않는다.** 왜 발화하지 않는지는 각각 다른 문제다(후보 굶주림·트리거 미충족·
소비처 부재). 여기서는 **사실을 보이게** 할 뿐이다 — `effector_reach` 가 도달범위에
대해 그렇게 하듯이.

★그리고 **"0건 = 결함"이라고 단정하지 않는다.** `reach=NONE` 인 효과기가 영원히
발화하지 않는 것이 정상일 수 있다. 이 표면은 **사실과 판단 근거**를 주고, 판단은 사람이 한다.

## ★알려진 한계 — `never_fired` 는 **세 가지를 구별하지 못한다**

독립 적대 리뷰(2026-08-27)가 위 0건 셋을 하나하나 추적해 **서로 다른 상황**임을 보였다.
내가 셋을 **같은 줄에 나란히 적은 것은 과대주장**이었다:

| 효과기 | 실제 | 0건의 뜻 |
|---|---|---|
| `feature_toggle` | **살아 있는 경로** — 조건 미충족 | ★**데이터 조건**이다(배선 결함 아님). ★★**막는 축이 하나가 아니다**: 게이트는 `status='open'` **AND** `created_at >= now-6h` **AND** `down_pct>=40` **AND** `ftotal+vtotal>=10` 네 술어의 곱이다. 라이브 실측 (2026-09-13 · `GET /growth/insights?insight_type=quality_drop` · total=4=len(items) **비절단**): 표본 축 **4/4 통과** · `status='open'` **2/4** · **창 축 0/4**(행 나이 461~479시간 ≈ 19~20일) · `down_pct>=40` **0/4**. ⇒ ***`down_pct` 를 100 으로 만들어도 창 축에서 0행이다.*** 그리고 더 상위 사실은 **`quality_drop` 이 약 19일째 생산되지 않았다**는 것이다. 잠금: `tests/test_feature_toggle_band_is_reachable.py` |
| `stale_reanalysis` | **자기참조** — 유일한 생산자가 자기 자신 | **건강한 시스템의 사실**(원장 훼손이 없었다는 뜻). 결함 아님 |
| `prompt_ab_adopt` | ★**구조적 도달 불가** | `_pick_better_version` 이 `cand-N` 라벨을 기대하는데 텔레메트리는 `"v4"` 를 준다 → 언제나 `insufficient_versions`. **부트스트랩 교착** |

★★**2026-09-13 정정 — `feature_toggle` 행의 근거가 거짓이었다.**
  종전 근거: *"`down_pct >= 40` 이 필요한데 `_classify_quality` 는 **20% 위에서만** 낸다"*.
  ***`> 20` 은 `>= 40` 을 포함한다*** — `down_pct=45` 는 20 도 넘으므로 발행되고 소비처도 통과한다.
  임계 모순은 **없고** 경로는 **도달 가능**하다. 0건은 «그런 서비스가 없었다»는 데이터 조건이다.
  ★**열(「조건 미충족」)은 맞았고 evidence 문장만 거짓이었다** — 결론이 맞으면 아무도 근거를 되짚지 않는다.
  ★★**이 오진이 지시하는 처방이 위험하다**: *"임계가 어긋났으니 맞추자"* → `FEATURE_DISABLE_ERROR_PCT`
    **40 → 20**. 그런데 `_classify_quality` 의 severity 는 **`"warn"` 하나뿐**이라 등급 구분이 없다
    ⇒ 임계를 20 으로 내리면 ***「경고」와 「자동 비활성」이 같은 지점이 된다.*** 임계를 조금 낮추는 것이
    아니라 **관측 층과 조치 층의 분리를 없애는 것**이다(`llm_narrative` 가 절반의 down 비율에 꺼진다).
  ★★**2026-09-13 2·3차 정정** — 1차 정정도, 그것을 고친 2차도 **부정확했다.**

    2차: *"막는 것은 `down_pct` 축 **하나**"* → ★**거짓**(R2 MAJOR-D).
    두 축을 갈라 놓고 **질의문의 나머지 두 축을 뭉뚱그렸다** — 내가 고치러 온 그 모양 그대로다.

    소비 게이트 전문(`feature_flags.py:480-484`)은 **네 술어의 곱**이다:
        insight_type='quality_drop' AND severity IN ('warn','critical')
        AND status='open' AND created_at >= now-6h        ← ★질의 안의 두 축
        …이후 파이썬에서  down_pct>=40  AND  ftotal+vtotal>=10

    라이브 실측(2026-09-13 · `insight_type` 필터 · **total=4=len(items) 비절단**):
        ftotal+vtotal>=10   **4/4 통과**
        status='open'       **2/4**
        created_at>=now-6h  **0/4**   ← ★이 축 하나가 전부를 떨어뜨린다(나이 461~479h ≈ 19~20일)
        down_pct>=40        **0/4**
    ⇒ ***`down_pct` 를 100 으로 만들어도 게이트는 0행을 반환한다.***
    ⇒ 그리고 **더 상위 원인**: `quality_drop` 자체가 **약 19일째 생산되지 않았다.**

    ★**「보류→None→강등」 기제 서술도 추론이었다**(R2 MEDIUM-B). 측정된 4행의 `metrics_json` 은
      `"down_pct": 0.0`(**실수**)이고 `down_pct_absent` 가 **없다** — `withheld()` 는
      `{field: None, …_absent}` 를 낸다. ⇒ 그 4행은 **보류 도입 이전 생산자**가 쓴 것이다
      (전부 2026-08-24 생성). **현재 코드가 그럴 것**이라는 추론을 **측정된 행의 설명으로 단정**했다.
      ***결론(0이라 통과 못 함)은 맞고 기제가 틀렸다*** — 이 파일이 고치러 온 바로 그 형태다.
    ★「못 잰다」고 적기 전에 「이 축으로 잴 수 있나」를 물어라(1차 정정의 교훈은 유효하다).

  ⇒ 그래서 산문을 고치는 데서 그치지 않고 **계약을 잠갔다**:
    `tests/test_feature_toggle_band_is_reachable.py` — «생산처가 내는 severity ⊆ 소비처가 받는 severity»
    (소비처를 `severity='critical'` 로 좁히면 이 효과기가 **조용히 도달 불가**가 된다. 그것이 진짜
    «구조적 도달 불가»이고 지금은 아니다) + down_pct 바닥의 **두 모집단** + insight_type 오타 잠금.

★그래서 **이 표면의 `never_fired` 하나로 셋을 가를 수 없다.** "무장했으나 미발화"와
"발화 불가"는 **처방이 다르다**(전자는 데이터 조건, 후자는 배선 결함).
그 판별은 코드 추적이 필요해 여기에 넣지 않았다 — **넣으면 그 분석이 낡는다.**
대신 **이 한계를 적어 둔다**: 이 표를 보는 사람은 0건을 보면 **그 효과기의 경로를
직접 따라가야 한다.** 표는 "어디를 볼지"를 알려 줄 뿐이다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.services.growth.capture_service import capture_status as _capture_status
from app.services.growth.effector_reach import EFFECTORS, Reach

#: 발화 기록이 사는 곳 — L0(`heal_actions`)·L1(`feature_flags._emit_l1_event`) **공통**.
#: 두 층이 같은 `event_type` 을 쓴다(실측). 한쪽만 보면 절반을 놓친다.
EVENT_TYPE = "heal_action"

#: 이 시간을 넘게 조용하면 `dormant` 로 표시한다.
#:
#: ★**이 값은 측정이 아니라 운영 판단이다.** "3일이면 사람이 알아야 한다"는 것뿐이고,
#:   효과기마다 자연 주기가 다르므로 임계 하나로 옳게 가를 수 없다.
#:   그래서 **`hours_since` 를 항상 함께 싣는다** — 사람이 이 라벨에 동의하지 않을 수 있게.
#:   ★임계를 낮춰 "휴면 0건"을 만들지 마라(굿하트). 이 값은 **경보의 민감도**일 뿐이고
#:   진실은 `hours_since` 와 `total` 이다.
DORMANT_HOURS = 72

#: 발화 상태 — ★닫힌 집합. 새 상태를 늘리면 락이 라벨을 요구한다.
STATE_NEVER = "never_fired"      # ★**계측 시작 이후** 0건(아래 TELEMETRY_SINCE 참조)
STATE_DORMANT = "dormant"        # 발화한 적은 있으나 DORMANT_HOURS 를 넘게 조용
STATE_ACTIVE = "active"          # 최근 발화
ALL_STATES: frozenset[str] = frozenset({STATE_NEVER, STATE_DORMANT, STATE_ACTIVE})

#: ★`never_fired` 가 **무엇에 대해** 0건인가 — 과대주장을 막는다.
#:
#:   *"기록 전체에서 0건"* 이라고 적었었는데 **그렇게 말할 근거가 없다.**
#:   저장소에는 `platform_events` 삭제 경로가 없지만(전수 확인 — `DELETE FROM
#:   platform_events` 는 테스트 정리 1건뿐), 그것이 *"영원히 0건"* 을 뜻하지는 않는다:
#:     · 테이블 생성 이전은 애초에 기록이 없다
#:     · `capture_service._QUEUE` 는 `maxlen=10_000` **드롭-올디스트**라 유실이 가능하다
#:   → 화면·주석은 **"계측 시작 이후"** 로 좁혀 말한다.
#:   ★계획서 §3-4 가 이미 *"표현을 그렇게 좁혀야 한다"* 고 적었는데 코드는 안 좁혔다 —
#:     주석에 쓴 주장도 검증 대상이다(§G-30).
TELEMETRY_SINCE = "2026-06-14"

#: 표에 **없는데** 이벤트에는 있는 액션 — 선언이 낡았다는 뜻이다.
#: ★한 방향만 보면 이걸 못 잡는다(선언→실측만 보면 실측→선언이 빈다).
STATE_UNDECLARED = "undeclared"


def classify(total: int, hours_since: float | None, *, dormant_hours: int = DORMANT_HOURS) -> str:
    """발화 상태 판정 — 순수 함수(DB 없이 단위검증 가능).

    ★`total == 0` 과 `hours_since` 가 큰 것은 **다른 사실**이다.
      "한 번도 안 했다"와 "하다가 멈췄다"는 원인도 처방도 다르다. 뭉개지 않는다.
    """
    if total <= 0:
        return STATE_NEVER
    if hours_since is not None and hours_since >= dormant_hours:
        return STATE_DORMANT
    return STATE_ACTIVE


async def _fired_rows(db: Any) -> dict[str, tuple[int, datetime | None]]:
    """이벤트에서 실제 발화를 집계한다 — `action_type` → (건수, 최신시각)."""
    rows = (
        await db.execute(
            text(
                "SELECT payload->>'action_type' AS k, COUNT(*) AS n, MAX(created_at) AS last"
                "  FROM platform_events"
                " WHERE event_type = :et AND payload->>'action_type' IS NOT NULL"
                " GROUP BY 1"
            ),
            {"et": EVENT_TYPE},
        )
    ).fetchall()
    return {str(r[0]): (int(r[1] or 0), r[2]) for r in rows}


async def firing_status(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """선언된 효과기 전수 × 실제 발화 — **양방향**으로 본다.

    Returns:
        effectors: 선언 표에서 **파생**한 전수(발화 0건도 행으로 나온다 — 그게 핵심이다)
        undeclared: 이벤트에는 있는데 표에 **없는** 액션(선언이 낡았다는 신호)
        summary: 상태별 집계 + `product_reaching_active` (제품에 닿으면서 살아 있는 수)

    ★한쪽 방향만 보면 반대가 샌다:
      · 선언→실측만 보면 **표에 없는 새 액션**이 감시망 밖
      · 실측→선언만 보면 **한 번도 발화 안 한 선언**이 안 보인다
    """
    now = now or datetime.now(UTC)
    fired = await _fired_rows(db)

    out: list[dict[str, Any]] = []
    for e in EFFECTORS:
        total, last = fired.get(e.key, (0, None))
        hours = None
        if last is not None:
            last_utc = last if last.tzinfo else last.replace(tzinfo=UTC)
            hours = round((now - last_utc).total_seconds() / 3600.0, 1)
        out.append(
            {
                "key": e.key,
                # ★선언과 실측을 **같은 행에** 둔다 — 따로 두면 아무도 대조하지 않는다.
                "declared_reach": str(e.reach),
                "total": total,
                "last_fired_at": last.isoformat() if last is not None else None,
                # ★라벨에 동의하지 않을 수 있게 **원값을 항상 싣는다**.
                "hours_since": hours,
                "state": classify(total, hours),
                # 왜 그 reach 인지 — 표가 요구하는 근거를 그대로 나른다.
                "evidence": e.evidence,
                "missing": e.missing,
            }
        )

    declared = {e.key for e in EFFECTORS}
    undeclared = [
        {
            "key": k,
            "declared_reach": None,
            "total": v[0],
            "last_fired_at": v[1].isoformat() if v[1] is not None else None,
            "state": STATE_UNDECLARED,
        }
        for k, v in sorted(fired.items())
        if k not in declared
    ]

    states = [r["state"] for r in out]
    return {
        "effectors": out,
        "undeclared": undeclared,
        "dormant_hours": DORMANT_HOURS,
        # ★화면이 "한 번도 없음"을 **무엇에 대해** 말하는지 밝힐 수 있게.
        "telemetry_since": TELEMETRY_SINCE,
        # ★**수집 파이프라인의 건강** — 이 표의 모든 결론이 `platform_events` 의
        #   완전성을 가정한다. 그 가정이 참인지 여기서 말한다.
        #   ★유실이 있으면 `never_fired` 도 `dormant` 도 **믿을 수 없다** —
        #     "발화 안 함"과 "발화 기록이 사라짐"이 같은 0 으로 보이기 때문이다.
        "capture": _capture_status(),
        "summary": {
            "declared": len(out),
            STATE_NEVER: states.count(STATE_NEVER),
            STATE_DORMANT: states.count(STATE_DORMANT),
            STATE_ACTIVE: states.count(STATE_ACTIVE),
            "undeclared": len(undeclared),
            # ★가장 중요한 한 줄 — **제품에 닿으면서 실제로 살아 있는** 효과기 수.
            #   `effector_reach.product_reaching_count()` 는 *선언*을 세고, 이건 *실제*를 센다.
            #   둘이 갈리면 표는 초록인데 제품은 아무 효과도 못 받고 있다는 뜻이다.
            "product_reaching_declared": sum(
                1 for e in EFFECTORS if e.reach is Reach.PRODUCT
            ),
            "product_reaching_active": sum(
                1
                for e, r in zip(EFFECTORS, out, strict=True)
                if e.reach is Reach.PRODUCT and r["state"] == STATE_ACTIVE
            ),
            # ★**임계 없는 사실** — 제품에 닿는 효과기 중 가장 오래 조용한 시간.
            #
            #   왜 이게 따로 필요한가: 이 작업을 촉발한 관측이 `threshold_relax` **66시간
            #   휴면**(★**2026-08-27 당시의 관측값** — 지금 값이 아니다. 2026-09-12 재측정은
            #   약 447시간이었다)이었는데, `DORMANT_HOURS=72` 라 그 사례는 `active` 로 분류된다.
            #   ★임계를 66 아래로 내려 그 하나를 잡게 만드는 것은 **관측에 지표를 맞추는
            #     것**이고(굿하트), 다음 관측에서 또 내려야 한다.
            #   그래서 라벨은 그대로 두고 **원값을 싣는다** — 라벨은 경보이고 이 값이 진실이다.
            #
            # ★★**혼합 모집단에서 거짓말을 했다**(독립 적대 리뷰 2026-08-27, 실측):
            #   PRODUCT 효과기가 둘일 때 하나는 5시간 전 발화, 하나는 **한 번도 발화 없음**이면
            #   옛 식은 `None` 을 걸러 **5.0** 을 냈다 — "최장 침묵 5시간"은 **거짓**이다.
            #   한쪽이 영원히 조용한데 그 사실이 이 한 줄에서 사라졌다.
            #   ★그리고 이 결함은 `product_reaching_count()` 가 1 을 넘는 순간 발화한다 —
            #     즉 `effector_reach` 가 *"이 값이 늘어나는 것이 목표다"* 라고 적은 **성공 시점**에.
            #   → **한 번도 발화 없음이 하나라도 있으면 `None`** 을 낸다(= 무한대. 숫자로
            #     비교 가능한 값을 주면 그것이 곧 과소보고다). 그 사실은 아래 카운트가 나른다.
            "product_reaching_max_hours_since": (
                None
                if any(
                    e.reach is Reach.PRODUCT and r["state"] == STATE_NEVER
                    for e, r in zip(EFFECTORS, out, strict=True)
                )
                else max(
                    (
                        r["hours_since"]
                        for e, r in zip(EFFECTORS, out, strict=True)
                        if e.reach is Reach.PRODUCT and r["hours_since"] is not None
                    ),
                    # ★이 `default` 는 **도달 불가 방어**다(기계 변이 생존 · 설명을 남긴다):
                    #   위 `any(...)` 가 False 라는 것은 PRODUCT 효과기 중 `never_fired` 가
                    #   하나도 없다는 뜻이고, 그러면 모두 `hours_since` 가 있어 제너레이터가
                    #   비지 않는다. **PRODUCT 효과기가 아예 0종일 때만** 여기에 닿는다.
                    #   그 경우는 `effector_reach` 가 PRODUCT 를 전부 잃었다는 뜻이라
                    #   지금 구성에서는 발생하지 않는다 — 그래도 `max()` 가 터지지 않게 남긴다.
                    default=None,
                )
            ),
            # 한 번도 발화한 적 없는 **제품** 효과기 — 있으면 그 자체로 이상하다.
            "product_reaching_never_fired": sum(
                1
                for e, r in zip(EFFECTORS, out, strict=True)
                if e.reach is Reach.PRODUCT and r["state"] == STATE_NEVER
            ),
        },
    }
