"""공용 SoD(직무분리) 헬퍼(enforce_sod, 백로그③) 게이트 테스트 — 순수 함수·무 DB.

W1-B(심의엔진 hitl_queue.py) 계약과 동형인 표식을 기계 검증한다:
 ① 자기승인(author == approver, strip 정규화 후) → SelfApprovalError(R2 solo waiver 미해당 시).
 ② 타인 승인(author != approver) → SodCheck("passed").
 ③ author 미기록(None/공백) → SodCheck("skipped(author 미기록)")(skip — 차단 아님).
 ④ strip 정규화(양쪽 공백)만 적용, casefold(대소문자 무시)는 하지 않는다(W1-B 선례 동일).
 ⑤(R2 HIGH 봉합) sole_operator=True → SodCheck("waived(solo-tenant)")(자기승인 허용+정직 표식).
 ⑥(R2 HIGH 봉합) determination_failed=True → SodCheck("waived(solo-판정실패)")(fail-open).
 ⑦(R2 MEDIUM) approver 공백/공백문자열 → ValueError(W1-B _require_approver 동형).
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


# ══════════════════════════════════════════════════════════════════════════
# R2 HIGH 봉합 — solo 테넌트 waiver(1인 테넌트 영구 락아웃 방지)
# ══════════════════════════════════════════════════════════════════════════

def test_sole_operator_true_waives_self_approval():
    """⑤sole_operator=True(테넌트 사용자 수<=1 확인됨) → 자기승인이 차단되지 않고
    "waived(solo-tenant)" 표식만 남는다(예외 없음)."""
    result = enforce_sod("solo-user", "solo-user", context="site_basis_approve", sole_operator=True)
    assert result == SodCheck(marker="waived(solo-tenant)")


def test_determination_failed_waives_self_approval_with_distinct_marker():
    """⑥determination_failed=True(solo 판정 자체가 실패) → fail-open으로 통과하되
    "waived(solo-tenant)"과는 구분되는 "waived(solo-판정실패)" 표식을 남긴다(무언 확정 참칭 금지)."""
    result = enforce_sod(
        "user-x", "user-x", context="site_basis_approve", determination_failed=True,
    )
    assert result == SodCheck(marker="waived(solo-판정실패)")


def test_determination_failed_takes_precedence_over_sole_operator_value():
    """determination_failed=True가 sole_operator 값보다 우선한다 — 판정이 실패했다면 그 자체가
    "확정된 solo/멀티" 어느 쪽도 아니므로 판정실패 표식이어야 한다(모순 입력 방어)."""
    result = enforce_sod(
        "user-y", "user-y", context="test", sole_operator=False, determination_failed=True,
    )
    assert result.marker == "waived(solo-판정실패)"


def test_sole_operator_false_still_blocks_self_approval():
    """sole_operator=False(테넌트 사용자 수>1 확인됨) → R1과 동일하게 자기승인은 그대로 차단."""
    with pytest.raises(SelfApprovalError):
        enforce_sod("multi-user", "multi-user", context="site_basis_approve", sole_operator=False)


def test_sole_operator_default_none_preserves_r1_hard_block():
    """이 정책을 쓰지 않는 도메인(design_run·team_member — sole_operator 미전달)은 R1과 동일하게
    자기승인이 무조건 차단된다(무회귀 — 기본값 None은 solo 정책 자체를 적용하지 않는다는 뜻)."""
    with pytest.raises(SelfApprovalError):
        enforce_sod("user-z", "user-z", context="team_member_approve")


def test_different_approver_unaffected_by_sole_operator_kwargs():
    """자기승인이 아니면(author != approver) sole_operator/determination_failed 값과 무관하게
    항상 "passed"다 — solo 정책은 자기승인 후보에만 관여한다."""
    result = enforce_sod(
        "user-a", "user-b", context="test", sole_operator=True, determination_failed=True,
    )
    assert result.marker == "passed"


# ══════════════════════════════════════════════════════════════════════════
# R2 MEDIUM — approver 필수(W1-B _require_approver 동형)
# ══════════════════════════════════════════════════════════════════════════

def test_blank_approver_raises_value_error():
    """⑦approver가 빈 문자열이면 ValueError(승인자 신원 미기록 금지)."""
    with pytest.raises(ValueError, match="approver"):
        enforce_sod("user-a", "", context="test")


def test_none_approver_raises_value_error():
    """approver=None도 동일하게 ValueError(타입힌트상 str이지만 방어적으로 검증)."""
    with pytest.raises(ValueError, match="approver"):
        enforce_sod("user-a", None, context="test")  # type: ignore[arg-type]


def test_whitespace_only_approver_raises_value_error():
    """approver가 공백만이어도 ValueError(strip 후 빈 문자열은 미기록과 동치)."""
    with pytest.raises(ValueError, match="approver"):
        enforce_sod("user-a", "   ", context="test")
