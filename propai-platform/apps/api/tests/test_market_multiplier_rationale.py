"""시세보정계수 사유가 **계수로부터 통계를 역산하지 않는지** 잠근다(2026-09-07).

■ 무엇이 있었나
`comprehensive_analysis_service._get_market_multiplier` 와 형제 `land_price_estimator.
_market_multiplier` 가 **둘 다** 사용자 노출 문자열에 이렇게 썼다:

    f"{district} 지역의 공시지가 현실화율(약 {100/mult:.0f}%)을 반영한 보정계수 {mult}배..."

「현실화율」은 측정값이 아니라 **계수를 뒤집은 수**다(남양주 1.2 → 100/1.2 = 83.3 → "약 83%").
계수를 먼저 고르고 사유를 역산했으니 **산출물을 근거처럼** 말한 것이다.

★라이브 확증: 그 문자열은 `desk_appraisal` 응답의 `methods[0].rationale` 과
`evidence.evidence[1].basis`, 그리고 **제출용 감정평가 PDF** 에 실려 있었다. 그것도 「그밖의요인」
— 감정평가에서 **가액을 직접 곱하는 계수**의 근거로. 문구 결함이 아니라 **정당화가 거짓**이었다.

★저장소는 같은 금지를 자기 언어로 이미 적어 뒀고(`ai/market_interpreter.py` GROUNDING_RULE),
형제 검사(`field_audit/invariants/market_methodology.py`)는 같은 화면에 "실거래로 검증되지 않음"
배지를 상시 띄우고 있었다 — **두 표면이 모순**했고 더 구체적이라 더 신뢰받는 쪽이 거짓이었다.

■ 3축으로 잠근다(탐지·특이도·배선) — 하나만 잠그면 «항상 통과» 가 만점이 된다
  A 탐지 : 파생형 전수 — 등록 지역 **전 항목** + 폴백의 사유에 「현실화율 …%」류 수치 단정 없음
  B 특이도: 같은 검사기가 **옛 형태를 실제로 잡는지**(양성 대조) — 검사기 사망을 0건과 안 뭉친다
  C 배선 : 층위가 **서로 다른** 문자열을 내고 한정어·출처코드가 실제로 실리는지, 형제가 SSOT 를
           **행위로** 경유하는지(이름 존재가 아니라 동일 출력)

★산문 자체는 단언하지 않는다(§30). 계약은 **출처 판정용 코드**(`provenance`)와 **금지된 모양**이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.land_intelligence import market_multiplier as mm
from app.services.land_intelligence.comprehensive_analysis_service import (
    ComprehensiveAnalysisService,
)
from app.services.land_intelligence.land_price_estimator import (
    _market_multiplier,
    estimate_land_price,
)

# ★금지 형태 — 「현실화율」 뒤 가까운 곳에 숫자+% 가 오는 **수치 단정**.
#   낱말 자체를 금지하지 않는다(정정문·설명은 그 낱말을 써야 한다). 금지하는 것은 **수치 주장**이다.
_FABRICATED_RATE = re.compile(r"현실화율[^.\n]{0,20}?\d+\s*%")

# 양성 대조군 — 이 저장소가 실제로 내보내던 옛 문자열(축약). 검사기가 이걸 못 잡으면 죽은 것이다.
_OLD_FORM = "남양주시 지역의 공시지가 현실화율(약 83%)을 반영한 보정계수 1.2배를 적용하였습니다."

# 층위를 실제로 밟는 주소(픽스처가 모집단을 가르게 — §검증 규율 2).
_ADDR_DISTRICT = "경기도 남양주시 다산동 123-4"      # MAP 히트
_ADDR_REGION = "경기도 어딘가군 무등록면 1-1"          # MAP 미스 · REGION 히트
_ADDR_DEFAULT = "제주도아닌곳 미등록시 999"            # 둘 다 미스 → 폴백
_ADDR_UNKNOWN = ""                                     # 주소 자체가 없음


def _all_addresses() -> list[str]:
    """★파생형 수집 — 손으로 나열하지 않는다. 맵이 커지면 모집단이 자동으로 커진다.

    축은 **맵의 키**다(파일도 함수도 아니다 — §35 파생의 축을 명시하라).
    """
    return (
        [f"경기도 {k} 어딘가 1-1" for k in mm.MARKET_MULTIPLIER_MAP]
        + [f"{k} 어딘가 1-1" for k in mm.MARKET_MULTIPLIER_REGION]
        + [_ADDR_DEFAULT]
    )


# ─────────────────────────────────────────────────────────────
# 축 A — 탐지 (파생형 전수)
# ─────────────────────────────────────────────────────────────

def test_population_is_not_empty() -> None:
    """★공허 진리 가드 — 단언 **앞**에 둔다. 모집단이 비면 「위반 0」이 무의미하다."""
    assert len(mm.MARKET_MULTIPLIER_MAP) >= 40, len(mm.MARKET_MULTIPLIER_MAP)
    assert len(mm.MARKET_MULTIPLIER_REGION) >= 10, len(mm.MARKET_MULTIPLIER_REGION)
    assert len(_all_addresses()) >= 50


def test_no_fabricated_realization_rate_in_any_rationale() -> None:
    """전 층위 전수 — 사유(짧은형·문장형 **둘 다**)가 역산한 「현실화율 N%」를 담지 않는다."""
    offenders: list[str] = []
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        for label, text in (("short", v.short), ("sentence", v.sentence)):
            if _FABRICATED_RATE.search(text):
                offenders.append(f"{addr}[{label}] → {text}")
    assert not offenders, (
        "계수를 뒤집어 만든 「현실화율 N%」가 사유에 실렸다. 그 수는 측정값이 아니라 "
        "100/계수이며, 산출물을 근거처럼 말하는 것이다.\n  " + "\n  ".join(offenders[:8])
    )


def test_sibling_estimator_rationale_is_also_clean() -> None:
    """★형제도 같은 축으로 태운다 — 한쪽만 고치고 미러를 놓치는 일이 이 저장소에서 반복됐다."""
    offenders = [
        f"{a} → {r}"
        for a in _all_addresses()
        for _m, r in [_market_multiplier(a)]
        if _FABRICATED_RATE.search(r)
    ]
    assert not offenders, "형제(land_price_estimator)에 옛 형태가 남았다:\n  " + "\n  ".join(offenders[:8])


# ─────────────────────────────────────────────────────────────
# 축 B — 특이도 (양성 대조군: 검사기가 살아 있는가)
# ─────────────────────────────────────────────────────────────

def test_detector_actually_catches_the_old_form() -> None:
    """★대조군 없는 「0건」은 근거가 아니다. 옛 형태를 **실제로** 잡는지 증명한다.

    이것이 없으면 정규식을 `zzz` 로 바꿔도 축 A 가 전부 초록이다(«항상 통과» 가 만점).
    """
    assert _FABRICATED_RATE.search(_OLD_FORM), (
        "검사기가 죽었다 — 옛 형태를 못 잡는다. 이 상태의 「위반 0」은 무의미하다."
    )
    # 판별력 — 현재 문구는 잡히지 않아야 한다(위양성도 결함이다).
    assert not _FABRICATED_RATE.search(
        "남양주시에 대해 사전 설정된 지역 시세보정계수 1.2배를 적용했습니다."
    )
    assert not _FABRICATED_RATE.search(mm.UNVERIFIED_CAVEAT)


# ─────────────────────────────────────────────────────────────
# 축 C — 배선·계약
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("addr", "expected_scope"),
    [
        (_ADDR_DISTRICT, mm.SCOPE_DISTRICT),
        (_ADDR_REGION, mm.SCOPE_REGION),
        (_ADDR_DEFAULT, mm.SCOPE_DEFAULT),
        (_ADDR_UNKNOWN, mm.SCOPE_UNKNOWN),
        (None, mm.SCOPE_UNKNOWN),
    ],
)
def test_four_scopes_are_reachable_and_distinct(addr: str, expected_scope: str) -> None:
    """네 층위가 **실제로 밟히고** 각각 비어 있지 않은 사유를 낸다.

    ★`SCOPE_UNKNOWN` 은 독립 리뷰 m-2 로 생겼다 — 「주소를 모른다」를 「지역별 계수가
      미등록이다」로 뭉치면 **모름을 유효값으로 표현**하는 것이 된다(다른 주장이 된다).
    """
    v = mm.resolve_market_multiplier(addr)
    assert v.scope == expected_scope, f"{addr!r} → {v.scope}"
    assert v.short.strip() and v.sentence.strip()


def test_scope_rationales_differ_from_each_other() -> None:
    """네 층위가 서로 구별 가능해야 한다(사용자가 알 권리).

    ★알려진 생존(구멍 아님 · 변이 ⑦): REGION 문구의 앞 절을 DEFAULT 문구로 바꿔 넣어도 이
      락은 초록이다 — 뒤 절이 남아 문자열이 **여전히 서로 다르기** 때문이다. 즉 이 락은
      «문구가 옳은가» 가 아니라 «층위가 구별 가능한가» 를 잠근다. **의도된 경계다**:
      기계 판독 축(층위 코드)은 `test_scope_codes_are_pairwise_distinct` 가 잠그고,
      산문 문구 자체는 일부러 단언하지 않는다(§30 — 문구를 다듬을 때마다 깨지는 락은 곧 꺼진다).
    """
    for field in ("short", "sentence"):
        texts = {
            getattr(mm.resolve_market_multiplier(a), field)
            for a in (_ADDR_DISTRICT, _ADDR_REGION, _ADDR_DEFAULT, _ADDR_UNKNOWN)
        }
        assert len(texts) == 4, f"{field} 층위가 구별되지 않는다: {texts}"


def test_unverified_caveat_is_wired_into_every_scope() -> None:
    """★한정어가 **모든** 층위에 실제로 실린다 — 상수 선언만으로는 장식이다(§A-5)."""
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        assert mm.UNVERIFIED_CAVEAT in v.sentence, f"{addr} → 문장형 한정어 누락: {v.sentence}"
        assert mm.SHORT_CAVEAT in v.short, f"{addr} → 짧은형 한정어 누락: {v.short}"


def test_sibling_delegates_to_ssot_by_behavior_not_by_name() -> None:
    """★「부른다」가 아니라 **행위**를 태운다 — 두 소비처가 같은 입력에 같은 출력을 내는가.

    소스에 임포트가 있다는 것은 그 함수가 **불린다**는 뜻이 아니다(이 저장소의 반복 결함).
    ★자리에 맞는 표현을 고르는지까지 본다 — 수식 자리는 `.short`, 문장 자리는 `.sentence`.
    """
    svc = ComprehensiveAnalysisService.__new__(ComprehensiveAnalysisService)
    for addr in _all_addresses():
        v = mm.resolve_market_multiplier(addr)
        assert _market_multiplier(addr) == (v.multiplier, v.short), f"형제 갈림: {addr}"
        assert svc._get_market_multiplier(addr) == (v.multiplier, v.sentence), f"comprehensive 갈림: {addr}"


# ─────────────────────────────────────────────────────────────
# 회귀 락 — 이 PR 은 **값을 바꾸지 않는다**
# ─────────────────────────────────────────────────────────────

_EXPECTED_MAP = {
    "강남구": 1.8, "서초구": 1.7, "송파구": 1.6,
    "용산구": 1.6, "마포구": 1.5, "성동구": 1.5,
    "광진구": 1.4, "영등포구": 1.4, "동작구": 1.4,
    "강동구": 1.4, "관악구": 1.3, "구로구": 1.3,
    "금천구": 1.2, "노원구": 1.3, "도봉구": 1.2,
    "중랑구": 1.2, "강북구": 1.2, "성북구": 1.3,
    "은평구": 1.2, "서대문구": 1.3, "종로구": 1.5,
    "중구": 1.5, "양천구": 1.3, "강서구": 1.3,
    "성남시": 1.4, "분당": 1.5, "판교": 1.6,
    "수원시": 1.3, "용인시": 1.3, "화성시": 1.2,
    "고양시": 1.3, "일산": 1.3, "의정부시": 1.2,
    "남양주시": 1.2, "구리시": 1.3, "파주시": 1.1,
    "양주시": 1.1, "안양시": 1.3, "안산시": 1.2,
    "시흥시": 1.2, "김포시": 1.2, "광명시": 1.4,
    "하남시": 1.4, "부천시": 1.2, "광주시": 1.2,
    "해운대구": 1.4, "수영구": 1.3, "연수구": 1.3,
    "송도": 1.4,
}

_EXPECTED_REGION = {
    "서울특별시": 1.4, "서울": 1.4, "경기도": 1.2,
    "경기": 1.2, "인천광역시": 1.2, "인천": 1.2,
    "부산광역시": 1.2, "부산": 1.2, "대구광역시": 1.15,
    "대전광역시": 1.15, "광주광역시": 1.1, "울산광역시": 1.15,
    "세종특별자치시": 1.2, "제주특별자치도": 1.15,
}


def test_full_multiplier_table_is_frozen_including_order() -> None:
    """★전수 락 — 표의 모든 항목 **그리고 순서**를 독립 오라클로 못 박는다.

    ★순서가 계약인 이유(2026-09-27 정정 · 독립 리뷰 M-1): `resolve_market_multiplier` 는
      `for k in MAP: if k in addr` 로 **첫 매칭이 이긴다**. 그런데 `dict ==` 는 **순서를 무시**한다.
      리뷰어가 `"연수구": 1.3, "송도": 1.4` 를 뒤집는 변이를 넣어 락 218건을 **전부 생존**시켰다 —
      「인천광역시 연수구 송도동」의 계수가 1.3 → 1.4 로 바뀌어 **토지가액이 +7.7%** 되는데도.
      ⇒ `list(items())` 로 비교해 순서를 계약에 넣는다(파이썬 dict 리터럴은 순서 보존).

    이 PR 의 계약은 "계수는 바꾸지 않는다" 이므로 표 전체가 계약이다. 계수를 바꾸려면 이 표도
    함께 고쳐야 하고, 그것이 **의도된 마찰**이다 — 이 표는 토지가액을 움직인다.
    """
    assert list(mm.MARKET_MULTIPLIER_MAP.items()) == list(_EXPECTED_MAP.items())
    assert list(mm.MARKET_MULTIPLIER_REGION.items()) == list(_EXPECTED_REGION.items())
    assert len(mm.MARKET_MULTIPLIER_MAP) == 49
    assert len(mm.MARKET_MULTIPLIER_REGION) == 14


def test_first_match_wins_for_overlapping_keys() -> None:
    """★순서 계약을 **행위로** 태운다 — 상수 비교만 하면 락이 장식이 된다.

    「연수구」와 「송도」는 같은 주소에 둘 다 걸린다. 어느 쪽이 이기는지가 금액을 정한다.
    """
    overlapping = "인천광역시 연수구 송도동 1"
    assert "연수구" in overlapping and "송도" in overlapping  # 두 키가 실제로 겹치는가(공허 방지)
    assert mm.resolve_market_multiplier(overlapping).multiplier == 1.3


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("서울특별시 강남구 역삼동 1-1", 1.8),
        ("경기도 남양주시 다산동 123-4", 1.2),
        ("경기도 성남시 분당구 1-1", 1.4),
        (_ADDR_REGION, 1.2),
        (_ADDR_DEFAULT, 1.2),
        (_ADDR_UNKNOWN, 1.2),
    ],
)
def test_coefficients_are_unchanged(addr: str, expected: float) -> None:
    """계수는 **불변**이다. 진짜 현실화율을 잴 표본이 없으므로 값은 손대지 않았다 —
    근거 없이 값을 바꾸는 것은 이 PR 이 고치려는 바로 그 죄의 반복이다.
    """
    assert mm.resolve_market_multiplier(addr).multiplier == expected


def test_class_attribute_aliases_point_at_the_same_ssot_objects() -> None:
    """★별칭이 **복사본이 아니라 같은 객체**여야 SSOT 가 갈라지지 않는다."""
    assert ComprehensiveAnalysisService.MARKET_MULTIPLIER_MAP is mm.MARKET_MULTIPLIER_MAP
    assert ComprehensiveAnalysisService.MARKET_MULTIPLIER_REGION is mm.MARKET_MULTIPLIER_REGION


# ─────────────────────────────────────────────────────────────
# ★출처 판정용 **코드**를 잠근다 (독립 리뷰 M-2·M-3)
#
#   왜 문구가 아니라 코드인가: 종전 락은 `(검증된|확인된|실측된)\s*현실화율` 이라 **낱말
#   「현실화율」이 반드시 있어야** 걸렸다. 리뷰어가 한정어를
#   `"국토교통부 실거래가 통계로 산출된 지역 계수입니다"` 로 바꾸는 변이를 넣자 **21건 전부 초록**
#   이었다 — 즉 이 PR 이 고친 «없는 출처를 지어낸다» 가 **다른 낱말로 그대로 재발 가능**했다.
#   ★대리 변수(어휘)를 잠그면 속성(출처 주장)은 안 잠긴다.
#   ⇒ 형제 선례를 따른다: `field_audit/invariants/market_methodology.py` 가 같은 이유로
#     표시 문구와 분리된 `source_kind` 를 도입했다. 여기서는 `provenance` 다.
# ─────────────────────────────────────────────────────────────

def test_provenance_code_literal_is_pinned() -> None:
    """★상수를 **리터럴로 못 박는다** — 자기 자신과 비교하면 아무것도 안 잠긴다.

    ★내가 이 자리에서 같은 실수를 두 번 했다(2026-09-07): M-2 는 «한정어를 자기 상수로 단언해
      정반대 뜻으로 바꿔도 통과» 였고, 그것을 고치려고 넣은 `provenance` 락 자신이
      **또 자기 상수 비교**였다. 변이 `PROVENANCE_UNVERIFIED_PRESET = "VERIFIED_MARKET_DATA"` 가
      31건 전부를 통과시켰다. ⇒ 안정 식별자는 **값을 못 박아야** 계약이 된다
      (형제 선례: `market_methodology._OFFICIAL_PRICE_SOURCE_KIND = "OFFICIAL_LAND_PRICE"`).
      값을 바꾸려면 이 줄을 함께 고쳐야 하고, 그것이 **의도된 마찰**이다.
    """
    assert mm.PROVENANCE_UNVERIFIED_PRESET == "UNVERIFIED_PRESET"
    # ★그리고 그 코드가 «검증됨» 을 뜻해서는 안 된다(형태 축 — 이름을 바꿔도 뜻은 못 뒤집게).
    assert not re.search(r"(?i)verified(?<!unverified)", mm.PROVENANCE_UNVERIFIED_PRESET.replace("UNVERIFIED", "")), (
        f"출처 코드가 검증을 뜻한다: {mm.PROVENANCE_UNVERIFIED_PRESET}"
    )


def test_provenance_code_is_unverified_for_every_scope() -> None:
    """모든 층위가 «미검증 사전설정» 이라는 **기계 판독 출처**를 단다.

    이 값이 계약이다. 표시 문구는 자유롭게 다듬어도 되지만 이 코드가 바뀌면 «출처가 검증됐다» 는
    **다른 주장**이 되므로 반드시 리뷰를 거쳐야 한다.
    """
    for addr in _all_addresses() + [_ADDR_UNKNOWN, None]:
        v = mm.resolve_market_multiplier(addr)
        assert v.provenance == mm.PROVENANCE_UNVERIFIED_PRESET, f"{addr!r} → {v.provenance}"


def test_provenance_code_reaches_the_real_payload() -> None:
    """★코드를 선언만 하고 안 실으면 장식이다 — 실제 산출물에 도달하는지 본다."""
    import asyncio

    payload = asyncio.run(
        estimate_land_price(address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0)
    )
    trust = payload.get("trust") or {}
    assert trust.get("basis_kind") == mm.PROVENANCE_UNVERIFIED_PRESET, trust


# ─────────────────────────────────────────────────────────────
# ★★블랙리스트를 걷어내고 **화이트리스트로 뒤집는다** (R2 HIGH-1·HIGH-3)
#
#   1차 처방은 «출처를 주장하는 낱말» 목록(`검증된|확인된|…|국토교통부|…`)이었다. R2 가
#   **14/14 우회**를 실증했다 — `검증된`→`검증됨`(어미 한 글자) · `국토교통부`→`국토부` ·
#   `산출된`→`산정된` · `현실화율`→`실현율` · `%`→`퍼센트`. 그리고 부정어 억제(`_NEGATOR`)는
#   **담요**라서 문장 끝에 «· 오차 없음» 다섯 글자를 붙이면 가드 전체가 꺼졌다.
#   동시에 **위양성**도 냈다 — `한국부동산원 R-ONE 통계 기준 자본환원율` 처럼 **정확한 출처 표기**를
#   위반으로 신고한다(같은 서비스가 이미 `cap_source = "R-ONE"` 을 쓴다). 정상 코드를 막는
#   가드는 곧 꺼진다(§A-6).
#
#   ⇒ **금지어를 세지 말고, 허용된 모양을 요구한다.** 아래 셋이 계약이다:
#     ① **수 불변식** — 우리가 만든 사유에는 **계수 자신 말고 어떤 수도 없다**.
#        이것이 이 PR 의 금지 대상(«계수로부터 통계를 역산하지 않는다»)의 **직접 표현**이다.
#        ★★면역 범위를 정확히 적는다(R3 MED-1 정정 — 종전 서술은 **거짓 면역 주장**이었다):
#          이 불변식은 **유니코드 Nd 범주 숫자**만 잡는다. 아래는 실측이다.
#            잡힘  : `83%` · 전각 `８３` · 아라비아-인도 `٨٣` · 지수 `8.3e1` · 비율 `0.83`
#            못잡음: 한글수사 **`팔십삼`** · 한자 `八十三` · 원문자 `⑧③` · 로마 `LXXXIII`
#          리뷰어가 `공시지가 현실화율 팔십삼 퍼센트` 변이를 넣어 **생존**시켰다.
#          ⇒ «어휘와 완전히 무관» 은 **거짓**이다. 악용 확률은 낮지만 **면역을 거짓 주장하지 않는다**
#            (§C-11 — 코드가 그 면역을 갖고 있는지 확인하고 쓴다). 한글 수사까지 잠그려면
#            `_numbers_in` 에 수사 토큰을 추가하라(현재 미구현 — 아래 `it.todo` 격 xfail 로 노출).
#     ② **한정어 토큰** — 고지 문자열은 승인된 한정어 상수를 **담아야** 한다(없애면 실패).
#     ③ **출처 코드** — 리터럴로 못 박은 `PROVENANCE_UNVERIFIED_PRESET`.
#   ★①은 실측으로 위양성 0을 확인했다: 현재 `short` 의 수 토큰은 **0개**, `sentence` 는 **{계수}** 뿐.
# ─────────────────────────────────────────────────────────────

_NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> set[float]:
    """문자열의 **완전한 수 토큰**만 값으로 추출(부분문자열 오탐 방지 — 콤마 제거 후 비교)."""
    return {float(t.replace(",", "")) for t in _NUM_TOKEN.findall(text)}


def test_short_form_contains_no_numbers_at_all() -> None:
    """★수 불변식 ① — 짧은형에는 **어떤 수도 없다**.

    역산 통계(100/계수)를 넣으려면 반드시 **수**가 들어간다. 낱말을 무엇으로 바꾸든 이 락에 걸린다.
    """
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        assert _numbers_in(v.short) == set(), f"{addr} → 짧은형에 수가 있다: {v.short}"


# ★허용된 수의 집합 — **확장 경로를 명시**한다(R3 LOW-2).
#   이 불변식은 계수 외 모든 수를 금지하므로, 나중에 기준연도(`2025년`)·표본수(`3,291건`)·
#   형제 실측(`1.448배`) 같은 **정직한 수**를 사유에 싣고 싶을 때 이 락이 막는다.
#   정상 코드를 막는 가드는 곧 꺼지므로(§A-6), **지우지 말고 이 함수를 넓혀라**.
#   ★★단 하나의 금기: **역산 계열(100/계수)은 절대 넣지 마라** — 그것이 이 PR 이 고친 결함이다.
#   아래 `test_allowed_numbers_never_include_the_inverse_family` 가 그 금기를 기계로 지킨다.
def _allowed_numbers(v: mm.MultiplierVerdict) -> set[float]:
    return {float(v.multiplier)}


def test_allowed_numbers_never_include_the_inverse_family() -> None:
    """★확장 경로에 **가드레일**을 건다 — 누가 `_allowed_numbers` 를 넓히더라도 역산 계열은 못 넣는다."""
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        inverse = {round(100 / v.multiplier), round(100 / v.multiplier, 1), round(100 / v.multiplier, 2)}
        leaked = _allowed_numbers(v) & inverse
        assert not leaked, f"허용 집합에 역산 계열이 들어왔다: {leaked} (계수 {v.multiplier})"
    # 공허 방지 — 역산 계열이 실제로 계수와 다른 값인지(계수 1.0 이면 100/1=100 과 겹치지 않는다).
    v = mm.resolve_market_multiplier(_ADDR_DISTRICT)
    assert round(100 / v.multiplier) != v.multiplier


def test_sentence_contains_exactly_the_multiplier_and_no_other_number() -> None:
    """★수 불변식 ② — 문장형의 수는 **계수 자신 하나뿐**이다.

    ★이것이 «계수로부터 통계를 역산하지 않는다» 의 기계 표현이다. R2 가 뚫은 변이
      `실현율{100/mult:.0f}퍼센트` 는 어휘 가드를 통과했지만 **수를 하나 더 만들기 때문에**
      이 락에는 반드시 걸린다.
    """
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        assert _numbers_in(v.sentence) == _allowed_numbers(v), (
            f"{addr} → 문장형의 수 집합이 {{계수}} 가 아니다: "
            f"{sorted(_numbers_in(v.sentence))} (계수 {v.multiplier}) · {v.sentence}"
        )


def test_number_invariant_actually_catches_a_derived_statistic() -> None:
    """★양성 대조 — 이 불변식이 **역산 통계를 실제로 잡는지**. 없으면 위 둘은 공허하다."""
    mult = 1.2
    evasive = f"남양주시 실현율{100 / mult:.0f}퍼센트 · 실거래 미검증"   # R2 가 뚫은 그 형태
    assert _numbers_in(evasive) != set(), "검사기 사망 — 수를 못 찾는다"
    assert _numbers_in(evasive) != {mult}, "검사기 사망 — 역산값을 계수와 구별 못 한다"
    # 판별력 — 현재 문구는 통과해야 한다(위양성도 결함이다).
    assert _numbers_in(mm.resolve_market_multiplier(_ADDR_DISTRICT).short) == set()


def test_caveat_constants_carry_no_numbers_and_are_pinned() -> None:
    """★한정어 상수 자신도 수를 담아선 안 되고, **리터럴로 못 박는다**(화이트리스트).

    자기 상수 비교는 아무것도 안 잠근다 — 이 PR 에서 두 번 겪었다.
    """
    assert _numbers_in(mm.UNVERIFIED_CAVEAT) == set(), mm.UNVERIFIED_CAVEAT
    assert _numbers_in(mm.SHORT_CAVEAT) == set(), mm.SHORT_CAVEAT
    assert mm.SHORT_CAVEAT == "실거래 미검증"
    assert mm.UNVERIFIED_CAVEAT == "실거래로 검증된 현실화율이 아닌 사전 설정 참고 계수입니다"


# ─────────────────────────────────────────────────────────────
# ★수식 자리에 문장을 넣지 않는다 (독립 리뷰 M-4)
#   `desk_appraisal_service` 는 사유를 `… × 그밖의요인 {계수}({사유})` 로 **연산 항 주석**에 쓴다.
#   문장형(마침표 포함)을 넣었더니 51~62자가 102~104자가 되고 괄호가 3중 중첩됐으며 수식
#   한가운데 문장 종결부가 박혔다(그리고 그것이 감정평가 PDF 로 나간다).
# ─────────────────────────────────────────────────────────────

def test_short_form_is_formula_safe() -> None:
    """짧은 형태는 **항**이지 문장이 아니다 — 길이 상한 + 문장 종결부 금지 + 괄호 금지."""
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        assert len(v.short) <= 45, f"{addr} → {len(v.short)}자: {v.short}"
        assert "." not in v.short, f"수식 안에 문장 종결부: {v.short}"
        assert "(" not in v.short and ")" not in v.short, f"괄호 중첩 유발: {v.short}"
    # ★두 모집단을 가른다 — 문장형은 반대로 **문장이어야** 한다(둘이 같으면 분리가 무의미).
    sent = mm.resolve_market_multiplier(_ADDR_DISTRICT).sentence
    assert sent.endswith("."), sent
    assert len(sent) > 45


def test_desk_appraisal_formula_uses_the_short_form() -> None:
    """★배선 — 수식을 만드는 자리가 실제로 짧은 형태를 받는지 **행위로** 확인한다."""
    mult, rationale = _market_multiplier(_ADDR_DISTRICT)
    formula = f"개별공시지가 1,000,000원/㎡ × 그밖의요인 {mult}({rationale}) × 면적 500㎡"
    assert formula.count("(") == formula.count(")") == 1, formula
    assert "습니다" not in formula, f"수식에 문장이 섞였다: {formula}"


# ─────────────────────────────────────────────────────────────
# 구멍 4 — 헬퍼만 태우고 **실제 출력면**을 안 태웠다
# ─────────────────────────────────────────────────────────────

def _collect_user_facing_strings(payload: object) -> list[str]:
    """payload 안의 사용자 노출 문자열을 **파생형으로** 수집(손으로 키를 나열하지 않는다)."""
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(payload)
    return out


@pytest.mark.asyncio
async def test_real_estimator_payload_carries_no_fabricated_rate() -> None:
    """실제 층을 태운다 — 공시지가와 면적을 주면 외부호출 경로를 타지 않는다(무과금/무네트워크)."""
    payload = await estimate_land_price(
        address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0
    )
    strings = _collect_user_facing_strings(payload)
    assert len(strings) >= 5, f"수집기가 죽었다 — 문자열 {len(strings)}건"

    offenders = [t for t in strings if _FABRICATED_RATE.search(t)]
    assert not offenders, "실제 출력면에 조작된 현실화율이 실렸다: " + " | ".join(offenders)

    # 양성 대조 — 같은 검사기가 옛 형태를 실제로 잡는가(대조군 없는 "0건" 은 근거가 아니다).
    assert [t for t in strings + [_OLD_FORM] if _FABRICATED_RATE.search(t)] == [_OLD_FORM]


@pytest.mark.asyncio
async def test_trust_disclosure_fields_are_present_and_nonempty() -> None:
    """정직 고지 필드가 payload 에 **실재**하는지 — 문구가 아니라 계약을 본다.

    ★값이 틀리는 것보다 **사유가 사라지는 것이 더 조용하다** — 화면에서 그냥 안 보이므로
      아무도 신고하지 않는다(이 저장소 유료·비가역 산출물 규율의 「사유를 버렸다」와 같은 얼굴).
    """
    payload = await estimate_land_price(
        address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0
    )
    trust = payload.get("trust")
    assert isinstance(trust, dict), f"trust 블록이 없다: {type(trust)}"
    for key in ("method", "basis", "basis_kind", "note"):
        assert key in trust, f"정직 고지 필드 누락: trust.{key}"
        assert str(trust[key] or "").strip(), f"trust.{key} 가 비었다 — 고지가 침묵한다"
    ev = payload.get("evidence")
    assert isinstance(ev, list) and len(ev) >= 3, f"evidence 트레이스 부족: {ev!r}"
    mult_rows = [r for r in ev if isinstance(r, dict) and "보정계수" in str(r.get("label", ""))]
    assert mult_rows, f"보정계수 근거 행이 없다: {[r.get('label') for r in ev if isinstance(r, dict)]}"
    assert all(str(r.get("basis") or "").strip() for r in mult_rows), mult_rows


def test_scope_codes_are_pairwise_distinct() -> None:
    """네 층위 코드는 기계 판독 축이다 — 겹치면 층위 판정이 통째로 무의미해진다."""
    codes = (mm.SCOPE_DISTRICT, mm.SCOPE_REGION, mm.SCOPE_DEFAULT, mm.SCOPE_UNKNOWN)
    assert len(set(codes)) == 4, codes
    assert all(c.strip() for c in codes)


# ─────────────────────────────────────────────────────────────
# ★설명된 생존(구멍 아님) — 변이 점수를 부풀리지 않기 위해 사유를 적는다
#
#   · 사유 f-string 문구 변경 · trust.basis 문구 변경
#     -> **산문이다.** 이 락들은 «금지된 의미»(역산된 통계 · 출처 주장)와 «계약»(provenance 코드 ·
#        계수/순서 · 층위 구별 · 수식 안전성)만 잠그고 표현은 잠그지 않는다. 문구를 다듬을 때마다
#        깨지는 락은 곧 꺼지기 때문이다(CLAUDE.md §30).
#     ★★단, 이 «설명» 의 정확한 범위를 적어 둔다(독립 리뷰 M-3 정정): 종전에 나는 이것을 그냥
#       "산문이라 안 잠근다" 고 썼는데 **실제 경계는 그보다 좁았다** — 옛 문자열이 잡힌 유일한
#       이유는 거기에 낱말 「현실화율」이 있었기 때문이고, 그 낱말을 안 쓰는 허위 출처 주장은
#       **전부 무잠금**이었다. 그래서 위 `provenance` 계약을 새로 넣었다. 지금 무잠금으로 남은
#       것은 «출처를 주장하지 않으면서 부정확한 표현» 뿐이고, 그것은 리뷰가 잡을 일이다.
#   · SCOPE_* 문자열 변경
#     -> **내부 식별자**다. 계약은 «네 코드가 상호 구별되는가» 이고 위 테스트가 잠근다.
#        고유한 다른 이름으로 바뀌는 것은 관측 가능한 결함이 아니다 — 잠그면 위양성이 된다.
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# ★골든 픽스처가 **조용히 낡는 것**을 막는다 (독립 리뷰 m-1)
#
#   `fixtures/market/W2b_market_methodology.json` 이 `_calc_land_prices` 의 사유 문장을 얼려
#   두고 있었는데, 이 PR 이 그 문장을 바꾼 뒤에도 **218건 전수 초록**이었다 — 그 픽스처를 쓰는
#   테스트는 배지 개수만 보고 문장은 안 보기 때문이다. staleness 가 **무성**이었다.
#
#   ★★그리고 이것은 내 조회의 **구조적 사각지대**였다: 그 문자열에는 낱말 「현실화율」이
#     없으므로 `git grep 현실화율` 로는 **원리적으로 찾을 수 없었다**. 리뷰어가 찾았다.
#     ⇒ 낱말로 찾지 못하는 것은 **생산자에서 파생해 대조**해야 잡힌다.
# ─────────────────────────────────────────────────────────────

def test_golden_fixture_annotation_matches_the_real_producer() -> None:
    """픽스처가 얼려 둔 사유가 **생산자가 지금 실제로 내는 문장**과 같은지 파생으로 대조한다."""
    import json
    from pathlib import Path

    fx = (
        Path(__file__).parent
        / "services/verification/field_audit/fixtures/market/W2b_market_methodology.json"
    )
    assert fx.exists(), f"픽스처 경로가 바뀌었다: {fx}"
    blob = json.loads(fx.read_text(encoding="utf-8"))

    # 픽스처 안의 모든 land_prices.annotations 를 **파생형으로** 걷는다(케이스명 하드코딩 금지).
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            lp = node.get("land_prices")
            if isinstance(lp, dict) and isinstance(lp.get("annotations"), list):
                found.extend(str(a) for a in lp["annotations"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(blob)
    assert found, "픽스처에서 annotations 를 하나도 못 걷었다 — 수집기가 죽었거나 구조가 바뀌었다"

    # 보정계수 사유 줄만 골라 생산자 출력과 대조한다.
    expected = mm.resolve_market_multiplier("주소미상시 미등록동 1").sentence
    multiplier_lines = [a for a in found if "보정계수" in a]
    assert multiplier_lines, f"보정계수 사유 줄이 없다(공허 진리 방지): {found}"
    assert expected in multiplier_lines, (
        "픽스처가 **코드가 더 이상 낼 수 없는 문장**을 얼려 두고 있다(무성 staleness).\n"
        f"  생산자 실제 출력: {expected}\n"
        f"  픽스처 안의 값  : {multiplier_lines}"
    )


# ─────────────────────────────────────────────────────────────
# ★출처 주장 가드를 **실제 출력면**까지 확장 (독립 리뷰 M-3 잔여)
#
#   `provenance` 코드를 계약으로 넣은 뒤에도, 리뷰어의 변이
#   `trust.basis = "개별공시지가 × 실거래로 검증된 지역 보정계수"` 는 생존했다.
#   기계 코드는 `UNVERIFIED_PRESET` 인데 **사람이 읽는 줄은 「검증됐다」고 말한다** —
#   그것이 바로 이 PR 이 고치는 결함(**한 화면의 두 표면이 모순**)의 재발이다.
#   한정어 상수만 검사하고 payload 는 안 봤기 때문에 뚫렸다.
#   ⇒ 상수가 아니라 **산출물**을 태운다. 여전히 최선노력이지만, 이제 결함이 사는 자리에 있다.
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# ★★포함(containment)을 동일성(equality)으로 바꾼다 (R3 HIGH-A)
#
#   종전 락은 `SHORT_CAVEAT in text` 였다. 그래서 거짓 주장으로 바꾸려면 한정어를 **지울 필요가
#   없었다 — 덧붙이면 됐다**. 리뷰어가 실증했다:
#       f"{district} 국토부 실거래 검증 계수 · {SHORT_CAVEAT}"        → 36건 전부 SURVIVED
#       "국토교통부 실거래가 통계로 검증된 … · 오차 없음(실거래 미검증)"  → SURVIVED
#   ★그리고 그 문자열은 **감정평가 PDF 에 도달한다**(리뷰어가 렌더해 확인: 9,437 bytes).
#   ★★내가 테스트 독스트링에 «거짓으로 바꾸려면 한정어를 지워야 한다» 고 적은 것은
#     **거짓 면역 주장**이었다(§C-11). 포함은 «거짓을 말하지 않는가» 를 함의하지 않는다.
#
#   ★기계 변이가 이 자리를 CAUGHT 로 찍었던 이유도 리뷰어가 짚었다 — 그 도구는 문자열을
#     `__MUTATED__` 로 **치환**(=한정어 삭제)한다. 위험한 편집은 **삭제가 아니라 첨가**이고
#     기계 변이는 그 축을 만들지 않는다. **도구가 만들지 않는 축은 사람이 만들어야 한다.**
#
#   ⇒ 표시 문구를 템플릿 상수로 꺼내고(생산자), 여기서 **리터럴로 못 박는다**(계수표와 같은 방식).
#     감정평가 표면에 나가는 문구를 바꾸려면 이 줄도 함께 고쳐야 하고 그것이 의도된 마찰이다.
# ─────────────────────────────────────────────────────────────

_EXPECTED_SHORT_TEMPLATES = {
    mm.SCOPE_DISTRICT: "{key} 사전설정 계수 · {caveat}",
    mm.SCOPE_REGION: "{key} 광역 사전설정 계수 · 시군구 미등록 · {caveat}",
    mm.SCOPE_DEFAULT: "전국 기본 계수 · 지역 미등록 · {caveat}",
    mm.SCOPE_UNKNOWN: "주소 미상 · 전국 기본 계수 · {caveat}",
}


def test_display_templates_are_pinned_as_literals() -> None:
    """★사용자·PDF 표면에 나가는 문구를 **리터럴로 동결**한다(자유 첨가 차단)."""
    assert _EXPECTED_SHORT_TEMPLATES[mm.SCOPE_DISTRICT] == mm.SHORT_TEMPLATE_DISTRICT
    assert _EXPECTED_SHORT_TEMPLATES[mm.SCOPE_REGION] == mm.SHORT_TEMPLATE_REGION
    assert _EXPECTED_SHORT_TEMPLATES[mm.SCOPE_DEFAULT] == mm.SHORT_TEMPLATE_DEFAULT
    assert _EXPECTED_SHORT_TEMPLATES[mm.SCOPE_UNKNOWN] == mm.SHORT_TEMPLATE_UNKNOWN
    assert mm.SENTENCE_TEMPLATE_DISTRICT == (
        "{key}에 대해 사전 설정된 지역 시세보정계수 {mult}배를 적용했습니다({caveat})."
    )
    assert mm.SENTENCE_TEMPLATE_REGION == (
        "{key} 광역 단위의 사전 설정 시세보정계수 {mult}배를 적용했습니다"
        "(시·군·구 세부 계수 미등록 · {caveat})."
    )
    assert mm.SENTENCE_TEMPLATE_DEFAULT == (
        "지역별 보정계수가 미등록되어 전국 기본 보정계수 {mult}배를 적용했습니다({caveat})."
    )
    assert mm.SENTENCE_TEMPLATE_UNKNOWN == (
        "주소가 확인되지 않아 전국 기본 보정계수 {mult}배를 적용했습니다"
        "(지역별 계수의 미등록 여부는 확인되지 않았습니다 · {caveat})."
    )


def test_every_short_form_equals_its_template_exactly() -> None:
    """★전수 — 짧은형이 템플릿 **그대로**여야 한다(첨가 0). 포함이 아니라 동일성이다."""
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        key = next(
            (k for k in list(mm.MARKET_MULTIPLIER_MAP) + list(mm.MARKET_MULTIPLIER_REGION) if k in (addr or "")),
            "",
        )
        expected = _EXPECTED_SHORT_TEMPLATES[v.scope].format(key=key, caveat=mm.SHORT_CAVEAT)
        assert v.short == expected, f"{addr}\n  got     : {v.short}\n  expected: {expected}"


def test_no_markdown_emphasis_in_runtime_strings() -> None:
    """★런타임 문자열에 마크다운 강조를 넣지 않는다 (R3 MED-2).

    ★이 PR 이 신설한 SCOPE_UNKNOWN 문장에 `**확인되지 않았습니다**` 를 넣었는데, 소비 렌더러
      (`ComprehensiveAnalysisPanel` 의 `<p>{text}</p>`)는 **마크다운을 파싱하지 않아** 별표가
      그대로 화면에 찍힌다. 세션 메모리의 09-06 항목과 **같은 결함이 하루 만에 재발**했다.
      ⇒ 강조는 주석에만. 사용자 문자열에는 절대.
    """
    texts = []
    for addr in _all_addresses() + [_ADDR_UNKNOWN]:
        v = mm.resolve_market_multiplier(addr)
        texts += [v.short, v.sentence]
    texts += [mm.SHORT_CAVEAT, mm.UNVERIFIED_CAVEAT]
    assert texts, "수집기가 죽었다"
    offenders = [t for t in texts if "**" in t or "__" in t]
    assert not offenders, "런타임 문자열에 마크다운 강조가 있다(화면에 별표가 찍힌다): " + " | ".join(offenders)
    # 양성 대조 — 검사기가 실제로 잡는가.
    assert "**" in "지역별 계수의 **미등록 여부**는", "검사기 사망"


@pytest.mark.asyncio
async def test_trust_basis_equals_the_assembled_template() -> None:
    """★고지 문자열은 **조립식과 정확히 같아야** 한다 — 덧붙이기 우회를 막는다(R3 HIGH-A)."""
    from app.services.land_intelligence.land_price_estimator import TRUST_BASIS_TEMPLATE

    assert TRUST_BASIS_TEMPLATE == "개별공시지가 × 사전 설정 지역 보정계수({caveat})"
    payload = await estimate_land_price(
        address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0
    )
    trust = payload.get("trust") or {}
    assert trust.get("basis_kind") == mm.PROVENANCE_UNVERIFIED_PRESET, trust
    assert trust.get("basis") == TRUST_BASIS_TEMPLATE.format(caveat=mm.SHORT_CAVEAT), trust

    # ★양성 대조 — 리뷰어가 통과시킨 «덧붙이기» 문자열들을 이 검사가 실제로 거부하는가.
    for bad in (
        "국토교통부 실거래가 통계로 검증된 지역 보정계수 · 오차 없음(실거래 미검증)",
        "개별공시지가 × 국토부 실거래 검증 계수(실거래 미검증)",
    ):
        assert bad != TRUST_BASIS_TEMPLATE.format(caveat=mm.SHORT_CAVEAT), f"검사기 사망: {bad}"
        assert mm.SHORT_CAVEAT in bad, "★이 문자열들은 한정어를 담고도 거짓이다 — 포함 검사가 뚫린 이유"

    # 보조 그물 — 역산 통계 형태는 payload 어디에도 없어야 한다.
    strings = _collect_user_facing_strings(payload)
    assert len(strings) >= 5, f"수집기가 죽었다 — 문자열 {len(strings)}건"
    assert not [t for t in strings if _FABRICATED_RATE.search(t)]


# ─────────────────────────────────────────────────────────────
# ★출처 코드가 **가장 값비싼 표면**에 도달하는가 (R2 MEDIUM)
#
#   1차에서는 출처 코드를 `land_price_estimator` 의 `trust` 블록에만 실었다. R2 가 재보니
#   **3개 표면 중 1개**였고, 빠진 하나가 하필 이 PR 의 계획서가 「제출용 감정평가 PDF」라고
#   지목한 `desk_appraisal` 이었다. 그밖의요인은 **가액을 직접 곱하는 계수**이므로 그 자리가
#   가장 중요하다. ⇒ `methods[0].factor_provenance` 로 전파하고 여기서 태운다.
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_desk_appraisal_carries_factor_provenance() -> None:
    """감정평가 표면(=PDF 원천)이 그밖의요인의 **출처 코드**를 싣는지 실제 호출로 태운다."""
    from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

    result = await desk_appraisal(
        address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0
    )
    methods = result.get("methods") or []
    assert methods, "methods 가 비었다 — 이 락이 공허해진다"
    pub = next((m for m in methods if isinstance(m, dict) and m.get("unit_price")), None)
    assert pub is not None, f"채택 방법이 없다: {[m.get('method') for m in methods if isinstance(m, dict)]}"

    prov = pub.get("factor_provenance")
    assert isinstance(prov, dict), f"factor_provenance 부재: {pub.keys()}"
    assert prov.get("그밖의요인") == mm.PROVENANCE_UNVERIFIED_PRESET, prov

    # ★수식 문자열도 같은 축으로 태운다 — 짧은형이 쓰였는가(문장이 섞이지 않았는가).
    rationale = str(pub.get("rationale") or "")
    assert "그밖의요인" in rationale, rationale
    assert "습니다" not in rationale, f"수식에 문장이 섞였다: {rationale}"
    assert _numbers_in(rationale) & {round(100 / other, 0) for other in (1.2,)} == set(), rationale


# ★부채 — 출처 코드를 **읽는 소비처가 아직 0**이다(R2 MEDIUM).
#   저장소가 반복해 데인 «정의만 하고 소비처 0» 형태다. 커밋 메시지에만 적으면 안 보이므로
#   **초록 안에 드러낸다**(xfail strict — 소비처가 생기면 XPASS 로 실패해 이 줄을 지우게 된다).
#
#   ★★조회 함정을 하나 밟고 적는다: 처음엔 검색어에 `basis_kind` 를 넣었는데, 그 이름은
#     **다른 기능의 동명 필드**(`feasibility/legacy_ledger.py` 의 `"data"|"structural"`)라
#     소비처 4곳을 잘못 세어 이 부채가 **이미 해소된 것처럼** 통과했다. R2 가 그 함정을 경고했고
#     나는 그 경고를 **바로 윗줄에 적어 놓고도** 검색어에 넣었다.
#     ⇒ 부재를 판정할 때는 **모호하지 않은 식별자**로만 조회한다(§«내가 말한 집합 ≠ 내 도구가 센 집합»).
_UNAMBIGUOUS_MARKERS = ("PROVENANCE_UNVERIFIED_PRESET", "factor_provenance")
_PRODUCERS_AND_TESTS = (
    "market_multiplier.py",
    "land_price_estimator.py",
    "desk_appraisal_service.py",
    "test_market_multiplier_rationale.py",
    "_workspace/",          # 계획서는 소비처가 아니다(문서)
)


def _repo_root() -> Path:
    """★cwd 가 아니라 **파일 위치에서 파생**한다(R3 HIGH-B).

    종전에는 `cwd="../../.."` 라 **어디서 돌리느냐**에 따라 다른 저장소를 봤다. CI 는 우연히
    맞았지만(`working-directory: propai-platform/apps/api`), repo root 에서 돌리면 조회기가
    **빈 결과**를 냈다 — 그리고 그 빈 결과가 xfail 안에 있어 **의도된 부채와 구별되지 않았다**.
    """
    return Path(__file__).resolve().parents[3]


def _marker_files() -> list[str]:
    import subprocess

    out = subprocess.run(
        ["git", "grep", "-l", "-E", "|".join(_UNAMBIGUOUS_MARKERS)],
        capture_output=True, text=True, cwd=str(_repo_root()),
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def test_marker_scanner_is_alive() -> None:
    """★대조군은 **xfail 밖**에 둔다 (R3 HIGH-B).

    ★종전에는 이 단언이 부채 테스트 **안**에 있었다. 그래서 조회기가 죽어도 «xfailed» 로 초록이라
      «의도된 부채»와 **바이트 하나 다르지 않았다**. 더 나쁜 것은 `strict=True` 의 목적
      («소비처가 생기면 XPASS 로 터진다»)이 조회기 사망 시 **영원히 발화하지 않는다**는 것이다.
      ⇒ 조회기 생존은 **별도 테스트로 초록/빨강**을 가른다.
    """
    files = _marker_files()
    assert any("market_multiplier.py" in f for f in files), (
        f"조회기가 죽었다 — 생산자조차 못 찾았다(저장소 루트={_repo_root()}): {files}"
    )


@pytest.mark.xfail(strict=True, reason="★부채: provenance 를 읽는 소비처가 아직 0건(배지·감사 미배선)")
def test_provenance_has_a_consumer() -> None:
    """출처 코드를 **읽는** 코드가 저장소에 있는가(현재 없음 — 부채로 노출).

    조회기 생존은 위 `test_marker_scanner_is_alive` 가 따로 보증한다.
    """
    consumers = [f for f in _marker_files() if not any(k in f for k in _PRODUCERS_AND_TESTS)]
    assert consumers, "소비처 0 — 선언만 하고 아무도 안 읽는다"


@pytest.mark.xfail(strict=True, reason="★부채(R3 MED-1): 한글·한자 수사(「팔십삼」)는 수 불변식이 못 잡는다")
def test_number_invariant_catches_korean_numerals() -> None:
    """한글 수사로 쓴 역산 통계도 잡아야 이상적이다 — 현재 **미구현**이라 초록 안에 드러낸다."""
    assert _numbers_in("공시지가 현실화율 팔십삼 퍼센트") != set()
