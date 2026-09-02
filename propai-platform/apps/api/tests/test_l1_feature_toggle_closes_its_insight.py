"""L1 자가수정이 **자기가 조치한 인사이트를 닫지 않았다** — `#886` 의 안 쓸린 형제.

## 왜 (라이브 실측 2026-08-27)

`#886` 이 L0(`healing_rules`)에서 *"치유는 실행되고 `insight_id` 까지 아는데 닫는 코드가 0건"*
을 고쳤다. **그 형제인 L1(`feature_flags`)은 안 쓸렸다.**

    feature_flags 의 닫는 코드      →  **0건**
    ★양성 대조군 healing_rules      →  **4건**   (조회기 생존)

게다가 형태가 더 안쪽이었다 — 후보를 만드는 SQL 이 `SELECT metrics_json` 뿐이라
**닫을 대상(`id`)을 아예 조회하지 않았다.** 즉 "닫는 코드를 빠뜨린" 게 아니라
**닫는 것이 원천적으로 불가능한 구조**였다.

★현재는 게이트(`down_pct >= 40.0`)가 라이브에서 미달이라 **잠복**이다
(관측: 열린 `quality_drop` 4건 전부 `down_pct=0.0`). 잠복이 곧 무해가 아니다 —
게이트가 넘는 날 그 인사이트는 **영원히 `open`** 이 된다.

## 이 파일이 잠그는 것

1. **id 를 실제로 조회하는가**(안 하면 나머지가 전부 무의미)
2. **두 모집단이 다른 답을 내는가** — 인사이트 기반 조치는 닫고, 연속 보정은 안 닫는다
3. ★**형제 전파** — 인사이트에서 후보를 만드는 **모든** 모듈이 닫기를 경유하는가
   (목록형 금지 — 코드에서 파생. 세 번째 형제가 생기면 여기서 걸린다)
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.services.growth import feature_flags as ff
from app.services.growth import healing_rules

_GROWTH = Path(__file__).resolve().parents[1] / "app" / "services" / "growth"


# ══════════════════════════════════════════════════════════════════════
# ① 닫을 대상을 **조회하는가** — 이게 없으면 나머지 락이 전부 공허하다
# ══════════════════════════════════════════════════════════════════════

def test_candidate_query_selects_the_id():
    src = inspect.getsource(ff.evaluate)
    assert "SELECT id, metrics_json FROM platform_insights" in src, \
        "후보 SQL 이 id 를 조회하지 않는다 — 닫을 대상을 모른다"
    assert '"insight_id": str(_ins_id)' in src, "후보가 출처 인사이트를 안 들고 간다"


def test_close_goes_through_the_shared_helper_not_a_copy():
    """★공용 헬퍼를 **재사용**해야 한다. 복제하면 한쪽만 고쳐지는 형제가 또 생긴다."""
    src = inspect.getsource(ff.evaluate)
    assert "healing_rules.mark_insight_acted" in src
    assert "UPDATE platform_insights" not in src, \
        "닫기 SQL 을 여기 복제했다 — 형제가 또 갈린다"


# ══════════════════════════════════════════════════════════════════════
# ② 두 모집단 — 인사이트 기반은 닫고, 연속 보정은 안 닫는다
# ══════════════════════════════════════════════════════════════════════

class _Recorder:
    """`mark_insight_acted` 가 **무엇을 받는지** 붙잡는다(호출 여부만 세면 배선이 안 잠긴다).

    ★**추출을 복제하지 않는다**(2026-08-28 · development-ai-01 이 질문으로 짚었다).
      첫 판은 여기서 `(action.get("params") or {}).get("insight_id")` 를 **다시 썼다.**
      그러면 진짜 함수가 `action.get("insight_id")` 로 계약을 바꿔도 **이 락은 초록**이다
      (변이 실측: 이 파일 단독 `SURVIVED` / 형제 락이 CAUGHT).
      **락이 사본을 태우면 그 층은 안 잠긴다** — `#905` 에서 같은 형태를 이미 냈다.
      → **원문 그대로** 보관하고, 판정은 `_extracted_by_the_real_closer()` 가 한다.
    """

    def __init__(self):
        self.raw: list[tuple[dict, dict]] = []

    async def __call__(self, db, action, result):
        self.raw.append((action, result))
        return 1 if (action.get("params") or {}).get("insight_id") else 0

    @property
    def calls(self) -> list[tuple]:
        """★**진짜 closer 가 읽어 낼 값**으로 환산한다 — 스텁의 해석이 아니다."""
        return [_extracted_by_the_real_closer(a, r) for a, r in self.raw]


def _extracted_by_the_real_closer(action: dict, result: dict) -> tuple:
    """`mark_insight_acted` **자신의 소스**에서 추출 표현식을 꺼내 그대로 평가한다.

    ★이렇게 하면 진짜 함수가 계약을 바꾸는 순간 이 락이 **따라 움직인다.**
      복제해 두면 옛 계약에 고정돼 배선이 끊겨도 초록이다.
    """
    # ★**소스 파일에서** 꺼낸다 — 라이브 속성이 아니다.
    #   이 락은 `monkeypatch.setattr(healing_rules, "mark_insight_acted", rec)` 아래에서
    #   돌아가므로 `inspect.getsource(healing_rules.mark_insight_acted)` 는 **스텁**을 본다
    #   (실측: `TypeError: … got _Recorder`). 파일을 보면 그 간섭이 원리적으로 없다.
    mod = Path(healing_rules.__file__)
    tree = next(n for n in ast.parse(mod.read_text(encoding="utf-8")).body
                if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
                and n.name == "mark_insight_acted")
    ins_expr = executed_expr = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "ins_id":
            ins_expr = node.value
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get" \
                and getattr(node.func.value, "id", None) == "result":
            executed_expr = node
    assert ins_expr is not None and executed_expr is not None, \
        "진짜 closer 에서 추출식을 못 꺼냈다 — 이 락이 무의미하다(추출기 사망)"
    env = {"action": action, "result": result}
    return (eval(compile(ast.Expression(ins_expr), "<ins>", "eval"), {}, env),  # noqa: S307
            eval(compile(ast.Expression(executed_expr), "<exe>", "eval"), {}, env))  # noqa: S307


@pytest.mark.parametrize("cand,expect_id", [
    ({"kind": ff.ACTION_FEATURE_TOGGLE, "insight_id": "abc"}, "abc"),   # 인사이트 기반 → 닫는다
    ({"kind": ff.ACTION_THRESHOLD_AUTOTUNE}, None),                     # 연속 보정 → 닫을 대상 없음
    ({"kind": ff.ACTION_PROMPT_AB_ADOPT}, None),                        # 〃
])
def test_only_insight_scoped_actions_carry_a_close_target(cand, expect_id):
    """★파티션 — 세 종류가 **다른 답**을 내야 한다.

    한 모집단만 보면 "전부 닫는다"도 "전부 안 닫는다"도 통과한다.
    """
    assert cand.get("insight_id") == expect_id


@pytest.mark.asyncio
async def test_applied_toggle_closes_its_source_insight(monkeypatch):
    """★배선 — `evaluate` 가 실제로 그 인사이트 id 로 닫기를 부르는가."""
    rec = _Recorder()
    monkeypatch.setattr(healing_rules, "mark_insight_acted", rec)

    async def _guards(_db, _k, _t, _n):
        return 0, 0, None
    monkeypatch.setattr(healing_rules, "_guard_counts", _guards)

    async def _apply(_db, feature, *, enabled, error_pct=None, trigger_key=None):
        return {"applied": True, "action_id": "a1", "setting_key": f"feature.{feature}"}
    monkeypatch.setattr(ff, "apply_feature_toggle", _apply)

    db = _QualityDropDB(insight_id="11111111-1111-1111-1111-111111111111")
    out = await ff.evaluate(db, now=_NOW)

    assert out["applied"] == 1, out
    assert rec.calls, "닫기가 호출되지 않았다 — 배선이 끊겼다"
    ins_id, executed = rec.calls[0]
    assert ins_id == "11111111-1111-1111-1111-111111111111", \
        f"엉뚱한 인사이트를 닫는다: {ins_id}"
    assert executed is True, "applied→executed 번역이 틀렸다"
    assert out["closed"] == 1


@pytest.mark.asyncio
async def test_unapplied_toggle_closes_nothing(monkeypatch):
    """★음성 모집단 — 조치가 **적용되지 않았으면** 닫지 않는다."""
    rec = _Recorder()
    monkeypatch.setattr(healing_rules, "mark_insight_acted", rec)

    async def _guards(_db, _k, _t, _n):
        return 0, 0, None
    monkeypatch.setattr(healing_rules, "_guard_counts", _guards)

    async def _apply(_db, feature, *, enabled, error_pct=None, trigger_key=None):
        return {"applied": False, "reason": "noop"}
    monkeypatch.setattr(ff, "apply_feature_toggle", _apply)

    out = await ff.evaluate(_QualityDropDB(), now=_NOW)
    assert out["applied"] == 0
    assert not rec.calls, "적용 안 됐는데 인사이트를 닫았다"
    assert out["closed"] == 0


# ══════════════════════════════════════════════════════════════════════
# ③ ★형제 전파 — 세 번째 형제가 같은 구멍을 갖지 못하게 (파생형)
# ══════════════════════════════════════════════════════════════════════

def test_every_module_acting_on_open_insights_closes_them():
    """인사이트에서 후보를 만드는 **모든** growth 모듈이 닫기를 경유하는가.

    ★목록형 금지 — `growth/` 를 훑어 *"open 인사이트를 읽어 조치를 만드는"* 모듈을
    **파생**한다. 그래야 **세 번째 형제**가 생겼을 때 여기서 걸린다.
    (`#886` 이 L0 만 고치고 L1 을 놓친 것이 정확히 이 락의 부재 때문이다.)
    """
    offenders: list[str] = []
    population: list[str] = []
    for path in sorted(_GROWTH.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        reads_open = ("FROM platform_insights" in src and "status='open'" in src)
        builds_actions = "candidates.append(" in src
        if not (reads_open and builds_actions):
            continue
        population.append(path.name)
        if "mark_insight_acted" not in src:
            offenders.append(path.name)

    # 공허한 참 방지 — 모집단이 비면 이 락은 아무것도 안 본다
    assert len(population) >= 2, f"모집단이 {population} — 파생이 죽었다"
    assert {"healing_rules.py", "feature_flags.py"} <= set(population), population
    assert not offenders, f"open 인사이트로 조치를 만들면서 닫지 않는 모듈: {offenders}"


# ── 픽스처 ─────────────────────────────────────────────────────────────

from datetime import UTC, datetime  # noqa: E402

_NOW = datetime(2026, 8, 27, 9, 0, 0, tzinfo=UTC)


class _Result:
    def __init__(self, rows=(), scalar=0):
        self._rows, self._scalar = rows, scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class _QualityDropDB:
    """`quality_drop` 한 행이 게이트를 넘는 상태를 만든다(그 외 질의는 빈 결과)."""

    def __init__(self, insight_id: str = "11111111-1111-1111-1111-111111111111",
                 *, metrics: dict | None = None):
        self.insight_id = insight_id
        # ★기본은 게이트를 **넘는** 값. `metrics` 로 **경계 아래** 모집단을 만든다.
        self.metrics = metrics or {
            "down_pct": 90.0, "feedback_total": 20, "verify_total": 20,
            "service": "site_analysis",
        }

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        if "SELECT id, metrics_json FROM platform_insights" in q:
            return _Result(rows=[(self.insight_id, self.metrics)])
        return _Result()

    async def commit(self):
        pass

    async def rollback(self):  # pragma: no cover
        pass


# ══════════════════════════════════════════════════════════════════════
# ★게이트가 실제로 판정하는가 — 픽스처가 **경계 근처**를 태우는가
#   (2026-08-28 · development-ai-01 이 질문으로 짚었다)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metrics", "want_applied", "why"),
    [
        ({"down_pct": ff.FEATURE_DISABLE_ERROR_PCT, "feedback_total": ff.FEATURE_MIN_SAMPLES,
          "verify_total": ff.FEATURE_MIN_SAMPLES, "service": "site_analysis"},
         1, "경계 **위**(>= 이므로 같은 값은 발화한다)"),
        ({"down_pct": ff.FEATURE_DISABLE_ERROR_PCT - 0.1, "feedback_total": ff.FEATURE_MIN_SAMPLES,
          "verify_total": ff.FEATURE_MIN_SAMPLES, "service": "site_analysis"},
         0, "품질저하가 임계 **바로 아래**"),
        # ★게이트는 **합**이다: `(feedback_total + verify_total) >= FEATURE_MIN_SAMPLES`.
        #   처음에 각각 `-1`(9와 9 = 합 18)로 썼다가 **실패했다** — 내가 계약을 잘못 읽었다.
        #   픽스처 주석도 "표본 >= 10" 이라고만 적혀 있어 **합인지 각각인지 말하지 않았다.**
        ({"down_pct": 90.0, "feedback_total": ff.FEATURE_MIN_SAMPLES, "verify_total": 0,
          "service": "site_analysis"},
         1, "표본 합이 **정확히 하한**(>= 이므로 발화한다)"),
        ({"down_pct": 90.0, "feedback_total": ff.FEATURE_MIN_SAMPLES - 1, "verify_total": 0,
          "service": "site_analysis"},
         0, "표본 합이 하한 **한 칸 아래**"),
    ],
    ids=["경계값", "품질_한칸_아래", "표본합_경계", "표본합_한칸_아래"],
)
async def test_the_gate_decides_at_the_boundary(monkeypatch, metrics, want_applied, why):
    """★**분쟁 대역을 태운다** — 픽스처가 경계에서 멀면 상수를 0 으로 바꿔도 초록이다.

    실측(2026-08-28): 종전 픽스처는 `down_pct=90.0 · 표본 20` 이라
    `FEATURE_DISABLE_ERROR_PCT` 를 **40.0 → 0.0**, `FEATURE_MIN_SAMPLES` 를 **10 → 0**
    으로 바꿔도 **둘 다 SURVIVED** 였다. 게이트가 잠겨 있지 않았다.

    ★기대값을 **상수에서 파생**시킨다 — 리터럴 40.0/10 을 쓰면 상수를 바꿀 때
      기대값이 따라오지 않아 **다른 모집단을 재게 된다**.
    ★★**그런데 파생만 하면 상수 자체는 안 잠긴다** — 상수를 낮추면 픽스처와 기대값이
      **같이 움직여** 이 테스트가 초록이다(실측: 40.0→0.0 · 10→0 **둘 다 SURVIVED**).
      **파생(경계를 따라가게)과 못 박기(값을 낮추지 못하게)는 다른 락이다** —
      아래 `test_the_gate_constants_are_pinned` 가 그 나머지 반쪽이다.
    ★그리고 이 축은 **닫기와 이어져 있다**: 게이트가 무너지면 조치가 남발되고
      그만큼 인사이트가 **부당하게 닫힌다.**
    """
    rec = _Recorder()
    monkeypatch.setattr(healing_rules, "mark_insight_acted", rec)

    async def _guards(_db, _k, _t, _n):
        return 0, 0, None
    monkeypatch.setattr(healing_rules, "_guard_counts", _guards)

    async def _apply(_db, feature, *, enabled, error_pct=None, trigger_key=None):
        return {"applied": True, "action_id": "a1", "setting_key": f"feature.{feature}"}
    monkeypatch.setattr(ff, "apply_feature_toggle", _apply)

    out = await ff.evaluate(_QualityDropDB(metrics=metrics), now=_NOW)
    assert out["applied"] == want_applied, f"{why}: {out}"
    # ★닫기도 같이 갈려야 한다 — 발화하지 않았으면 아무것도 닫히지 않는다
    assert out["closed"] == want_applied, f"{why}: closed={out['closed']}"
    assert len(rec.calls) == want_applied, f"{why}: calls={rec.calls}"


def test_the_gate_constants_are_pinned() -> None:
    """★게이트 상수를 **리터럴로 못 박는다** — 파생형 락의 나머지 반쪽.

    위 경계 테스트는 상수에서 기대값을 파생시키므로 **상수를 낮추면 함께 움직여** 초록이다
    (실측 2026-08-28: `FEATURE_DISABLE_ERROR_PCT` 40.0→0.0 · `FEATURE_MIN_SAMPLES` 10→0
    **둘 다 SURVIVED**). 자기지시적 기대값은 **모집단과 함께 깎인다.**

    ★**이 하한이 지키는 것**: 이 값이 낮아지면 **표본 없는 상태에서 프로덕션 피처가
      자동으로 꺼진다.** 이 저장소는 *"트래픽 0인 스택이 프로덕션 임계를 바꿨다"* 는
      사고 기록을 이미 갖고 있다. 목표 수치를 맞추려고 **하한을 내리는 것**이 언제나
      가장 먼저 떠오르는 길이므로, 그 길을 기계가 막는다.

    바꿔야 할 근거가 생기면 **이 단언을 함께 고치고 그 근거를 여기 적는다**(그게 요점이다).
    """
    assert ff.FEATURE_DISABLE_ERROR_PCT == 40.0, "오류율 임계를 낮추면 정상 변동에도 피처가 꺼진다"
    assert ff.FEATURE_MIN_SAMPLES == 10, "표본 하한을 낮추면 표본 없는 상태에서 자동 비활성이 발화한다"
