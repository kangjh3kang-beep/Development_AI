"""보류값 계약 — **부재의 사유를 코드로** 말한다.

## 왜 코드인가 (산문은 셀 수 없다)

이 저장소는 *무목업*(값을 못 구하면 정직 null)을 오래 지켜 왔다. 그런데 **왜 없는지**는
파일마다 다른 모양으로 적혀 있었다 — 실측(2026-08-25, `origin/main`):

    site_score_service          grade=None                     + grade_basis
    parcel_rights_survey        sell_claim_judgment="판정 보류"  + sell_claim_reason   ★센티널
    zoning/ordinance_conditional _bucket="undecidable"          + why
    sales/pricing/suggest       data_source="unavailable"      + note
    sales/admin/console         None                           + (주석뿐)
    decision_brief_service      —                              + reasons[]

**부재가 아니라 불일치**였다(§29). 어휘가 다섯 갈래라 **기계가 셀 수 없고**, 셀 수 없으면
새 표면이 생겨도 감시망에 들지 않는다.

## 표준 근거 (세 도메인이 같은 답에 도달해 있다)

- **HL7 FHIR `dataAbsentReason`** — 값이 없는 이유를 **코드**로(`unknown`·`masked`·
  `not-applicable`·`error`). 값과 사유는 **배타**다(값이 있으면 사유가 없다).
- **SDMX `OBS_STATUS`/`CONF_STATUS`** — `M`(존재 불가)와 `_Z`(해당 없음)를 **구분**하고,
  기밀 억제는 **별도 축**으로 둔다.
- **W3C PROV-O** — `wasDerivedFrom`/`wasGeneratedBy`. 출처는 **값이 있을 때도** 말한다.

공통 교훈: **null 은 그 자체로 모호하다** — unknown / not-applicable / withheld 중 무엇인지
알 수 없다. 그래서 표준들은 예외 없이 **값 옆에 사유를 코드로** 둔다.

## 계약

    X                    : 값 | None
    X_basis 또는 X_reason : str        # 사람이 읽는 문구
    X_absent             : 코드 | None  # ★X 가 None 일 때만 — 아래 닫힌 어휘

★**문구 키 이름은 강제하지 않는다.** 이 저장소에는 **두 관용이 다 살아 있다**(실측):
  · `_basis` **고유키 62** — *값의 출처*(`legal_basis`·`far_basis`·`price_basis`…) → PROV-O 결
  · `_reason` **고유키 32** — *왜 안 일어났나*(`skipped_reason`·`stop_reason`·`exclude_reason`
    ·`fallback_reason`…) → **보류에 의미상 더 맞는 계열**

  둘 중 무엇을 쓸지는 **국소 문맥**이 정한다. 강제할 것은 **`_absent` 코드 하나**다 —
  기계가 세는 것은 그것이고, 문구는 사람이 읽는다.

  ★2026-08-25 자기정정: 처음엔 *"`_basis` 가 유일한 관용이고 `_withheld_reason` 은 이단아"*
    라고 판단했는데, 그건 **like-for-like 비교가 아니었다** — "내 키 이름이 몇 번 나오나"를
    "다른 키 이름들이 몇 번 나오나"와 비교했다. 고유키로 세니 두 관용이 **둘 다** 있었다.

★**센티널 금지** — 값 자리에 `"판정 보류"`·`"mixed_review_required"` 같은 문자열을 넣지
않는다. 소비처가 `x == "매도청구 가능"` 으로 비교하면 **조용히 거짓**이 된다(D7 과 같은 결함).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ABSENT_REASONS",
    "ABSENT_SHORT",
    "AMBIGUOUS",
    "AWAITING_INPUT",
    "INSUFFICIENT_COVERAGE",
    "MASKED_BY_SOURCE",
    "NOT_APPLICABLE",
    "SENTINEL_VALUES",
    "SINGLE_SOURCE",
    "SOURCE_UNAVAILABLE",
    "is_withheld",
    "validate_withheld_pair",
    "withheld",
]

# ── 닫힌 어휘 ───────────────────────────────────────────────────────────────
INSUFFICIENT_COVERAGE = "insufficient_coverage"  # 지표·표본이 하한 미달
SINGLE_SOURCE = "single_source"                  # 독립 추정 1개 — 교차검증 불가
SOURCE_UNAVAILABLE = "source_unavailable"        # 외부 원천 조회 실패·무응답 (FHIR error)
MASKED_BY_SOURCE = "masked_by_source"            # 원천이 가림 (FHIR masked)
AMBIGUOUS = "ambiguous"                          # 판정이 갈려 단일화 거부 (SDMX M)
NOT_APPLICABLE = "not_applicable"                # 이 대상엔 해당 없음 (SDMX _Z)
AWAITING_INPUT = "awaiting_input"                # 사용자 입력 대기 (FHIR not-asked)

#: 코드 → 사람이 읽는 짧은 뜻. **닫힌 어휘**다 — 여기 없는 코드는 계약 위반이다.
ABSENT_REASONS: dict[str, str] = {
    INSUFFICIENT_COVERAGE: "판정에 필요한 지표·표본이 하한에 미치지 못했습니다",
    SINGLE_SOURCE: "독립 추정이 하나뿐이라 교차검증이 성립하지 않습니다",
    SOURCE_UNAVAILABLE: "외부 원천을 조회하지 못했습니다(응답 없음·오류)",
    MASKED_BY_SOURCE: "원천이 값을 가려 제공하지 않습니다",
    AMBIGUOUS: "판정이 갈려 하나로 단일화하지 않았습니다",
    NOT_APPLICABLE: "이 대상에는 해당하지 않는 항목입니다",
    AWAITING_INPUT: "판정에 필요한 입력을 아직 받지 못했습니다",
}

#: 코드 → **표 한 칸에 들어갈 짧은 라벨**. 긴 문구(`ABSENT_REASONS`)와 **별개 축**이다 —
#: 칩·툴팁은 긴 것을, 표 칸은 짧은 것을 쓴다. 한 벌로 뭉치면 표가 무너지거나 칩이 뜻을 못 전한다.
#:
#: ★**키 집합은 `ABSENT_REASONS` 와 반드시 같다**(락이 양방향으로 강제한다). 왜냐하면 소비자가
#:   자기 목록으로 코드를 해석하다가 **생산자가 내는 코드를 못 덮는** 결함이 실재했기 때문이다:
#:
#:       생산자 realtx_report_service.py → not_applicable · insufficient_coverage · masked_by_source
#:       소비자(PDF·화면)                → not_applicable · masked_by_source · source_unavailable
#:
#:   `insufficient_coverage` 가 양쪽에서 `"—"` 로 떨어져 **사유가 소실**됐다. 목록은 곧 상한이다.
#:   ★처방은 "목록을 늘려라"가 아니라 **"덮지 않은 코드에도 말할 것이 있게 하라"** 다 —
#:   열 고유 문구는 소비자가 계속 덮되, 덮지 않으면 **여기로 떨어진다.**
#: ★문구 선정의 판단 하나를 여기 남긴다(실거래 단가 열에서 옮겨 왔다):
#:   `NOT_APPLICABLE` 을 **"해제"라고 쓰지 않는다.** 그 열에는 상태 열이 따로 있어 이미
#:   "해제"를 말하므로, 두 열이 같은 말을 하면 사용자가 얻는 정보가 0이 된다. 여기서 말할 것은
#:   **"왜 값이 없는가"** 이고 답은 "해당 없음" 이다. 이 계약은 화면 락 D14 가 **렌더 결과로**
#:   고정한다(문구를 못 박지 않고 «두 열이 다른 말을 한다» 를 본다 — 그래서 취약하지 않다).
ABSENT_SHORT: dict[str, str] = {
    INSUFFICIENT_COVERAGE: "표본부족",
    SINGLE_SOURCE: "교차검증불가",
    SOURCE_UNAVAILABLE: "조회실패",
    MASKED_BY_SOURCE: "원천미제공",
    AMBIGUOUS: "판정보류",
    NOT_APPLICABLE: "해당없음",
    AWAITING_INPUT: "입력대기",
}

#: 값 자리에 **들어가면 안 되는** 문자열(과거 센티널). 값은 `None` 이어야 한다.
SENTINEL_VALUES: frozenset[str] = frozenset({
    "판정 보류", "산출 보류", "미상", "N/A", "n/a",
    "mixed_review_required", "undecidable", "unavailable",
})


def withheld(
    code: str, text: str, *, field: str,
    text_key: str = "basis", text_field: str | None = None,
) -> dict[str, Any]:
    """보류 3종 세트를 만든다 — `{field: None, field_basis: text, field_absent: code}`.

    ★`text` 는 **왜 없는지 사용자에게** 말한다. 코드만으로는 화면에 못 쓴다.
    ★`code` 는 **기계가 센다**. 산문만 있으면 새 표면이 감시망에 들지 않는다.
    ★`text_key` 로 `_basis`/`_reason` 을 고른다 — 국소 관용을 존중한다(둘 다 저장소 idiom).
    """
    if text_key not in ("basis", "reason"):
        raise ValueError(f"문구 키는 basis|reason 만: {text_key!r}")
    # ★값 키와 사유 키의 **접두가 다를 수 있다**(실측: 값 `sell_claim_judgment` ↔
    #   사유 `sell_claim_reason`). 저장소를 헬퍼 편의에 맞추지 않는다 — 헬퍼가 받는다.
    _text_field = text_field or f"{field}_{text_key}"
    if code not in ABSENT_REASONS:
        raise ValueError(
            f"닫힌 어휘 밖 코드: {code!r} — 새 사유가 필요하면 ABSENT_REASONS 에 "
            f"뜻과 함께 추가하라(임의 문자열 금지). 현재 어휘: {sorted(ABSENT_REASONS)}"
        )
    if not (text or "").strip():
        raise ValueError(f"{field}: 보류에는 **사유 문구**가 있어야 한다(무언 보류 금지)")
    return {field: None, _text_field: text, f"{field}_absent": code}


def is_withheld(payload: dict[str, Any], field: str) -> bool:
    """`field` 가 보류 상태인가 — 값이 None 이고 사유 코드가 붙어 있는가."""
    if not isinstance(payload, dict):
        return False
    return payload.get(field) is None and bool(payload.get(f"{field}_absent"))


def validate_withheld_pair(
    payload: dict[str, Any], field: str, *, text_field: str | None = None,
) -> list[str]:
    """계약 위반을 **양방향**으로 찾는다. 위반 목록(빈 리스트면 정상)을 돌려준다.

    ★한쪽만 걸면 반대쪽이 무제한이 된다(§19) — 그래서 네 방향을 다 본다:
      ① 값이 None 인데 사유 코드가 없다        → 무언 보류
      ② 값이 있는데 사유 코드가 남아 있다        → 거짓 보류(발행했는데 보류라 말함)
      ③ 사유 코드가 닫힌 어휘 밖이다             → 셀 수 없는 사유
      ④ 값 자리에 **센티널 문자열**이 들어 있다  → 판정이 아닌 것을 판정이라 말함
    """
    if not isinstance(payload, dict) or field not in payload:
        return []
    v, code = payload.get(field), payload.get(f"{field}_absent")
    # ★문구는 `_basis` 또는 `_reason` 어느 쪽이든 받는다(두 관용이 다 살아 있다).
    basis = (payload.get(text_field) if text_field else None) \
        or payload.get(f"{field}_basis") or payload.get(f"{field}_reason")
    out: list[str] = []
    if isinstance(v, str) and v.strip() in SENTINEL_VALUES:
        out.append(f"{field}: 값 자리에 센티널 문자열 {v!r} — 값은 None, 사유는 {field}_absent")
    if v is None and not code:
        out.append(f"{field}: 값이 없는데 **사유 코드가 없다**({field}_absent 누락)")
    if v is not None and code:
        out.append(f"{field}: 값이 있는데 보류 사유가 남아 있다({field}_absent={code!r})")
    if code and code not in ABSENT_REASONS:
        out.append(f"{field}: 닫힌 어휘 밖 사유 코드 {code!r}")
    if v is None and not (basis or "").strip():
        out.append(
            f"{field}: 보류인데 **사유 문구가 없다**"
            f"({field}_basis · {field}_reason 둘 다 비어 있음)"
        )
    return out
