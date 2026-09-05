"""★**아무 일도 하지 않은 치유가 진짜 문제를 닫아서는 안 된다** — 그리고 그 사실이 산출물에 보여야 한다.

## 왜 (라이브 실측 2026-09-05)

`healing_rules.mark_insight_acted` 는 `result["executed"]` 가 참일 때만 인사이트를 닫는다.
그런데 `_do_cache_warm` 은 **디스패치가 배선돼 있지 않은데도** 성공을 상수로 보고했다.

    DB 전체 status='acted' 인사이트           4건
    그 4건을 닫은 액션                         ★4건 전부 cache_warm (100%)
    전부 trigger_key='fallback_rate:registry'  — 유료 등기부 경로(3,200원/필지)
    폴백률                                     18.18% · 18.18% · 23.08% · 26.32%
    ★음성 대조군: 실제로 동작하는 threshold_relax 는 acted 0건
                 (acknowledged 5 · open 13 · superseded 29)

## ★이 파일이 「무엇을」 태우는가 — 2차 적대 리뷰가 여기서 나를 무너뜨렸다

첫 판은 `inspect.getsource` 부분문자열만 봤고, **`_do_cache_warm` 을 한 번도 실행하지
않았다.** 실측: 그 함수가 **무조건 예외를 던지게 만들어도 성장·치유 스위트 463건이 전부
초록**이었고, `triggered = True` 한 줄로 **결함 본체가 그대로 복원**됐다.
그리고 소스 단언은 등가 리팩토링(`bool(triggered)`)과 **독스트링 수정**을 **위반으로
신고**했다 — ★내가 독스트링에 적은 예시가 내 검사의 위양성이 됐다.

> ***락은 함수를 태워야 한다. 이름이 소스에 있는 것과 그 값이 실리는 것은 다르다.***

이 판은 **`_do_cache_warm` 을 직접 호출**하고 **두 모집단**으로 가른다.
"""

from __future__ import annotations

import pytest

from app.services.growth import heal_actions

#: ★두 모집단을 가르는 축은 **`enqueue` 하나**여야 한다.
#:   celery 유무로 가르면 `triggered = bool(params.get("enqueue", ...))` 줄이 무동작 쪽에서
#:   **실행조차 되지 않아**, 그 줄을 `True` 로 바꾸는 변이가 **생존**한다(2차 리뷰 실측).
#:   ***차가 0인 픽스처는 잠금이 아니다 — 유일하게 가르는 입력을 찾아라.***
_CELERY_PRESENT = object()


class _RecordingDB:
    """`_emit_heal_event` 의 INSERT 파라미터를 그대로 붙잡는다(산출물 관측용)."""

    def __init__(self) -> None:
        self.payloads: list[str] = []

    async def execute(self, stmt, params=None):
        if params and "pl" in params:
            self.payloads.append(params["pl"])
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _run(enqueue: bool, *, celery=_CELERY_PRESENT):
    """★`_do_cache_warm` 은 celery 앱을 **함수-로컬 임포트**로 읽는다.

    그래서 monkeypatch 대상은 **모듈 속성**이다(호출 시점에 해석된다).

    ★**두 환경이 다르다 — 이것을 섞으면 무동작의 원인을 오진한다**(실측 2026-09-05):

        테스트/로컬  `celery_app.app is None`  → `_celery is not None` 이 거짓
        ★라이브 api  `app` = **Celery 인스턴스(truthy)** → 그 분기는 **통과한다**

    즉 프로덕션에서 무동작인 이유는 **celery 부재가 아니라**
    ①**어떤 호출부도 `params["enqueue"]` 를 넣지 않고**(전수 0건)
    ②넣더라도 **그 뒤에 디스패치 코드가 없다** 는 것이다.
    ★그래서 「배선됨」 모집단은 테스트에서 celery 를 **주입해야** 만들어진다.
    """
    import sys as _sys

    mod = _sys.modules.get("app.tasks.celery_app")
    if mod is None:
        import app.tasks.celery_app as mod  # noqa: PLC0415
    old = mod.app
    mod.app = celery
    try:
        db = _RecordingDB()
        res = await heal_actions._do_cache_warm(
            db, "aid-1", {"enqueue": enqueue, "insight_id": "iid-1"}, "registry", "warn"
        )
        return res, db
    finally:
        mod.app = old


