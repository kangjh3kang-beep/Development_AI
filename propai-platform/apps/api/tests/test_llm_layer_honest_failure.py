"""LLM 계층이 **조용히 죽는 것**을 막는 락 (2026-08-21).

## 무엇이 있었나

종합 부지분석 화면이 *"AI 종합은 일시적으로 미제공"* 이라고 말하고 있었다.
**일시적이 아니었다.** 라이브 로그에 결정론적 영구 실패가 둘 있었다.

| 실패 | 내용 |
|---|---|
| `temperature` 400 | `claude-opus-4-8`(사용자가 고른 **프리미엄**)이 그 인자를 거부 |
| `list indices ... not str` | `parse_llm_json` 이 배열을 줬는데 호출부가 dict 를 가정 |

라이브 실측(2026-08-21): `opus-5`·`sonnet-5`·`opus-4-8` → temp 지정 시 **FAIL**,
미지정 시 **OK**. `sonnet-4-6`·`haiku-4-5` → 지정해도 OK.
**신세대일수록 거부**한다. 즉 모델 목록을 표로 들고 있으면 그 표가 곧 상한이 된다.

## 이 파일이 잠그는 것

1. temperature 거부를 **런타임에 감지**해 그 인자 없이 재시도하는가
2. 그 감지가 **너무 넓지 않은가**(다른 오류까지 삼키면 진짜 장애가 또 조용해진다)
3. LLM 이 dict 가 아닌 값을 줘도 죽지 않고 **정직한 폴백**을 내는가
4. **"일시적"·"잠시 후 다시 시도" 같은 거짓 단정**이 실행 코드에 다시 들어오지 않는가
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.ai.llm_provider import _TemperatureAwareChat


class _FakeChat:
    """temperature 를 받으면 400 을 던지는 모델을 흉내낸다."""

    def __init__(self, temperature=None, *, reject: bool = True, other_error: bool = False):
        self.temperature = temperature
        self._reject = reject
        self._other = other_error
        self.calls = 0

    async def ainvoke(self, *_a, **_k):
        self.calls += 1
        if self._other:
            raise RuntimeError("network unreachable")
        if self._reject and self.temperature is not None:
            raise RuntimeError(
                "Error code: 400 - {'type': 'error', 'error': "
                "{'type': 'invalid_request_error', 'message': '`temperature` is deprecated'}}"
            )
        return "OK"

    def invoke(self, *_a, **_k):
        self.calls += 1
        if self._other:
            raise RuntimeError("network unreachable")
        if self._reject and self.temperature is not None:
            raise RuntimeError("Error code: 400 - `temperature` is deprecated")
        return "OK"


def _factory(store: list):
    def build(temp):
        c = _FakeChat(temperature=temp)
        store.append(c)
        return c
    return build


@pytest.mark.asyncio
async def test_temperature_를_거부하면_그_인자_없이_재시도한다() -> None:
    built: list[_FakeChat] = []
    chat = _TemperatureAwareChat(_factory(built), 0.3, "fake-model")

    assert await chat.ainvoke("hi") == "OK"

    # 첫 객체는 temperature 를 갖고 실패했고, 두 번째는 없이 성공해야 한다.
    assert len(built) == 2, f"재시도용 객체가 만들어지지 않았다: {len(built)}개"
    assert built[0].temperature == 0.3
    assert built[1].temperature is None, "재시도인데 temperature 를 또 넘겼다"


@pytest.mark.asyncio
async def test_두번째_호출부터는_처음부터_temperature_없이_간다() -> None:
    """★재시도가 매 호출마다 반복되면 요청이 2배가 된다. 한 번 배웠으면 기억해야 한다."""
    built: list[_FakeChat] = []
    chat = _TemperatureAwareChat(_factory(built), 0.3, "fake-model")
    await chat.ainvoke("hi")
    n_after_first = len(built)

    await chat.ainvoke("hi again")
    assert len(built) == n_after_first, "두 번째 호출에서 또 재시도했다(학습하지 않았다)"


@pytest.mark.asyncio
async def test_temperature_와_무관한_오류는_삼키지_않는다() -> None:
    """★감지가 넓으면 진짜 장애가 다시 조용해진다 — 그게 이 사고의 근본이었다.

    ★★이 케이스의 첫 판은 **예외 타입만** 봤다. 그래서 감지를 `return True` 로 넓히는
      변이가 **통과했다** — 재시도해도 같은 예외가 다시 나므로 타입만으로는 구분이 안 된다.
      → **재시도를 시도했는지(객체를 다시 만들었는지)** 를 세어야 잡힌다.
    """
    built: list[_FakeChat] = []

    def build(temp):
        c = _FakeChat(temperature=temp, other_error=True)
        built.append(c)
        return c

    chat = _TemperatureAwareChat(build, 0.3, "fake-model")
    with pytest.raises(RuntimeError, match="network unreachable"):
        await chat.ainvoke("hi")

    assert len(built) == 1, (
        "temperature 와 무관한 오류인데 재시도했다 — 감지 조건이 너무 넓다. "
        f"만들어진 객체 {len(built)}개(기대 1개)"
    )


@pytest.mark.asyncio
async def test_temperature_를_받는_모델은_재시도하지_않는다_대조군() -> None:
    """★위 락들은 *무조건 재시도하는* 래퍼에서도 초록이다. 정상 경로를 함께 본다."""
    built: list[_FakeChat] = []

    def build(temp):
        c = _FakeChat(temperature=temp, reject=False)
        built.append(c)
        return c

    chat = _TemperatureAwareChat(build, 0.3, "fake-model")
    assert await chat.ainvoke("hi") == "OK"
    assert len(built) == 1, "정상 모델인데 재시도 객체를 만들었다"
    assert built[0].temperature == 0.3, "정상 모델의 temperature 를 버렸다"


# ──────────────────────────────────────────────────────────────
# 거짓 단정 폴백 재유입 방지 (전역)
# ──────────────────────────────────────────────────────────────

_API = pathlib.Path(__file__).resolve().parents[1]
_SERVICES = _API / "app" / "services"

# 재시도로 풀린다고 **단정**하는 표현. 사용자에게 보이는 문자열에 들어가면 안 된다.
_FALSE_TRANSIENT = ("일시적으로 제공되지 않", "일시적으로 미제공", "일시적으로 산출하지")

# 시간이 지나면 실제로 풀리는 것(쿼터·한도)은 예외다 — 그건 참말이다.
_ALLOW = {"coin_orders_service.py", "nearby_map_service.py", "llm_failure.py"}


def _string_literals(path: pathlib.Path) -> list[str]:
    """★주석이 아니라 **문자열 리터럴만** 본다. 주석에 사례를 적는 것은 막지 않는다
    (이 저장소는 재발 방지를 위해 주석에 실패 사례를 남기는 규율이 있다)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def test_거짓_일시장애_문구가_실행_문자열에_없다() -> None:
    files = [p for p in _SERVICES.rglob("*.py") if p.name not in _ALLOW]
    # ★공허 진리 방지 — 스캔 대상이 0이면 '위반 0'은 아무 의미가 없다.
    assert len(files) > 200, f"스캔 대상이 {len(files)}개뿐이다 — 경로가 틀렸다"

    위반 = []
    for p in files:
        for s in _string_literals(p):
            if any(bad in s for bad in _FALSE_TRANSIENT):
                위반.append(f"{p.relative_to(_API)}: {s[:70]}")

    assert not 위반, (
        "재시도로 풀린다고 **단정**하는 폴백 문구가 다시 들어왔다. "
        "영구 실패를 일시 장애로 위장해 장애를 숨긴다: " + str(위반)
    )


def test_판별기가_주석과_문자열을_가른다_대조군() -> None:
    """★위 락이 *아무것도 못 잡는 판별기*를 써도 초록이 되는 것을 막는다."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "probe.py"
        f.write_text(
            '# 일시적으로 미제공 — 주석이므로 잡히면 안 된다\n'
            'MSG = "AI 종합은 일시적으로 미제공"\n',
            encoding="utf-8",
        )
        lits = _string_literals(f)
        assert any("일시적으로 미제공" in s for s in lits), "문자열 리터럴을 못 잡는다"
        assert not any(s.startswith("# ") for s in lits), "주석을 문자열로 잘못 집었다"
