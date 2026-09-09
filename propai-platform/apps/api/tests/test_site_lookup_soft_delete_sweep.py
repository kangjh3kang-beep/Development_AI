"""★삭제된 현장은 **없는 현장**이다 — `select(SalesSite)` 전수 스윕(2026-09-09).

【왜 · 이 PR 이 만든 위험】
「승인이 곧 인증이다」로 **비번 미설정 현장이 멤버에게 열렸다**(실측 14현장 중 11).
그 전까지는 비번 409 가 사실상의 2차 관문이라 «삭제된 현장에 진입» 이 드러나지 않았다.
관문을 걷어내면 **삭제 필터가 유일한 관문**이 된다 — 그래서 이 축을 전역으로 잠근다.

【실측(2026-09-09)】리뷰 M5 는 `_get_site` **한 자리**를 짚었다. 같은 축으로 전수를 세니
진입점 중 **셋**이 안 걸려 있었다:

    app/api/endpoints/sales/site_auth.py::_get_site          ← 리뷰가 짚은 자리
    app/api/deps_sales.py::resolve_site                      ← 경로·헤더·서브도메인 진입점
    app/api/endpoints/sales/ws_routes.py::_authorize_site_channel  ← WS 채널 합류

★**지적된 자리에만 처방을 적용하면 형제 축이 남는다**(저장소 반복 결함). 그래서 축을
  「함수 하나」가 아니라 **`select(SalesSite)` 를 담은 함수 전수**로 파생시킨다.

【조회기】`SalesSite` 부분문자열로 세면 **`SalesSiteConfig`**(다른 표)가 섞여 들어온다
  — 실측 위양성 5건. 그래서 문자열이 아니라 **AST 로 `select(...)` 의 첫 인자 이름**을 본다.
"""
from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# ★면제 원장 — 「진입점이 아니라 **이미 해석된 현장**을 쓰는 자리」만 들어온다.
#   사유는 **측정한 것**이고, 죽은 항목은 아래 테스트가 실패시킨다(면제는 조용히 썩는다).
_EXEMPT: dict[tuple[str, str], str] = {
    ("app/api/endpoints/sales/crm_enhance.py", "work_log_summary"):
        "모집단이 `_my_site_roles`(deleted_at 필터 있음)에서 오고 여기선 **이름만** 붙인다 "
        "— 요청이 준 식별자로 현장을 여는 자리가 아니다(crm_enhance.py:517-518 에서 교집합).",
    ("app/api/endpoints/sales/crm_enhance.py", "my_customers"):
        "`target_sites` 가 `roles`(=`_my_site_roles`, deleted_at 필터 있음) 또는 `resolve_site` "
        "(이 PR 에서 필터를 걸었다)에서만 오고, 403 으로 교집합을 강제한다(crm_enhance.py:234) "
        "— 여기선 **이름만** 붙인다. ★함수 단위 축은 이 자리를 **놓쳤다**: 같은 함수의 "
        "`SalesCustomer.deleted_at`(다른 표)가 낱말 검사를 만족시켰다(crm_enhance.py:247).",
    ("app/services/sales/pricing/suggest.py", "_site_location"):
        "인자 `site_id` 가 이미 해석된 값이다(유일 호출부 suggest.py:522) — 다운스트림 조회.",
    ("app/services/sales/units/generation.py", "map_from_design"):
        "인자 `site_id` 가 이미 해석된 값이다(유일 호출부 generation.py:130) — 다운스트림 조회.",
}


def _chain(tree: ast.AST, call: ast.Call) -> ast.AST:
    """`select(SalesSite)` 를 감싼 **메서드 체인 전체**(`.where(...).order_by(...)`)를 돌려준다.

    ★축이 «함수» 면 한 함수 안에 조회가 둘일 때 **한쪽만 걸어도 통과**한다.
      실측(2026-09-09 변이 ④): `resolve_site` 는 UUID 조회와 site_code 조회 **둘**인데
      site_code 쪽의 `deleted_at` 을 걷어도 함수 소스에 낱말이 남아 **SURVIVED** 했다.
      그래서 판정 단위를 **조회 하나**로 내린다.
    """
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    cur: ast.AST = call
    while True:
        par = parents.get(cur)
        # `X.where` (Attribute 의 value) 또는 `X.where(...)` (Call 의 func) 로만 올라간다.
        climbs = ((isinstance(par, ast.Attribute) and par.value is cur)
                  or (isinstance(par, ast.Call) and par.func is cur))
        if not climbs:
            return cur
        cur = par


