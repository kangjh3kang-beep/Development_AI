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

★R2(R1 REVISE HIGH 봉합 — 1인 테넌트 영구 락아웃 방지, 오케스트레이터 제품 결정 옵션(b) 변형):
SoD 하드 차단(SelfApprovalError)은 "테넌트 사용자 수 > 1"일 때만 강제한다. 사용자 1명뿐인
solo 테넌트에서는 자기승인을 허용하되(무회귀 최우선 — 이 커밋 전에는 성공하던 assess→approve
왕복이 solo 테넌트에서 영구히 막히면 그 자체가 회귀다) sod_check="waived(solo-tenant)"로 정직
표식만 남긴다(v4 스펙의 SoD 의도는 다인 조직의 직무분리이며, solo 테넌트에는 적용 실익이 없다는
제품 결정). 이 판정(테넌트 사용자 수 조회)은 enforce_sod 자신이 하지 않는다 — DB·테넌트를
전혀 모르는 순수 함수로 남기고, 판정 결과만 호출측이 `sole_operator`/`determination_failed`
키워드로 주입한다(정책과 판정 로직의 분리 — 이 헬퍼가 아는 것은 "무엇을 할지"뿐이다).
  - sole_operator=None(기본, 이 정책을 쓰지 않는 도메인 — design_run·team_member는 전달하지
    않는다) → 기존 R1 동작 그대로(자기승인이면 무조건 SelfApprovalError).
  - determination_failed=True(호출측의 사용자 수 조회 자체가 실패·불가) → fail-open(차단하지
    않음) + marker="waived(solo-판정실패)". 판정 인프라 장애가 정상 사용자를 승인 불능으로
    영구 락아웃시키는 것을 막기 위한 보수적 선택이지만, "solo임을 확인해서" 통과한 것과는
    다른 표식으로 감사 가능성을 유지한다(무언 "waived(solo-tenant)" 참칭 금지).
  - sole_operator=True(판정 성공, 사용자 수<=1) → marker="waived(solo-tenant)".
  - sole_operator=False(판정 성공, 사용자 수>1) → 기존 R1 동작 그대로(자기승인이면 차단).

sod_check 표식 4종(무언 통과 금지 — W1-B와 동일 관례 + R2 신설 2종):
  "passed"                    — author 기록 존재 + author != approver(정상 통과, 자기승인 아님).
  "skipped(author 미기록)"    — author가 None/공백(해당 도메인이 author를 기록하지 않음, 또는
                                 아직 배선되지 않음 — 레거시 데이터 문제가 아니라 정직한 미배선 표시).
  "waived(solo-tenant)"       — 자기승인이지만 테넌트 사용자 수<=1로 확인돼 정책상 허용(R2).
  "waived(solo-판정실패)"     — 자기승인이지만 solo 여부 판정 자체가 실패해 fail-open(R2).
자기승인(author == approver, strip 정규화 후 비교)인데 solo 관련 waiver 조건에 해당하지 않으면
SelfApprovalError를 던진다 — 호출측(각 도메인의 approve 함수)이 잡아서 자기 도메인 고유의
ok/message 응답 관례로 변환한다(site_basis·design_run은 {"ok": False, "message": ...}, team은
{"ok": False, "error": ...}).
"""
from __future__ import annotations

from dataclasses import dataclass


class SelfApprovalError(Exception):
    """SoD(직무분리) 위반 — 작성자(author)와 승인자(approver)가 동일함(solo 테넌트 waiver 미해당).

    심의엔진 app.core.errors.SelfApprovalError(W1-B, RefusedError(DomainError) 하위)와 "의미론"은
    동일하게 맞춘 계약 동형 클래스다 — 상속 계층 자체는 앱마다 다르다(이 apps/api 트리에는
    심의엔진의 DomainError/RefusedError 베이스가 없어 그대로 흉내 내면 존재하지 않는 개념을
    지어내는 것이 되므로, 정직하게 Exception 직속으로 둔다). 두 앱은 별도 배포단위라 클래스
    자체를 공유(import)할 수도 없다(모듈 docstring 참조).
    """


@dataclass(frozen=True)
class SodCheck:
    """SoD 판정 결과(통과·waiver 포함) — marker만 담는다. 하드 차단만 SelfApprovalError로 승격된다."""

    marker: str


def enforce_sod(
    author: str | None,
    approver: str,
    *,
    context: str,
    sole_operator: bool | None = None,
    determination_failed: bool = False,
) -> SodCheck:
    """author==approver(공백 strip 정규화 후 비교) 자기승인 차단. author 미기록이면 skip 표식.

    판정 순서(먼저 해당하는 조건 하나만 적용):
    1) approver가 비어있으면(None/공백만) ValueError — 승인자 신원 미기록 금지(W1-B
       hitl_queue._require_approver 동형 — 4번째 채택자가 빈 승인자로 통과하는 것을 방지).
    2) author가 None이거나 strip 후 빈 문자열 → SodCheck("skipped(author 미기록)") 반환(통과 —
       아직 해당 도메인이 author를 기록하지 않는다는 뜻이지, 레거시 데이터 오염이 아니다).
    3) author != approver(양쪽 strip 후) → SodCheck("passed") 반환(정상 통과, 자기승인 아님).
    4) author == approver(자기승인 후보) — R2 solo waiver 정책 분기:
       - determination_failed=True → SodCheck("waived(solo-판정실패)")(fail-open).
       - sole_operator is True     → SodCheck("waived(solo-tenant)").
       - 그 외(sole_operator None/False) → SelfApprovalError(하드 차단).

    casefold는 적용하지 않는다(W1-B hitl_queue.py 선례와 동일 — principal ID 체계가 대소문자
    구분 없는지 확정되지 않은 상태에서 과도한 정규화를 피하고, strip만 방어적으로 적용한다).

    context: 호출 도메인 식별자(예: "site_basis_approve"/"design_run_approve"/"team_member_approve")
      — 로그·예외 메시지에서 어느 형제 경로의 위반인지 구분하기 위한 표기용(판정 로직에는 무관여).
    sole_operator/determination_failed: 모듈 docstring "R2" 절 참조 — 이 함수는 테넌트·DB를
      전혀 알지 못한다. 판정(테넌트 사용자 수 조회)은 전적으로 호출측 책임이다.
    """
    approver_norm = (approver or "").strip()
    if not approver_norm:
        raise ValueError(
            "approver는 필수임(SoD — 승인자 신원 미기록 금지, W1-B _require_approver 동형)."
        )
    author_norm = author.strip() if author is not None else ""
    if not author_norm:
        return SodCheck(marker="skipped(author 미기록)")
    if author_norm != approver_norm:
        return SodCheck(marker="passed")
    # 여기부터 author == approver(자기승인 후보) — R2 solo waiver 정책만 이 차단을 면제한다.
    if determination_failed:
        return SodCheck(marker="waived(solo-판정실패)")
    if sole_operator is True:
        return SodCheck(marker="waived(solo-tenant)")
    raise SelfApprovalError(
        f"SoD 위반 — 작성자와 승인자가 동일함(context={context}, actor={approver_norm})"
    )


__all__ = ["SelfApprovalError", "SodCheck", "enforce_sod"]
