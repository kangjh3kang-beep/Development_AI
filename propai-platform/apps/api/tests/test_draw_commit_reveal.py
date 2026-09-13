"""★**사전 공약 없는 추첨은 거부된다** — 그리고 공고번호로는 결과를 예측할 수 없다.

## 무엇이 뚫려 있었나 (실측 2026-09-13)

`run_draw` 의 seed 는 이랬다:

    seed = seed or ann.announce_no or str(announcement_id)

  ①-a **호출자가 `seed` 를 보낼 수 있었다** — `POST /subscription/{ann}/draw` 의 body 로.
       동점자 순서가 seed 로 정해지므로, 오프라인에서 원하는 당첨자가 나올 때까지 굴린 뒤
       제출하면 **결과를 고를 수 있다.**
  ①-b 미지정이면 seed 가 **공고번호**였다. 공고번호는 공개값이다 —
       ***누구나 추첨 전에 당첨자를 계산할 수 있었다.***

★그런데 이 결함은 **아무 신호도 내지 않는다.** 추첨은 정상적으로 끝나고 기록도 남는다.
  그래서 자동 락이 필요하다.
"""

from __future__ import annotations

import inspect

import pytest

from app.services.sales.draw import vrng
from app.services.sales.subscription import engine as sub_engine

NONCE = "7c" * 32


def test_caller_cannot_supply_a_seed():
    """★`run_draw` 가 **seed 를 더는 받지 않는다** — 시그니처로 잠근다.

    인자가 남아 있으면 누군가 다시 넘긴다. 「안 쓴다」는 주석은 잠금이 아니다.
    """
    params = list(inspect.signature(sub_engine.run_draw).parameters)
    assert "seed" not in params, f"seed 인자가 아직 있다: {params}"
    # 공허 방지 — 이 함수를 실제로 읽고 있는가
    assert "announcement_id" in params, params


def test_endpoint_does_not_forward_body_seed():
    """호출부(엔드포인트)도 body 의 seed 를 넘기지 않는다 — 시그니처만 고치면 호출부가 남는다."""
    import pathlib

    src = pathlib.Path(
        sub_engine.__file__).parents[3] / "api" / "endpoints" / "sales" / "lifecycle_p5.py"
    code = "\n".join(
        ln for ln in src.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#"))
    assert "run_draw(" in code, "대조군 실패 — 호출부를 못 읽었다"
    assert '.get("seed")' not in code, "엔드포인트가 여전히 body.seed 를 넘긴다"


def test_announce_no_is_no_longer_a_seed_source():
    """★**공고번호 폴백이 사라졌다** — 실행되는 줄에서 확인(주석은 경위를 적고 있으므로 배제)."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(sub_engine.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_draw")
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert "rules" in attrs, "대조군 실패 — run_draw 본문을 못 읽었다"
    assert "announce_no" not in attrs, (
        "run_draw 가 아직 announce_no 를 읽는다 — 공개값이 추첨 키가 된다"
    )


class _Ann:
    def __init__(self, rules):
        import uuid
        self.id = uuid.uuid4()
        self.status = "OPEN"
        self.announce_no = "2026-PUBLIC"
        self.rules = rules
        self.round_id = None
        self.contract_end = None


def _run_with(rules):
    """공약 상태만 바꿔 `run_draw` 초입을 태운다(DB 없이 seed 결정 구간까지)."""
    import asyncio

    class _Res:
        def __init__(self, obj):
            self._o = obj

        def scalar_one_or_none(self):
            return self._o

        def scalars(self):
            return []

        def first(self):
            return None

    class _DB:
        async def execute(self, *_a, **_k):
            return _Res(ann)

        async def flush(self):
            return None

    ann = _Ann(rules)
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        sub_engine.run_draw(_DB(), object(), ann.id))


def test_draw_without_commitment_is_refused():
    """★**공약이 없으면 추첨하지 않는다**(fail-closed).

    종전에는 조용히 공고번호로 떨어졌다 — ***예측 가능한 값으로 조용히 떨어지는 것이
    가장 나쁜 실패다***(아무도 모른다).
    """
    with pytest.raises(ValueError) as e:
        _run_with({})
    msg = str(e.value)
    # ★★**두 갈래를 한 신호로 보지 않는다**(2026-09-13 변이 실측).
    #   종전엔 `"공약" in msg` 만 봤는데, 「공약이 **없습니다**」와 「공약이 **일치하지 않습니다**」가
    #   **둘 다 「공약」을 포함**해서 부재 가드를 지워도 **초록**이었다(변이 SURVIVED).
    #   ***한 신호가 두 사건을 덮으면 어느 것이 고장났는지 못 가른다.***
    assert "공약이 없습니다" in msg, msg
    assert "일치하지" not in msg, f"부재가 아니라 불일치로 떨어졌다 — 부재 가드가 죽었다: {msg}"


def test_tampered_nonce_is_refused():
    """★공약 이후 nonce 를 바꾸면 거부된다 — 서버가 뽑아 보고 갈아치우는 것을 막는다."""
    good = vrng.commitment(NONCE)
    with pytest.raises(ValueError) as e:
        _run_with({"draw_commit": good, "draw_nonce": "aa" * 32})
    msg = str(e.value)
    assert "일치하지" in msg, msg
    assert "공약이 없습니다" not in msg, f"불일치가 아니라 부재로 떨어졌다: {msg}"


def test_matching_commitment_passes_the_gate():
    """★**두 모집단** — 옳은 공약은 게이트를 **통과**한다(거부만 단언하면 「항상 거부」도 통과한다).

    게이트를 넘은 뒤 DB 가 가짜라 다른 예외로 끝나는 것은 정상이다 —
    여기서 보는 것은 **공약 검증이 통과했는가** 하나다.
    """
    rules = {"draw_commit": vrng.commitment(NONCE), "draw_nonce": NONCE}
    try:
        _run_with(rules)
    except ValueError as e:
        assert "공약" not in str(e.value), f"옳은 공약인데 게이트에서 막혔다: {e}"
    except Exception:
        pass  # DB 가짜로 인한 다른 실패 — 이 테스트의 관심사가 아니다
