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
import re

import pytest

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# ★★면제 원장 — **좌표 단위**(`파일::함수:줄`)다.
#
#   종전엔 키가 `(파일, 함수)` 였다. R4 가 그 축을 정확히 뚫었다 — **면제된 함수에
#   「요청 식별자로 현장을 여는」 새 무필터 조회를 넣으면 그 사유째로 승계된다.**
#   「조회 하나로 축을 내렸다」는 선언이 면제 경로에서 되돌아간 것이다.
#
#   ★그리고 R4 는 종전 면제 4건 중 **3건의 사유가 거짓**임을 실증했다:
#     ①② `_my_site_roles` 의 필터는 `SalesOrgNode.deleted_at` 이고 `SalesSite` 생존은
#        검증하지 않는다 · ② 는 `scope=all` 분기가 403 도 `resolve_site` 도 거치지 않는다
#     ③ `_site_location` 의 «인자가 이미 해석된 값» — `rough-scenario` 가 **익명 허용**으로
#        요청 본문 `site_id` 를 무검증 전달한다(딕셔너리 디스패치라 grep 이 0건으로 보였다)
#   ⇒ **그 넷을 면제로 유지하지 않고 필터를 걸었다.** 거짓 사유를 관리하는 것보다
#     조회를 고치는 것이 싸다. 원장에는 «걸면 더 나빠지는» 한 건만 남는다.
_EXEMPT: dict[str, str] = {
    "app/services/sales/org/service.py::assign_user_to_node:240":
        "★필터를 걸면 **더 나빠진다**(2026-09-12 실측). 이 조회는 "
        "`select(SalesSite.organization_id)` 이고 바로 다음 줄이 "
        "`if org_id and u[2] and str(u[2]) != str(org_id)`"
        "(app/services/sales/org/service.py:241) 다 — "
        "삭제된 현장이면 `org_id` 가 `None` 이 되어 **테넌트 검사가 건너뛰어진다**(fail-open). "
        "즉 여기서 막을 것은 「삭제된 현장의 값을 읽는 것」이 아니라 「삭제된 현장에 배정하는 "
        "것」이고, 그 판정은 **호출부**가 해야 한다. 봉합이 새 결함을 만드는 자리라 "
        "이 PR 에서 건드리지 않고 별건으로 남긴다.",
}


def _filters_live_sales_site(chain: ast.AST) -> bool:
    """체인이 **`SalesSite.deleted_at.is_(None)`** 을 정확히 걸었는가.

    ★★**낱말 검사는 틀렸다**(2026-09-12 · 리뷰 M1 실측). 종전 판정은
      `"deleted_at" not in ast.unparse(chain)` 이었는데, 그러면 셋이 통과한다:
        ① **반전** — `.is_(None)` → `.isnot(None)`(삭제된 현장**만** 찾는다)
        ② **다른 표** — 같은 체인의 `SalesOrgNode.deleted_at`
        ③ 독스트링·주석에 적힌 `deleted_at`
      ★내가 면제 사유에 *"`SalesCustomer.deleted_at`(다른 표)가 낱말 검사를 만족시켰다"* 고
        적어 두고 **판정식에는 같은 실수를 남겼다**. 사유를 쓰는 것과 고치는 것은 다른 일이다.
    """
    for node in ast.walk(chain):
        # `X.deleted_at.is_(None)` 형태만 인정한다.
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "is_"):
            continue
        if not (len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                and node.args[0].value is None):
            continue                      # `.is_(None)` 이 아니면 인정하지 않는다(반전 차단)
        inner = node.func.value           # `X.deleted_at`
        if not (isinstance(inner, ast.Attribute) and inner.attr == "deleted_at"):
            continue
        owner = inner.value               # `X`
        if isinstance(owner, ast.Name) and owner.id == "SalesSite":
            return True                   # ★소유 표가 `SalesSite` 여야 한다(다른 표 차단)
    return False


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


