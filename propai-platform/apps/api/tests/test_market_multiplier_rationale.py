"""시세보정계수 사유가 **계수로부터 통계를 역산하지 않는지** 잠근다(2026-09-07).

■ 무엇이 있었나
`comprehensive_analysis_service._get_market_multiplier` 와 형제 `land_price_estimator.
_market_multiplier` 가 **둘 다** 사용자 노출 문자열에 이렇게 썼다:

    f"{district} 지역의 공시지가 현실화율(약 {100/mult:.0f}%)을 반영한 보정계수 {mult}배..."

「현실화율」은 측정값이 아니라 **계수를 뒤집은 수**다(남양주 1.2 → 100/1.2 = 83.3 → "약 83%").
계수를 먼저 고르고 사유를 역산했으니 **산출물을 근거처럼** 말한 것이다. 그 문자열은
`land_price_estimator:113 _price_evidence` → row `basis` → `EvidencePanel.tsx:99` 로
**사용자 화면에 도달**한다(배선 실측).

★이 저장소는 같은 금지를 **자기 언어로 이미 적어 두고 있었다**(`ai/market_interpreter.py`
GROUNDING_RULE 5항 — "'70~80%' 같은 일반비율을 데이터 근거 없이 확정 단정하지 않는다"),
그리고 형제 검사 `field_audit/invariants/market_methodology.py` 는 같은 화면에 "실거래로
검증되지 않음" 배지를 상시 띄우고 있었다. **한 화면의 두 표면이 모순**했고, 구체적으로
들려서 더 신뢰받는 「83%」 쪽이 거짓이었다.

■ 3축으로 잠근다(탐지·특이도·배선) — 하나만 잠그면 «항상 통과» 가 만점이 된다
  A 탐지 : 파생형 전수 — 등록 지역 **전 항목** + 폴백의 사유에 「현실화율 …%」류 수치 단정 없음
  B 특이도: 같은 검사기가 **옛 형태를 실제로 잡는지**(양성 대조) — 검사기 사망을 0건과 안 뭉친다
  C 배선 : 세 층위가 **서로 다른** 문자열을 내고 한정어 상수가 **실제로 실리는지**,
           그리고 형제가 SSOT 를 **행위로** 경유하는지(이름 존재가 아니라 동일 출력)

★산문 자체는 단언하지 않는다(§30) — 문구를 다듬을 때마다 깨지는 취약한 락이 되므로,
  «금지된 형태가 없다»(부정 파생형)와 «계약»(계수·층위 구분·형제 동치)에만 건다.
"""

from __future__ import annotations

import re

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

# 세 층위를 실제로 밟는 주소(픽스처가 두 모집단을 가르게 — §검증 규율 2).
_ADDR_DISTRICT = "경기도 남양주시 다산동 123-4"      # MAP 히트
_ADDR_REGION = "경기도 어딘가군 무등록면 1-1"          # MAP 미스 · REGION 히트
_ADDR_DEFAULT = "제주도아닌곳 미등록시 999"            # 둘 다 미스 → 폴백


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
    """전 층위 전수 — 사유 문자열이 계수에서 역산한 「현실화율 N%」를 담지 않는다."""
    offenders: list[str] = []
    for addr in _all_addresses():
        _mult, rationale, _scope = mm.resolve_market_multiplier(addr)
        if _FABRICATED_RATE.search(rationale):
            offenders.append(f"{addr} → {rationale}")
    assert not offenders, (
        "계수를 뒤집어 만든 「현실화율 N%」가 사유에 실렸다. 그 수는 측정값이 아니라 "
        "100/계수이며, 산출물을 근거처럼 말하는 것이다.\n  " + "\n  ".join(offenders[:8])
    )


def test_sibling_estimator_rationale_is_also_clean() -> None:
    """★형제도 같은 축으로 태운다 — 한쪽만 고치고 미러를 놓치는 일이 이 저장소에서 반복됐다."""
    offenders = []
    for addr in _all_addresses():
        _mult, rationale = _market_multiplier(addr)
        if _FABRICATED_RATE.search(rationale):
            offenders.append(f"{addr} → {rationale}")
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
    # 음성 대조 — 판별력이 있는가(아무 문자열이나 잡으면 그것도 결함이다).
    assert not _FABRICATED_RATE.search(
        "남양주시에 대해 사전 설정된 지역 시세보정계수 1.2배를 적용했습니다."
    )
    # ★한정어 상수 자체도 금지 형태를 담아선 안 된다(자기 상수를 단언하는 락의 구멍 봉합).
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
    ],
)
def test_three_scopes_are_reachable_and_distinct(addr: str, expected_scope: str) -> None:
    """세 층위가 **실제로 밟히고** 서로 다른 문자열을 낸다.

    ★두 모집단을 가르지 않으면(전부 같은 문구면) 배선을 끊어도 결과가 같아 락이 무의미해진다.
    """
    _mult, rationale, scope = mm.resolve_market_multiplier(addr)
    assert scope == expected_scope, f"{addr} → {scope}"
    assert rationale.strip()