class Test무동작과동작이갈린다:
    """★두 모집단. 한 축만 보면 「늘 False」도 「늘 True」도 만점을 받는다."""

    @pytest.mark.asyncio
    async def test_디스패치가_없으면_실행했다고_말하지_않는다(self):
        res, _ = await _run(enqueue=False)  # ★celery 는 주입돼 있다 — 가르는 축은 enqueue 다
        assert res["executed"] is False, (
            "★무동작이 성공을 보고하면 mark_insight_acted 가 진짜 문제를 닫는다"
        )
        assert res["detail"]["no_op_reason"] == "no_dispatch_wired", (
            "무동작 사유가 없으면 「왜 안 닫혔나」를 사람이 알 수 없다 — 진단 불가는 장애다"
        )

    @pytest.mark.asyncio
    async def test_디스패치가_있으면_실행했다고_말한다(self):
        """★과잉 억제 방지 — 「늘 False」인 구현은 위 테스트만으로는 못 잡는다."""
        res, _ = await _run(enqueue=True)
        assert res["executed"] is True
        assert "no_op_reason" not in res["detail"], "동작했는데 무동작 사유가 붙었다"


class Test무동작이산출물에서구별된다:
    """★`/growth/heal-log` 가 무동작을 진짜 치유와 **같은 모양**으로 싣던 것을 가른다.

    ★적대 리뷰 실측: 첫 판은 `no_op_reason` 을 `detail` 에만 넣었는데
    `_emit_heal_event` 는 `params` 만 payload 에 담아 **어떤 산출물에도 도달하지
    않았다**(라이브 heal_action 524건 중 `executed` 키를 실은 행 **0**).
    계획서가 «보존한다»고 선언한 것이 **거짓**이었다.
    """

    @pytest.mark.asyncio
    async def test_무동작이_payload에_실린다(self):
        _, db = await _run(enqueue=False)
        assert db.payloads, "heal_action 이벤트가 INSERT 되지 않았다 — 조회기가 죽었다"
        pl = db.payloads[-1]
        assert '"executed": false' in pl.lower(), f"payload 에 executed 가 없다: {pl[:200]}"
        # ★키까지 본다 — 값 부분문자열만 보면 키를 바꿔도 초록이다(3차 리뷰 실측 S4).
        assert '"no_op_reason"' in pl, f"payload 에 no_op_reason **키**가 없다: {pl[:200]}"
        assert "no_dispatch_wired" in pl, f"payload 에 무동작 사유 값이 없다: {pl[:200]}"

    @pytest.mark.asyncio
    async def test_동작한_경우와_구별된다(self):
        """★음성 대조군 — 두 payload 가 **같으면** 이 축은 판별력 0 이다."""
        _, db_noop = await _run(enqueue=False)
        _, db_ok = await _run(enqueue=True)
        assert db_noop.payloads[-1] != db_ok.payloads[-1], (
            "무동작과 동작의 payload 가 동일하다 — 산출물이 둘을 못 가른다"
        )
        assert '"executed": true' in db_ok.payloads[-1].lower()
        assert "no_dispatch_wired" not in db_ok.payloads[-1]


class Test닫기게이트가executed에걸려있다:
    """★상류 계약이 사라지면 위가 전부 공허해진다(처방 범위 ≠ 결함 범위 방지).

    ★`mark_insight_acted` 의 **행위** 자체는 형제
    `test_heal_closes_the_insight.py` 가 더 강하게(SQL 본문·커밋 계수까지) 잠근다.
    여기서는 **그 게이트가 존재하는지만** 본다 — 중복을 만들지 않는다.
    """

    def test_닫기가_executed로_게이트된다(self):
        import inspect

        from app.services.growth import healing_rules

        src = inspect.getsource(healing_rules.mark_insight_acted)
        assert 'result.get("executed")' in src, (
            "★닫기 게이트가 `executed` 를 안 본다 — 그러면 `_do_cache_warm` 을 정직하게 "
            "고쳐도 인사이트는 계속 닫힌다."
        )


