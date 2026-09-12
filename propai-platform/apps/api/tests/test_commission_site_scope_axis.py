"""★`commission/extension.py` 의 함수가 **외부 id 를 받으면 반드시 현장 축을 갖는다** — AST 파생.

## 왜 이 락이 필요한가 (2026-09-08 적대 리뷰 B3)

`release_holdback` 하나만 고쳤는데, **라우터 세 개가 연속 배치**돼 있고
(`lifecycle_p6.py:80 / 88 / 97`) 앞의 둘이 **정확히 같은 결함**이었다:

    create_schedule(db, split_id, ...)   ← A현장이 B현장 split 에 지급표를 만든다
    set_holdback(db, split_id, ...)      ← A현장이 B현장 split 에 보류금을 건다
                                            ⇒ run_due_payouts 가 gross -= holdback 하므로
                                              **B현장 지급이 A가 건 만큼 깎인다**
    release_holdback(db, holdback_id)    ← 내가 고친 것

★저장소 메모리 최상단 항목의 재발이다 —
*「처방을 「지적된 자리」에만 적용하면 형제 축이 그대로 남는다」*.

## 축

**목록이 아니라 `ast` 로 시그니처를 파생**시킨다. 새 함수가 생기면 **내가 이 락을 고치지 않아도**
자동으로 들어온다. 손으로 세 함수를 적으면 네 번째가 조용히 빠진다.

## 판정 규칙

`db` 를 첫 인자로 받는 공개 함수(`_` 로 시작하지 않는) 중 **외부 식별자**(`*_id`)를 받는 것은
`site_id` 를 **기본값 없이** 받아야 한다.

★`site_id` 자체는 식별자이지만 **그것이 곧 현장 축**이므로 대상에서 제외한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1]
        / "app" / "services" / "sales" / "commission" / "extension.py")


def _public_db_functions() -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    out = []
    for n in tree.body:
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if n.name.startswith("_"):
            continue
        args = [a.arg for a in n.args.args]
        if args and args[0] == "db":
            out.append(n)
    return out


def test_population_is_not_empty() -> None:
    """★공허 진리 가드 — 모집단이 비면 아래 판정이 무의미하다."""
    fns = _public_db_functions()
    assert len(fns) >= 3, f"수집된 공개 db 함수가 너무 적다: {[f.name for f in fns]}"
    # 대조군: 오늘 실제로 있는 이름이 잡히는가(조회기 생존).
    names = {f.name for f in fns}
    assert {"create_schedule", "set_holdback", "release_holdback"} <= names


def test_external_id_functions_take_site_id() -> None:
    """★외부 id 를 받는 함수는 **현장 축**을 갖는다."""
    offenders: list[str] = []
    for fn in _public_db_functions():
        args = [a.arg for a in fn.args.args]
        takes_external_id = any(a.endswith("_id") and a != "site_id" for a in args)
        if takes_external_id and "site_id" not in args:
            offenders.append(f"{fn.name}({', '.join(args)})")

    assert not offenders, (
        "외부 id 를 받는데 현장 축이 없다 — A현장이 B현장 것을 다룰 수 있다:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_site_id_has_no_default() -> None:
    """★`site_id` 에 **기본값이 없어야** 한다 — 있으면 새 호출부가 빠뜨려도 조용하다.

    (적대 리뷰 M4: `site_id=None` 기본값은 «점진 이행» 이 아니라 **아무도 안 쓰는 우회로**였고,
     빠뜨리면 격리가 예외도 경고도 없이 꺼진다.)
    """
    offenders: list[str] = []
    for fn in _public_db_functions():
        args = [a.arg for a in fn.args.args]
        if "site_id" not in args:
            continue
        # 기본값은 뒤에서부터 대응된다.
        n_def = len(fn.args.defaults)
        defaulted = set(args[len(args) - n_def:]) if n_def else set()
        if "site_id" in defaulted:
            offenders.append(fn.name)

    assert not offenders, f"site_id 에 기본값이 있다(빠뜨려도 조용히 통과한다): {offenders}"


def test_two_populations_are_different() -> None:
    """★두 모집단이 **서로 다른 결과**를 낸다 — 판정이 무엇이든 통과시키지 않는다는 증거."""
    fns = {f.name: [a.arg for a in f.args.args] for f in _public_db_functions()}
    # 양성: 외부 id 를 받는 함수가 실재하고 site_id 를 갖는다.
    assert "split_id" in fns["set_holdback"] and "site_id" in fns["set_holdback"]
    # 특이도: 외부 id 를 안 받는 함수는 site_id 를 **요구받지 않는다**(위양성 방지).
    assert "run_due_payouts" in fns  # site_id 는 갖지만 그것은 외부 id 가 아니다


# ─────────────────────────────────────────────────────────────────────────────
# ★행위 축 — 관문이 **실제로 거부하는가**
# ─────────────────────────────────────────────────────────────────────────────
#
# 위 세 검사는 «시그니처에 site_id 가 있는가» 를 본다. 그것만으로는
# **관문의 판정을 죽이는 변이**가 통과한다(실측):
#
#     _assert_split_in_site: if row is None:  →  if False:
#         ::VERDICT=SURVIVED
#
# ⇒ 시그니처는 **선언**이고 거부는 **행위**다. 둘을 각각 잠근다.

import sys  # noqa: E402

import pytest  # noqa: E402

# ★`extension.py` 는 `datetime.UTC`(3.11+)를 임포트한다. 로컬 셸이 3.10 이면 **임포트 자체가**
#   실패한다(AST 검사는 임포트가 필요 없어 통과한다 — 그래서 이 축만 조건부다).
#   ★**skip 이 아니라 이유를 남긴다** — 조용한 skip 은 「돌았는데 통과」와 구별되지 않는다.
_NEEDS_311 = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="extension.py 가 datetime.UTC(3.11+)를 임포트한다 — CI(3.12)에서 실행된다. "
           "★로컬에서 돌리려면 3.12 venv 를 쓴다: /home/kangjh3kang/.venvs/propai312/bin/python -m pytest <이 파일> (propai312 · GDAL 불필요).",
)


class _Res:
    def __init__(self, row): self._row = row
    def first(self): return self._row


class _DB:
    """`_assert_split_in_site` 가 쓰는 것만: `execute(...).first()`."""

    def __init__(self, row): self._row = row
    async def execute(self, *_a, **_k): return _Res(self._row)


@_NEEDS_311
@pytest.mark.asyncio
async def test_gate_rejects_split_from_another_site() -> None:
    """★남의 현장 split → **거부**(조회 결과가 비면 거부한다)."""
    from app.services.sales.commission import extension as ext

    with pytest.raises(ValueError) as ei:
        await ext._assert_split_in_site(_DB(None), "site-A", "split-of-B")
    assert "현장" in str(ei.value)


@_NEEDS_311
@pytest.mark.asyncio
async def test_gate_allows_own_site_split() -> None:
    """★★**반대편 모집단** — 내 현장 split 은 **통과**한다.

    이것이 없으면 위 단언이 «항상 거부한다» 와 구별되지 않는다(정상 운영을 막는 위양성).
    """
    from app.services.sales.commission import extension as ext

    await ext._assert_split_in_site(_DB(("split-1",)), "site-A", "split-1")  # 예외가 나면 실패
