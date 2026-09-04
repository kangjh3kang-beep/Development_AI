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
    for job in JOB_SPECS:
        key = watermark_key(job)
        last = parse_watermark(await settings_api.get_setting(session, key))
        if should_seed(job, last):
            # 워터마크가 없고 지금 돌릴 잡이 아니면 **기준점만** 찍는다.
            await settings_api.set_setting(
                session, key, now.isoformat(), updated_by="growth-scheduler(seed)",
            )
            due[job] = False
            continue
        due[job] = is_due(job, last, now)
    return due
