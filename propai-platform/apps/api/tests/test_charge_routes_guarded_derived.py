"""파생형 락 — **과금하는 라우트는 전부 멱등 가드 안에 있어야 한다.**

## 왜 목록형이면 안 되는가

`test_registry_charge_idempotency_wiring.py` 는 `/registry/bulk` **하나만** 태운다. 나머지
세 경로(`get-one`·`analyze`·`survey/strategy`)는 코드로는 배선돼 있지만 **아무 락도 없다.**
누가 리팩터링하다 `async with charge_once(...)` 를 벗기면 조용히 이중청구로 돌아가고,
CI 는 초록이다. 그리고 **새 과금 라우트가 추가되면 아무도 목록을 갱신하지 않는다** —
이 저장소가 반복해서 데인 형태 그대로다(CLAUDE.md A4·D20).

그래서 대상을 **소스에서 파생**한다: "과금 헬퍼를 부르는 핸들러"를 전부 긁어와, 그 호출이
`charge_once` 블록 **안**에 있는지 본다. 새 과금 라우트가 생기면 **자동으로** 감시망에 든다.

## 왜 정규식이 아니라 AST 인가

주석·문자열에 뚫리지 않는다(CLAUDE.md A3). `async with` 의 **어휘적 포함관계**는 정규식으로
정확히 판정할 수 없다 — 들여쓰기를 세는 순간 틀린다.

## 면제 (있으면 **코드에 적는다** — 무증빙 면제 금지)

`_run_registry_job` 은 백그라운드 잡이라 요청 컨텍스트(`Request`·헤더)가 없다. 멱등 키를
받을 자리가 없으므로 가드를 걸 수 없다. **미보호가 맞고, 그 사실을 여기 적어 둔다.**
→ 후속: 제출 시점에 키를 선점하고 워커가 정산하는 형태가 필요하다(계획서 §11-4 ①).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROUTER = Path(__file__).resolve().parents[1] / "routers" / "registry.py"

# 과금을 실제로 집행하는 헬퍼(= 돈이 나가는 자리).
_CHARGE_FNS = {"_charge_registry_issue", "_charge_registry_analysis"}
# 가드 컨텍스트 매니저.
_GUARD = "charge_once"

# ★면제 — 이유를 **여기 적은 것만** 면제된다. 목록이 늘면 리뷰에서 보인다.
_EXEMPT = {
    # 백그라운드 잡: 요청 헤더가 없어 Idempotency-Key 를 받을 자리가 자체가 없다.
    "_run_registry_job": "백그라운드 잡 — 요청 컨텍스트 없음(후속: 제출 시 선점 + 워커 정산)",
}


def _guarded_ranges(fn: ast.AST) -> list[tuple[int, int]]:
    """함수 안의 `async with charge_once(...)` 블록들의 줄 범위."""
    out: list[tuple[int, int]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            call = item.context_expr
            name = ""
            if isinstance(call, ast.Call):
                f = call.func
                name = getattr(f, "id", "") or getattr(f, "attr", "")
            if name == _GUARD:
                out.append((node.lineno, node.end_lineno or node.lineno))
    return out


def _charging_handlers() -> dict[str, list[int]]:
    """과금 헬퍼를 호출하는 함수 → 그 호출들의 줄번호."""
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    found: dict[str, list[int]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        lines = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", "") or getattr(n.func, "attr", "")) in _CHARGE_FNS
        ]
        # 헬퍼 자신의 정의는 제외(자기 몸통 안의 billing 호출).
        if lines and fn.name not in _CHARGE_FNS:
            found[fn.name] = lines
    return found


def test_과금_라우트를_소스에서_파생한다():
    """공허 진리 가드 — 대상이 0개면 아래 단언이 전부 무의미하다."""
    handlers = _charging_handlers()
    assert len(handlers) >= 4, (
        f"과금 핸들러를 {len(handlers)}개밖에 못 찾았다 — 파서가 깨졌거나 라우터가 바뀌었다. "
        f"찾은 것={sorted(handlers)}"
    )


def test_과금하는_모든_핸들러가_멱등_가드_안에_있다():
    """★목록형이 아니다 — 새 과금 라우트가 생기면 자동으로 여기서 잡힌다."""
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    fns = {
        fn.name: fn
        for fn in ast.walk(tree)
        if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
    }

    unguarded: list[str] = []
    guarded: list[str] = []
    for name, call_lines in _charging_handlers().items():
        if name in _EXEMPT:
            continue
        ranges = _guarded_ranges(fns[name])
        outside = [ln for ln in call_lines if not any(a <= ln <= b for a, b in ranges)]
        (unguarded if outside else guarded).append(
            f"{name}(줄 {outside})" if outside else name
        )

    # 대조군 — 하나도 '가드됨'이 없으면 판정기가 죽은 것이다(전부 unguarded 로 몰림).
    assert guarded, f"가드된 핸들러가 0개다 — 판정기가 죽었다. unguarded={unguarded}"
    assert not unguarded, (
        "과금하는데 멱등 가드 밖에 있는 핸들러가 있다 — 재전송하면 이중청구된다:\n  "
        + "\n  ".join(unguarded)
        + f"\n(가드된 것: {sorted(guarded)})"
    )


def test_면제는_사유가_적혀_있어야_한다():
    """★무증빙 면제 금지 — 면제가 늘면 리뷰에서 보이게 한다."""
    for name, reason in _EXEMPT.items():
        assert reason.strip(), f"{name} 의 면제 사유가 비어 있다"
    assert set(_EXEMPT) <= set(_charging_handlers()), (
        "실제로 과금하지 않는 함수가 면제 목록에 있다(죽은 면제) — "
        f"{set(_EXEMPT) - set(_charging_handlers())}"
    )


@pytest.mark.parametrize("route_fn", sorted(_charging_handlers()))
def test_각_과금_핸들러_개별_판정(route_fn: str):
    """핸들러별로 갈라 놓아 **어느 것이 뚫렸는지** 실패 메시지에서 바로 보이게 한다."""
    if route_fn in _EXEMPT:
        pytest.skip(f"면제: {_EXEMPT[route_fn]}")
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    fn = next(
        f
        for f in ast.walk(tree)
        if isinstance(f, ast.AsyncFunctionDef | ast.FunctionDef) and f.name == route_fn
    )
    ranges = _guarded_ranges(fn)
    outside = [
        ln
        for ln in _charging_handlers()[route_fn]
        if not any(a <= ln <= b for a, b in ranges)
    ]
    assert not outside, f"{route_fn}: 줄 {outside} 의 과금 호출이 charge_once 밖에 있다"