def _population() -> dict[str, ast.AST]:
    """`sales_sites` 를 여는 **조회 하나**마다 → {좌표: 그 조회의 체인 AST}.

    ★축이 넓어졌다(2026-09-12 · 리뷰 M2). 종전엔 `select(SalesSite)` — **첫 인자가
      `SalesSite` 인 형태 하나**뿐이라 실제 조회 셋이 밖에 있었다(실측):
        · `select(SalesOrgNode, SalesSite)`        — `my_sites` (a) · 내 독스트링이
          «형제 3곳이 전부 필터를 건다» 고 쓴 그 (a) 가 **측정 대상이 아니었다**
        · `select(SalesSite.organization_id)`      — 첫 인자가 `ast.Attribute`
        · `select(func.count()).select_from(SalesSite)`
      ⇒ `select(...)` 의 **모든 인자**와 `select_from(...)` 을 본다.
    ★남은 한계(부채 · 아래 `test_raw_sql_site_lookups_are_declared` 가 초록 안에 보이게 한다):
      **원시 SQL**(`text("… FROM sales_sites …")`)은 이 축 밖이다.
    """
    found: dict[str, ast.AST] = {}
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
            if not isinstance(call, ast.Call):
                continue
            hit = False
            # ① `select(...)` 의 **모든 인자** — `SalesSite` 또는 `SalesSite.<col>`
            if isinstance(call.func, ast.Name) and call.func.id == "select":
                for a in call.args:
                    if isinstance(a, ast.Name) and a.id == "SalesSite":
                        hit = True
                    if (isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)
                            and a.value.id == "SalesSite"):
                        hit = True
            # ② `.select_from(SalesSite)`
            if (isinstance(call.func, ast.Attribute) and call.func.attr == "select_from"
                    and any(isinstance(a, ast.Name) and a.id == "SalesSite"
                            for a in call.args)):
                hit = True
            if hit:
                fn = fn_of.get(id(call), "<module>")
                found[f"{rel}::{fn}:{call.lineno}"] = _chain(tree, call)
    return found


def test_scanner_is_alive_and_does_not_count_a_different_table() -> None:
    """★공허 방지 — 조회기가 살아 있고, **다른 표**를 세지 않는가."""
    pop = _population()
    assert len(pop) >= 10, f"모집단이 붕괴했다({len(pop)}건) — 파서가 죽었으면 위반 0건은 공짜다"

    fns = {c.split("::")[0] + "::" + c.split("::")[1].rsplit(":", 1)[0] for c in pop}
    fns = {tuple(x.split("::")) for x in fns}
    # 이 PR 이 실제로 고친 자리가 모집단에 있어야 한다(축이 살아 있다는 증거).
    assert ("app/api/endpoints/sales/site_auth.py", "_get_site") in fns
    assert ("app/api/deps_sales.py", "resolve_site") in fns
    assert ("app/api/endpoints/sales/ws_routes.py", "_authorize_site_channel") in fns

    # ★`resolve_site` 는 조회가 **둘**이다(UUID · site_code). 둘 다 세어야 한다 —
    #   한 건만 세면 함수 단위 축으로 되돌아간 것이다.
    assert len([c for c in pop if c.startswith("app/api/deps_sales.py::resolve_site:")]) == 2

    # ★특이도 — `SalesSiteConfig` 만 조회하는 함수는 **들어오면 안 된다**(부분문자열 위양성 5건).
    assert ("app/api/endpoints/sales/lifecycle_p5.py", "payment_installments") not in fns, (
        "조회기가 `SalesSiteConfig`(다른 표)를 `SalesSite` 로 센다 — 위양성도 결함이다"
    )


def test_every_sales_site_lookup_filters_soft_deleted() -> None:
    """★전수 — `select(SalesSite)` 하는 함수는 `deleted_at` 을 걸거나 **원장에 사유가 있다**."""
    pop = _population()
    violations = [
        coord for coord, chain in sorted(pop.items())
        if not _filters_live_sales_site(chain) and coord not in _EXEMPT
    ]
    assert not violations, (
        "삭제된 현장을 그대로 내주는 조회가 있다(면제하려면 원장에 **측정한 사유**를 적어라): "
        + ", ".join(violations)
    )