def test_scope_rationales_differ_from_each_other() -> None:
    """등록 지역 / 광역 폴백 / 전국 폴백이 서로 구별 가능해야 한다(사용자가 알 권리).

    ★알려진 생존(구멍 아님 · 2026-09-07 변이 ⑦): REGION 문구의 앞 절을 DEFAULT 문구로
      바꿔 넣어도 이 락은 초록이다 — 뒤 절("시·군·구 세부 계수 미등록")이 남아 세 문자열이
      **여전히 서로 다르기** 때문이다. 즉 이 락은 «문구가 옳은가» 가 아니라 «층위가 구별
      가능한가» 를 잠근다. **의도된 경계다**:
        · 기계 판독 축(층위 코드)은 위 `test_three_scopes_are_reachable_and_distinct` 가
          잠근다 — 변이 ⑥(REGION→DISTRICT 오보)이 CAUGHT 됐다.
        · 산문 문구 자체는 일부러 단언하지 않는다(CLAUDE.md §30). 계약이 아니라 표현이라,
          문구를 다듬을 때마다 깨지는 취약한 락이 되고 그런 락은 곧 꺼진다.
      ⇒ 점수를 올리려고 문구를 단언하지 말 것. 문구가 틀리는 것은 리뷰가 잡을 일이다.
    """
    texts = {
        mm.resolve_market_multiplier(a)[1]
        for a in (_ADDR_DISTRICT, _ADDR_REGION, _ADDR_DEFAULT)
    }
    assert len(texts) == 3, f"층위가 구별되지 않는다: {texts}"


def test_unverified_caveat_is_wired_into_every_scope() -> None:
    """★한정어가 **모든** 층위에 실제로 실린다 — 상수 선언만으로는 장식이다(§A-5)."""
    for addr in _all_addresses():
        _mult, rationale, _scope = mm.resolve_market_multiplier(addr)
        assert mm.UNVERIFIED_CAVEAT in rationale, f"{addr} → 한정어 누락: {rationale}"


def test_sibling_delegates_to_ssot_by_behavior_not_by_name() -> None:
    """★「부른다」가 아니라 **행위**를 태운다 — 두 소비처가 같은 입력에 같은 출력을 내는가.

    소스에 임포트가 있다는 것은 그 함수가 **불린다**는 뜻이 아니다(이 저장소의 반복 결함).
    """
    svc = ComprehensiveAnalysisService.__new__(ComprehensiveAnalysisService)
    for addr in _all_addresses():
        want_mult, want_rationale, _ = mm.resolve_market_multiplier(addr)
        got_mult, got_rationale = _market_multiplier(addr)
        assert (got_mult, got_rationale) == (want_mult, want_rationale), f"형제 갈림: {addr}"
        cas_mult, cas_rationale = svc._get_market_multiplier(addr)
        assert (cas_mult, cas_rationale) == (want_mult, want_rationale), f"comprehensive 갈림: {addr}"


# ─────────────────────────────────────────────────────────────
# 회귀 락 — 이 PR 은 **값을 바꾸지 않는다**
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("서울특별시 강남구 역삼동 1-1", 1.8),
        ("경기도 남양주시 다산동 123-4", 1.2),   # ★인계서가 지목한 바로 그 값
        ("경기도 성남시 분당구 1-1", 1.4),        # MAP 순서상 성남시가 먼저 히트
        (_ADDR_REGION, 1.2),
        (_ADDR_DEFAULT, 1.2),
    ],
)
def test_coefficients_are_unchanged(addr: str, expected: float) -> None:
    """계수는 **불변**이다. 진짜 현실화율을 잴 데이터원이 없으므로(미측정) 값은 손대지 않았다 —
    근거 없이 값을 바꾸는 것은 이 PR 이 고치려는 바로 그 죄의 반복이다.
    """
    mult, _rationale, _scope = mm.resolve_market_multiplier(addr)
    assert mult == expected


def test_class_attribute_aliases_point_at_the_same_ssot_objects() -> None:
    """★별칭이 **복사본이 아니라 같은 객체**여야 SSOT 가 갈라지지 않는다."""
    assert ComprehensiveAnalysisService.MARKET_MULTIPLIER_MAP is mm.MARKET_MULTIPLIER_MAP
    assert ComprehensiveAnalysisService.MARKET_MULTIPLIER_REGION is mm.MARKET_MULTIPLIER_REGION


