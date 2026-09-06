"""분석기의 **처방**과 치유기의 **처리**가 갈리지 않는지 잠근다.

★왜(2026-09-06 라이브 실측 · sid=0a08a179):
  분석기는 `latency_regression` 에 `recommended_action="heal"` 을 실어 발행하는데,
  치유기의 후보 쿼리는 `insight_type = ANY(HANDLED_INSIGHT_TYPES)` 로 거른다.
  `HANDLED_INSIGHT_TYPES` 에 그 타입이 **없다** → **원리적으로 도달 불가**.
  라이브에 열린 `latency_regression` 이 **22건** 쌓여 있었고(최신 2026-09-05T22:05:05Z),
  열린 인사이트 126건 중 **치유기가 분기를 가진 것은 0건**이었다.
  그런데 그것을 말해 주는 기계가 **하나도 없었다** — 좁힌 사유는 산문 주석뿐이었다.

★그리고 그 산문은 **이미 낡아 있었다**: 주석이 `analyzer.py:846` 을 가리키는데
  현재 846 은 `"none"` 이고 실제 자리는 **1064** 다. **주석을 인용하지 말고 파생하라** —
  이 락이 정확히 그것을 한다.

★이 락은 **처방을 강제하지 않는다.** 「분기를 갖거나, 사유를 적고 면제하거나」 둘 중
  하나를 강제할 뿐이다. 치유를 붙일지는 사람의 판단이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.growth.healing_rules import (
    HANDLED_INSIGHT_TYPES,
    HEAL_UNHANDLED_REASONS,
)

_GROWTH = Path(__file__).resolve().parents[1] / "app" / "services" / "growth"
_ANALYZER = _GROWTH / "analyzer.py"
_HEALING = _GROWTH / "healing_rules.py"

#: 분석기가 발행하는 (insight_type, recommended_action) 쌍의 **하한**.
#  ★공허 진리 가드: 파서가 모집단을 자르면 「위반 0」이 조용히 참이 된다.
#  2026-09-06 실측 7종. 하한을 5로 두어 서너 종이 사라져도 알아채게 한다.
_MIN_EMIT_SITES = 5

#: 한 발행 자리에서 함께 풀 공유 자유변수 상한(2^n 폭발 방지). 실측상 1개면 충분하다.
_MAX_SHARED_VARS = 4


def _string_constants(node: ast.AST) -> set[str]:
    """표현식 안의 문자열 상수를 전부 모은다(마지막 수단의 보수적 근사)."""
    return {
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _free_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _truth(test: ast.AST, env: dict[str, bool]) -> bool | None:
    """조건의 진리값. 모르면 None(= 양쪽 가지 다 가능)."""
    if isinstance(test, ast.Name):
        return env.get(test.id)
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _truth(test.operand, env)
        return None if inner is None else (not inner)
    return None


def _eval_strings(expr: ast.AST, env: dict[str, bool], funcs: dict) -> set[str]:
    """`env` 아래에서 이 표현식이 낼 수 있는 문자열 집합.

    ★핵심: `insight_type` 과 `recommended_action` 은 **같은 자유변수**(예: `sev`)를
      공유한다. 따로 풀면 `insight_type_for_latency` 의 **두 반환값을 다** 끌어와
      `latency_baseline`(실제로는 `"none"`)까지 heal 로 세는 **위양성**이 난다 —
      2026-09-06 이 락을 처음 돌렸을 때 실제로 그렇게 났고, 락이 그것을 잡았다.
      그래서 **같은 `env` 를 두 표현식에 함께** 먹인다.
    """
    if isinstance(expr, ast.Constant):
        return {expr.value} if isinstance(expr.value, str) else set()
    if isinstance(expr, ast.IfExp):
        t = _truth(expr.test, env)
        if t is True:
            return _eval_strings(expr.body, env, funcs)
        if t is False:
            return _eval_strings(expr.orelse, env, funcs)
        return _eval_strings(expr.body, env, funcs) | _eval_strings(expr.orelse, env, funcs)
    if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.Or):
        out: set[str] = set()
        for v in expr.values:
            out |= _eval_strings(v, env, funcs)
        return out
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
        fn = funcs.get(expr.func.id)
        if fn is not None:
            # 인자를 파라미터 이름에 **진리값으로** 묶어 함수 몸통을 같은 env 로 편다.
            inner = dict(env)
            for param, arg in zip(fn.args.args, expr.args):
                inner[param.arg] = _truth(arg, env)  # type: ignore[assignment]
            out = set()
            for n in ast.walk(fn):
                if isinstance(n, ast.Return) and n.value is not None:
                    out |= _eval_strings(n.value, inner, funcs)
            return out
    return _string_constants(expr)


def _heal_emitting_types() -> tuple[set[str], int]:
    """분석기가 `recommended_action` 에 `"heal"` 을 낼 수 있는 insight_type 집합.

    두 표현식의 **공유 자유변수**에 대해 {참, 거짓} 을 전부 대입해, **같은 대입에서**
    `recommended_action` 이 `"heal"` 이 되는 경우의 `insight_type` 만 모은다.

    반환: (타입 집합, 발행 자리 총수 — 공허 진리 가드용)
    """
    tree = ast.parse(_ANALYZER.read_text(encoding="utf-8"))
    funcs = _module_functions(tree)
    heal_types: set[str] = set()
    sites = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keyed: dict[str, ast.AST] = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keyed[k.value] = v
        if "insight_type" not in keyed or "recommended_action" not in keyed:
            continue
        sites += 1
        it_expr, ra_expr = keyed["insight_type"], keyed["recommended_action"]
        shared = sorted(_free_names(it_expr) & _free_names(ra_expr))[:_MAX_SHARED_VARS]
        assignments: list[dict[str, bool]] = [{}]
        for name in shared:
            assignments = [{**a, name: b} for a in assignments for b in (True, False)]
        for env in assignments:
            if "heal" in _eval_strings(ra_expr, env, funcs):
                heal_types |= _eval_strings(it_expr, env, funcs)
    return heal_types, sites


# ════════════════════════════════════════════════════════════════════════════
# ① 공허 진리 가드 — 파서가 모집단을 자르면 **판정 자체를 실패**시킨다
# ════════════════════════════════════════════════════════════════════════════

def test_derivation_population_is_not_truncated() -> None:
    """모집단이 하한 미만이면 아래 단언들이 전부 공허해진다 → 여기서 먼저 죽는다.

    ★2026-09-06 에 두 세션의 파서가 **반대 부호**로 틀렸다(튜플 미인식 → 거짓 빨강 /
      AnnAssign 미인식 → 41/58 만 읽고 거짓 초록). **읽은 수를 단언하지 않으면
      「위반 0」과 「아무것도 안 읽음」이 같은 모양**이다.
    """
    _, sites = _heal_emitting_types()
    assert sites >= _MIN_EMIT_SITES, (
        f"분석기에서 (insight_type, recommended_action) 쌍을 {sites}자리만 찾았다"
        f"(하한 {_MIN_EMIT_SITES}). 파서가 모집단을 잘랐거나 발행부가 사라졌다 — **판정 불가**."
    )


def test_at_least_one_type_actually_prescribes_heal() -> None:
    """`heal` 을 내는 타입이 0이면 아래 정합 단언이 **원리적으로 위반 불가**가 된다."""
    heal_types, _ = _heal_emitting_types()
    assert heal_types, "분석기가 `recommended_action='heal'` 을 내는 자리를 0건 찾았다 — 판정 불가."


# ════════════════════════════════════════════════════════════════════════════
# ② 탐지 — 처방됐는데 처리도 면제도 없는 타입이 있으면 실패
# ════════════════════════════════════════════════════════════════════════════

def test_every_heal_prescription_is_handled_or_exempted_with_a_reason() -> None:
    heal_types, _ = _heal_emitting_types()
    known = set(HANDLED_INSIGHT_TYPES) | set(HEAL_UNHANDLED_REASONS)
    orphan = sorted(heal_types - known)
    assert not orphan, (
        f"분석기가 `recommended_action='heal'` 로 발행하는데 치유기가 분기도 면제도 갖지 않는 "
        f"타입: {orphan}. 후보 쿼리가 `insight_type = ANY(HANDLED_INSIGHT_TYPES)` 로 거르므로 "
        f"이 인사이트는 **원리적으로 치유기에 도달하지 못하고 영원히 open 으로 남는다.** "
        f"분기를 추가하거나, `HEAL_UNHANDLED_REASONS` 에 **사유를 적어** 면제하라."
    )


def test_exemption_reasons_are_substantive() -> None:
    """사유가 빈 문자열이면 면제가 아니라 침묵이다."""
    for t, why in HEAL_UNHANDLED_REASONS.items():
        assert isinstance(why, str) and len(why.strip()) >= 30, (
            f"`{t}` 의 면제 사유가 너무 짧다({why!r}). "
            f"§36 — 면제에는 **왜 하지 않기로 했는지**를 적는다."
        )


# ════════════════════════════════════════════════════════════════════════════
# ③ 죽은 면제 — 더 이상 heal 을 안 내는데 면제표에 남아 있으면 실패
# ════════════════════════════════════════════════════════════════════════════

def test_no_dead_exemptions() -> None:
    heal_types, _ = _heal_emitting_types()
    dead = sorted(set(HEAL_UNHANDLED_REASONS) - heal_types)
    assert not dead, (
        f"면제표에 있는데 분석기가 더 이상 `heal` 을 내지 않는 타입: {dead}. "
        f"죽은 면제는 다음 사람에게 **아직 부채가 있다**고 거짓말한다 — 지워라."
    )


def test_exemption_and_handled_do_not_overlap() -> None:
    """분기가 있는데 면제까지 걸려 있으면 둘 중 하나가 거짓이다."""
    both = sorted(set(HANDLED_INSIGHT_TYPES) & set(HEAL_UNHANDLED_REASONS))
    assert not both, f"분기와 면제에 동시에 있는 타입: {both}"


# ════════════════════════════════════════════════════════════════════════════
# ④ 배선 — 상수만 단언하면 장식이다. 그 상수가 **실제로 후보 쿼리에 쓰이는지** 태운다
# ════════════════════════════════════════════════════════════════════════════

def test_handled_types_is_actually_wired_into_the_candidate_query() -> None:
    """`HANDLED_INSIGHT_TYPES` 가 `_candidate_actions` 안에서 실제로 소비되는지.

    ★소스 문자열 검색이 아니라 **AST 로 함수 몸통 안의 Name 참조**를 본다
      (주석·독스트링에 이름만 적혀 있어도 통과하는 것을 막는다).
    """
    tree = ast.parse(_HEALING.read_text(encoding="utf-8"))
    target = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_candidate_actions":
            target = n
            break
    assert target is not None, "`_candidate_actions` 를 찾지 못했다 — 판정 불가."
    names = {x.id for x in ast.walk(target) if isinstance(x, ast.Name)}
    assert "HANDLED_INSIGHT_TYPES" in names, (
        "`HANDLED_INSIGHT_TYPES` 가 `_candidate_actions` 에서 참조되지 않는다 — "
        "상수가 장식이 됐고, 이 파일의 다른 단언들은 전부 공허하다."
    )


# ════════════════════════════════════════════════════════════════════════════
# ⑤ 특이도 — 현재 코드는 통과해야 한다(가드가 정상 코드를 막으면 그것도 결함)
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("t", sorted(HANDLED_INSIGHT_TYPES))
def test_handled_types_are_nonempty_strings(t: str) -> None:
    assert isinstance(t, str) and t.strip()


def test_current_tree_is_green_end_to_end() -> None:
    """오늘 실측한 상태(=`latency_regression` 이 면제로 덮인 상태)가 통과하는지."""
    heal_types, sites = _heal_emitting_types()
    assert sites >= _MIN_EMIT_SITES
    assert "latency_regression" in heal_types, (
        "★기대한 결함 자리가 사라졌다 — `latency_regression` 이 더 이상 `heal` 을 내지 않는다면 "
        "면제표에서 지워야 한다(위 `test_no_dead_exemptions` 가 잡는다)."
    )
    assert not (heal_types - set(HANDLED_INSIGHT_TYPES) - set(HEAL_UNHANDLED_REASONS))
