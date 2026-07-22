"""공용 SoD(직무분리) 헬퍼 — 형제 승인 경로 3곳(site_basis·design_run·team_member) 일원화.

v4.0 Wave1 마감 백로그③ — W1-B(#420, 심의엔진 HITL)가 이미 구현한 SoD 계약("작성자(author)==
승인자(approver)면 자기승인 차단·author 미기록은 skip 표식으로 정직 통과")을 메인 플랫폼
(apps/api)의 형제 승인 경로 3곳(site_basis_service.approve_site_basis·design_run_store.
approve_design_run·team_service.approve_member)에 동형(同型) 재구현한다.

★"동형 재구현"이지 "공유"가 아니다: 심의엔진(services/deliberation-review)은 별도 FastAPI 앱
(별도 배포단위·별도 requirements)이라 이 apps/api 트리에서 그 코드(app.core.errors.
SelfApprovalError·hitl_queue.HITLQueue._sod_marker)를 import할 수 없다. 이 파일은 그 계약의
어휘·판정 규칙·표식 문언을 그대로 복제해, 두 앱이 "같은 SoD 정책"을 쓴다는 사실이 코드만
봐도 드러나게 한다(로직 수렴이 목표이지 import 수렴이 아니다 — 그린필드 재구현 금지 원칙과
충돌하지 않는다. 원형 3도메인의 승인 규칙 자체(can_approve 류)는 이 파일이 건드리지 않는다).

sod_check 표식(무언 통과 금지 — W1-B와 동일 관례):
  "passed"                 — author 기록 존재 + author != approver(정상 통과, 자기승인 아님).
  "skipped(author 미기록)" — author가 None/공백(해당 도메인이 author를 기록하지 않음, 또는
                              아직 배선되지 않음 — 레거시 데이터 문제가 아니라 정직한 미배선 표시).
자기승인(author == approver, strip 정규화 후 비교)이면 표식을 만들지 않고 SelfApprovalError를
던진다 — 호출측(각 도메인의 approve 함수)이 잡아서 자기 도메인 고유의 ok/message 응답 관례로
변환한다(site_basis·design_run은 {"ok": False, "message": ...}, team은 {"ok": False, "error": ...}).
"""
from __future__ import annotations

from dataclasses import dataclass


class SelfApprovalError(Exception):
    """SoD(직무분리) 위반 — 작성자(author)와 승인자(approver)가 동일함.

    심의엔진 app.core.errors.SelfApprovalError(W1-B)와 이름·의미론을 동일하게 맞춘 계약 동형
    클래스다 — 두 앱은 별도 배포단위라 클래스 자체를 공유(import)할 수 없다(모듈 docstring 참조).
    """


@dataclass(frozen=True)
class SodCheck:
    """SoD 판정 결과(통과분만) — marker만 담는다. 차단은 SelfApprovalError로 별도 승격된다."""

    marker: str


def enforce_sod(author: str | None, approver: str, *, context: str) -> SodCheck:
    """author==approver(공백 strip 정규화 후 비교) 자기승인 차단. author 미기록이면 skip 표식.

    - author가 None이거나 strip 후 빈 문자열 → SodCheck("skipped(author 미기록)") 반환(통과 —
      아직 해당 도메인이 author를 기록하지 않는다는 뜻이지, 레거시 데이터 오염이 아니다).
    - author == approver(양쪽 strip 후) → SelfApprovalError(자기승인 거부, 값은 만들지 않음).
    - 그 외(author 기록 존재 + 서로 다름) → SodCheck("passed") 반환(정상 통과).

    casefold는 적용하지 않는다(W1-B hitl_queue.py 선례와 동일 — principal ID 체계가 대소문자
    구분 없는지 확정되지 않은 상태에서 과도한 정규화를 피하고, strip만 방어적으로 적용한다).

    context: 호출 도메인 식별자(예: "site_basis_approve"/"design_run_approve"/"team_member_approve")
      — 로그·예외 메시지에서 어느 형제 경로의 위반인지 구분하기 위한 표기용(판정 로직에는 무관여).
    """
    approver_norm = (approver or "").strip()
    author_norm = author.strip() if author is not None else ""
    if not author_norm:
        return SodCheck(marker="skipped(author 미기록)")
    if author_norm == approver_norm:
        raise SelfApprovalError(
            f"SoD 위반 — 작성자와 승인자가 동일함(context={context}, actor={approver_norm})"
        )
    return SodCheck(marker="passed")


__all__ = ["SelfApprovalError", "SodCheck", "enforce_sod"]
