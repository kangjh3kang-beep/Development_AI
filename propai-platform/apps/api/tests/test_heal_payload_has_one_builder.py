"""★`heal_action` payload 를 **만드는 코드**가 하나인지 잠근다 — 복제가 형제를 만든다.

## 왜 (실측 2026-09-05)

`heal_action` 이벤트를 쓰는 생산자는 **둘**이다:
`heal_actions._emit_heal_event`(L0) 와 `feature_flags._emit_l1_event`(L1).
두 번째가 payload 를 **복제**하고 있었고, 라이브 **524행 중 441행(84.2%)** 의 생산자다.
그래서 `#995` 가 `executed`/`no_op_reason` 을 L0 에만 넣었을 때 **L1 이 그대로 뒤처졌고**,
`/growth/heal-log` 의 84% 가 `executed: null` 로 왔다.

★**저장소가 이미 경고하고 있었다** — 그런데 산문이라 발화하지 않았다:
  · `effector_firing.py` : *"L0·L1 **공통**. 한쪽만 보면 **절반을 놓친다**"*
  · `feature_flags.py`   : *"★공용 헬퍼를 **재사용**한다. **복제하면 한쪽만 고쳐지는
    형제가 또 생긴다**"*

## 이 파일이 잠그는 것

★**모집단을 파생형으로 센다** — «생산자 2곳» 이라는 손목록을 쓰지 않는다.
`INSERT INTO platform_events ... 'heal_action'` 을 **소스에서 찾아** 그 수를 세고,
찾은 **모든** 생산자가 공용 빌더를 쓰는지 본다. 세 번째 생산자가 생기면 이 락이 빨개진다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.services.growth import feature_flags, heal_actions

_GROWTH_DIR = Path(heal_actions.__file__).parent
_EVENT_TYPE = "heal_action"
_BUILDER = "build_heal_payload"


_APP_DIR = _GROWTH_DIR.parents[1]          # apps/api/app
_INSERT = "INSERT INTO platform_events"


def _platform_event_inserters() -> list[tuple[Path, bool]]:
    """`platform_events` 에 INSERT 하는 **모든** 파일을 파생한다 — `(파일, 리터럴 heal_action)`.

    ★**세 번의 축 오류를 거쳐 여기까지 왔다**(적대 리뷰 실측 2026-09-05):
      ① «파일에 낱말이 있는가» → `healing_rules.py` **위양성**(그 파일은 `heal_blocked` 를 넣는다)
      ② «`growth/` 최상위 `*.py`» → **하위 디렉토리·다른 패키지**의 생산자를 못 본다
      ③ «INSERT 문에 `'heal_action'` 리터럴» → **`event_type` 을 바인드 파라미터로 주는**
         INSERT 를 원리적으로 못 본다. ★가설이 아니다 —
         `capture_service._INSERT_SQL` 이 정확히 그 형태이고,
         `routers/growth.py` 의 `_ALLOWED_TYPES` 에 **`heal_action` 이 들어 있어서**
         그 경로로 `heal_action` 행이 실제로 만들어질 수 있다.
    ***파생형으로 바꾼 것과 그 파생의 축이 맞는 것은 다른 일이다.***

    그래서 이 함수는 **INSERT 하는 파일 전부**를 돌려주고, 리터럴 여부를 **함께** 준다.
    바인드형은 이 락이 배선을 강제할 수 없으므로 **부채로 세어 드러낸다**(침묵시키지 않는다).
    """
    out: list[tuple[Path, bool]] = []
    for f in sorted(_APP_DIR.rglob("*.py")):
        text = f.read_text(encoding="utf-8")
        if _INSERT not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover
            # ★조용히 빠뜨리지 않는다 — 파싱 불가도 후보로 세어 아래 단언이 알게 한다.
            out.append((f, False))
            continue
        literal = any(
            isinstance(n, ast.Constant) and isinstance(n.value, str)
            and _INSERT in n.value and f"'{_EVENT_TYPE}'" in n.value
            for n in ast.walk(tree)
        )
        out.append((f, literal))
    return out


def _producer_files() -> list[Path]:
    """`heal_action` 을 **리터럴로** INSERT 하는 파일(= 이 락이 배선을 강제할 수 있는 모집단)."""
    return [f for f, lit in _platform_event_inserters() if lit]


class Test수집기가살아있다:
    """★단언 **앞에** 생존을 증명한다 — 0건이면 아래가 전부 공허하다."""

    def test_생산자를_최소한_찾는다(self):
        files = _producer_files()
        assert len(files) >= 2, (
            f"★생산자를 2곳 미만으로 찾았다 — 수집기가 죽었거나 경로가 바뀌었다: "
            f"{[f.name for f in files]}"
        )

    def test_공용빌더가_실재한다(self):
        assert callable(getattr(heal_actions, _BUILDER, None))


class Test모든생산자가공용빌더를쓴다:
    """★판정은 **payload 에 흘러드는 표현식**으로 한다 — 이름·리터럴이 아니라."""

    @staticmethod
    def _payload_sources(f: Path) -> list[ast.AST]:
        """`payload` 에 **대입되는 표현식**을 모은다 — ★**INSERT 하는 함수 안에서만**.

        `ast.Dict` 만 금지하면 `dict()`·`{}`+대입·`.copy()` 로 샌다(적대 리뷰 실증).
        ★그러나 함수를 안 가르면 **저장된 payload 를 읽는 코드**(`rollback()` 이
        `row["payload"]` 를 파싱하는 자리)까지 위반으로 신고한다 — 실제로 그랬다.
        ***위양성도 결함이다.*** 그래서 «그 함수가 INSERT 문을 갖는가»로 좁힌다.
        """
        tree = ast.parse(f.read_text(encoding="utf-8"))
        out: list[ast.AST] = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inserts = any(
                isinstance(n, ast.Constant) and isinstance(n.value, str) and _INSERT in n.value
                for n in ast.walk(fn)
            )
            if not inserts:
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == "payload":
                            out.append(node.value)
        return out

    def test_payload_는_공용빌더의_반환이다(self):
        """★`ast.Dict` 만 금지하면 `dict(...)`·`{}`+대입·`.copy()` 로 전부 샌다
        (적대 리뷰가 두 생산자 모두에서 실증했다). **대입되는 표현식이 빌더 호출인지**를 본다."""
        bad = []
        for f in _producer_files():
            srcs = self._payload_sources(f)
            assert srcs, f"★{f.name} 에서 `payload =` 대입을 못 찾았다 — 조회기가 죽었다"
            for node in srcs:
                ok = (isinstance(node, ast.Call)
                      and (getattr(node.func, "id", None) == _BUILDER
                           or getattr(node.func, "attr", None) == _BUILDER))
                if not ok:
                    bad.append(f"{f.name}:{node.lineno} {ast.dump(node)[:60]}")
        assert not bad, (
            f"★`payload` 가 공용 `{_BUILDER}` 의 반환이 아니다 — 손조립이면 한쪽만 "
            f"고쳐지는 형제가 또 생긴다: {bad}"
        )

    def test_바인드형_생산자는_부채로_드러난다(self):
        """★이 락이 **강제할 수 없는 모집단**을 침묵시키지 않는다.

        `event_type` 을 바인드 파라미터로 주는 INSERT 는 배선을 강제할 수 없다.
        그 수를 여기서 **세어 고정**한다 — 늘어나면 빨개져서 사람이 판단하게 된다.
        """
        binders = [f.name for f, lit in _platform_event_inserters() if not lit]
        assert binders == ["capture_service.py", "healing_rules.py"], (
            "★`platform_events` 에 바인드형으로 INSERT 하는 파일 집합이 바뀌었다. "
            "새로 생긴 것이 `heal_action` 을 넣는다면 이 락은 그것을 **강제하지 못한다** — "
            f"사람이 판단하라: {binders}"
        )

class Test판정값이실린다:
    """★「빌더를 부른다」와 「판정값이 실린다」는 다르다 — 값까지 본다."""

    @pytest.mark.parametrize(
        ("executed", "expect"), [(True, True), (False, False), (None, None)]
    )
    def test_세_모집단이_그대로_실린다(self, executed, expect):
        pl = heal_actions.build_heal_payload(
            "aid", "cache_warm", {}, rollbackable=False, setting_key=None,
            ttl_expires_at=None, actor="growth_engine",
            executed=executed, no_op_reason=None,
        )
        assert pl["executed"] is expect, "판정값이 빌더에서 소실됐다"

    def test_모든_emit_호출부가_executed_를_넘긴다(self):
        """★AST 로 호출부를 **파생**시킨다 — 하나라도 안 넘기면 그 액션은 `null` 이 된다."""
        missing = []
        constants: list[str] = []
        for mod, fn in ((heal_actions, "_emit_heal_event"),
                        (feature_flags, "_emit_l1_event")):
            tree = ast.parse(inspect.getsource(mod))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == fn):
                    kws = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                    if "executed" not in kws:
                        missing.append(f"{mod.__name__.split('.')[-1]}:{node.lineno}")
                    elif (isinstance(kws["executed"], ast.Constant)
                          and kws["executed"].value is None):
                        # ★금지하는 것은 **`None`**(=「모름」으로 축을 버리는 것)이다.
                        #   `executed=True` 는 «관측을 기록했다»처럼 **진짜 상수 판정**일 수
                        #   있으므로 막지 않는다 — 막으면 정상 코드를 위반으로 신고한다.
                        constants.append(f"{mod.__name__.split('.')[-1]}:{node.lineno}")
        assert not missing, (
            f"★`executed` 를 안 넘기는 호출부가 있다 — 그 액션의 heal-log 행은 "
            f"「모름(null)」으로 와서 무동작과 구별되지 않는다: {missing}"
        )
        # ★★**이름이 있는 것과 값이 실리는 것은 다르다** — `executed=None` 도 키워드 이름은
        #   있다. 직전 PR(`#995`)에서 정확히 그 변이가 **생존**했고 그 처방을 여기 옮긴다.
        assert not constants, (
            f"★`executed=None` 이다 — 축을 「모름」으로 버리는 것이라, 그 액션의 행은 "
            f"무동작과 구별되지 않는다: "
            f"{constants}"
        )


class _CaptureDB:
    """INSERT 파라미터의 `payload` JSON 을 붙잡는다 — ★**행위**를 본다."""

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


class Test두생산자가실제로판정을싣는다:
    """★**이 PR 의 존재 이유를 태운다.**

    적대 리뷰 실측: L1 의 `executed=executed` 를 `executed=None` 으로 되돌려도
    **락 8건이 전부 초록**이었다 — 84.2% 행이 다시 `null` 이 되는데 아무도 모른다.
    ***락이 자기가 잠근다는 것을 태우지 않았다.***

    그래서 여기서는 **두 생산자를 각각 실제로 호출**해 INSERT 파라미터를 붙잡고
    **값을 단언**한다. 그리고 **세 모집단**으로 가른다 — 한 축만 보면
    「늘 None」도 「늘 True」도 만점을 받는다.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("value", "expect"), [(True, "true"), (False, "false")])
    async def test_L0_가_판정을_싣는다(self, value, expect):
        db = _CaptureDB()
        await heal_actions._emit_heal_event(
            db, "aid", "cache_warm", {}, severity="info", executed=value
        )
        assert db.payloads, "★L0 이 INSERT 를 안 했다 — 조회기가 죽었다"
        assert f'"executed": {expect}' in db.payloads[-1].lower(), db.payloads[-1][:200]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("value", "expect"), [(True, "true"), (False, "false")])
    async def test_L1_이_판정을_싣는다(self, value, expect):
        """★라이브 84.2% 행의 생산자다 — 여기가 뚫리면 이 PR 은 아무것도 안 한 것이다."""
        db = _CaptureDB()
        await feature_flags._emit_l1_event(
            db, "aid", "threshold_autotune", "tkey", "threshold.x", {}, executed=value
        )
        assert db.payloads, "★L1 이 INSERT 를 안 했다 — 조회기가 죽었다"
        assert f'"executed": {expect}' in db.payloads[-1].lower(), db.payloads[-1][:200]

    @pytest.mark.asyncio
    async def test_모름은_모름으로_실린다(self):
        """★세 번째 모집단 — 「늘 True/False」인 구현을 잡는다."""
        db = _CaptureDB()
        await feature_flags._emit_l1_event(
            db, "aid", "threshold_autotune", "tkey", "threshold.x", {}, executed=None
        )
        assert '"executed": null' in db.payloads[-1].lower(), db.payloads[-1][:200]

    @pytest.mark.asyncio
    async def test_L1도_사유를_실을_수_있다(self):
        """★«안 됐는데 이유는 없음»을 막는다 — 진단 불가는 그 자체로 장애다."""
        db = _CaptureDB()
        await feature_flags._emit_l1_event(
            db, "aid", "threshold_autotune", "tkey", "threshold.x", {},
            executed=False, no_op_reason="setting_write_failed",
        )
        assert "setting_write_failed" in db.payloads[-1]
        assert '"no_op_reason"' in db.payloads[-1]


