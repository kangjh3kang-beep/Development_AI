"""`sale_price_source` **어휘 선언 ↔ 생산자** 정합을 잠근다.

★선언은 자기를 검증하지 않는다. 이 저장소에 그 실패가 기록돼 있다 —
*"손으로 고른 키가 상한이 된다"* 를 적고 그 처방(선언 표)까지 만들어 놓고,
**새 선언이 생산자와 어긋났다.**

그래서 여기서 **ast 로 생산자를 파생**해 선언과 양방향 대조한다.
소비처(프론트 `lib/sale-source-label.ts`)는 이 선언을 읽는다.
"""
from __future__ import annotations

import ast
from pathlib import Path

_API = Path(__file__).resolve().parents[1]
_REVAL = _API / "app" / "services" / "feasibility" / "market_revaluation_service.py"


def _api_py_files():
    """★모집단을 **파생**한다. 종전엔 `_PIPE`·`_REVAL` **두 파일을 손으로** 골랐고,
    그래서 `routers/project_dashboard.py` 가 내는 `national_default_no_address` 를
    **못 봤다** — 테스트 이름이 `…matches_the_producers` 인데 모집단이 손 목록이었다.
    (이 파일 독스트링이 인용한 그 실패를 그 처방 안에서 재발시킨 것이다.)
    """
    return [f for f in (_API / "app").rglob("*.py") if "__pycache__" not in str(f)]


def _emitted_literals() -> set[str]:
    """`sale_price_source` 에 **실제로 대입되는** 문자열을 ast 로 모은다.

    ★정규식으로 줄을 긁으면 키 이름 자체(`"sale_price_source"`)와 **다른 필드의 값**
      (`market_price_basis == "national_default"`)까지 집힌다 — 실측으로 두 번 겪었다.
      **대입문의 오른쪽만** 본다.
    """
    out: set[str] = set()

    def collect(node: ast.AST) -> None:
        """대입값의 문자열만 걷는다.

        ★`ast.walk` 를 쓰면 안 된다 — **하위 트리를 건너뛸 수 없어서**
          `.get("sale_price_source")` 의 **키**까지 값으로 집는다(실측으로 두 번 겪었다).
          `Call` 은 **내려가지 않는** 재귀 방문자를 쓴다.
        """
        if isinstance(node, ast.Call):
            return  # 인자·키는 대입값이 아니다
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
            return
        for child in ast.iter_child_nodes(node):
            collect(child)

    nodes = []
    for f in _api_py_files():
        try:
            nodes += list(ast.walk(ast.parse(f.read_text(encoding="utf-8"))))
        except SyntaxError:
            continue
    for n in nodes:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "sale_price_source" for t in n.targets
        ):
            # ★오른쪽만 — 조건식의 **비교 대상**은 값이 아니므로 제외한다
            v = n.value
            if isinstance(v, ast.IfExp):
                collect(v.body)
                collect(v.orelse)
            elif isinstance(v, ast.BoolOp):
                for x in v.values:
                    collect(x)
            else:
                collect(v)

    # `_blend_label` 이 만드는 값
    rtree = ast.parse(_REVAL.read_text(encoding="utf-8"))
    for fn in ast.walk(rtree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "_blend_label":
            for n in ast.walk(fn):
                if isinstance(n, ast.Return) and n.value is not None:
                    if isinstance(n.value, ast.JoinedStr):
                        for part in n.value.values:
                            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                                out.add(part.value)
                    else:
                        collect(n.value)
    return {v for v in out if v and v.replace("_", "").replace(":", "").isalnum()}


def test_vocabulary_declaration_matches_the_producers() -> None:
    from app.services.feasibility.market_revaluation_service import SALE_PRICE_SOURCE_VOCAB

    emitted = _emitted_literals()
    # ★공허진리 방지 + 조회기 생존
    assert len(emitted) >= 4, f"생산자 리터럴 추출 {len(emitted)}개 — 파서가 죽었다: {sorted(emitted)}"
    assert "market_blended" in emitted, f"양성 대조군 실패: {sorted(emitted)}"

    declared = set(SALE_PRICE_SOURCE_VOCAB)
    missing = {e for e in emitted if e not in declared and not any(
        e.startswith(d) for d in declared if d.endswith(":"))}
    assert not missing, f"생산자가 내는데 선언에 없는 값: {sorted(missing)}"

    # ★반대 방향 — 선언에만 있고 아무도 안 내는 값은 **죽은 어휘**다
    stale = {d for d in declared if not d.endswith(":") and d not in emitted}
    assert not stale, f"선언에만 있고 생산자가 안 내는 값(죽은 어휘): {sorted(stale)}"


def test_single_source_is_a_prefix_family() -> None:
    """접두 계열임을 못 박는다 — 하위 출처가 늘어나도 소비처가 견디게."""
    from app.services.feasibility.market_revaluation_service import SALE_PRICE_SOURCE_VOCAB

    pref = [v for v in SALE_PRICE_SOURCE_VOCAB if v.endswith(":")]
    assert pref == ["single_source:"], f"접두 계열 선언이 바뀌었다: {pref}"