def test_no_dead_exemptions() -> None:
    """★죽은 면제는 실패한다 — 면제는 파일이 사라져도 **조용히** 남는다(저장소 §36)."""
    pop = _population()
    dead = [k for k in _EXEMPT if k not in pop]
    assert not dead, (
        "모집단에 없는 면제가 남아 있다(좌표가 낡았다 — 줄이 밀렸거나 조회가 사라졌다): "
        f"{dead}"
    )
    # ★면제가 «필요 없어진» 경우도 잡는다 — 스스로 필터를 걸었으면 원장에서 빼라.
    stale = [k for k in _EXEMPT if _filters_live_sales_site(pop[k])]
    assert not stale, f"이미 필터를 건 조회가 면제에 남아 있다(지워라): {stale}"

    # ★★원장이 비면 위 두 단언이 **공허**해진다 — 그 사실을 드러낸다.
    assert _EXEMPT, (
        "면제 원장이 비었다. 좋은 일이지만, 그러면 위 두 단언은 아무것도 검사하지 않는다 — "
        "이 줄을 지우기 전에 그 사실을 알고 지워라"
    )


def resolve_coordinate(root: pathlib.Path, rel: str) -> pathlib.Path:
    """사유가 인용한 `파일.py` 경로를 **모호하지 않게** 해석한다.

    ★함수로 뺀 이유: 모호 분기가 **한 번도 태워지지 않았다**(변이 실측 — 짧은 경로
      `org/service.py` 는 접미가 유일해 모호 분기에 도달하지 않는다). 합성 입력으로
      네 갈래(정확 · 접미 유일 · **모호** · 부재)를 각각 태운다.

    ★★이 함수 자신이 위양성의 서식지였다 — `rglob(basename)` 폴백이 이 저장소의
      `service.py` **8개** 중 엉뚱한 것을 집어 정상 사유를 거짓으로 찍었다(CI 실측).
    """
    exact = root / rel
    if exact.is_file():
        return exact
    cands = [c for c in root.rglob("*.py") if str(c.relative_to(root)).endswith(rel)]
    if not cands:
        raise FileNotFoundError(rel)
    if len(cands) > 1:
        raise ValueError(
            f"경로가 모호하다({len(cands)}개) — 전체 경로를 적어라: "
            f"{sorted(str(c.relative_to(root)) for c in cands)[:4]}"
        )
    return cands[0]


def test_the_coordinate_resolver_discriminates_all_four_cases() -> None:
    """★해석기 자신을 태운다 — **네 갈래 전부**(정확 · 접미 유일 · 모호 · 부재)."""
    root = APP.parent

    # ① 정확 경로
    assert resolve_coordinate(root, "app/services/sales/org/service.py").is_file()

    # ② 접미 유일 — 짧게 적어도 옳게 해석된다(위양성이었던 자리)
    got = resolve_coordinate(root, "org/service.py")
    assert str(got).endswith("app/services/sales/org/service.py"), got

    # ③ **모호** — 이 저장소에 `service.py` 는 여러 개다. 조용히 아무거나 집으면 안 된다.
    n = len([c for c in root.rglob("*.py") if str(c.relative_to(root)).endswith("service.py")])
    assert n > 1, f"대조군 실패 — `service.py` 가 {n}개라 모호 분기를 태울 수 없다"
    with pytest.raises(ValueError, match="모호"):
        resolve_coordinate(root, "service.py")

    # ④ 부재
    with pytest.raises(FileNotFoundError):
        resolve_coordinate(root, "zzz_no_such_file.py")


