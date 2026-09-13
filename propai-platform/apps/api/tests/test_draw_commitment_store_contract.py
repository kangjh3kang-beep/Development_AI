"""★공약 저장소 계약 — **「공약처럼 보이는 것」과 「공약」을 가른다.**

독립 적대 리뷰(2026-09-13)가 짚은 두 MAJOR:

  **M-1** 공약을 `announcement.rules` 에 두었더니 **범용 CRUD 로 덮어쓸 수 있었고**,
       그 쓰기 역할이 추첨 역할을 **완전히 포함**했다. 운영자는 명부를 본 뒤
       commit+nonce 를 **한 번에** 써 넣고 바로 추첨할 수 있었다 — ***공약이 연극이었다.***
  **M-2** `rules` 는 읽기 API 에 실린다. 정직하게 «미리» 게시하면 **누구나 사전 계산**하고,
       미리 안 하면 M-1 이다. ***같은 칸에 둔 것이 딜레마의 원인이었다.***

이 파일은 그 구조가 **실제로 분리됐는지**를 소스에서 파생해 본다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.sales.draw import commitment_store as cs
from app.services.sales.draw import vrng

_API = pathlib.Path(__file__).resolve().parents[1]
_STORE = pathlib.Path(cs.__file__)


def test_commitment_table_is_not_registered_in_any_generic_crud():
    """★**CRUD 표면 밖**이어야 한다 — 등록되는 순간 PATCH 로 덮인다(M-1 의 원인)."""
    reg = (_API / "app" / "api" / "endpoints" / "sales" / "__init__.py").read_text(encoding="utf-8")
    # 공허 방지 — 이 파일이 실제로 등록 표를 들고 있는가
    assert "subscription/announcements" in reg, "대조군 실패 — CRUD 등록표를 못 읽었다"
    assert "commitment" not in reg.lower(), "공약 테이블이 범용 CRUD 에 등록됐다"
    assert "sales_draw_commitments" not in reg


def test_nonce_never_leaves_in_a_public_return():
    """★**nonce 는 공개 반환에 실리지 않는다**(M-2).

    `commit_draw`·`public_commitment` 가 돌려주는 dict 의 **리터럴 키**를 AST 로 뽑아 확인한다
    (문자열 grep 은 주석·독스트링에 뚫린다).
    """
    tree = ast.parse(_STORE.read_text(encoding="utf-8"))
    public_keys: set[str] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef) or fn.name not in (
                "commit_draw", "public_commitment"):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                public_keys |= {
                    k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert "commit_hash" in public_keys, "대조군 실패 — 공개 반환 키를 하나도 못 읽었다"
    assert "nonce" not in public_keys, (
        f"공개 반환에 nonce 가 실린다 — 추첨 전에 결과가 계산된다: {sorted(public_keys)}"
    )


def test_recommit_is_structurally_impossible():
    """★**재공약 불가**가 스키마에 있어야 한다 — 코드 분기만으로는 경합에서 샌다."""
    ddl = _STORE.read_text(encoding="utf-8")
    assert "sales_draw_commitments" in ddl, "대조군 실패 — DDL 을 못 읽었다"
    assert "UNIQUE (scope, ref_id)" in ddl, (
        "재공약을 막는 UNIQUE 제약이 없다 — 운영자가 다시 공약하고 다시 뽑을 수 있다"
    )


def test_committed_at_exists_so_order_can_be_proven():
    """★**시점**이 있어야 「공약이 추첨보다 앞섰다」를 말할 수 있다(M-1 의 증거 축)."""
    ddl = _STORE.read_text(encoding="utf-8")
    assert "committed_at" in ddl, "공약 시점을 기록하지 않으면 선후를 증명할 수 없다"


def test_caller_cannot_choose_the_nonce():
    """★nonce 를 **서버가 만든다** — 호출자가 넣으면 `body.seed` 결함이 자리만 옮긴 것이다."""
    import inspect
    params = list(inspect.signature(cs.commit_draw).parameters)
    assert "nonce" not in params, f"호출자가 nonce 를 넣을 수 있다: {params}"
    assert "ref_id" in params, params
    src = inspect.getsource(cs.commit_draw)
    assert "secrets.token_hex" in src, "서버가 nonce 를 만들지 않는다"


def test_generated_nonce_meets_the_strength_floor():
    """생성된 nonce 가 `vrng` 의 하한을 실제로 넘는가 — 두 상수가 갈리면 조용히 약해진다."""
    import re
    src = (_STORE.read_text(encoding="utf-8"))
    m = re.search(r"secrets\.token_hex\((\d+)\)", src)
    assert m, "nonce 생성부를 못 찾았다"
    produced = "ab" * int(m.group(1))
    assert vrng.is_strong_nonce(produced), (
        f"생성 nonce({int(m.group(1))}바이트)가 vrng 하한에 못 미친다 — 게이트가 자기 값을 거부한다"
    )


def test_reveal_refuses_when_there_is_no_commitment():
    """★fail-closed — 공약이 없으면 nonce 를 만들어 내지 않는다."""
    import asyncio

    class _Res:
        def first(self):
            return None

    class _DB:
        async def execute(self, *_a, **_k):
            return _Res()

    with pytest.raises(ValueError) as e:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            cs.reveal_nonce(_DB(), "subscription", "x"))
    assert "공약이 없습니다" in str(e.value), str(e.value)
