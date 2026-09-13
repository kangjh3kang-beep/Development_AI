"""★**남은 부채** — 추첨 **순번(seq)** 이 아직 「등록 순서」다.

즉석추첨은 순번대로 돌아가며 남은 세대 중 하나를 뽑는다. 그래서 **앞 순번이 선택지가 많다.**
그런데 `_next_seq` 는 `MAX(seq)+1` — ***명부에 먼저 올린 사람이 유리하다.***

계획서 §0-5 가 「순번도 같은 VRNG 로」라 적었고 `vrng.shuffle` 이 그 자리를 위해 있다.
아직 배선하지 않았으므로 **초록 안에서 보이게** 둔다 — 배선하면 XPASS 로 빨개져
「부채가 사라졌으니 이 파일을 지워라」고 말한다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[1] / (
    "app/services/sales/draw/draw_engine.py")


def _live_src() -> str:
    tree = ast.parse(_ENGINE.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "_next_seq"), None)
    assert fn is not None, "대조군 실패 — `_next_seq` 를 못 찾았다(락이 낡았다)"
    return ast.dump(fn)


@pytest.mark.xfail(strict=True, reason=(
    "★부채: 추첨 순번이 아직 등록 순서(MAX(seq)+1)다. `vrng.shuffle` 로 옮기면 "
    "XPASS 로 빨개진다 — 그때 이 파일을 지워라."))
def test_seq_is_drawn_not_insertion_order():
    assert "shuffle" in _live_src(), "순번이 아직 추첨되지 않는다"


def test_the_debt_is_still_real():
    """부채 서술이 **지금도 참인지** — 낡은 부채 표시는 거짓말이 된다."""
    assert "MAX(seq)" in _ENGINE.read_text(encoding="utf-8"), (
        "등록 순서 방식이 사라졌다 — 이 부채 파일이 낡았다(지워라)"
    )
