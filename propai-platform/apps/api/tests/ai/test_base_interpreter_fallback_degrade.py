"""BaseInterpreter 폴백-only 근원 봉합 회귀앵커(R1 R2, 전역 전파방지 HIGH).

배경(2026-07-22 라이브 실측): design_ingest/orchestrator.py._interpret_proposal에만 있던
"fallback_key 하나에 원문 텍스트 뭉치만 채워졌으면 정상 해석이 아니다" 가드가 design_v61.py의
/bim/generate 엔드포인트(CadBimIntegrationPanel "설계 해설" 패널이 실제로 쓰는 경로)에는 없어
raw JSON이 그대로 노출됐다(PR live-fix②). 리뷰(R1 R2)는 이 가드를 서브클래스마다 개별
호출하지 않고 한 곳(BaseInterpreter)에서 적용해 모든 소비처(40여 곳)가 자동으로 커버되게
하라고 요구했다.

★설계 결정(R2 2차 조율): 병행 작업(#424, 같은 base_interpreter.py의 _invoke/_parse_response
내부를 캐시오염 차단·절단 관측으로 재구조화)과의 충돌 표면을 줄이기 위해, 이 강등은 _invoke
"내부"가 아니라 **_invoke를 감싸는 별도 래퍼 메서드(_invoke_or_empty)**에서 수행한다.
서브클래스의 generate_interpretation은 `self._invoke(...)` 대신 `self._invoke_or_empty(...)`를
호출하도록 전환됐다(9개 이상 인터프리터, 1줄씩 — fallback_key가 빈 문자열인 blindspot/
brief_extractor는 애초에 무해(no-op)라 전환 대상에서 제외). 관심사 분리:
  - #424 = _invoke의 캐시에 무엇을 "저장"할지(캐시 오염 차단) — _invoke 내부 소유.
  - 이 파일(R2) = 호출자에게 무엇을 "반환"할지(원문 노출 차단) — _invoke 바깥의 얇은 층.
두 관심사는 상보적이라 중복이 아니며, _invoke 자체의 반환값(캐시에 무엇이 쌓이는지 포함)은
이 변경으로 전혀 달라지지 않는다(아래 test_invoke_itself_unchanged가 이를 고정한다).

이 파일은 세 가지를 고정한다:
1) is_fallback_only 진리표(폴백-only=True/부분키 유효=False/빈dict=True/fallback_key 공란=False/
   None 값 방어).
2) _invoke_or_empty가 실제로 절단(파싱 실패) 응답을 빈 dict({})로 강등해서 반환하는지(LLM을
   모킹해 _invoke→_parse_response의 실제 폴백 경로를 통과시킨다).
3) _invoke 자체는 이 변경으로 손대지 않았음을 고정(동일 폴백-only 응답에 대해 _invoke를 직접
   호출하면 여전히 원문 폴백 dict를 그대로 반환 — #424가 캐시 게이팅을 얹을 지점은 그대로 보존).
"""

from __future__ import annotations

import pytest

from app.services.ai.base_interpreter import BaseInterpreter, is_fallback_only

# ── ① is_fallback_only 진리표 ──────────────────────────────────────────────


def test_fallback_only_true_when_only_fallback_key_has_content():
    # 파싱 실패 폴백의 전형: fallback_key 하나에만 원문 텍스트가 있고 나머지 키는 없음.
    assert is_fallback_only({"design_overview": "절단된 원문 텍스트"}, "design_overview") is True


def test_fallback_only_false_when_other_key_has_content():
    # fallback_key 외에 실내용 섹션이 하나라도 있으면 정상 해석(폴백 아님).
    assert is_fallback_only(
        {"design_overview": "개요", "mass_strategy": "매스 전략 실내용"}, "design_overview"
    ) is False


def test_fallback_only_true_when_result_empty():
    # 완전히 빈 dict(LLM 실패 등)도 True — 호출자가 "빈 결과"로 동일 처리.
    assert is_fallback_only({}, "design_overview") is True


