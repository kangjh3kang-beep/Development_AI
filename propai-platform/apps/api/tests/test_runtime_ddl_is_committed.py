"""런타임 DDL 은 **커밋돼야** 한다 — 안 하면 읽기 경로에서 통째로 사라진다.

## 왜 (2026-09-14 · 프로덕션 500 · 라이브 예외로 확증)

    sqlalchemy.exc.ProgrammingError: UndefinedTableError:
    relation "sales_draw_commitments" does not exist

**Postgres 에서 DDL 은 트랜잭션이다.** `_ensure` 가 `CREATE TABLE` 을 실행하고
**커밋하지 않은 채** 「했다」 플래그를 세웠다. 그런데 `public_commitment`·`group_status` 는
**SELECT 만 하고 끝난다 — 커밋하지 않는다.** 그래서:

  ① 워커의 **첫 요청**이 읽기 경로면 → 같은 트랜잭션이라 **그 요청은 성공한다**
  ② 요청이 끝나며 롤백 → **테이블이 사라진다**
  ③ 플래그는 `True` 로 남는다 → 이후 **모든 요청이 없는 테이블을 조회**한다

★***내 배포 검증 프로브가 바로 그 「첫 요청」이었다.*** 「배선 확인」이라 보고한 그 호출이
**테이블을 만들고 되돌려 놓았다.** ***검증 행위가 검증 대상을 망가뜨렸다.***

★저장소 기준선과도 어긋났다 — DDL 을 돌리는 파일 **40개 중 39개가 커밋**한다(전수 실측).

## 이 락의 축

**목록을 손으로 관리하지 않는다.** `sales/draw` 안의 `_ensure` 계열 함수를 **AST 로 파생**해
① DDL 을 실행하는가 ② 그 뒤에 `commit()` 이 있는가 ③ **플래그를 커밋 뒤에 세우는가** 를 본다.
"""
from __future__ import annotations

import ast
import pathlib

_DRAW = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "sales" / "draw"
_DDL_TOKENS = ("CREATE TABLE", "ALTER TABLE", "CREATE INDEX")


def _ddl_functions() -> list[tuple[str, ast.AsyncFunctionDef, str]]:
    """`(파일명, 함수노드, 소스)` — **DDL 을 실행하는 함수만** 파생한다."""
    got = []
    for f in sorted(_DRAW.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            body = ast.get_source_segment(src, n) or ""
            # ★독스트링·주석의 DDL 언급에 속지 않는다 — **실행 리터럴**만 본다
            literals = " ".join(
                c.value for c in ast.walk(n)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
                and c is not (n.body[0].value if n.body and isinstance(n.body[0], ast.Expr)
                              and isinstance(n.body[0].value, ast.Constant) else None)
            )
            if any(tok in literals for tok in _DDL_TOKENS):
                got.append((f.name, n, body))
    return got


def test_every_runtime_ddl_function_commits():
    """★DDL 을 돌리는 함수는 **반드시 커밋**한다 — 읽기 경로가 첫 요청이면 롤백되기 때문이다."""
    fns = _ddl_functions()
    # 공허 방지 — 파싱이 죽으면 「위반 0」이 된다
    assert len(fns) >= 2, f"DDL 함수를 거의 못 찾았다(조회기 사망?): {[f'{a}:{b.name}' for a, b, _ in fns]}"
    bad = []
    for fname, node, body in fns:
        commits = [c for c in ast.walk(node)
                   if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "commit"]
        if not commits:
            bad.append(f"{fname}:{node.name}")
    assert not bad, (
        "★런타임 DDL 을 실행하고 **커밋하지 않는다** — 읽기 전용 요청이 첫 호출이면 "
        f"테이블이 롤백되고 이후 모든 요청이 500 이 된다(2026-09-14 프로덕션 실측): {bad}"
    )


def test_done_flag_is_set_after_the_commit_not_before():
    """★플래그를 **커밋보다 먼저** 세우면, 롤백된 DDL 을 「했다」로 기억해 **영원히 재시도하지 않는다.**

    줄 번호로 순서를 본다 — «커밋한다」와 «커밋한 뒤에 기억한다」는 다른 계약이다.
    """
    checked = 0
    for fname, node, _ in _ddl_functions():
        commit_lines = [c.lineno for c in ast.walk(node)
                        if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "commit"]
        flag_lines = [a.lineno for a in ast.walk(node)
                      if isinstance(a, ast.Assign)
                      for t in a.targets
                      if isinstance(t, ast.Name) and t.id.isupper()
                      and isinstance(a.value, ast.Constant) and a.value.value is True]
        if not flag_lines:
            continue
        checked += 1
        assert commit_lines, f"{fname}:{node.name} 플래그는 세우는데 커밋이 없다"
        assert min(flag_lines) > max(commit_lines), (
            f"★{fname}:{node.name} 이 **커밋보다 먼저** 「했다」 플래그를 세운다"
            f"(flag@{min(flag_lines)} ≤ commit@{max(commit_lines)}) — "
            "실패를 「했다」로 기억하면 영원히 재시도하지 않는다"
        )
    assert checked >= 2, f"플래그를 쓰는 DDL 함수를 거의 못 찾았다(공허 방지): {checked}"


def test_the_two_functions_that_caused_the_outage_are_covered():
    """★이 락을 낳은 **두 자리**가 실제로 검사 대상에 들어 있는지 못 박는다.

    ***락만 넣고 원인을 안 덮으면 다음 사람이 「이미 다뤄진 문제」로 읽는다.***
    """
    names = {f"{f}:{n.name}" for f, n, _ in _ddl_functions()}
    for want in ("commitment_store.py:_ensure", "draw_engine.py:_ensure"):
        assert want in names, f"★{want} 가 DDL 함수로 파생되지 않았다 — 축이 그 자리를 안 본다: {names}"