# ─────────────────────────────────────────────────────────────
# ★기계 변이가 낸 구멍 봉합(2026-09-07 · scripts/mutate_changed.py 47건 중 27 생존 트리아지)
#   base: origin/main -> 63a7e126ca40(공통 조상). 아래 넷은 **설명할 수 없는 생존**이었다.
#   손으로 고른 변이 8건은 이 자리를 하나도 짚지 못했다 — 기계로 뽑아야 하는 이유다.
# ─────────────────────────────────────────────────────────────

# 구멍 1 — 계수 회귀 락이 **손으로 고른 5개**였고 모집단은 49+14 였다.
#   맵에서 한 줄을 지워도(예: 마포구 1.5) 파생형 테스트는 **모집단과 함께 깎여** 초록이었다
#   (자기지시적 기대값의 전형). 마포구가 사라지면 서울 1.4 로 **조용히 재라우팅**된다 — 금액이 바뀐다.
#   => 표 전체를 **독립 오라클**(아래 명시 리터럴)로 못 박는다. 계수를 바꾸려면 이 표도 함께
#      고쳐야 하고, 그것이 **의도된 마찰**이다 — 이 표는 토지가액을 움직인다.
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


def test_full_multiplier_table_is_frozen() -> None:
    """전수 락 — 표의 **모든** 항목이 불변임을 독립 오라클로 단언한다.

    이 PR 의 계약은 "계수는 바꾸지 않는다" 이므로 표 전체가 계약이다. 대표 5개만 잠그면
    나머지 58개는 무잠금이고, 실제로 기계 변이가 그 자리를 22건 관통했다.
    """
    assert mm.MARKET_MULTIPLIER_MAP == _EXPECTED_MAP
    assert mm.MARKET_MULTIPLIER_REGION == _EXPECTED_REGION
    # 개수도 따로 못 박는다 — dict 비교가 통과해도 "항목이 추가됐는지" 를 사람이 읽게.
    assert len(mm.MARKET_MULTIPLIER_MAP) == 49
    assert len(mm.MARKET_MULTIPLIER_REGION) == 14


# 구멍 2 — 한정어를 **자기 상수로 단언**해, 상수를 정반대 뜻으로 바꿔도 전부 통과했다.
#   UNVERIFIED_CAVEAT 를 "실거래로 검증된 현실화율입니다" 로 바꾸면, "한정어가 실렸다" 는 락이
#   오히려 거짓을 실어 나른다(자기 상수를 단언하는 락은 정반대 주장을 통과시킨다).
#   => **금지된 모양**으로 잠근다 — 한정어는 검증을 **주장해서는 안 된다**.
_CLAIMS_VERIFICATION = re.compile(r"(검증된|확인된|실측된)\s*현실화율(?!이\s*아)")


def test_caveat_constant_does_not_claim_verification() -> None:
    """한정어가 "검증됐다" 고 주장하면 그것 자체가 이 PR 이 고친 결함의 재발이다."""
    # 탐지축이 살아 있는가(양성 대조) — 없으면 아래 단언은 공허하다.
    assert _CLAIMS_VERIFICATION.search("실거래로 검증된 현실화율입니다"), "검사기 사망"
    # 판별력 — 현재 문구(부정형)는 잡히지 않아야 한다.
    assert not _CLAIMS_VERIFICATION.search(mm.UNVERIFIED_CAVEAT), mm.UNVERIFIED_CAVEAT
    assert mm.UNVERIFIED_CAVEAT.strip(), "한정어가 비었다 — 배선 락이 공허해진다"


# 구멍 3 — 층위 코드가 서로 **구별되는지**를 아무도 단언하지 않았다.
def test_scope_codes_are_pairwise_distinct() -> None:
    """세 층위 코드는 기계 판독 축이다 — 겹치면 층위 판정이 통째로 무의미해진다."""
    codes = (mm.SCOPE_DISTRICT, mm.SCOPE_REGION, mm.SCOPE_DEFAULT)
    assert len(set(codes)) == 3, codes
    assert all(c.strip() for c in codes)


