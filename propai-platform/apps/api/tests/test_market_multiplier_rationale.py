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
from app.services.land_intelligence.land_price_estimator import _market_multiplier

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
    """등록 지역 / 광역 폴백 / 전국 폴백이 서로 구별 가능해야 한다(사용자가 알 권리)."""
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
