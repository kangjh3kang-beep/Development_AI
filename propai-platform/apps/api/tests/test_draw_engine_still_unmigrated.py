"""★**부채를 초록 안에서 보이게 둔다** — ②(동·호 즉석추첨)는 아직 VRNG 로 안 옮겼다.

독립 적대 리뷰(2026-09-13 · M-3)가 짚은 것:
  브랜치·계획서 제목은 *"동·호 추첨에 VRNG 적용"* 인데 **고친 것은 ①(청약 당첨자 추첨)뿐**이고
  ②`draw_engine.draw_for_candidate` 는 `random.Random(secrets.token_hex(8)).choice(...)` 가
  그대로다. pool 해시도 `sha256(...)[:16]` 으로 **64비트 절단**이다.

***커밋 메시지에만 적으면 드러나지 않는다.*** 그래서 `xfail(strict=True)` 로 둔다 —
②를 옮기는 순간 이 테스트가 **XPASS 로 빨개져** 「부채가 사라졌으니 이 파일을 지워라」고 말한다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[1] / (
    "app/services/sales/draw/draw_engine.py")


def _live_names() -> set[str]:
    """실행되는 줄의 이름만(주석·독스트링은 경위를 적고 있으므로 배제)."""
    tree = ast.parse(_ENGINE.read_text(encoding="utf-8"))
    return ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            | {a.name.split(".")[0] for n in ast.walk(tree)
               if isinstance(n, ast.Import) for a in n.names})


@pytest.mark.xfail(strict=True, reason=(
    "★부채: ②동·호 즉석추첨이 아직 `random.Random` 을 쓴다(VRNG 미적용). "
    "옮기면 이 테스트가 XPASS 로 빨개진다 — 그때 이 파일을 지워라."))
def test_draw_engine_uses_vrng():
    names = _live_names()
    assert "vrng" in names, "②가 vrng 를 쓰지 않는다"
    assert "random" not in names, "②가 아직 표준 random 을 쓴다"


def test_the_debt_is_real_and_specific():
    """★부채 서술이 **지금도 참인지** 확인한다 — 낡은 부채 표시는 거짓말이 된다."""
    names = _live_names()
    assert "random" in names, (
        "②가 더는 random 을 안 쓴다 — 이 부채 파일이 낡았다(지워라)"
    )
    src = _ENGINE.read_text(encoding="utf-8")
    assert "hexdigest()[:16]" in src, (
        "pool 해시 절단이 사라졌다 — 부채 서술을 갱신하라"
    )
