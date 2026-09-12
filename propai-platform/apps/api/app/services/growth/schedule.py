"""자가성장 스케줄러의 **실행 시점 판정** — 순수 함수.

## 왜 생겼나 (2026-08-22)

인프로세스 스케줄러는 **1분 틱을 세는 방식**이었다:

    tick = 0
    while True:
        run_analyze = (tick % 60 == 0)          # 매시
        run_learn   = (tick % 10080 == 0 and tick > 0)   # 주간
        ...
        tick += 1
        await sleep(60)

`tick` 은 **함수 안의 지역변수**다. 컨테이너가 새로 뜨면 0으로 돌아가고, **밀린 잡을
따라잡는 장치도 없다.** 그래서 `learn`(7일)·`improve`(24시간)은 **컨테이너가 그만큼
연속으로 살아 있어야** 한 번 발화한다. 이 저장소는 배포마다 컨테이너를 새로 만든다
(`deploy-zero-downtime.sh` 의 `docker run -d --name`, `safe-deploy.sh` 의 `compose up -d`).

즉 **주간·일배치 잡이 사실상 발화하지 못하는 상태**였다. 스케줄러는 돌고 로그도 남으니
겉보기엔 정상이라, 아무도 눈치채지 못했다.

## 무엇으로 바꿨나

시각을 **DB(`platform_settings`)에 적어 두고** "마지막 실행 이후 주기만큼 지났는가"로
판정한다. 재시작을 넘고, 밀렸으면 **다음 틱에 바로 따라잡는다.**

이 파일은 그 판정만 담는 **순수 함수**다 — DB·시계·네트워크를 타지 않아야 테스트가
그 판정을 **직접** 태울 수 있다(이 저장소가 반복해서 데인 *"검증이 실제 대상을 태우지
않는다"* 를 피하기 위해서다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class JobSpec:
    """잡 하나의 실행 주기.

    period_minutes
        실행 간격(분).
    run_when_unseen
        **워터마크가 없을 때**(첫 기동·DB 초기화) 곧바로 한 번 돌릴지.

        ★짧은 주기는 곧바로 도는 편이 낫다(부팅 직후 상태를 봐야 하고, 다시 돌아도 싸다).
          긴 주기는 그러면 **배포할 때마다** 주간 배치가 도는 꼴이라 과하다 — 그래서 기준점만
          찍고 다음 주기부터 발화한다.
    """

    period_minutes: int
    run_when_unseen: bool


#: 잡별 주기. 종전 `tick % N` 값을 그대로 옮겼다(동작을 바꾸지 않는다).
JOB_SPECS: dict[str, JobSpec] = {
    "analyze": JobSpec(60, True),       # 매시 — 인사이트 산출
    "heal": JobSpec(10, True),          # 10분 — 자가치유
    "correct": JobSpec(15, True),       # 15분 — 자가보정
    "improve": JobSpec(1440, False),    # 24시간 — L2 개선제안(인간 게이트)
    "learn": JobSpec(10080, False),     # 7일 — 학습 사이클 + 프롬프트 후보
}


def parse_watermark(raw: object) -> datetime | None:
    """저장된 워터마크를 datetime 으로. 못 읽으면 None.

    `platform_settings` 는 jsonb 라 문자열로 돌아온다. 값이 깨졌거나 형식이 바뀌었을 때
    **조용히 넘어가지 않도록** None 을 돌려주고, 호출부가 "본 적 없음"으로 다룬다.
    """
    # ★아래 세 검사는 **겹치는 이중 가드**다(변이 검증에서 각각 생존한다 — 하나를 무력화해도
    #   다음 가지가 같은 값을 낸다). 구멍이 아니라 의도한 중복이라 그 사실을 적어 둔다:
    #   `None` 은 첫 줄에서 걸리고, 걸리지 않더라도 `isinstance(None, str)` 가 False 라
    #   세 번째에서 다시 걸린다. 저장 형식이 바뀌어도(예: jsonb 가 숫자를 돌려줌) 새는 값이
    #   없도록 남긴다.
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def is_due(job: str, last_run: datetime | None, now: datetime) -> bool:
    """지금 이 잡을 돌려야 하는가.

    · 워터마크가 없으면 `run_when_unseen` 에 따른다.
    · 있으면 **경과 ≥ 주기** 일 때 참. 밀려 있었다면 즉시 따라잡는다.
    · ★시계가 뒤로 간 경우(경과가 음수)도 **참**으로 본다 — 그러지 않으면 시계 보정
      한 번에 잡이 **영원히 멈춘다**. 다시 도는 비용보다 멈추는 비용이 크다.
    """
    spec = JOB_SPECS.get(job)
    if spec is None:
        raise KeyError(f"모르는 잡: {job}")
    if last_run is None:
        return spec.run_when_unseen
    elapsed = (now - last_run).total_seconds()
    if elapsed < 0:
        return True
    return elapsed >= spec.period_minutes * 60


def should_seed(job: str, last_run: datetime | None) -> bool:
    """워터마크가 없고 지금은 돌리지 않을 잡인가 — 그러면 **기준점만** 찍는다.

    이걸 안 하면 긴 주기 잡이 매 틱마다 `is_due` 를 다시 물어 영원히 False 를 받는다.
    """
    return last_run is None and not JOB_SPECS[job].run_when_unseen


def watermark_key(job: str) -> str:
    """`platform_settings` 키. 잡별로 나눠 한 잡의 실패가 다른 잡을 막지 않게 한다."""
    return f"growth_last_run.{job}"


#: 스케줄 스냅샷이 사는 자리. ★**새 표면을 만들지 않는다** — `growth_analysis`(#997) 와 같은
#:   통로(`platform_settings` → `/growth/heal-log` 의 `active_flags`)를 쓴다. 라우터는 키를
#:   필터하지 않으므로(`routers/growth.py:574` 의 WHERE 는 TTL 만 본다) **라우터 변경이 필요 없다.**
SCHEDULE_SNAPSHOT_KEY = "growth_schedule"


def schedule_snapshot_payload(observed, now: datetime) -> dict[str, object]:
    """잡별 **경과/주기**를 한 줄 요약으로 만든다(발행용).

    ★**왜 이것이 필요한가 — 「경과」만으로는 정상과 정지를 가를 수 없다.**
      실측(2026-09-12 13:11Z): `growth_last_run.learn` 이 **9,471분 전**이었다. 이것을 보고
      *"학습 사이클이 6.6일째 멈췄다"* 고 의심했는데, `JOB_SPECS["learn"].period_minutes` 는
      **10080(7일)** 이라 **아직 발화할 때가 아니었다.** 같은 「7일 전」이 `learn` 에겐 정상이고
      `analyze`(60분)에겐 **대형 장애**다 — ***한 신호가 두 사건을 덮는다.***
      그런데 주기를 아는 표면이 없었다: `JOB_SPECS` 의 **런타임·표면 소비처 0**
      (조회 기준: `propai-platform` 이하 · `.py/.ts/.tsx/.sh` · **`.venv` 2개 제외** →
       `schedule.py` 와 `tests/unit/test_growth_schedule.py` 둘뿐).

    ★**판정하지 않는다 — 관측만 싣는다.** `overdue` 는 «경과 ≥ 주기» 라는 **사실**이지
      «고장» 이 아니다(정상적으로도 발화 직전에는 참이 된다). 무엇이 고장인지는
      **이 값이 계속 참으로 남는가**로 소비처가 판단한다.

    ★**요약에 잡 이름을 줄이지 않는다.** `growth_analysis.axes` 는 축 이름이 길어 3글자로
      줄였지만, 여기서 같은 짓을 하면 접두가 겹치는 잡이 생기는 순간 **두 잡이 한 칸으로
      뭉친다**. 이 파일이 고치려는 결함과 **같은 형태**라 하지 않는다.

    Parameters
    ----------
    observed
        `(job, last_run|None)` 쌍들. `None` 은 **워터마크를 본 적 없음**이고
        「경과 0」과 **다른 사실**이라 `-` 로 구분해 적는다.
    now
        기준 시각(주입받는다).
    """
    parts: list[str] = []
    overdue: list[str] = []
    for job, last in observed:
        spec = JOB_SPECS.get(job)
        if spec is None:          # 모르는 잡은 조용히 버리지 않는다
            parts.append(f"{job} ?/?")
            continue
        period = spec.period_minutes
        if last is None:
            parts.append(f"{job} -/{period}")
            continue
        elapsed = int((now - last).total_seconds() // 60)
        parts.append(f"{job} {elapsed}/{period}")
        # ★음수(시계 되돌림)도 `is_due` 가 참으로 보므로 여기서도 같은 값을 낸다.
        #   두 곳이 갈리면 계기판이 「돌 때가 됐다」와 반대를 말한다.
        if elapsed < 0 or elapsed >= period:
            overdue.append(job)
    return {
        "at": now.isoformat(),
        "jobs": " ".join(parts) or "-",
        "overdue": " ".join(overdue) or "-",
    }


async def compute_due(session, settings_api, now: datetime) -> dict[str, bool]:
    """워터마크를 **읽어** 잡별 실행 여부를 만든다. 씨드(기준점 찍기)도 여기서 한다.

    ★왜 이 함수가 `main.py` 가 아니라 여기 있나 — **배선을 태우기 위해서**다.
      판정만 순수 함수로 빼고 "읽고 쓰는 부분"을 `main.py` 안의 클로저로 두었더니,
      변이 검증에서 **그 연결 15줄이 통째로 생존**했다(지워도 아무 테스트가 안 죽었다).
      순수 함수가 잠겨 있어도 **그걸 부르는 곳이 안 잠기면** 결함은 그대로 새어 나간다 —
      이 저장소가 반복해서 데인 *"배선 미변이"* 다.
      그래서 세션과 설정 API 를 **인자로 받아** 테스트가 가짜를 넣고 직접 태울 수 있게 한다.

    Parameters
    ----------
    session
        DB 세션(설정 API 에 그대로 넘긴다).
    settings_api
        `get_setting(db, key)` · `set_setting(db, key, value, *, updated_by=...)` 를 가진 객체.
        운영에서는 `app.services.growth.schema_guard`.
    now
        판정 기준 시각(주입받는다 — 시계를 타면 테스트가 흔들린다).
    """
    due: dict[str, bool] = {}
    observed: list[tuple[str, datetime | None]] = []
    for job in JOB_SPECS:
        key = watermark_key(job)
        last = parse_watermark(await settings_api.get_setting(session, key))
        if should_seed(job, last):
            # 워터마크가 없고 지금 돌릴 잡이 아니면 **기준점만** 찍는다.
            await settings_api.set_setting(
                session, key, now.isoformat(), updated_by="growth-scheduler(seed)",
            )
            observed.append((job, now))   # 방금 찍은 기준점이 이 잡의 last 다
            due[job] = False
            continue
        observed.append((job, last))
        due[job] = is_due(job, last, now)
    # ★스냅샷 발행 — **판정에 개입하지 않는다**(위 `due` 는 이미 확정됐다). 이 블록을 지우면 원상이다.
    #   TTL 을 걸지 않는다: `/growth/heal-log` 는 `ttl_expires_at IS NULL` 도 활성으로 보므로
    #   행은 늘 노출되고, **「스케줄러가 도는가」는 `at` 의 나이로** 판정한다(부재가 아니라 나이).
    await settings_api.set_setting(
        session,
        SCHEDULE_SNAPSHOT_KEY,
        schedule_snapshot_payload(observed, now),
        updated_by="growth-scheduler",
    )
    return due
