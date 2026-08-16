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

# ★★모집단은 **파일 하나가 아니라 라우터 전부**다.
#   초판은 `routers/registry.py` 만 봤다 — 함수는 파생했지만 **파일은 손으로 고른 목록(1개)** 이었다.
#   그건 이 락이 고치려던 결함 클래스 그 자체다(CLAUDE.md D20: 처방 범위 = 결함 범위인가).
#   실측: 과금 호출부는 **5개 파일 12개 함수**에 걸쳐 있었고, 초판은 그중 5개만 덮었다.
_API_ROOT = Path(__file__).resolve().parents[1]
_ROUTER_DIRS = (
    _API_ROOT / "routers",
    _API_ROOT / "app" / "routers",
    _API_ROOT / "app" / "api" / "endpoints",
)

# 과금을 실제로 집행하는 헬퍼(= 돈이 나가는 자리).
_CHARGE_FNS = {"charge_service", "_charge_registry_issue", "_charge_registry_analysis"}
# 가드 컨텍스트 매니저.
_GUARD = "charge_once"

# ★면제 — 이유를 **여기 적은 것만** 면제된다. 목록이 늘면 리뷰에서 보인다.
# ★면제 = **사유를 적은 것만**. 그리고 아래 대부분은 **설계가 아니라 부채**다 —
#   부채를 목록에 적어 두는 이유는 초록 안에서 보이게 하기 위해서다(CLAUDE.md C13).
#   배선하면 해당 줄을 지우면 된다. 새 과금 라우트가 생기면 면제에 없으므로 **자동으로 실패**한다.
_EXEMPT = {
    # ── 구조적 면제(배선 불가) ──
    "_run_registry_job": "백그라운드 잡 — 요청 컨텍스트가 없어 Idempotency-Key 를 받을 자리 자체가 없다"
                         "(후속: 제출 시 선점 + 워커 정산)",
    "charge": "명시 과금 엔드포인트(POST /billing/charge) — 사용자가 '청구하라'를 직접 부른다."
              " 재전송 안전이 필요하긴 하나 의미가 달라 별도 설계가 필요하다",
    # ── ★부채(배선 가능한데 아직 안 함) — 재전송하면 이중청구된다 ──
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


def _router_sources() -> list[tuple[str, str]]:
    """라우터 소스를 **디렉토리에서 파생**한다(파일 목록을 손으로 적지 않는다)."""
    out: list[tuple[str, str]] = []
    for d in _ROUTER_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.py")):
            if "__pycache__" in str(f):
                continue
            out.append((str(f.relative_to(_API_ROOT)), f.read_text(encoding="utf-8")))
    return out


def _charging_handlers() -> dict[str, list[int]]:
    """과금 헬퍼를 호출하는 함수 → 그 호출들의 줄번호(라우터 전역)."""
    found: dict[str, list[int]] = {}
    for _rel, src in _router_sources():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
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


def _fn_nodes() -> dict[str, ast.AST]:
    """이름 → 함수 노드(라우터 전역)."""
    out: dict[str, ast.AST] = {}
    for _rel, src in _router_sources():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
                out.setdefault(fn.name, fn)
    return out


def test_과금_라우트를_소스에서_파생한다():
    """공허 진리 가드 — 대상이 0개면 아래 단언이 전부 무의미하다."""
    handlers = _charging_handlers()
    assert len(handlers) >= 10, (
        f"과금 핸들러를 {len(handlers)}개밖에 못 찾았다 — 파서가 깨졌거나 라우터가 바뀌었다. "
        f"찾은 것={sorted(handlers)}"
    )


def test_과금하는_모든_핸들러가_멱등_가드_안에_있다():
    """★목록형이 아니다 — 새 과금 라우트가 생기면 자동으로 여기서 잡힌다."""
    fns = _fn_nodes()

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
    fn = _fn_nodes()[route_fn]
    ranges = _guarded_ranges(fn)
    outside = [
        ln
        for ln in _charging_handlers()[route_fn]
        if not any(a <= ln <= b for a, b in ranges)
    ]
    assert not outside, f"{route_fn}: 줄 {outside} 의 과금 호출이 charge_once 밖에 있다"