# 구멍 4 — 헬퍼만 태우고 **실제 출력면**을 안 태웠다. 사용자가 보는 것은 estimator 의 반환
#   payload(trust.basis / evidence[].basis / rationale)이고, 그 자리에도 같은 거짓 모델이
#   따로 적혀 있었다(land_price_estimator 의 trust.basis — 전역 스윕이 찾아낸 다섯 번째 자리).
#   => 스텁이 아니라 **진짜 함수를 태워** 모든 사용자 노출 문자열을 한 번에 훑는다.
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
    """실제 층을 태운다 — 공시지가와 면적을 주면 외부호출 경로를 타지 않는다(무과금/무네트워크).

    두 모집단을 가른다: 조작 형태는 **없어야** 하고, 검사기는 **살아 있어야** 한다.
    """
    payload = await estimate_land_price(
        address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0
    )
    strings = _collect_user_facing_strings(payload)
    assert len(strings) >= 5, f"수집기가 죽었다 — 문자열 {len(strings)}건"

    offenders = [t for t in strings if _FABRICATED_RATE.search(t)]
    assert not offenders, "실제 출력면에 조작된 현실화율이 실렸다: " + " | ".join(offenders)

    # 양성 대조 — 같은 검사기가 옛 형태를 실제로 잡는가(대조군 없는 "0건" 은 근거가 아니다).
    assert [t for t in strings + [_OLD_FORM] if _FABRICATED_RATE.search(t)] == [_OLD_FORM]


# 구멍 5 — trust.basis 가 **통째로 사라져도** 초록이었다(기계 변이 [3] 줄삭제).
#   그 필드는 "이 값이 어떻게 나왔나" 를 사용자에게 말하는 **정직 고지**다. 값이 틀리는 것보다
#   사유가 사라지는 것이 더 조용하다 — 화면에서 그냥 안 보이므로 아무도 신고하지 않는다.
#   (이 저장소의 유료·비가역 산출물 규율: "사유를 버렸다" 가 네 얼굴 중 하나였다.)
#   => 문구가 아니라 **존재와 형태**를 잠근다(산문 단언 아님).
@pytest.mark.asyncio
async def test_trust_disclosure_fields_are_present_and_nonempty() -> None:
    """정직 고지 필드가 payload 에 **실재**하는지 — 문구가 아니라 계약을 본다."""
    payload = await estimate_land_price(
        address=_ADDR_DISTRICT, area_sqm=500.0, official_price_per_sqm=1_000_000.0
    )
    trust = payload.get("trust")
    assert isinstance(trust, dict), f"trust 블록이 없다: {type(trust)}"
    for key in ("method", "basis", "note"):
        assert key in trust, f"정직 고지 필드 누락: trust.{key}"
        assert str(trust[key] or "").strip(), f"trust.{key} 가 비었다 — 고지가 침묵한다"
    # 산출 근거 트레이스(EvidencePanel)도 비면 안 된다 — 근거 0줄은 근거 없음과 같다.
    ev = payload.get("evidence")
    assert isinstance(ev, list) and len(ev) >= 3, f"evidence 트레이스 부족: {ev!r}"
    # 보정계수 행이 사유(basis)를 달고 있는가 — 배선 락(라벨만 있고 근거가 빈 행 방지).
    mult_rows = [r for r in ev if isinstance(r, dict) and "보정계수" in str(r.get("label", ""))]
    assert mult_rows, f"보정계수 근거 행이 없다: {[r.get('label') for r in ev if isinstance(r, dict)]}"
    assert all(str(r.get("basis") or "").strip() for r in mult_rows), mult_rows


# ─────────────────────────────────────────────────────────────
# ★설명된 생존 6건(구멍 아님 · 기계 변이 재실행 결과 7 중 6)
#   변이 점수를 부풀리지 않기 위해 **왜 잠그지 않았는지**를 적는다.
#
#   [34] UNVERIFIED_CAVEAT · [41][44][46] 사유 f-string 3종 · [4] trust.basis 문구
#     -> **산문이다.** 이 락들은 «금지된 의미»(검증 주장 · 역산된 통계)만 잠그고 표현은 잠그지
#        않는다. 문구를 다듬을 때마다 깨지는 락은 곧 꺼지기 때문이다(CLAUDE.md §30).
#        의미를 뒤집는 변이는 실제로 CAUGHT 다 — 손 변이 ⑩(한정어를 "검증된 현실화율입니다"로)
#        · ⑫(trust.basis 에 "현실화율 83%" 재도입) 둘 다 잡혔다.
#   [36] SCOPE_DISTRICT 문자열 변경
#     -> **내부 식별자**다. 계약은 «세 코드가 상호 구별되는가» 이고 그것은
#        test_scope_codes_are_pairwise_distinct 가 잠근다(손 변이 ⑪ 충돌 = CAUGHT).
#        고유한 다른 이름으로 바뀌는 것은 관측 가능한 결함이 아니다 — 잠그면 위양성이 된다.
# ─────────────────────────────────────────────────────────────
