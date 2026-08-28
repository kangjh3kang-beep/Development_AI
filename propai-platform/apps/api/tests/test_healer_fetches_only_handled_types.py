"""치유 후보 조회가 **처리하지 못하는 타입까지 슬롯을 먹었다**.

## 관측 (라이브 2026-08-27)

`_candidate_actions` 는 `recommended_action IN ('heal','none','correct')` 로만 걸러
`LIMIT 200` 을 채우는데, 아래 `for` 루프는 **두 타입에만 분기**를 갖는다.

    open 인사이트 구성:  latency_baseline 76.2% + latency_regression 21.0% = **97.2%**
    latency_regression 은 `recommended_action='heal'` 을 낸다 (`analyzer.py:846`)
    그런데 `_candidate_actions` 에 그 분기가 **없다**

★`'none'` 도 종전 WHERE 를 통과하므로 **사유로는 못 막는다 — 타입으로만 막힌다.**

## 왜 위험한가 — 조용한 기아

잡음이 슬롯을 채우면 진짜 후보가 200 밖으로 밀린다. 그런데 **한 배치의 `created_at` 이
하나**라(라이브 실측: 배치당 17~34행이 같은 타임스탬프) **어느 200 이 남는지가 임의**가 된다.
잘려 나간 행은 **로그도 없다.**

## ★이 파일의 핵심 — 선언은 스스로 옳음을 보증하지 않는다

`HANDLED_INSIGHT_TYPES` 는 **손으로 적은 목록**이다. 목록은 곧 상한이 된다.
그래서 `ast` 로 `_candidate_actions` 의 `itype == "..."` 비교를 **전부 뽑아** 대조한다.
분기를 추가하고 상수에 안 적으면(또는 그 반대면) **빨개진다.**
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import textwrap

from app.services.growth import healing_rules as H


def _fn_ast(fn) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]


def _branch_types() -> set[str]:
    """`_candidate_actions` 안에서 분기되는 `itype` 값을 **파서로** 뽑는다.

    ★**인식하지 못하는 형태를 만나면 조용히 빠지지 않고 예외를 던진다.**
      독립 리뷰(2026-08-27)가 등가 분기 **7형태 중 6개**를 이 추출기가 놓치는 것을 실증했다
      (`in (...)` · 좌우 교환 · `match/case` · dict 디스패치 · `startswith` · 상수 참조).
      놓치면 **락은 초록인데 SQL 이 그 타입을 모집단에서 빼므로 새 분기가 죽은 코드**가 된다
      — 이 PR 이 고친다고 선언한 「조용한 기아」가 락의 사각으로 되돌아온다.
      → **전 형태를 지원하는 것보다 「모르면 실패」가 강하다**(수집기가 못 모은 것을 신고).
    """
    node = _fn_ast(H._candidate_actions)
    recognized: set[str] = set()
    seen_loads = 0
    accounted = 0
    for sub in ast.walk(node):
        # `itype` 의 **모든 읽기 사용**을 센다
        if isinstance(sub, ast.Name) and sub.id == "itype" and isinstance(sub.ctx, ast.Load):
            seen_loads += 1
        if isinstance(sub, ast.Compare) and isinstance(sub.left, ast.Name) \
                and sub.left.id == "itype":
            for op, cmp in zip(sub.ops, sub.comparators, strict=False):
                if isinstance(op, ast.Eq) and isinstance(cmp, ast.Constant) \
                        and isinstance(cmp.value, str):
                    recognized.add(cmp.value)
                    accounted += 1
    if seen_loads != accounted:
        raise AssertionError(
            f"★추출기가 모르는 `itype` 분기 형태가 있다(읽기 {seen_loads}회 중 "
            f"인식 {accounted}회). `in (...)`·`match`·dict 디스패치·좌우 교환·상수 참조 등이면 "
            "이 추출기를 넓히거나 그 형태를 쓰지 마라 — 조용히 통과시키지 않는다.")
    return recognized


def _candidate_sql() -> str:
    """`_candidate_actions` 의 `text(...)` **문자열 상수**만 파서로 꺼낸다.

    ★`inspect.getsource()` 는 **주석을 포함한 원본 텍스트**를 준다. 그래서 문자열 검사로
      배선을 잠그면 **질의 줄을 주석 처리해도 초록**이다(독립 리뷰가 3종 전부 실증).
      ★이 파일의 다른 독스트링이 *"판정은 파서로"* 라고 적어 놓고 **배선 락에는 적용하지
      않았던** 것이 그 결함이다(§D-20: 처방을 적용한 범위 = 결함이 사는 범위인지 확인하라).
      AST 는 주석을 **노드로 만들지 않으므로** 구조적으로 안 걸린다.
    """
    node = _fn_ast(H._candidate_actions)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "text" \
                and sub.args and isinstance(sub.args[0], ast.Constant) \
                and isinstance(sub.args[0].value, str) \
                and "platform_insights" in sub.args[0].value:
            return sub.args[0].value
    raise AssertionError("후보 조회의 text(...) SQL 상수를 못 찾았다 — 파서가 죽었다")


def _handled_param_sources() -> set[str]:
    """`db.execute(...)` 의 파라미터 dict 에서 `handled` 값이 참조하는 **이름들**."""
    node = _fn_ast(H._candidate_actions)
    names: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Dict):
            continue
        for k, v in zip(sub.keys, sub.values, strict=False):
            if isinstance(k, ast.Constant) and k.value == "handled":
                names |= {n.id for n in ast.walk(v) if isinstance(n, ast.Name)}
    return names


def test_declared_handled_types_match_the_actual_branches():
    """★선언 ↔ 생산자 **정합**. 둘 중 하나만 바뀌면 빨개진다."""
    branches = _branch_types()
    assert branches, "분기를 하나도 못 찾았다 — 파서가 죽었다(공허한 참 방지)"
    assert set(H.HANDLED_INSIGHT_TYPES) == branches, (
        f"선언={sorted(H.HANDLED_INSIGHT_TYPES)} 실제분기={sorted(branches)}")


def test_the_query_actually_filters_by_type():
    """★배선 — 상수만 선언하고 질의에 안 태우면 아무것도 안 고쳐진다.

    ★**판정을 파서로 한다.** 문자열 검사였을 때는 질의 줄을 **주석 처리해도 초록**이었다
      (독립 리뷰 실증). `_candidate_sql()` 은 `text(...)` 의 문자열 상수만 꺼내므로
      주석은 애초에 대상이 아니다.
    """
    sql = _candidate_sql()
    assert "insight_type = ANY(:handled)" in sql, "타입 필터가 질의에 없다"
    assert "recommended_action IN ('heal','none','correct')" in sql, "사유 필터가 사라졌다"
    assert "HANDLED_INSIGHT_TYPES" in _handled_param_sources(), \
        "handled 파라미터가 상수를 경유하지 않는다(리터럴 하드코딩)"


def test_order_by_has_an_id_tiebreaker():
    """★배치당 `created_at` 이 하나라, 타이브레이커가 없으면 **어느 200 이 남는지가 임의**다.

    형제 `insight_retention._build_select` 는 이미 `created_at DESC, id DESC` 다 —
    옳은 패턴이 옆에 있었다.
    """
    assert "ORDER BY created_at DESC, id DESC" in _candidate_sql()


def test_latency_types_are_not_fetched():
    """★음성 모집단 — open 의 97% 를 차지하는 그 둘이 **모집단에서 빠져야** 한다.

    이게 없으면 "전부 통과시키는" 구현도 위 정합 테스트를 통과한다
    (상수에 latency 를 적고 분기도 추가하면 정합은 맞는다).
    """
    for noisy in ("latency_regression", "latency_baseline"):
        assert noisy not in H.HANDLED_INSIGHT_TYPES, (
            f"{noisy} 가 후보 모집단에 들어 있다 — 분기가 없다면 슬롯만 먹는다")


def test_handled_types_are_literals():
    """자기 상수 단언 금지 — 리터럴로 못 박는다."""
    assert H.HANDLED_INSIGHT_TYPES == ("fallback_rate", "stale_reanalysis")


def test_recommended_action_filter_is_kept_too():
    """★타입 필터가 사유 필터를 **대체하지 않는다** — 둘 다 있어야 한다.

    한쪽만 남기면 반대 방향(같은 타입인데 조치 대상이 아닌 행)이 무제한이 된다.
    """
    assert "recommended_action IN ('heal','none','correct')" in _candidate_sql()
