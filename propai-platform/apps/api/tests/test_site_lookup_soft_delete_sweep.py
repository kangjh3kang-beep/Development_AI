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
    ("app/services/sales/pricing/suggest.py", "_site_location"):
        "인자 `site_id` 가 이미 해석된 값이다(유일 호출부 suggest.py:522) — 다운스트림 조회.",
    ("app/services/sales/units/generation.py", "map_from_design"):
        "인자 `site_id` 가 이미 해석된 값이다(유일 호출부 generation.py:130) — 다운스트림 조회.",
}


def _population() -> dict[tuple[str, str], str]:
    """`select(SalesSite)` 를 담은 함수 전수 → {(경로, 함수명): 소스}."""
    found: dict[tuple[str, str], str] = {}
    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # PEP 695 등 이 인터프리터가 못 읽는 파일 — 아래 하한이 이 손실을 잡는다.
        rel = str(path.relative_to(APP.parent))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for call in ast.walk(node):
                if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id == "select" and call.args
                        and isinstance(call.args[0], ast.Name)
                        and call.args[0].id == "SalesSite"):
                    found[(rel, node.name)] = ast.unparse(node)
                    break
    return found


def test_scanner_is_alive_and_does_not_count_a_different_table() -> None:
    """★공허 방지 — 조회기가 살아 있고, **다른 표**를 세지 않는가."""
    pop = _population()
    assert len(pop) >= 8, f"모집단이 붕괴했다({len(pop)}건) — 파서가 죽었으면 위반 0건은 공짜다"

    # 이 PR 이 실제로 고친 자리가 모집단에 있어야 한다(축이 살아 있다는 증거).
    assert ("app/api/endpoints/sales/site_auth.py", "_get_site") in pop
    assert ("app/api/deps_sales.py", "resolve_site") in pop
    assert ("app/api/endpoints/sales/ws_routes.py", "_authorize_site_channel") in pop

    # ★특이도 — `SalesSiteConfig` 만 조회하는 함수는 **들어오면 안 된다**(부분문자열 위양성 5건).
    assert ("app/api/endpoints/sales/lifecycle_p5.py", "payment_installments") not in pop, (
        "조회기가 `SalesSiteConfig`(다른 표)를 `SalesSite` 로 센다 — 위양성도 결함이다"
    )


def test_every_sales_site_lookup_filters_soft_deleted() -> None:
    """★전수 — `select(SalesSite)` 하는 함수는 `deleted_at` 을 걸거나 **원장에 사유가 있다**."""
    pop = _population()
    violations = [
        f"{f}::{fn}" for (f, fn), src in sorted(pop.items())
        if "deleted_at" not in src and (f, fn) not in _EXEMPT
    ]
    assert not violations, (
        "삭제된 현장을 그대로 내주는 조회가 있다(면제하려면 원장에 **측정한 사유**를 적어라): "
        + ", ".join(violations)
    )


def test_no_dead_exemptions() -> None:
    """★죽은 면제는 실패한다 — 면제는 파일이 사라져도 **조용히** 남는다(저장소 §36)."""
    pop = _population()
    dead = [f"{f}::{fn}" for (f, fn) in _EXEMPT if (f, fn) not in pop]
    assert not dead, f"모집단에 없는 면제가 남아 있다(지워라): {dead}"

    # ★면제가 «필요 없어진» 경우도 잡는다 — 스스로 `deleted_at` 을 걸었으면 원장에서 빼라.
    stale = [f"{f}::{fn}" for (f, fn) in _EXEMPT
             if (f, fn) in pop and "deleted_at" in pop[(f, fn)]]
    assert not stale, f"이미 필터를 건 함수가 면제에 남아 있다(지워라): {stale}"


def test_exemptions_carry_a_measured_reason() -> None:
    """★사유 없는 면제는 면제가 아니라 **잊어버린 것**이다."""
    for key, reason in _EXEMPT.items():
        assert len(reason) >= 30, f"{key} 의 면제 사유가 너무 짧다 — 무엇을 재서 면제했는가"
        assert ".py:" in reason, f"{key} 의 면제 사유에 **좌표(파일:줄)** 가 없다"
