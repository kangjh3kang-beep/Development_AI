"""**조건부 법정 상한** — 법정상한은 부지 조건에 따라 올라갈 수 있다.

【왜 이 파일이 필요한가 — 2026-08-19 실측】
`far_tier_service` 는 실효 한도를 `min(법정상한, 조례값)` 으로 낸다. 그래서 조례가 정한
**완화값**(예: 자연녹지 건폐율 30%)을 아무리 정확히 파싱해도, 법정상한 20% 에 다시 깎여
**화면에 도달하지 못한다.**

그런데 국토계획법은 그 상한 자체를 **조건부로 열어 둔다**:

> **제75조의3제2항** 성장관리계획구역에서는 **제77조제1항에도 불구하고** 다음 각 호의 구분에
> 따른 범위에서 성장관리계획으로 정하는 바에 따라 … **조례로 정하는 비율까지 건폐율을
> 완화하여 적용할 수 있다.**
>   1. 계획관리지역: 50퍼센트 이하
>   2. 생산관리지역·농림지역 및 대통령령으로 정하는 녹지지역: 30퍼센트 이하
>
> **제3항** 성장관리계획구역 내 **계획관리지역**에서는 제78조제1항에도 불구하고
> **125퍼센트 이하**의 범위에서 … 용적률을 완화하여 적용할 수 있다.
>
> **시행령** — "대통령령으로 정하는 녹지지역"이란 **자연녹지지역과 생산녹지지역**을 말한다.

(전부 법제처 DRF 원문 확인 — 국토계획법 MST=284013 · 시행령 MST=287269)

【★그러나 자동 적용하지 않는다 — 조건이 셋인데 우리는 둘만 안다】
완화가 실제로 성립하려면
  ① **성장관리계획구역 지정**   ← VWorld 토지이용계획으로 **측정 가능**
  ② **성장관리계획이 건폐율·용적률을 정할 것**(법 제75조의3제1항제2호)
     ← 우리에게 **원천이 없다**(계획 본문 미보유)
  ③ **조례가 정한 비율**        ← 조례 파서로 **측정 가능**
②를 모르는 채 값을 올리면, 근거 없는 숫자를 그럴듯하게 만들어 내는 것이다(날조).
그래서 이 모듈은 **상한을 열어 줄 뿐 적용하지 않는다** — 소비처는 이것을
"여기까지 가능하다(계획 본문 확인 필요)"로 표시하고, 실효값은 보수적으로 유지한다.

★이름 함정: `성장관리권역`(수도권정비계획법)은 **완화 근거가 아니다**. 판별은
`district_regime.is_growth_management_plan` 단일출처로만 한다(PR #703 참조).
"""

from __future__ import annotations

from typing import Any

from app.services.zoning.district_regime import is_growth_management_plan

# 법 제75조의3제2항 각 호 — 성장관리계획구역에서 완화 가능한 **건폐율 상한**.
GROWTH_MGMT_BCR_CEILING: dict[str, int] = {
    "계획관리지역": 50,      # 제1호
    "생산관리지역": 30,      # 제2호
    "농림지역": 30,          # 제2호
    "자연녹지지역": 30,      # 제2호(시행령이 정한 녹지지역)
    "생산녹지지역": 30,      # 제2호(시행령이 정한 녹지지역)
}

# 법 제75조의3제3항 — **계획관리지역에 한해** 용적률 완화.
GROWTH_MGMT_FAR_CEILING: dict[str, int] = {
    "계획관리지역": 125,
}

_LEGAL_BASIS_BCR = "국토의 계획 및 이용에 관한 법률 제75조의3제2항(성장관리계획구역 건폐율 완화)"
_LEGAL_BASIS_FAR = "국토의 계획 및 이용에 관한 법률 제75조의3제3항(성장관리계획구역 용적률 완화)"


def resolve_conditional_ceiling(
    zone_type: str | None, districts: Any
) -> dict[str, Any] | None:
    """부지 조건이 여는 **조건부 법정 상한**. 해당 없으면 None.

    Args:
        zone_type: 용도지역명(예: '자연녹지지역').
        districts: 토지이용계획 designation 목록(str[] 또는 dict[] — VWorld 계약 그대로).

    Returns:
        `{"bcr_ceiling_pct", "far_ceiling_pct", "condition", "legal_basis",
          "applied": False, "requires": [...]}` 또는 None.

        ★`applied: False` 는 장식이 아니다 — 이 값은 **가능 상한**이지 적용값이 아니라는
          계약을 소비처에 명시적으로 전달한다. 소비처가 이것을 실효값으로 쓰면 안 된다.
    """
    zone = (zone_type or "").strip()
    # ※변이감사 메모: 이 가드를 지워도 결과가 같다 — 빈 문자열은 아래 테이블 조회에서
    #   어차피 None 이 되어 같은 경로로 닫힌다(**이중 가드**). 조기 반환이 의도를
    #   읽기 쉽게 하므로 남기고, 락을 더 걸지 않는다(변이 점수 부풀리기 방지).
    if not zone:
        return None

    rows = districts if isinstance(districts, (list, tuple)) else []
    if not any(is_growth_management_plan(d) for d in rows):
        return None

    bcr = GROWTH_MGMT_BCR_CEILING.get(zone)
    far = GROWTH_MGMT_FAR_CEILING.get(zone)
    if bcr is None and far is None:
        # 구역 안이어도 **완화 대상 용도지역이 아니면** 열리지 않는다(법 제2항 각 호 한정).
        return None

    basis = [b for b, v in ((_LEGAL_BASIS_BCR, bcr), (_LEGAL_BASIS_FAR, far)) if v is not None]
    return {
        "condition": "성장관리계획구역",
        "zone_type": zone,
        "bcr_ceiling_pct": bcr,
        "far_ceiling_pct": far,
        "legal_basis": basis,
        # ★적용하지 않는다 — 아래 요건을 우리가 확인할 수 없다.
        "applied": False,
        "requires": [
            "성장관리계획 본문에 건폐율·용적률이 정해져 있을 것(법 제75조의3제1항제2호)",
            "지자체 조례가 그 비율을 정하고 있을 것(법 제75조의3제2항·제3항)",
        ],
        "note": _build_note(zone, bcr, far),
    }


def _build_note(zone: str, bcr: int | None, far: int | None) -> str:
    """화면에 그대로 나가는 설명문 — **수치를 담되 적용을 주장하지 않는다**.

    ★조각을 조립한다(분기 아님). 종전엔 `bcr is not None else …` 로 갈랐는데, 테이블상
      **용적률만 열리고 건폐율은 안 열리는 용도지역이 없어** else 쪽이 **도달 불가한 죽은
      분기**였다(변이감사에서 그 줄들이 생존해 드러났다). 조립식은 그 죽은 코드를 없애고,
      나중에 한쪽만 열리는 용도지역이 추가돼도 자동으로 맞는다.
    """
    parts: list[str] = []
    if bcr is not None:
        parts.append(f"건폐율 상한이 {bcr}%")
    if far is not None:
        parts.append(f"용적률 상한이 {far}%")
    opened = " · ".join(parts)
    return (
        f"성장관리계획구역이라 {zone}의 법정 {opened} 까지 열릴 수 있습니다"
        "(제77조제1항·제78조제1항에도 불구하고). "
        "다만 실제 완화 폭은 성장관리계획 본문과 조례가 정하므로, "
        "그 두 가지를 확인하기 전까지는 적용값으로 쓰지 않습니다."
    )