def test_exemptions_carry_a_reason_whose_coordinates_exist() -> None:
    """★사유 없는 면제는 면제가 아니라 **잊어버린 것**이다.

    ★★그리고 **형태만 보면 거짓 사유가 통과한다**(2026-09-12 · 리뷰 MINOR 3 실증).
      종전 판은 `len(reason) >= 30` + `".py:" in reason` 뿐이었고, R4 가 거짓으로 밝힌
      사유 **3건이 전부 이 락을 통과**했다. ⇒ 사유가 인용한 **좌표가 실재하는지**까지 본다
      (파일이 있고, 그 줄이 있고, 빈 줄이 아니다). 사유의 *참*은 기계가 못 보지만
      **매달린 참조**는 볼 수 있다.
    """
    root = APP.parent
    for key, reason in _EXEMPT.items():
        assert len(reason) >= 30, f"{key} 의 면제 사유가 너무 짧다 — 무엇을 재서 면제했는가"
        coords = re.findall(r"([A-Za-z0-9_/.]+\.py):(\d+)", reason)
        assert coords, f"{key} 의 면제 사유에 **좌표(파일:줄)** 가 없다"
        for rel, lineno in coords:
            # ★★**해석기가 엉뚱한 파일을 집었다**(2026-09-12 CI 실측 · 내 가드의 위양성).
            #   종전엔 `rglob(basename)` 로 폴백했는데 이 저장소에 `service.py` 가 **8개** 있어
            #   19줄짜리 `guarantee/service.py` 를 집고 «좌표가 파일 밖이다» 로 신고했다.
            #   실제 대상은 `app/services/sales/org/service.py`(303줄)이고 133줄은 실재한다.
            #   ★**가드의 위양성도 결함이다** — 정상 사유를 거짓으로 찍으면 다음 사람이
            #     사유를 고치려 들거나 이 락을 끈다.
            #   ⇒ ①정확 경로 우선 ②없으면 **전체 상대경로의 접미 일치**로 찾고
            #     ③후보가 둘 이상이면 **모호하다고 실패**시킨다(짧게 쓴 사람에게 전체 경로를 요구).
            # ★사본을 만들지 않는다 — 위 `resolve_coordinate` 를 쓴다(판정식은 한 곳).
            try:
                found = resolve_coordinate(root, rel)
            except FileNotFoundError:
                raise AssertionError(f"{key}: 사유가 없는 파일을 가리킨다 — {rel}") from None
            except ValueError as e:
                raise AssertionError(f"{key}: {e}") from None
            lines = found.read_text(encoding="utf-8").splitlines()
            n = int(lineno)
            assert 1 <= n <= len(lines), (
                f"{key}: 사유의 좌표가 파일 밖이다 — {rel}:{n}(총 {len(lines)}줄)"
            )
            assert lines[n - 1].strip(), f"{key}: 사유의 좌표가 **빈 줄**이다 — {rel}:{n}"



