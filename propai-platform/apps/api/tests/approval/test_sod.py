"""공용 SoD(직무분리) 헬퍼(enforce_sod, 백로그③) 게이트 테스트 — 순수 함수·무 DB.

W1-B(심의엔진 hitl_queue.py) 계약과 동형인 3가지 표식을 기계 검증한다:
 ① 자기승인(author == approver, strip 정규화 후) → SelfApprovalError.
 ② 타인 승인(author != approver) → SodCheck("passed").
 ③ author 미기록(None/공백) → SodCheck("skipped(author 미기록)")(skip — 차단 아님).
 ④ strip 정규화(양쪽 공백)만 적용, casefold(대소문자 무시)는 하지 않는다(W1-B 선례 동일).
"""
from __future__ import annotations

import pytest

from app.services.approval.sod import SelfApprovalError, SodCheck, enforce_sod


def test_self_approval_raises():
    """①author == approver(동일 문자열)면 SelfApprovalError."""
    with pytest.raises(SelfApprovalError):
        enforce_sod("user-a", "user-a", context="test")


def test_self_approval_raises_after_strip_normalization():
    """양쪽 공백만 다른 동일인도 자기승인으로 차단(strip 정규화)."""
    with pytest.raises(SelfApprovalError):
        enforce_sod("user-a", "  user-a  ", context="test")


def test_different_approver_passes():
    """②author != approver → 정상 통과("passed")."""
    result = enforce_sod("user-a", "user-b", context="test")
    assert result == SodCheck(marker="passed")


def test_author_none_skips_without_raising():
    """③author=None(해당 도메인이 author를 기록하지 않음) → skip 표식, 예외 없음."""
    result = enforce_sod(None, "user-b", context="test")
    assert result.marker == "skipped(author 미기록)"


def test_author_blank_string_treated_as_missing():
    """author가 공백만이면 미기록으로 취급(빈 문자열을 유효 author로 오인하지 않음)."""
    result = enforce_sod("   ", "user-b", context="test")
    assert result.marker == "skipped(author 미기록)"


def test_case_sensitivity_not_folded():
    """casefold는 적용하지 않는다(W1-B 선례 동일) — 대소문자만 다르면 별개 신원으로 통과."""
    result = enforce_sod("User-A", "user-a", context="test")
    assert result.marker == "passed"


def test_error_message_includes_context_and_actor():
    """예외 메시지에 어느 형제 경로(context)의 위반인지 표기된다(디버깅 가능성)."""
    with pytest.raises(SelfApprovalError, match="site_basis_approve"):
        enforce_sod("same-user", "same-user", context="site_basis_approve")
