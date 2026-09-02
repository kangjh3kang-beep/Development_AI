"""법제처 DRF **XML 200-실패**를 조례 경로에서도 잡는다(형제 미스윕 봉합).

【무엇이 잘못돼 있었나 — 2026-08-28 실측】
법제처는 실패도 **HTTP 200** 으로 준다. 저장소에 그것을 잡는 `moleg_drf_envelope` 가 있고
형제 둘(`regulation_monitor`·`gosi_search_service`)은 쓰는데 — 그 검증기가
`isinstance(payload, dict)` 라 **JSON 전용**이고, 조례 조회는 `type=XML` 이라
**조례 경로만 무방비**였다. 광범위 `except Exception: return None` 이 그것을 삼켜
화면에는 *"조례를 확인하지 못해 법정상한 잠정 적용"* 으로 나갔다 — **낙관 방향 폴백**이다.

실측한 실패 봉투:
    <Response><result>사용자 정보 검증에 실패하였습니다.</result><msg>…</msg></Response>
실측한 정상 루트태그: 목록=<OrdinSearch> · 본문=<LawService>
"""

import pytest

from app.services.land_intelligence.ordinance_service import (
    _ORDIN_LIST_ROOTS,
    _ORDIN_TEXT_ROOTS,
)
from app.services.legal.moleg_drf_envelope import (
    MolegDrfError,
    raise_unless_expected_xml,
    xml_failure_reason,
)

# 라이브 실측 봉투(2026-08-28) — 문자열을 지어내지 않는다.
FAILURE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "    <Response>\n"
    "        <result>사용자 정보 검증에 실패하였습니다.</result>\n"
    "        <msg>OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 "
    "IP주소 및 도메인주소를 등록해 주세요.</msg>\n"
    "    </Response>\n"
)
OK_LIST_XML = '<?xml version="1.0"?><OrdinSearch><totalCnt>1</totalCnt></OrdinSearch>'
OK_TEXT_XML = '<?xml version="1.0"?><LawService><자치법규기본정보/></LawService>'


def test_failure_envelope_is_detected_with_its_reason() -> None:
    """탐지 — 200-실패를 잡고, **사람이 읽을 사유**까지 실어 준다(무음 금지)."""
    reason = xml_failure_reason(FAILURE_XML, expect=_ORDIN_LIST_ROOTS)
    assert reason is not None, "200-실패를 정상으로 통과시켰다"
    assert "사용자 정보 검증에 실패" in reason, f"사유가 유실됐다: {reason!r}"
    # ★공허 방지(변이 실측): 사유 추출을 지워도 폴백이 **본문 앞 120자를 그대로 echo** 해서
    #   위 단언만으로는 SURVIVED 였다. **추출된 형태**인지까지 본다 —
    #   원문 덤프면 XML 태그가 섞이고 폴백 문구가 붙는다.
    assert "<result>" not in reason, f"원문 덤프가 그대로 나왔다(추출 실패): {reason!r}"
    assert "기대 루트태그" not in reason, f"폴백 경로로 샜다(태그 추출이 안 됐다): {reason!r}"
    assert reason.startswith("사용자 정보 검증에 실패"), f"추출 형태가 아니다: {reason!r}"
    # ★`<msg>` 절반도 실려야 한다 — 그것이 **사용자가 할 수 있는 유일한 행동**을 담는다
    #   (독립 리뷰 실측: 태그 목록을 `("result",)` 로 줄이는 변이가 SURVIVED 였다).
    assert "IP주소 및 도메인주소를 등록" in reason, (
        f"조치 안내(<msg>)가 유실됐다 — 사유의 절반만 실렸다: {reason!r}"
    )


def test_reason_tags_derive_from_the_json_sibling() -> None:
    """★형제 정합 — XML 판이 태그를 **손으로 나열**하면 두 판이 갈린다(목록=상한)."""
    from app.services.legal.moleg_drf_envelope import _REASON_KEYS

    assert "result" in _REASON_KEYS and "msg" in _REASON_KEYS, _REASON_KEYS
    # 파생이 실제로 동작하는지 — 두 태그 값이 **모두** 사유에 들어간다.
    both = xml_failure_reason(
        "<Response><result>가</result><msg>나</msg></Response>", expect=("OrdinSearch",)
    )
    assert both is not None and "가" in both and "나" in both, both


def test_success_envelopes_are_not_flagged() -> None:
    """★특이도 — 정상 응답을 실패로 찍으면 **정상 조회를 막는다**(위양성도 결함)."""
    assert xml_failure_reason(OK_LIST_XML, expect=_ORDIN_LIST_ROOTS) is None
    assert xml_failure_reason(OK_TEXT_XML, expect=_ORDIN_TEXT_ROOTS) is None


def test_raises_typed_error_not_silent_none() -> None:
    """배선 — 조용한 `None` 이 아니라 **전용 예외**로 죽는다(호출부가 구별할 수 있게)."""
    with pytest.raises(MolegDrfError):
        raise_unless_expected_xml(FAILURE_XML, expect=_ORDIN_LIST_ROOTS)
    # 정상은 던지지 않는다.
    raise_unless_expected_xml(OK_LIST_XML, expect=_ORDIN_LIST_ROOTS)


def test_expected_roots_are_measured_not_guessed() -> None:
    """★추측 태그 금지 — 목록이 넓으면 **실패 봉투를 정상으로** 통과시킨다.

    라이브 실측값만 담겨야 한다(목록=OrdinSearch · 본문=LawService).
    """
    assert _ORDIN_LIST_ROOTS == ("OrdinSearch",)
    assert _ORDIN_TEXT_ROOTS == ("LawService",)
    # 실패 봉투의 루트(<Response>)가 기대목록에 **없어야** 탐지가 성립한다.
    assert "Response" not in _ORDIN_LIST_ROOTS + _ORDIN_TEXT_ROOTS


def test_empty_body_is_a_failure_not_success() -> None:
    """빈 본문(우리가 실측한 무효키 HTTP 404·0바이트 경로)도 성공으로 읽지 않는다."""
    assert xml_failure_reason("", expect=_ORDIN_LIST_ROOTS) is not None
    assert xml_failure_reason("   ", expect=_ORDIN_LIST_ROOTS) is not None