def test_fallback_only_false_when_fallback_key_blank():
    # fallback_key가 공란이면 판정 불가 → False(과차단 방지, 호출자가 별도 판단).
    assert is_fallback_only({"design_overview": "무엇이든"}, "") is False


def test_fallback_only_none_value_defended():
    # ★None 방어: str(None)="None"(비어있지 않음)으로 오판정되지 않아야 한다.
    # other_key 값이 None(실내용 없음)이면 여전히 폴백-only로 판정.
    assert is_fallback_only(
        {"design_overview": "원문", "mass_strategy": None}, "design_overview"
    ) is True


def test_fallback_only_other_key_blank_string_still_fallback():
    # 다른 키가 있어도 값이 공백뿐이면 실내용으로 치지 않는다.
    assert is_fallback_only(
        {"design_overview": "원문", "mass_strategy": "   "}, "design_overview"
    ) is True


# ── ② _invoke_or_empty 근원 봉합(실제 강등 경로) ──────────────────────────────


class _Probe(BaseInterpreter):
    name = "probe_fallback"
    expected_keys = ["design_overview", "mass_strategy"]
    fallback_key = "design_overview"
    max_tokens = 256
    system_prompt = "test"


class _FakeTruncatedResp:
    # 절단(파싱 실패) — fallback_key 하나에 원문 텍스트가 그대로 담겨야 할 응답.
    content = '{"design_overview": "설계 개요를 서술하던 중 문장이 중간에서 짤'
    response_metadata = {"stop_reason": "max_tokens"}
    usage_metadata: dict = {}


class _FakeOkResp:
    content = '{"design_overview": "개요", "mass_strategy": "매스 전략 실내용"}'
    response_metadata: dict = {}
    usage_metadata: dict = {}


class _FakeLLM:
    model = "fake"

    def __init__(self, resp):
        self._resp = resp

    async def ainvoke(self, messages, config=None):  # noqa: ARG002
        return self._resp


async def _noop_billing(*a, **k):  # noqa: ANN001
    return None


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.base_interpreter._record_llm_billing", _noop_billing, raising=True
    )
    monkeypatch.setenv("INTERP_REDIS_CACHE", "0")


async def test_invoke_or_empty_degrades_fallback_only_to_empty_dict(monkeypatch):
    monkeypatch.setattr(_Probe, "_get_llm", lambda self: _FakeLLM(_FakeTruncatedResp()), raising=True)
    itp = _Probe()
    result = await itp._invoke_or_empty("PROMPT")
    # ★핵심: raw 원문("짤"로 끝나는 미완성 문장)이 그대로 반환되지 않고 빈 dict로 강등된다.
    assert result == {}


async def test_invoke_or_empty_keeps_valid_multisection_result(monkeypatch):
    # 무회귀: 정상(다중 섹션 채워진) 결과는 그대로 통과한다.
    monkeypatch.setattr(_Probe, "_get_llm", lambda self: _FakeLLM(_FakeOkResp()), raising=True)
    itp = _Probe()
    result = await itp._invoke_or_empty("PROMPT")
    assert result == {"design_overview": "개요", "mass_strategy": "매스 전략 실내용"}


async def test_invoke_itself_unchanged_by_this_fix(monkeypatch):
    """★분업 경계 고정: _invoke를 "직접" 호출하면(래퍼를 거치지 않으면) 여전히 폴백-only 원문
    dict를 그대로 반환한다 — 이 R2 작업이 _invoke 내부(캐시·파싱)를 건드리지 않았다는 증거이자,
    #424(캐시 게이팅)가 손댈 지점이 이 변경으로 훼손되지 않았음을 고정하는 앵커."""
    monkeypatch.setattr(_Probe, "_get_llm", lambda self: _FakeLLM(_FakeTruncatedResp()), raising=True)
    itp = _Probe()
    result = await itp._invoke("PROMPT")
    assert result == {"design_overview": '{"design_overview": "설계 개요를 서술하던 중 문장이 중간에서 짤'}