class Test사유는무동작에만붙는다:
    """★`no_op_reason` 은 «무동작일 때의 사유»로 정의돼 있다.

    `executed=True` 인데 사유가 붙으면, 그 존재를 「무동작」 술어로 읽는 소비자가
    오분류한다(적대 리뷰가 `circuit_observe` 에서 지적했다).
    """

    def test_실행한_액션은_사유를_안_넘긴다(self):
        import inspect

        src = inspect.getsource(heal_actions)
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "_emit_heal_event"):
                kws = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                ex, rs = kws.get("executed"), kws.get("no_op_reason")
                if (rs is not None and isinstance(ex, ast.Constant) and ex.value is True):
                    bad.append(f"heal_actions:{node.lineno}")
        assert not bad, (
            f"★`executed=True` 인데 `no_op_reason` 을 넘긴다 — 「사유가 있으면 무동작」으로 "
            f"읽는 소비자가 그 행을 오분류한다: {bad}"
        )


class Test공용화가위험을한점에모았다:
    """★**공용 빌더는 위험을 한 점에 모은다** — 그러면 그 한 점의 **모든 키**를 잠가야 한다.

    적대 리뷰 실측: 8키 중 `executed` 하나만 잠겨 있었고 `params`·`rollbackable` 을
    죽이는 변이가 **생존**했다. 그 둘은 장식이 아니다:

    | 키 | 죽으면 무슨 일이 나나 |
    |---|---|
    | `params` | `healing_rules._guard_counts` 가 `payload->'params'->>'trigger_key'` 로 **쿨다운·트리거별 캡**을 센다 → **두 생산자의 가드가 동시에 조용히 실명** |
    | `rollbackable` | `heal_actions.rollback()` 이 그 값으로 판정 → 모든 액션이 `not_rollbackable` |
    | `setting_key` | 롤백 대상 키가 사라진다 |
    | `actor` | 생산자 구별이 사라진다(익명 주입과 안 갈린다) |
    """

    @staticmethod
    def _pl(**kw):
        base = dict(
            action_id="aid", action_type="cache_warm", params={"trigger_key": "TK"},
            rollbackable=True, setting_key="relax.x", ttl_expires_at="T",
            actor="growth_engine", executed=True, no_op_reason=None,
        )
        base.update(kw)
        p = base.pop("params")
        a, t = base.pop("action_id"), base.pop("action_type")
        return heal_actions.build_heal_payload(a, t, p, **base)

    def test_판정에_쓰이는_키가_그대로_실린다(self):
        """★**8키 전부**를 본다 — 기계 변이도구(`scripts/mutate_changed.py`)가 남은 키의
        생존 9건을 냈다. 한 키만 잠그면 나머지 일곱이 조용히 죽는다."""
        pl = self._pl()
        assert pl["params"]["trigger_key"] == "TK", "★가드가 세는 키가 소실됐다"
        assert pl["rollbackable"] is True, "★롤백 판정 키가 소실됐다"
        assert pl["setting_key"] == "relax.x"
        assert pl["actor"] == "growth_engine"
        # ★`action_id` — `rollback()` 이 이 값으로 원본 액션을 찾는다(소실 = 롤백 불가)
        assert pl["action_id"] == "aid"
        # ★`action_type` — `_guard_counts` 가 이 값으로 캡·쿨다운을 센다(소실 = 가드 실명)
        assert pl["action_type"] == "cache_warm"
        # ★`ttl_expires_at` — TTL 자동원복의 만료 시각(소실 = 영구 플래그)
        assert pl["ttl_expires_at"] == "T"
        assert set(pl) == {
            "action_id", "action_type", "params", "rollbackable", "setting_key",
            "ttl_expires_at", "actor", "executed", "no_op_reason",
        }, f"★정본 payload 의 키 집합이 바뀌었다 — 소비자 계약이 갈린다: {sorted(pl)}"

    @pytest.mark.parametrize(
        "key", ["action_id", "action_type", "setting_key", "ttl_expires_at", "actor"]
    )
    def test_각_키가_입력을_실제로_읽는다(self, key):
        """★차가 0인 단언은 잠금이 아니다 — **키마다** 반대 입력이 반대 값을 내는지."""
        a = self._pl()
        kw = {key: "ZZZ"} if key != "action_id" else {}
        b = (heal_actions.build_heal_payload(
                "OTHER", "cache_warm", {"trigger_key": "TK"}, rollbackable=True,
                setting_key="relax.x", ttl_expires_at="T", actor="growth_engine",
                executed=True, no_op_reason=None)
             if key == "action_id" else self._pl(**kw))
        assert a[key] != b[key], f"★`{key}` 가 입력을 안 읽는다(상수로 굳었다)"

    def test_두_모집단이_다른_값을_낸다(self):
        """★차가 0인 단언은 잠금이 아니다 — 반대 입력이 반대 값을 내는지 본다."""
        a = self._pl(rollbackable=True)
        b = self._pl(rollbackable=False)
        assert a["rollbackable"] != b["rollbackable"], "★rollbackable 이 입력을 안 읽는다"
        c = self._pl()
        d = heal_actions.build_heal_payload(
            "aid", "cache_warm", {"trigger_key": "OTHER"}, rollbackable=True,
            setting_key=None, ttl_expires_at=None, actor="growth_engine",
            executed=True, no_op_reason=None,
        )
        assert c["params"] != d["params"], "★params 가 입력을 안 읽는다"


