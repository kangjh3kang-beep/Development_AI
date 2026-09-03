"""LLM 폴백을 **정직하게** 표기하는 공용 헬퍼.

## 왜 필요한가 (2026-08-21 실측)

종합 부지분석 화면이 *"AI 종합은 일시적으로 미제공"* 이라고 말하고 있었다.
**일시적이 아니었다.** 라이브 로그에는 두 개의 결정론적 영구 실패가 있었다.

  · `claude-opus-4-8`(사용자가 고른 **프리미엄** 모델)이 `temperature` 를 400 으로 거부
  · `parse_llm_json` 이 배열을 줬는데 호출부가 dict 를 가정 → `list indices ... not str`

둘 다 **매번** 실패한다. 그런데 화면이 "일시적"이라고 단정해 **아무도 이상하게 여기지
않았다**. 조용한 폴백이 장애를 숨긴 것이지, 장애가 조용했던 게 아니다.

## 규칙

1. **"일시적"이라고 단정하지 않는다.** 재시도로 풀릴지 우리는 모른다.
2. **사유를 함께 싣는다**(`failure_reason`). 화면·로그·원장 어디서든 원인이 보여야 한다.
3. **규칙기반 결과가 있으면 그것으로 답한다고 밝힌다** — 사용자는 무엇을 보고 있는지 알아야 한다.
"""

from __future__ import annotations

from typing import Any

# 사유 문자열 상한 — 로그·응답에 실릴 수 있으므로 과도한 길이를 막는다.
_REASON_MAX = 160


def failure_reason(exc: BaseException) -> str:
    """예외를 `타입: 메시지` 한 줄로 요약한다(길이 제한)."""
    return f"{type(exc).__name__}: {str(exc)[:_REASON_MAX]}"


def honest_llm_fallback(
    exc: BaseException,
    *,
    what: str,
    rule_based: bool = True,
) -> dict[str, Any]:
    """LLM 실패 시 **정직한** 폴백 페이로드를 만든다.

    Args:
        exc: 실제로 발생한 예외.
        what: 무엇을 생성하지 못했는지(예: "AI 종합", "AI 권리분석").
        rule_based: 규칙기반 결과로 대체 제공하는지 여부.

    Returns:
        `summary` + `failure_reason` 을 담은 dict. 호출부가 자기 스키마에 병합한다.
    """
    tail = " — 아래 규칙기반 결과로 답합니다." if rule_based else ""
    return {
        "summary": f"{what}을(를) 생성하지 못했습니다{tail}",
        "failure_reason": failure_reason(exc),
    }


# ── 실패 사유 분류 — "왜 실패했나"를 **집계 가능한 단위**로 ────────────────────────
#
# ★왜 필요한가(2026-08-24 설계). 지금 우리가 아는 것은 *"폴백률 80.77%"* 뿐이다. 그 안에
#   절단·타임아웃·스키마 위반이 섞여 있는데, 처방은 셋이 완전히 다르다.
#   **원인을 모르고 고치면 그 수정이 다음 조사의 잡음이 된다** — 그래서 개선보다 분포가 먼저다.
#
# ★분류표가 **새 실패 유형을 숨기지 못하게** 한다. 어느 것에도 안 맞으면 `other` 로 두되
#   `error_type`(예외 클래스명)을 **항상 함께** 싣는다. 그러면 `other` 안에서도 타입별로
#   셀 수 있어, 분류표가 낡아도 새 유형이 조용히 묻히지 않는다(목록형이 상한이 되는 것을 막는다).
_REASON_BY_TYPE = {
    # ★모델이 폐기된 실패 — 라이브 실측(2026-08-27): google 카탈로그 3모델이 전부
    #   404 "no longer available to new users". 종전엔 `other` 로 떨어져
    #   ①대시보드에서 「기타」로만 보이고 ②**재시도 대상**이 되어 볼 때마다 LLM 을 다시 샀다.
    "NotFoundError": "model_gone",
    "NotFound": "model_gone",
    "TimeoutError": "timeout",
    "ReadTimeout": "timeout",
    "ConnectTimeout": "timeout",
    "JSONDecodeError": "parse",
    "ConnectError": "network",
    "ConnectionError": "network",
    "RemoteProtocolError": "network",
    "KeyError": "shape",
    "IndexError": "shape",
    "AttributeError": "shape",
    "TypeError": "shape",
}

