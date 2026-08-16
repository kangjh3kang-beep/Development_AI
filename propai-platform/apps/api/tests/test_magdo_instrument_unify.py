"""정책표 통로 일원화 — 화면이 **수용 대상지를 "매도청구 가능"으로** 안내하던 결함의 회귀망.

★배포된 채 틀린 안내를 하고 있었다(실측):
    도시개발사업      화면 "매도청구 가능 잔여 33%"  ← 실제 instrument=**수용**
    가로주택정비사업   화면 "매도청구 가능 잔여 20%"  ← 실제 판정보류(트랙 미정)

수용과 매도청구는 절차(협의→재결→보상 vs 3개월협의→소)도 보상기준(공시지가·개발이익 배제
vs **시가**)도 다르다.

★락은 **두 모집단을 가른다** — 같은 함수가 사업방식에 따라 **다른 값**을 내야 한다.
  차가 0이면 잠금이 아니다.
"""

from __future__ import annotations

import pytest

from app.services.development.scenario_simulator import (
    MAGDO_RULES,
    _magdo,
    scheme_legal_profile,
)

EXPROPRIATION_SCHEME = "도시개발사업(도시개발법)"   # 실제 수단 = 수용
SELL_CLAIM_SCHEME = "재개발·재건축(정비사업)"        # 실제 수단 = 매도청구
TRACK_SCHEME = "가로주택정비사업"                    # 트랙 미정 → 수단 판정보류


def test_수용_사업방식을_매도청구로_말하지_않는다() -> None:
    """★핵심 회귀 — 도시개발은 **수용**(토지보상법 준용)이지 매도청구가 아니다."""
    m = _magdo(EXPROPRIATION_SCHEME)
    assert m is not None
    assert m["instrument"] == "수용", m
    assert m["instrument"] != "매도청구"
    assert m["governing_act"] == "도시개발법", m


def test_같은_함수가_사업방식에_따라_다른_수단을_낸다() -> None:
    """두 모집단 — 수단이 갈리지 않으면 이 필드는 장식이다."""
    a = _magdo(EXPROPRIATION_SCHEME)["instrument"]
    b = _magdo(SELL_CLAIM_SCHEME)["instrument"]
    c = _magdo(TRACK_SCHEME)["instrument"]
    assert a == "수용" and b == "매도청구" and c is None, (a, b, c)
    assert len({a, b, c}) == 3, "세 모집단이 같은 값을 낸다 — 잠금이 아니다"


def test_트랙_미정이면_잔여비율을_단정하지_않는다() -> None:
    """★미정인데 숫자를 내면 그 단정 자체가 거짓이다."""
    m = _magdo(TRACK_SCHEME)
    assert m["instrument_undetermined"] is True
    assert m["claimable_remainder_pct"] is None, m
    # 대조군 — 확정된 방식은 숫자를 낸다(차가 0이면 잠금이 아니다).
    fixed = _magdo(SELL_CLAIM_SCHEME)
    assert fixed["instrument_undetermined"] is False
    assert isinstance(fixed["claimable_remainder_pct"], (int, float))


def test_동의임계의_기준축이_명시된다() -> None:
    """★`consent_pct` 는 행마다 기준이 다르다 — 축 없이 쓰면 면적 임계를 개수에 곱한다."""
    assert _magdo(EXPROPRIATION_SCHEME)["consent_basis"] == "land_area"
    assert _magdo(SELL_CLAIM_SCHEME)["consent_basis"] == "owner_count"
    assert _magdo("지구단위계획 연계")["consent_basis"] == "use_right_area"


@pytest.mark.parametrize("scheme", sorted(MAGDO_RULES))
def test_모든_정책표_행이_축을_선언한다(scheme: str) -> None:
    """★파생형 — 새 사업방식이 축 없이 추가되면 자동으로 걸린다(목록형이면 못 잡는다)."""
    prof = scheme_legal_profile(scheme)
    assert prof is not None
    assert prof["consent_basis"] in ("owner_count", "land_area", "use_right_area"), (
        f"{scheme} 의 consent_basis 가 없다 — 소비처가 축을 몰라 개수/면적을 혼동한다"
    )


def test_정책표_직접조회는_공용통로_하나뿐이다() -> None:
    """★같은 표를 두 곳에서 읽으면 반드시 갈라진다 — 이 결함이 정확히 그래서 났다.

    `_magdo` 가 `scheme_legal_profile` 을 경유하는지 **행동으로** 확인한다:
    프로필이 내는 값과 `_magdo` 가 내는 값이 어긋나면 통로가 둘이라는 뜻이다.
    """
    for scheme in MAGDO_RULES:
        prof, m = scheme_legal_profile(scheme), _magdo(scheme)
        assert m["governing_act"] == prof["governing_act"], scheme
        assert m["consent_threshold_pct"] == prof["consent_threshold_pct"], scheme
        assert m["consent_basis"] == prof["consent_basis"], scheme