class Test모집단이함께깎이지않는다:
    """★**파생형 단언은 모집단이 줄면 조용해진다** — 하한을 따로 건다.

    기계 변이도구 실측: `rollback()` 의 `_emit_heal_event(...)` **호출을 통째로 지우면**
    「호출부마다 executed 를 넘기는가」 단언이 **공허하게 참**이 된다(셀 것이 하나 줄었을 뿐).
    ***기대값이 내가 깎으려는 그 모집단에서 나오면 안 된다.***
    """

    def test_emit_호출부가_하한_이상이다(self):
        import inspect

        counts = {}
        for mod, fn in ((heal_actions, "_emit_heal_event"),
                        (feature_flags, "_emit_l1_event")):
            tree = ast.parse(inspect.getsource(mod))
            counts[fn] = sum(
                1 for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == fn
            )
        assert counts["_emit_heal_event"] >= 5, (
            f"★L0 의 emit 호출부가 줄었다 — 그 액션은 heal-log 에 아예 안 남는다: {counts}"
        )
        assert counts["_emit_l1_event"] >= 3, (
            f"★L1 의 emit 호출부가 줄었다: {counts}"
        )

    def test_관측전용_표식이_실린다(self):
        """★`circuit_observe` 가 「관측만」임을 `params.mode` 로 말한다(사유 필드가 아니라).

        이 표식이 죽으면 `executed=True` 인 30행이 «조치했다»와 구별되지 않는다 —
        `no_op_reason` 으로 옮기는 것은 **배타성 계약을 깬다**(그래서 다른 축에 둔다).
        """
        import inspect

        # ★**소스 부분문자열로 보지 않는다** — 이 함수의 **내 주석**에 `no_op_reason` 이
        #   적혀 있어서 첫 판이 **정상 코드를 위반으로 신고**했다(오늘 세 번째 같은 형태).
        #   ***내가 쓴 산문이 내 검사의 위양성이 된다.*** 그래서 **호출 키워드**를 판정한다.
        tree = ast.parse(inspect.getsource(heal_actions._do_circuit_observe))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", None) == "_emit_heal_event"]
        assert len(calls) == 1, f"★emit 호출이 하나가 아니다: {len(calls)}"
        kws = {kw.arg for kw in calls[0].keywords if kw.arg}
        assert "no_op_reason" not in kws, (
            "★`executed=True` 인 액션이 사유 필드를 넘긴다 — 「사유가 있으면 무동작」으로 "
            "읽는 소비자를 오분류시킨다(배타성 계약)"
        )
        # 관측전용 표식은 **다른 축**(`params.mode`)에 실린다.
        dumped = ast.dump(calls[0])
        assert "observe_only" in dumped, (
            "★관측전용 표식이 사라졌다 — executed=True 인 행이 실제 조치와 구별되지 않는다"
        )