# 메시지로만 갈리는 것들(프로바이더가 예외 타입을 뭉뚱그려 던지는 경우가 많다).
# 앞에서부터 먼저 맞는 것을 쓴다 — 순서가 곧 우선순위다.
_REASON_BY_TEXT: tuple[tuple[str, tuple[str, ...]], ...] = (
    # ★`auth` 보다 **앞**에 둔다 — google 404 본문에 "not available" 같은 표현이 섞여도
    #   권한 문제로 오분류되지 않게. 순서가 곧 우선순위다(위 주석 참조).
    ("model_gone", ("404", "no longer available", "is not found", "not found for api",
                    "model not found", "does not exist", "has been deprecated",
                    "is not supported for")),
    ("rate_limit", ("rate limit", "rate_limit", "too many requests", "429")),
    ("overloaded", ("overloaded", "529", "capacity")),
    # ★실제 문구로 맞춘다 — Anthropic 은 `invalid x-api-key`(하이픈)를 쓴다.
    #   "api key" 만 넣었다가 그 실문구를 놓쳤다(테스트가 잡았다).
    ("auth", ("api key", "api_key", "api-key", "unauthorized", "authentication",
              "permission", "credit balance", "quota", "401", "403")),
    ("timeout", ("timeout", "timed out", "deadline")),
    ("content_filter", ("content filter", "content_filter", "safety", "refus")),
    ("parse", ("expecting value", "unterminated", "invalid json", "json")),
    ("bad_request", ("invalid_request", "400", "bad request")),
    ("network", ("connection", "dns", "ssl", "socket")),
)


def classify_failure(exc: BaseException) -> str:
    """예외 → **집계 가능한 사유 라벨**. 모르면 `other`(그때도 `error_type` 은 남는다).

    타입을 먼저 보고, 그다음 메시지를 본다. 메시지 매칭은 소문자 부분일치라
    프로바이더가 문구를 바꿔도 큰 범주는 유지된다.
    """
    name = type(exc).__name__
    by_type = _REASON_BY_TYPE.get(name)
    if by_type:
        return by_type
    text = str(exc).lower()
    for reason, needles in _REASON_BY_TEXT:
        if any(n in text for n in needles):
            return reason
    return "other"


# ── 재시도가 의미 있는 실패 / 없는 실패 ───────────────────────────────────────
#
# ★왜 가르나(2026-08-25). 실패한 분석은 캐시하지 않는다 — LLM 이나 프로바이더가 회복하면
#   다음 시도에 성공해야 하기 때문이다(자가치유). 그런데 그 설계는 **결정론적 실패**에서
#   대가를 치른다: 같은 문서가 같은 이유로 계속 실패하는데 **볼 때마다 LLM 을 다시 산다.**
#   등기 재발급 누수와 **같은 얼굴**이고, 축만 다르다(벤더 발급 → LLM 토큰).
#
# ★보수적으로 가른다 — **모르면 일시 실패로 본다.** 결정론으로 잘못 분류하면 회복을 막지만,
#   일시로 잘못 분류하면 돈만 조금 더 쓴다. 두 오류의 대가가 다르므로 안전한 쪽으로 기운다.
_DETERMINISTIC = frozenset({
    "parse",           # 잘린/비-JSON 응답 — 같은 입력이면 같은 결과
    "shape",           # 파싱은 됐는데 구조가 계약과 다름
    "bad_request",     # 요청 자체가 거부됨(모델·파라미터)
    "content_filter",  # 정책 거부 — 같은 본문이면 반복된다
    # ★모델이 폐기된 것은 **재시도해도 영원히 같다.** `other`(모르는 것)와 다르다 —
    #   우리는 이것을 **라이브에서 정확히 관측**했다(google 3모델 404, 2026-08-27).
    #   위 「모르면 일시로 본다」는 보수 규칙은 *모르는 것*에만 적용된다.
    #   여기 두지 않으면 죽은 모델을 고른 사용자가 **볼 때마다 LLM 을 다시 산다.**
    "model_gone",
})


def is_retry_worthwhile(reason: str) -> bool:
    """이 사유는 **다시 시도할 가치가 있는가**(=일시적일 수 있는가).

    `timeout`·`rate_limit`·`overloaded`·`network` 는 회복된다. `auth` 도 그렇다
    (키 교체·잔액 충전으로 풀린다). `other` 는 **모르는 것**이라 재시도 쪽에 둔다.
    """
    return reason not in _DETERMINISTIC
