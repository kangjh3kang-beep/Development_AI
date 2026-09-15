"""★채용 승인의 «멤버십 연결 사유» 가 **하나의 목록에서만** 나오는가 — AST 파생형.

## 왜 (2026-09-08 적대 리뷰 M2)

`_link_membership_on_accept` 는 `bool` 하나를 돌려줬고, **여섯 가지 상황이 같은 `False`** 였다:
적용대상 아님 · 권한 없음 · 조직도 미시드 · 조직 테이블 미존재 · (그리고 멱등 무변경).

조치가 전부 다르다. 특히 **`ORG_NOT_SEEDED` 는 해결 가능한 보류**인데
(조직도를 시드하고 다시 승인하면 된다), 라이브 현장 대부분이 조직도 미시드라
**그것이 기본 경로**였다. 승인자는 «승인은 됐는데 조직도엔 아무도 없다» 를 원인 없이 마주쳤다.

★게다가 화면은 그 `False` 마저 **읽지 않고 버렸다**(`.then(() => loadApps())`) — 소비처 0.
  저장소 규율: *"실패는 전용 필드로 자기를 구별하고, 사유를 표면까지 싣는다.
  진단 불가는 그 자체로 장애다."*

## 이 파일이 잠그는 것

1. 함수가 **실제로 내는** 사유가 전부 `_MEMBERSHIP_REASONS` 안에 있다 (AST — 문자열 grep 아님)
2. 목록의 모든 사유가 **어딘가에서 실제로 발화한다** (죽은 사유 금지)
3. `membership_linked` 는 사유에서 **파생**된다 — 두 값이 갈릴 수 없다

★2 번이 없으면 목록에 아무 이름이나 넣어도 초록이다 — «도달 불가능한 사유».
  이 저장소가 [사유가 도달하는가 ≠ 그 사유가 발생하는가] 로 이미 한 번 데인 자리다.

★**임포트가 아니라 AST 로** 판정한다: 이 라우터 모듈은 무거운 의존을 끌고 와
  개발 환경(python 3.10)에서 수집조차 안 된다. 임포트에 의존하면 이 락이
  **CI 에서만 도는 락**이 되고, 그건 재발이 로컬에서 조용해진다는 뜻이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_MARKET = Path(__file__).resolve().parents[1] / "app/api/endpoints/sales/market.py"
_FN = "_link_membership_on_accept"


def _tree() -> ast.Module:
    return ast.parse(_MARKET.read_text(encoding="utf-8"))


def _declared_reasons() -> list[str]:
    """`_MEMBERSHIP_REASONS` 튜플 리터럴 — 소스에서 파생한다."""
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_MEMBERSHIP_REASONS" for t in node.targets
        ):
            elts = getattr(node.value, "elts", [])
            return [e.value for e in elts if isinstance(e, ast.Constant)]
    raise AssertionError("`_MEMBERSHIP_REASONS` 선언을 찾지 못했다 — 사유 목록이 사라졌다")


def _returned_reasons() -> list[str]:
    """`_link_membership_on_accept` 가 **실행 중 돌려주는** 문자열 리터럴 전수."""
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == _FN:
            return [
                r.value.value
                for r in ast.walk(node)
                if isinstance(r, ast.Return)
                and isinstance(r.value, ast.Constant)
                and isinstance(r.value.value, str)
            ]
    raise AssertionError(f"`{_FN}` 을 찾지 못했다")


def test_population_is_not_empty() -> None:
    """★공허 진리 가드 — 파서가 죽으면 아래 «전부 포함» 이 «0개를 검사» 가 된다.

    대조군 없이 «위반 0» 을 말하지 않는다: 두 모집단의 **하한**을 먼저 못 박는다.
    """
    assert len(_declared_reasons()) >= 5
    assert len(_returned_reasons()) >= 5


def test_every_returned_reason_is_declared() -> None:
    """★함수가 내는 사유는 전부 목록 안에 있다 — 목록 밖 값은 프론트가 번역하지 못한다."""
    undeclared = sorted(set(_returned_reasons()) - set(_declared_reasons()))
    assert not undeclared, (
        f"`{_FN}` 이 목록에 없는 사유를 돌려준다: {undeclared}\n"
        "  ★프론트는 이 목록에서 문구를 파생하므로, 목록 밖 값은 «알 수 없음» 으로 떨어진다."
    )


def test_every_declared_reason_is_reachable() -> None:
    """★★**반대 방향** — 목록의 사유는 전부 **실제로 발화**한다(죽은 사유 금지).

    이것이 없으면 목록에 무엇을 넣어도 초록이라, 「사유를 나눴다」는 주장이 **선언**으로 끝난다.
    """
    tree = _tree()
    # 멱등 분기는 함수가 아니라 라우터(`decide_application`)의 dict 리터럴이 낸다.
    # ★단, **선언 튜플 자신**은 모집단에서 뺀다 — 넣으면 모든 사유가 자기 자신으로 도달돼
    #   이 검사가 원리적으로 통과한다(자기지시적 기대값).
    declared_node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_MEMBERSHIP_REASONS" for t in n.targets)
    )
    declared_ids = {id(c) for c in ast.walk(declared_node)}
    emitted = {
        c.value
        for c in ast.walk(tree)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in declared_ids
    }
    dead = sorted(set(_declared_reasons()) - emitted)
    assert not dead, (
        f"선언만 되고 아무도 내지 않는 사유: {dead}\n"
        "  ★사유를 늘리는 것은 공짜지만, 발화하지 않는 사유는 «나눴다» 는 착시만 만든다."
    )


def test_every_decide_response_carries_the_reason() -> None:
    """★★**응답 계약 락** — `decide_application` 의 **모든** 반환이 사유를 싣는가.

    ★기계 변이가 짚어 준 자리다(2026-09-08 · 60변이 중 생존 2건이 정확히 여기):

        "membership_reason": membership_reason}        → 문자열 변경 ::VERDICT=SURVIVED
        "membership_linked": False, "membership_reason": "IDEMPOTENT_NO_CHANGE"  → SURVIVED

    즉 **키 이름을 바꾸거나 멱등 분기의 사유를 지워도** 아무것도 빨개지지 않았다.
    프론트 테스트는 응답을 **목킹**하므로 백엔드의 실제 키를 태우지 않는다 —
    저장소가 여러 번 데인 «양쪽을 각각 잠갔는데 사이가 비었다» 그 자리.

    축은 **반환문**이다(파일도, 함수 존재도 아니다).
    """
    returns: list[dict[str, ast.expr]] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "decide_application":
            for r in ast.walk(node):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict):
                    returns.append({
                        k.value: v
                        for k, v in zip(r.value.keys, r.value.values, strict=False)
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    })
    # ★공허 진리 가드 — 반환을 하나도 못 찾으면 아래 루프가 통째로 안 돈다.
    assert len(returns) >= 2, f"`decide_application` 의 dict 반환을 {len(returns)}개만 찾았다"

    declared = set(_declared_reasons())
    for i, keys in enumerate(returns):
        assert "membership_reason" in keys, f"{i}번째 반환에 `membership_reason` 이 없다"
        assert "membership_linked" in keys, f"{i}번째 반환에 `membership_linked` 가 없다"
        val = keys["membership_reason"]
        if isinstance(val, ast.Constant):  # 상수로 박힌 분기(멱등 등)
            assert val.value in declared, (
                f"{i}번째 반환이 목록에 없는 사유를 박았다: {val.value!r}"
            )


def test_reject_does_not_claim_not_applicable() -> None:
    """★거절 경로가 «해당 없음» 이라고 **거짓말하지 않는가**.

    앞 판은 `membership_reason = "NOT_APPLICABLE"` 을 기본값으로 두어, **거절**에도
    «현장 비연계 공고라 멤버십이 생길 일이 없다» 는 뜻의 값이 실렸다.
    화면은 accept 일 때만 읽으니 안 보이지만, 로그·감사로 이 값을 보는 쪽에는 **틀린 답**이 남는다.
    """
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "decide_application":
            for a in ast.walk(node):
                if (
                    isinstance(a, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "membership_reason" for t in a.targets)
                    and isinstance(a.value, ast.Constant)
                ):
                    assert a.value.value == "DECLINED", (
                        f"거절 경로의 기본 사유가 {a.value.value!r} 다 — "
                        "«승인이 아니라 거절이다» 를 말해야 한다."
                    )
                    return
    raise AssertionError("거절 경로의 기본 사유 대입을 찾지 못했다 — 축이 죽었다")


def test_linked_flag_is_derived_from_reason() -> None:
    """★`membership_linked` 를 **손으로 계산하지 않는다** — 사유와 갈릴 수 없어야 한다.

    두 값을 각각 만들면 «linked=True 인데 reason=ORG_NOT_SEEDED» 같은 모순이 조용히 나간다.
    """
    src = _MARKET.read_text(encoding="utf-8")
    assert '"membership_linked": membership_reason in _LINKED_REASONS' in src, (
        "`membership_linked` 가 사유에서 파생되지 않는다 — 두 필드가 갈릴 수 있다."
    )
    # ★연결로 치는 집합이 선언 목록의 **부분집합**인가(오타 하나로 영원히 False 가 되는 것을 막는다).
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_LINKED_REASONS" for t in node.targets
        ):
            linked = {c.value for c in ast.walk(node) if isinstance(c, ast.Constant)}
            assert linked and linked <= set(_declared_reasons()), (
                f"`_LINKED_REASONS` 에 목록 밖 값이 있다: {sorted(linked - set(_declared_reasons()))}"
            )
            return
    raise AssertionError("`_LINKED_REASONS` 선언을 찾지 못했다")
