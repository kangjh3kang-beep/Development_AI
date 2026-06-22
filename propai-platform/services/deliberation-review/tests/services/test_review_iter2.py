"""코드리뷰 iter2 회귀 가드 — comparator enum 거부·confidence 범위·BCR 판정."""
import pytest
from pydantic import ValidationError

from app.contracts.enums import Comparator
from app.contracts.finding import Finding, Verdict
from app.contracts.rule import Rule
from app.services.land.remaining_capacity import remaining_capacity


def test_comparator_rejects_invalid():
    # 미정의 comparator는 계약 단계에서 거부(무음 '!=' 폴백 제거).
    with pytest.raises(ValidationError):
        Rule(rule_id="x", comparator="≤")  # 오타/미정의 기호
    assert Rule(rule_id="x", comparator="<=").comparator == Comparator.LE


def test_confidence_range_enforced():
    # 신뢰도 [0,1] 범위이탈은 계약에서 거부(게이트 오통과/오차단 방지).
    with pytest.raises(ValidationError):
        Finding(rule_id="x", verdict=Verdict.COMPLIANT, composite_confidence=1.5)
    with pytest.raises(ValidationError):
        Finding(rule_id="x", verdict=Verdict.COMPLIANT, composite_confidence=-0.1)
    assert Finding(rule_id="x", verdict=Verdict.COMPLIANT, composite_confidence=0.8)


def test_remaining_capacity_bcr_judged():
    # 기존 건폐율 제공 → 건폐율 상한(서울 제2종일반 60%) 대비 판정(국토계획법 §84).
    rc = remaining_capacity("제2종일반주거지역", 1000.0, 1500.0,
                            pnu="1111010100100010000", existing_bcr=75.0)
    assert rc["bcr_limit_pct"] == 60 and rc["existing_bcr_pct"] == 75.0
    assert rc["bcr_over_limit"] is True and rc["remaining_bcr_pct"] == -15.0
    # 건폐율 결손 → 미판정 표면화(무음 추정 금지).
    rc2 = remaining_capacity("제2종일반주거지역", 1000.0, 1500.0, pnu="1111010100100010000")
    assert rc2["bcr_over_limit"] is None
    assert any("건폐율" in c and "미판정" in c for c in rc2["rationale"]["caveats"])
