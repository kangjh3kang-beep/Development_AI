"""자가검증 표면의 👎 가 **서술기능을 자동으로 끄는 경로**로 들어가지 않는다.

## 왜 (2026-09-12 실측)

`apps/web/eslint.config.mjs` 가 자가검증 표면에 피드백 위젯 임포트를 **빌드로 금지**하면서
이유를 적어 두었다 — 👎 → `quality_drop` → **`llm_narrative` 자동 비활성** 이라
*"값이 이상하다고 알려줄수록 그걸 설명하는 기능이 먼저 꺼지는"* **뒤집힌 루프**가 된다.
그리고 이렇게 덧붙였다:

> **지금 이 사고가 안 나는 유일한 이유는 `VerificationBadge` 가 `service` 를 넘기지 않아서인데,
> 그건 「우연한 차단」이지 설계된 격리가 아니다(집계 쿼리에 출처 필터 자체가 없다).**

★그 마지막 괄호를 **실측으로 확인했다**: `ai_feedback` 을 `service` 키로 읽는 **4곳 전부**가
  `target_type` 을 **한 번도 언급하지 않았다**(대조군: 같은 파일들이 `service` 를 42~58회 언급).

## ★이 파일이 잠그는 것 — 「전부 제외」가 아니라 「자동만 제외」

처방을 결함보다 넓게 걸면 **신호를 버린다**. 자가검증 표면의 👎 는 **사람이 보는 축에는
계속 들어가야** 한다. 끊는 것은 «사람 개입 없이 기능을 끄는» 한 갈래뿐이다.
⇒ 자동 경로에는 제외가 **있고**, 사람 게이트 경로에는 **없다** — 둘을 **같은 실행에서** 대조한다.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from app.routers import growth as R
from app.services.growth import analyzer as A
from app.services.growth import feature_flags as FF
from app.services.growth import feedback_scope as FS
from app.services.growth import improvement_agent as IA
from app.services.growth import learning_loop as LL

#: 사람 게이트 경로(제외가 **없어야** 한다 — 신호를 버리지 않는다)
_HUMAN = {
    "learning_loop.compute_down_rates": LL.compute_down_rates,
    "improvement_agent._failure_samples": IA._failure_samples,
}


def _feedback_sql(fn) -> str:
    """함수 안의 `text(...)` 문자열 상수 중 `ai_feedback` 을 읽는 것.

    ★**파서로 뽑는다** — 문자열 검사였으면 그 줄을 **주석 처리해도 초록**이다
      (형제 `test_healer_fetches_only_handled_types` 가 그 실증을 기록해 두었다).
    """
    node = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "text" \
                and sub.args:
            parts = [c.value for c in ast.walk(sub.args[0])
                     if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            sql = "".join(parts)
            if "ai_feedback" in sql:
                return sql
    raise AssertionError(f"{fn.__name__}: ai_feedback 질의를 못 찾았다 — 파서가 죽었다")


def _param_sources(fn, param: str) -> set[str]:
    """`db.execute(...)` 파라미터 dict 에서 `param` 이 참조하는 **이름들**."""
    node = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    names: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Dict):
            continue
        for k, v in zip(sub.keys, sub.values, strict=False):
            if isinstance(k, ast.Constant) and k.value == param:
                names |= {n.id for n in ast.walk(v) if isinstance(n, ast.Name)}
                names |= {a.attr for a in ast.walk(v) if isinstance(a, ast.Attribute)}
    return names


# ── ★두 갈래가 갈린다(공허 방지 선단언 포함) ────────────────────────────────

def test_automatic_path_excludes_the_self_verification_surface() -> None:
    """자동 효과기 경로에는 제외가 **있다**."""
    sql = _feedback_sql(A._analyze_quality_drop)
    # ★공허 방지 — 이 질의가 정말 우리가 겨눈 그 집계인가.
    assert "GROUP BY service" in sql and "verdict='down'" in sql, sql
    assert "target_type <> ALL(:excl_targets)" in sql, (
        "quality_drop 집계에 출처 필터가 없다 — 자가검증 👎 가 서술기능 자동 비활성으로 간다"
    )
    assert "auto_effector_excluded" in _param_sources(A._analyze_quality_drop, "excl_targets"), \
        "제외 목록이 정본을 경유하지 않는다(리터럴 하드코딩)"


def test_feature_flag_adoption_also_excludes_it() -> None:
    """버전 **자동 채택**도 같은 갈래다 — 형제를 빠뜨리지 않는다(전역 §6)."""
    src = Path(inspect.getfile(FF)).read_text(encoding="utf-8")
    # ★파일 축으로 보되 **실행 줄만** 본다(주석·독스트링에 뚫리지 않게 ast 로 문자열 상수만).
    lits = [n.value for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    joined = "".join(lits)
    assert "FROM ai_feedback " in joined, "feature_flags 가 ai_feedback 을 안 읽는다(파서 사망)"
    assert "target_type <> ALL(:excl_targets)" in joined, \
        "버전 자동 채택 집계에 출처 필터가 없다"


def test_human_gated_paths_are_left_alone() -> None:
    """★**처방을 결함보다 넓게 걸지 않는다** — 사람이 보는 축에는 신호가 그대로 들어간다.

    이 단언이 없으면 «전부 제외» 구현도 위 두 테스트를 통과한다(그러면 자가검증 표면의
    👎 가 **어디에서도 안 보이게** 된다 — 수집만 하고 버리는 종전 상태로 되돌아간다).
    """
    for name, fn in _HUMAN.items():
        sql = _feedback_sql(fn)
        assert "ai_feedback" in sql, f"{name}: 공허 — 질의를 못 찾았다"
        assert "excl_targets" not in sql, (
            f"{name}: 사람 게이트 경로까지 제외가 걸렸다 — 신호를 버린다"
        )


# ── 어휘·전제 ────────────────────────────────────────────────────────────────

def test_excluded_targets_are_pinned_to_literals() -> None:
    """★**계약 어휘는 리터럴로 못 박는다**(내부 구현 상수는 심볼로 둔다).

    소비처가 이 값을 **문자열로** SQL 파라미터에 싣는다. 락이 심볼만 비교하면 값을 바꿔도
    **양쪽이 함께 움직여 원리적으로 판별 불가**다 — 2026-09-12 기계 변이가 형제 자리에서
    정확히 그 구멍을 짚었다(코드 문자열 변경 3건 생존 → 리터럴 핀 후 CAUGHT).
    """
    assert FS.AUTO_EFFECTOR_EXCLUDED_TARGETS == ("analysis",)
    # ★`sorted(...)` 로 비교한다 — `frozenset({...})` 과의 직접 비교는 ruff SIM300 에 걸리고,
    #   정렬 리스트가 **읽기도 더 쉽다**(어휘 전수가 한눈에 보인다).
    assert sorted(FS.FEEDBACK_TARGET_TYPES) == ["analysis", "llm_output", "recommendation"]


def test_excluded_targets_are_within_the_closed_vocabulary() -> None:
    """제외 대상이 **실재하는 출처**여야 한다 — 오타면 아무것도 제외되지 않는다(조용히)."""
    assert FS.AUTO_EFFECTOR_EXCLUDED_TARGETS, "제외 집합이 비었다(공허한 참)"
    assert set(FS.AUTO_EFFECTOR_EXCLUDED_TARGETS) <= FS.FEEDBACK_TARGET_TYPES, (
        f"닫힌 어휘 밖: {set(FS.AUTO_EFFECTOR_EXCLUDED_TARGETS) - FS.FEEDBACK_TARGET_TYPES}"
    )


def test_router_delegates_to_the_canonical_vocabulary() -> None:
    """★손목록이 되살아나지 않는다 — **같은 객체**여야 한다(값만 같으면 갈린다)."""
    assert R._FEEDBACK_TARGET_TYPES is FS.FEEDBACK_TARGET_TYPES


def test_target_type_is_not_null_so_the_filter_drops_nothing() -> None:
    """★`<> ALL` 은 **NULL 행을 조용히 버린다** — 그 전제를 DDL 원문으로 잠근다.

    컬럼이 nullable 로 바뀌면 이 필터가 **의도하지 않은 행까지** 제외하게 되므로
    여기서 빨개져야 한다.
    """
    from app.services.growth import schema_guard

    ddl = Path(inspect.getfile(schema_guard)).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS ai_feedback" in ddl, "DDL 을 못 찾았다(파서 사망)"
    assert "target_type text NOT NULL" in ddl, (
        "ai_feedback.target_type 이 NOT NULL 이 아니다 — `<> ALL` 이 NULL 행을 버린다"
    )
