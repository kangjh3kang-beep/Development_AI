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

from app.services.growth import healing_rules as H


def _branch_types() -> set[str]:
    """`_candidate_actions` 안에서 실제로 분기되는 `itype` 값을 **파서로** 뽑는다.

    ★문자열 검사로 하면 이 파일의 설명 문장과 그 함수의 주석에 걸린다(오늘 실측으로
      같은 자리를 밟았다). **판정은 파서로.**
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(H._candidate_actions)))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Name) and left.id == "itype"):
            continue
        for op, cmp in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.Eq) and isinstance(cmp, ast.Constant) \
                    and isinstance(cmp.value, str):
                found.add(cmp.value)
    return found


def test_declared_handled_types_match_the_actual_branches():
    """★선언 ↔ 생산자 **정합**. 둘 중 하나만 바뀌면 빨개진다."""
    branches = _branch_types()
    assert branches, "분기를 하나도 못 찾았다 — 파서가 죽었다(공허한 참 방지)"
    assert set(H.HANDLED_INSIGHT_TYPES) == branches, (
        f"선언={sorted(H.HANDLED_INSIGHT_TYPES)} 실제분기={sorted(branches)}")


def test_the_query_actually_filters_by_type():
    """★배선 — 상수만 선언하고 질의에 안 태우면 아무것도 안 고쳐진다."""
    src = inspect.getsource(H._candidate_actions)
    assert "insight_type = ANY(:handled)" in src, "타입 필터가 질의에 없다"
    assert "HANDLED_INSIGHT_TYPES" in src, "질의가 상수를 경유하지 않는다(리터럴 하드코딩)"


def test_order_by_has_an_id_tiebreaker():
    """★배치당 `created_at` 이 하나라, 타이브레이커가 없으면 **어느 200 이 남는지가 임의**다.

    형제 `insight_retention._build_select` 는 이미 `created_at DESC, id DESC` 다 —
    옳은 패턴이 옆에 있었다.
    """
    src = inspect.getsource(H._candidate_actions)
    assert "ORDER BY created_at DESC, id DESC" in src


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
    src = inspect.getsource(H._candidate_actions)
    assert "recommended_action IN ('heal','none','correct')" in src
