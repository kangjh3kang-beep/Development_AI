"""시니어 추론 LLM 런너 — reasoner FinCoT 프롬프트로 narrative 생성(단일경유 메터링).

★LLM 계측 단일경유: BaseInterpreter._invoke를 경유해 토큰계측·키정상화·캐시·graceful 폴백을
모두 재사용한다(별도 LLM 호출 금지). 기본 off(use_llm=False)·키 미설정/실패 시 None(결정론 강등).
과금 게이트(enforce_llm_quota)는 라우터(db 보유)가 책임 — 본 런너는 호출만.
"""

from __future__ import annotations

from app.services.ai.base_interpreter import BaseInterpreter

_NARRATOR_SYSTEM = (
    "당신은 부동산개발 시니어 전문가 자문 종합기다. 주어진 IRAC 추론 체인(쟁점→규칙→적용→결론)과 "
    "정량 판정을 바탕으로 종합 판단(Go/조건부/No-Go)·핵심 리스크·충족 조건을 한국어로 간결히 서술하라. "
    "★제공된 근거(basis)만 사용하고 목록에 없는 법령·예규·판례·수치는 만들지 마라(없으면 '미확보'로 표기). "
    "AI 보조 의견이며 최종 책임은 면허 전문가임을 마지막에 한 줄로 고지하라. "
    'JSON {"narrative": "..."} 형식으로만 답하라.'
)


_DEBATE_SYSTEM = (
    "주어진 입장(적합/부적합)과 근거 제약을 따라 한국어로 간결히 논증하라. "
    "★제공된 근거(basis)만 사용하고 목록에 없는 법령·예규·판례·수치는 만들지 마라(없으면 '미확보'). "
    'JSON {"text": "..."} 형식으로만 답하라.'
)


class SeniorNarratorInterpreter(BaseInterpreter):
    """시니어 추론 서술 생성기 — BaseInterpreter 단일경유(계측·키가드·graceful)."""

    name = "senior_reasoning"
    expected_keys = ["narrative"]
    fallback_key = "narrative"  # JSON 파싱 실패 시 원문을 narrative로(graceful)
    max_tokens = 2048
    system_prompt = _NARRATOR_SYSTEM


class SeniorDebateInterpreter(BaseInterpreter):
    """적대 debate 단일 입장 논증기 — 동일 단일경유(계측 bucket=senior_reasoning)."""

    name = "senior_reasoning"
    expected_keys = ["text"]
    fallback_key = "text"
    max_tokens = 1536  # 입장당 간결 논증(narrative 2048보다 작게 — pro/con 2콜 합 통제)
    system_prompt = _DEBATE_SYSTEM


async def generate_senior_narrative(prompt: str, *, use_llm: bool) -> str | None:
    """FinCoT 프롬프트 → narrative(str) 또는 None.

    use_llm=False·빈 프롬프트·LLM 미설정/실패 → None(호출처가 결정론 구조로 강등).
    BaseInterpreter._invoke는 실패 시 빈 dict를 반환하므로 narrative 결측은 자연히 None.

    ★백로그①(2026-07-22): _invoke_or_empty(is_fallback_only 판정)는 여기 부적합하다 —
    fallback_key="narrative"가 유일한 expected_key라, 정상 응답도 폴백과 동일하게
    "narrative 키 하나만 채워짐"으로 보여 항상 폴백-only 판정이 나 전 응답이 강등된다.
    또한 narrative는 산문이 정상 출력이므로 parse_ok(원문이 JSON 객체로 파싱되는지)도
    부적합하다 — LLM이 시스템프롬프트의 JSON 지시를 어기고 순수 산문으로만 답하면
    (완전히 정상적인 답인데도) llm_json.parse_llm_json이 중괄호를 못 찾아 예외를 내
    parse_ok=False가 된다(오탐). 반면 is_truncated(stop_reason=max_tokens)는 실제
    응답이 중간에 잘렸는지만 가리키는 명확한 신호라 오탐이 없다 — 그래서 이 신호
    하나만으로 강등한다(절단 시 원문/부분 JSON 뭉치를 narrative로 노출 금지).
    """
    if not use_llm or not prompt.strip():
        return None
    interp = SeniorNarratorInterpreter()
    try:
        result = await interp._invoke(prompt)
    except Exception:  # noqa: BLE001 — 키 미설정·SDK 미존재·호출 실패 모두 결정론 강등
        return None
    if interp.last_truncated:
        return None
    narrative = (result.get("narrative") or "").strip()
    # ★R1 반영: 절단이 아니어도 "파싱 실패 + 중괄호로 시작"이면 깨진 JSON 덤프다(따옴표
    #   미이스케이프 등) — raw 노출 금지. 정상 산문(중괄호 미시작)은 parse_ok=False여도
    #   보존(산문=정상 출력인 인터프리터라 parse_ok 단독 강등은 오탐 — 위 docstring 참조).
    if not interp.last_parse_ok and narrative[:1] in ("{", "["):
        return None
    return narrative or None


async def _debate_side(prompt: str) -> str | None:
    """단일 입장 논증(graceful). 실패/빈결과/절단 → None(위 narrative와 동일 신호 설계)."""
    interp = SeniorDebateInterpreter()
    try:
        result = await interp._invoke(prompt)
    except Exception:  # noqa: BLE001 — 키 미설정·실패 시 해당 입장 생략(무중단)
        return None
    if interp.last_truncated:
        return None
    text = (result.get("text") or "").strip()
    # ★R1 반영: narrative 게이트와 동일 — 깨진 JSON 덤프(파싱 실패+중괄호 시작)만 차단.
    if not interp.last_parse_ok and text[:1] in ("{", "["):
        return None
    return text or None


async def generate_senior_debate(
    debate: dict[str, str] | None, *, use_llm: bool,
) -> dict[str, str] | None:
    """적대 debate(pro/con) 프롬프트 실행 → {pro, con} 논증. 둘 다 실패면 None(graceful).

    debate=reasoner의 {pro, con} 프롬프트. use_llm off/미발동/양측 실패 → None(결정론 구조 유지).
    """
    if not use_llm or not isinstance(debate, dict):
        return None
    pro = await _debate_side(debate.get("pro", ""))
    con = await _debate_side(debate.get("con", ""))
    out: dict[str, str] = {}
    if pro:
        out["pro"] = pro
    if con:
        out["con"] = con
    return out or None