class Test생산자가넘기는것까지본다:
    """★빌더를 잠그는 것과 **생산자가 무엇을 넘기는가**를 잠그는 것은 다른 층이다.

    기계 변이도구(`scripts/mutate_changed.py`)가 마지막까지 남긴 생존 2건이 그 층이었다:
      · `feature_flags.py:199` — L1 이 넘기는 `{"trigger_key": trigger_key, **params}`
      · `heal_actions.py:366`  — `rollback()` 이 넘기는 `setting_key=`
    둘 다 장식이 아니다 — `_guard_counts` 가 `params->>'trigger_key'` 로 **쿨다운·트리거별
    캡**을 세고, 롤백 이벤트의 `setting_key` 는 **무엇을 되돌렸는지**를 말한다.
    """

    @pytest.mark.asyncio
    async def test_L1이_trigger_key를_params에_넣는다(self):
        db = _CaptureDB()
        await feature_flags._emit_l1_event(
            db, "aid", "threshold_autotune", "TK-1", "threshold.x", {"name": "n"},
            executed=True,
        )
        pl = db.payloads[-1]
        assert '"trigger_key": "TK-1"' in pl, (
            f"★L1 이 trigger_key 를 안 싣는다 — 가드가 트리거별 캡을 못 센다: {pl[:200]}"
        )
        assert '"name": "n"' in pl, "★호출부가 준 params 가 소실됐다"

    @pytest.mark.asyncio
    async def test_L1이_다른_trigger_key를_구별한다(self):
        """★차가 0인 단언 방지 — 두 입력이 두 값을 내는가."""
        a, b = _CaptureDB(), _CaptureDB()
        for db, tk in ((a, "TK-A"), (b, "TK-B")):
            await feature_flags._emit_l1_event(
                db, "aid", "threshold_autotune", tk, "threshold.x", {}, executed=True)
        assert a.payloads[-1] != b.payloads[-1], "★trigger_key 가 payload 를 안 가른다"

    def test_rollback이_setting_key를_넘긴다(self):
        """★AST 로 본다 — 롤백 이벤트가 **무엇을 되돌렸는지** 말하지 않으면 감사 불가."""
        import inspect

        tree = ast.parse(inspect.getsource(heal_actions.rollback))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", None) == "_emit_heal_event"]
        assert len(calls) == 1, f"★rollback 의 emit 호출이 하나가 아니다: {len(calls)}"
        kws = {kw.arg for kw in calls[0].keywords if kw.arg}
        assert {"setting_key", "executed"} <= kws, (
            f"★rollback 이벤트가 되돌린 대상·판정을 안 싣는다: {sorted(kws)}"
        )