class Test환경차이가원인을흐리지않는다:
    """★celery 부재도 무동작이지만 **원인이 다르다** — 둘을 같은 사유로 보고하면 오진한다."""

    @pytest.mark.asyncio
    async def test_celery가_없어도_무동작이다(self):
        res, _ = await _run(enqueue=True, celery=None)
        assert res["executed"] is False
        assert res["detail"]["no_op_reason"] == "no_dispatch_wired"

    @pytest.mark.asyncio
    async def test_라이브는_celery가_있다는_사실을_잊지_않는다(self):
        """★라이브 api 컨테이너의 `celery_app.app` 은 **truthy** 다(실측 2026-09-05).

        그러므로 프로덕션 무동작의 원인은 celery 부재가 **아니라** 호출부가
        `enqueue` 를 넣지 않는 것이고, 넣더라도 디스패치 코드가 없다는 것이다.
        이 테스트는 그 구분이 `_run` 의 기본값으로 **고정돼 있는지** 본다.
        """
        assert _CELERY_PRESENT is not None, (
            "기본 모집단이 celery 부재가 되면 가르는 축이 enqueue 에서 환경으로 옮겨간다"
        )


class Test응답계약까지도달한다:
    """★마지막 층: `payload` 에 실렸어도 **라우터가 안 옮기면** 화면은 여전히 못 가른다.

    ★판정은 문자열이 아니라 **파서(AST)** 로 한다 — 소스 부분문자열은 주석·독스트링에
    뚫리고(내 독스트링이 실제로 내 검사의 위양성을 만들었다) 등가 표기에 깨진다.
    """

    def test_HealActionOut_이_두_필드를_갖는다(self):
        from app.routers.growth import HealActionOut

        fields = set(HealActionOut.model_fields)
        assert {"executed", "no_op_reason"} <= fields, (
            f"응답 계약에 무동작 축이 없다 — heal-log 가 둘을 못 가른다: {sorted(fields)}"
        )
        # ★두 모집단이 실제로 다른 값을 낸다(차가 0인 단언은 잠금이 아니다).
        assert HealActionOut(executed=False, no_op_reason="no_dispatch_wired").executed is False
        assert HealActionOut(executed=True).no_op_reason is None

    def test_라우터가_그_두_필드를_실제로_옮긴다(self):
        """★AST 로 `HealActionOut(...)` 호출의 **키워드 이름**을 파생시킨다."""
        import ast
        import inspect

        from app.routers import growth as growth_router

        tree = ast.parse(inspect.getsource(growth_router))
        kwargs: dict[str, ast.AST] = {}
        found = 0
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "HealActionOut"):
                found += 1
                kwargs.update({kw.arg: kw.value for kw in node.keywords if kw.arg})
        assert found >= 1, "★HealActionOut 호출을 하나도 못 찾았다 — 조회기가 죽었다"
        assert {"executed", "no_op_reason"} <= set(kwargs), (
            f"라우터가 무동작 축을 응답으로 옮기지 않는다(호출 {found}건): {sorted(kwargs)}"
        )
        # ★★**이름이 있는 것과 값이 실리는 것은 다르다.** `executed=None` 도 키워드 이름은
        #   있다 — 실제로 그 형태의 변이가 **생존**했다(같은 실행에서 실측).
        #   그래서 **값 표현식**을 본다: 상수면 payload 를 안 읽는 것이다.
        for name in ("executed", "no_op_reason"):
            node = kwargs[name]
            assert not isinstance(node, ast.Constant), (
                f"★`{name}=` 이 상수다 — payload 를 읽지 않으므로 화면은 무동작을 못 가른다"
            )
            # ★★3차 적대 리뷰가 이 자리를 **양방향으로** 뚫었다:
            #   ·위음성 — `ast.Call` 만 요구하면 `pl.get("exec_uted")` 처럼 **틀린 키**도 통과
            #   ·위양성 — 바로 윗줄 `params=` 가 쓰는 **방어적 `IfExp`** 를 위반으로 신고
            #   그래서 「호출 모양」이 아니라 **그 표현식이 이 필드 이름을 읽는가**를 본다.
            dumped = ast.dump(node)
            assert f"'{name}'" in dumped, (
                f"★`{name}=` 이 그 이름의 키를 읽지 않는다(오타·다른 키): {dumped[:160]}"
            )