def _population() -> dict[str, str]:
    """`select(SalesSite)` **조회 하나**마다 → {좌표: 그 조회의 체인 소스}."""
    found: dict[str, str] = {}
    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # PEP 695 등 이 인터프리터가 못 읽는 파일 — 아래 하한이 이 손실을 잡는다.
        rel = str(path.relative_to(APP.parent))
        fn_of: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for c in ast.walk(node):
                    fn_of.setdefault(id(c), node.name)
        for call in ast.walk(tree):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "select" and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "SalesSite"):
                fn = fn_of.get(id(call), "<module>")
                found[f"{rel}::{fn}:{call.lineno}"] = ast.unparse(_chain(tree, call))
    return found


def _fn_key(coord: str) -> tuple[str, str]:
    f, rest = coord.split("::", 1)
    return f, rest.rsplit(":", 1)[0]


def test_scanner_is_alive_and_does_not_count_a_different_table() -> None:
    """★공허 방지 — 조회기가 살아 있고, **다른 표**를 세지 않는가."""
    pop = _population()
    assert len(pop) >= 10, f"모집단이 붕괴했다({len(pop)}건) — 파서가 죽었으면 위반 0건은 공짜다"

    fns = {_fn_key(c) for c in pop}
    # 이 PR 이 실제로 고친 자리가 모집단에 있어야 한다(축이 살아 있다는 증거).
    assert ("app/api/endpoints/sales/site_auth.py", "_get_site") in fns
    assert ("app/api/deps_sales.py", "resolve_site") in fns
    assert ("app/api/endpoints/sales/ws_routes.py", "_authorize_site_channel") in fns

    # ★`resolve_site` 는 조회가 **둘**이다(UUID · site_code). 둘 다 세어야 한다 —
    #   한 건만 세면 함수 단위 축으로 되돌아간 것이다.
    assert len([c for c in pop if _fn_key(c) == ("app/api/deps_sales.py", "resolve_site")]) == 2

    # ★특이도 — `SalesSiteConfig` 만 조회하는 함수는 **들어오면 안 된다**(부분문자열 위양성 5건).
    assert ("app/api/endpoints/sales/lifecycle_p5.py", "payment_installments") not in fns, (
        "조회기가 `SalesSiteConfig`(다른 표)를 `SalesSite` 로 센다 — 위양성도 결함이다"
    )


def test_every_sales_site_lookup_filters_soft_deleted() -> None:
    """★전수 — `select(SalesSite)` 하는 함수는 `deleted_at` 을 걸거나 **원장에 사유가 있다**."""
    pop = _population()
    violations = [
        coord for coord, src in sorted(pop.items())
        if "deleted_at" not in src and _fn_key(coord) not in _EXEMPT
    ]
    assert not violations, (
        "삭제된 현장을 그대로 내주는 조회가 있다(면제하려면 원장에 **측정한 사유**를 적어라): "
        + ", ".join(violations)
    )


def test_no_dead_exemptions() -> None:
    """★죽은 면제는 실패한다 — 면제는 파일이 사라져도 **조용히** 남는다(저장소 §36)."""
    pop = _population()
    fns = {_fn_key(c) for c in pop}
    dead = [f"{f}::{fn}" for (f, fn) in _EXEMPT if (f, fn) not in fns]
    assert not dead, f"모집단에 없는 면제가 남아 있다(지워라): {dead}"

    # ★면제가 «필요 없어진» 경우도 잡는다 — 스스로 `deleted_at` 을 걸었으면 원장에서 빼라.
    stale = [f"{f}::{fn}" for (f, fn) in _EXEMPT
             if all("deleted_at" in src for c, src in pop.items() if _fn_key(c) == (f, fn))
             and (f, fn) in fns]
    assert not stale, f"이미 필터를 건 함수가 면제에 남아 있다(지워라): {stale}"


def test_exemptions_carry_a_measured_reason() -> None:
    """★사유 없는 면제는 면제가 아니라 **잊어버린 것**이다."""
    for key, reason in _EXEMPT.items():
        assert len(reason) >= 30, f"{key} 의 면제 사유가 너무 짧다 — 무엇을 재서 면제했는가"
        assert ".py:" in reason, f"{key} 의 면제 사유에 **좌표(파일:줄)** 가 없다"