def _docstring_lines(tree: ast.AST) -> set[int]:
    """독스트링이 차지하는 **줄 번호 집합**.

    ★이 헬퍼가 필요한 이유(2026-09-12 실측): 앞 판은 `#` 주석만 걷어내고 **독스트링은 그대로** 셌다.
      `site_join.py` 의 모듈 독스트링이 «`sales_sites` 는 테넌트에 묶여 있는데…» 라고 **설명**하자
      래칫이 9→10 으로 **거짓 발화**했다. 저장소 지침이 이미 명문으로 경고한다 —
      *「소스 검사는 주석뿐 아니라 **독스트링에도 뚫린다**」*. 그 경고를 **내 락이 위반하고 있었다.**
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        first = body[0] if body else None
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def _raw_sql_hits(root: pathlib.Path) -> list[str]:
    """`sales_sites` 를 **실행 줄에서** 여는데 `deleted_at` 이 없는 좌표.

    ★`root` 를 인자로 받는다 — 합성 입력으로 태울 수 있어야 판정식 자체를 잠글 수 있다.
    """
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root.parent))
        try:
            doc = _docstring_lines(ast.parse(src))
        except SyntaxError:
            doc = set()
        for i, line in enumerate(src.splitlines(), 1):
            if i in doc:
                continue
            if "sales_sites" in line and "deleted_at" not in line and not line.lstrip().startswith("#"):
                hits.append(f"{rel}:{i}")
    return hits


def test_raw_sql_site_lookups_are_visible_as_debt() -> None:
    """★남은 축을 **초록 안에 보이게** 둔다 — 원시 SQL 은 AST 로 못 본다.

    R4 실측: `market.py:786,807` · `referral.py:348` · `termination_cert.py:169,307,464,493`
    가 `text("… sales_sites …")` 로 조회하고 `deleted_at` 이 없다. 이 축은 파서가 다르고
    (SQL 문법) 「어느 표의 어느 별칭인가」 판정이 별건이라 이 PR 에서 넓히지 않는다.

    ★**부채를 숨기지 않는 방식**: 지금 몇 건인지 세어 두고, **늘면 실패**시킨다.
      새 원시 SQL 조회를 추가하는 사람이 여기서 걸린다(래칫).
    """
    hits = _raw_sql_hits(APP)

    # ★대조군 — 조회기가 죽으면 「0건」이 공짜다.
    assert hits, "원시 SQL 조회가 **한 건도** 안 잡혔다 — 조회기가 죽었다"

    # ★래칫: 현재 관측치(2026-09-12 R2). **늘면 실패**한다.
    #   ★9 → **8**. 줄어든 1건은 «고쳤다»가 아니라 **이 판정식이 독스트링을 세지 않게 됐기 때문**이다
    #     (`site_join.py:23` 의 모듈 독스트링이 `sales_sites` 를 **설명**하고 있었다).
    #     ***래칫을 내릴 때는 「무엇이 줄었나」가 아니라 「왜 줄었나」를 적어라*** —
    #     고친 것과 못 세던 것을 같은 칸에 두면 다음 사람이 진짜 개선으로 오독한다.
    RATCHET = 8
    assert len(hits) <= RATCHET, (
        f"`sales_sites` 를 원시 SQL 로 여는 줄이 {len(hits)}건으로 늘었다(래칫 {RATCHET}). "
        "새 조회에 `deleted_at` 을 걸었는지 확인하고, 걸었으면 래칫을 내려라: "
        + ", ".join(sorted(hits)[:6]) + " …"
    )

def test_the_raw_sql_scanner_separates_four_populations(tmp_path) -> None:
    """★판정식 자체를 **합성 입력**으로 잠근다 — 항목마다 「그것만 걸리는」 파일 하나씩.

    ★왜 필요했나(2026-09-12 실측): 앞 판은 `#` 주석만 걷어내고 **독스트링을 셌다.**
      `site_join.py` 의 모듈 독스트링이 `sales_sites` 를 **설명**하자 래칫이 9→10 으로
      **거짓 발화**했다. 그때 실제 코드는 한 줄도 늘지 않았다.
    ★★**차가 0인 픽스처는 잠금이 아니다** — 그래서 네 파일이 **각각 다른 이유로** 갈린다.
      한 파일에 여러 조건을 섞으면 하나를 지워도 나머지가 초록을 만든다.
    """
    app = tmp_path / "app"
    app.mkdir()
    (app / "only_docstring.py").write_text(
        '"""설명: sales_sites 는 테넌트에 묶여 있다."""\nX = 1\n', encoding="utf-8")
    (app / "real_code.py").write_text(
        'X = text("SELECT * FROM sales_sites WHERE id=:i")\n', encoding="utf-8")
    (app / "guarded.py").write_text(
        'X = text("SELECT * FROM sales_sites WHERE deleted_at IS NULL")\n', encoding="utf-8")
    (app / "line_comment.py").write_text('# sales_sites 를 연다\nX = 1\n', encoding="utf-8")

    hits = _raw_sql_hits(app)
    names = sorted(h.split("/")[-1].split(":")[0] for h in hits)

    # ★공허 방지 선단언 — 아무것도 안 잡으면 아래 「안 잡힌다」 셋이 공짜로 참이 된다.
    assert names == ["real_code.py"], (
        "실행 줄 하나만 잡혀야 한다(독스트링·주석·가드된 줄은 제외). 실제: " + repr(hits))

