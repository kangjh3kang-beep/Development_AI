"""`emit_outbox` 의 **모든 호출부**가 화이트리스트에 있는가 — 전역 재발 방지.

## 왜 (R2 독립 적대 리뷰 2026-09-13 MAJOR-1 실측)

`emit_outbox` 는 `WHITELIST.get(event_type, set())` 로 payload 를 거른다.
**모르는 이벤트는 빈 집합**이 되어 payload 가 **통째로 버려지고**, 원장에는 **빈 행**만 남는다.

실제로 그렇게 났다: 「사후 감사자가 대조할 수 있게 원장에 남긴다」는 주석을 달고
`DrawCommitmentRevealed` 를 내보냈는데, 화이트리스트에 없어서 **`payload = {}`** 였다.
***그 수정은 그것이 대체한 `logger.info` 보다 나빴다*** — 로그는 적어도 값을 찍었다.

## 이 락의 축

이벤트 이름을 **손으로 나열하지 않는다** — `emit_outbox(...)` 호출부를 **AST 로 파생**해
첫 인자 리터럴을 모은다. 새 이벤트를 내보내는 순간 이 테스트가 **그 자리에서** 빨개진다.
***목록은 곧 상한이 된다 — 수집은 파생형으로.***
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.services.sales.harness.outbox import WHITELIST, emit_outbox

_ROOT = pathlib.Path(__file__).resolve().parents[1] / "app"

#: ★인자 위치를 **하드코딩하지 않고 시그니처에서 파생**한다.
#:   처음에 `1` 로 적었다가 조회기가 **0건**을 냈다(실제 위치는 2). 공허 방지 단언이 그것을 잡았다 —
#:   ***그 단언이 없었으면 「위반 0건」이라는 초록이 나왔을 것이다.***
_EVENT_ARG = list(inspect.signature(emit_outbox).parameters).index("event_type")


def _emitted_event_types() -> dict[str, set[str]]:
    """`{이벤트이름: {파일:줄, …}}` — 리터럴 첫 인자만(변수는 판정 불가라 따로 보고한다)."""
    found: dict[str, set[str]] = {}
    for f in _ROOT.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:                     # pragma: no cover — 파싱 불가 파일은 건너뛴다
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name != "emit_outbox" or len(n.args) <= _EVENT_ARG:
                continue
            ev = n.args[_EVENT_ARG]
            if isinstance(ev, ast.Constant) and isinstance(ev.value, str):
                found.setdefault(ev.value, set()).add(f"{f.name}:{n.lineno}")
    return found


def test_every_emitted_event_is_whitelisted():
    emitted = _emitted_event_types()
    # ★공허 방지 — 호출부를 하나도 못 찾았으면 이 테스트는 아무것도 안 잠근다.
    assert len(emitted) >= 3, f"emit_outbox 호출부를 거의 못 찾았다(조회기 사망?): {emitted}"
    missing = {ev: sorted(at) for ev, at in emitted.items() if ev not in WHITELIST}
    assert not missing, (
        "★화이트리스트에 없는 이벤트를 내보낸다 — payload 가 **통째로 버려져 빈 행**이 된다"
        f"(조용한 손실): {missing}. `outbox.WHITELIST` 에 허용 키를 추가하라"
    )


def test_whitelisted_keys_actually_survive_the_filter():
    """★**두 모집단** — 허용 키는 살아남고, 허용 밖 키는 버려지는지 같은 실행에서 본다.

    이게 없으면 「화이트리스트에 있다」가 「값이 실제로 실린다」를 함의하지 않는다.
    """
    allow = WHITELIST["DrawCommitmentRevealed"]
    payload = {k: f"v-{k}" for k in allow} | {"nonce": "비밀", "무관키": 1}
    clean = {k: v for k, v in payload.items() if k in allow}
    assert set(clean) == allow, f"허용 키가 버려졌다: {allow - set(clean)}"
    assert "nonce" not in clean, "★nonce 가 원장에 실리면 누구나 사전 계산한다"
    assert "무관키" not in clean


def test_draw_commitment_event_carries_the_audit_fields():
    """감사자가 `GET …/commitment` 의 공개값과 대조하려면 이 넷이 있어야 한다."""
    allow = WHITELIST["DrawCommitmentRevealed"]
    for k in ("commit_hash", "beacon_round", "participants_hash", "pool_hash"):
        assert k in allow, f"{k} 가 원장에 안 실린다 — 대조할 값이 없다"
    assert "nonce" not in allow, "★nonce 는 절대 원장에 싣지 않는다"
