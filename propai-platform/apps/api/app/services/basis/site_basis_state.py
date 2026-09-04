"""부지기반(site basis) 상태머신 — 명세 P7 artifact_status 의미론 최소 사상(WP-G).

순수 함수(무 I/O·DB 불의존)로만 구성 — 결정적 단위테스트가 라이브 API·DB 없이 가능하다.
DB/원장 연동은 site_basis_service.py(별도 파일)가 이 모듈을 호출해 수행한다.

핵심 의미론
-----------
- artifact_status(운영 상태) ∈ {DRAFT, ANALYZED, REVIEW_REQUIRED, APPROVED, STALE}.
- basis_status(부지기반 판정) ∈ {ADVISORY, AUTHORIZED} — AUTHORIZED는 artifact_status==APPROVED
  에서만 성립한다(구조적으로 강제). APPROVED는 오직 "approve" 액션(인간승인, approved_by 필수)
  으로만 도달 가능하고, 그 액션은 승인 시점 P0 전건 충족을 요구한다.
  ⇒ "인간승인 없는 자동 AUTHORIZED 0"이 이 모듈의 구조 자체로 성립한다(별도 방어코드 불필요).
- P0 게이트 3종(P2 개발행위·P3 권리·P4 접도) 중 하나라도 미충족·미확정이면 AUTHORIZED 불가
  (ADVISORY 유지) — aggregate_p0()가 all_clear=False를 반환하면 approve()가 거부된다.

★재사용: P2(dev_act_permit_gate.STATUS_*)·P4(access.AccessStatus) 두 표면이 이미 동일한 상태
어휘(PASS/CONDITIONAL/BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION)를 공유하므로, 이 모듈은 그 문자열
status 값만 받아 판정한다(각 게이트의 판정 로직 자체는 재구현하지 않는다 — 그린필드 금지 준수).
P3 권리는 registry_analysis_service의 전용 차단 상태머신이 아직 없어(알려진 갭), 이번 WP는
'권리분석 미확정=AUTHORIZED 차단'이라는 보수 게이트(rights_confirmed bool)로만 소비한다.

★W2-4 Required Data Matrix와의 관계(즉시 전면 이관 금지 — 무회귀, 특수사례로만 문서화):
이 모듈의 ``aggregate_p0()``(access/dev_act_permit/rights 3게이트 중 하나라도 미충족이면
전체 미충족)은 provenance.required_data.evaluate_matrix()로 access/dev_act_permit/rights
3개 필드를 모두 requirement_level=REQUIRED+critical=True로 선언한 매트릭스와 동형이다(이
모듈의 PASS/CONDITIONAL="충족"·BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION/None="미충족" 분류를
그 계약의 PRESENT_VALID·PRESENT_INVALID/MISSING으로 옮기면 된다). 이 동형성은
tests/test_required_data.py로 증명하지만, 이 모듈 자체(DB·원장·승인 상태전이와 깊게 얽혀
있음)는 이번 WP에서 evaluate_matrix()로 재구현하지 않는다(즉시 이관은 무회귀 원칙에 반함 —
후속 과제).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ArtifactStatus(StrEnum):
    """운영 상태(artifact_status) — 명세 P7 5종 최소 사상."""

    DRAFT = "DRAFT"
    ANALYZED = "ANALYZED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    STALE = "STALE"


class BasisStatus(StrEnum):
    """부지기반 판정 — 통합분석 산출의 ADVISORY/AUTHORIZED 분리(명세 WP-G 목표)."""

    ADVISORY = "ADVISORY"
    AUTHORIZED = "AUTHORIZED"


class GateName(StrEnum):
    """P0 게이트 3종 식별자."""

    ACCESS = "access"                  # P4 — WP-A access_basis_service(AccessAssessment.status)
    DEV_ACT_PERMIT = "dev_act_permit"  # P2 — WP-B dev_act_permit_gate(assess_dev_act_permit.status)
    RIGHTS = "rights"                  # P3 — 권리분석 보수 게이트(확정 여부만)


# P2·P4가 공유하는 정직 상태 어휘 — CONDITIONAL은 "허가·협의를 조건으로 진행 가능"이므로 P0
# 충족으로 인정한다(개발이 완전 무조건 확정이라는 뜻은 아니다). BLOCKED·미확정만 AUTHORIZED를 차단.
_CLEAR_STATUSES = frozenset({"PASS", "CONDITIONAL"})
_BLOCKING_STATUSES = frozenset({"BLOCKED", "REQUIRES_AUTHORITY_CONFIRMATION"})


class IllegalTransitionError(Exception):
    """허용되지 않은 artifact_status 전이 시도(예: DRAFT→APPROVED 직행)."""


@dataclass(frozen=True)
class GateResult:
    """단일 P0 게이트 판정 결과(직렬화 가능 — jsonb 원장·응답 부착용).

    source(신뢰경계 — MEDIUM-3 교정): 이 status가 어디서 왔는지 표기한다.
      "server_derived"                — 권위 서비스(access_basis_service·dev_act_permit_gate)
                                         재도출값을 그대로 채택.
      "server_derived_conflict_resolved" — 재도출값과 caller 자기신고가 불일치해 더 보수적
                                         (차단쪽) 값을 채택.
      "caller_declared"               — 재도출 재료(site_context) 없이 caller 자기신고를 그대로
                                         신뢰(P3 권리 게이트는 이 WP에서 항상 이 값).
      "unknown"                       — 아무 신호도 없음(값 자체가 None).
    """

    name: str
    clear: bool
    status: str | None
    reason: str
    source: str = "caller_declared"

    def to_dict(self) -> dict[str, Any]:
        return {"name": str(self.name), "clear": self.clear, "status": self.status,
                "reason": self.reason, "source": self.source}


def evaluate_gate(name: str, status: str | None, *, source: str = "caller_declared") -> GateResult:
    """P2·P4 공용 어휘 기반 단일 게이트 판정.

    status 미상(None)은 정직하게 차단으로 취급한다(REQUIRES_AUTHORITY_CONFIRMATION과 동치) —
    데이터가 없다고 낙관적으로 PASS 처리하지 않는다(무날조·정직 강등 원칙). 이때 source는
    "unknown"으로 고정(아무 것도 신고되지 않았으므로 caller_declared라는 표기조차 부정확).
    """
    if status is None:
        return GateResult(name=name, clear=False, status=None, source="unknown",
                           reason=f"{name}: 판정 데이터 미확보(미상) — AUTHORIZED 차단")
    normalized = str(status).strip().upper()
    if normalized in _CLEAR_STATUSES:
        return GateResult(name=name, clear=True, status=normalized, source=source,
                           reason=f"{name}: {normalized} — P0 충족")
    return GateResult(name=name, clear=False, status=normalized, source=source,
                       reason=f"{name}: {normalized} — P0 미충족(AUTHORIZED 차단)")


def evaluate_rights_gate(rights_confirmed: bool | None) -> GateResult:
    """P3 권리 게이트 — '권리분석 미확정=AUTHORIZED 차단' 보수 게이트.

    registry_analysis_service는 현행 LLM 서술형(전용 차단 상태머신 부재)이라, 이번 WP는 확정 여부
    (rights_confirmed=True)만 P0 충족으로 인정한다. None/False는 모두 미확정으로 정직 차단.
    재도출 권위 서비스가 없어 source는 항상 caller_declared(명시 신고)·unknown(미신고)뿐이다.
    """
    if rights_confirmed is True:
        return GateResult(name=GateName.RIGHTS, clear=True, status="CONFIRMED", source="caller_declared",
                           reason="rights: 권리분석 확정됨 — P0 충족")
    if rights_confirmed is False:
        return GateResult(name=GateName.RIGHTS, clear=False, status="UNCONFIRMED", source="caller_declared",
                           reason="rights: 권리분석 미확정 — AUTHORIZED 차단(보수 게이트, 전용 상태머신 부재)")
    return GateResult(name=GateName.RIGHTS, clear=False, status=None, source="unknown",
                       reason="rights: 권리분석 미확정 — AUTHORIZED 차단(보수 게이트, 전용 상태머신 부재)")


def aggregate_p0(
    *,
    access_status: str | None,
    dev_act_status: str | None,
    rights_confirmed: bool | None,
    access_source: str = "caller_declared",
    dev_act_source: str = "caller_declared",
) -> tuple[bool, list[GateResult]]:
    """P2·P3·P4 P0 게이트 3종을 집계 — 하나라도 미충족·미확정이면 all_clear=False.

    access_source/dev_act_source: 호출측(site_basis_service)이 권위 서비스로 재도출했으면
    "server_derived"(또는 불일치 조정 시 "server_derived_conflict_resolved")를, 재도출 재료가
    없어 caller 자기신고를 그대로 썼으면 기본값 "caller_declared"를 넘긴다.
    """
    gates = [
        evaluate_gate(GateName.ACCESS, access_status, source=access_source),
        evaluate_gate(GateName.DEV_ACT_PERMIT, dev_act_status, source=dev_act_source),
        evaluate_rights_gate(rights_confirmed),
    ]
    return all(g.clear for g in gates), gates


def classify_after_assess(all_p0_clear: bool) -> ArtifactStatus:
    """자동판정 — P0 전건 충족이면 ANALYZED, 아니면 REVIEW_REQUIRED(인간 검토 필요)."""
    return ArtifactStatus.ANALYZED if all_p0_clear else ArtifactStatus.REVIEW_REQUIRED


# P0 상태 어휘의 '차단 정도' 순위 — reconcile_status가 caller 자기신고와 권위 재도출값이
# 불일치할 때 더 보수적(차단쪽)인 값을 고르는 데 쓴다. 미상 등급은 REQUIRES_AUTHORITY_CONFIRMATION
# 취급(보수) — 알 수 없는 문자열을 낙관적으로 PASS 취급하지 않는다.
_STATUS_BLOCK_RANK = {"PASS": 0, "CONDITIONAL": 1, "REQUIRES_AUTHORITY_CONFIRMATION": 2, "BLOCKED": 3}


def reconcile_status(caller_declared: str | None, authoritative: str | None) -> tuple[str | None, str]:
    """caller 자기신고 status와 권위 서비스 재도출(authoritative) status를 신뢰경계에 따라 조정.

    ★MEDIUM-3 교정(택1의 (a)): /basis/assess가 site_context(판정 재료)를 받으면 호출측이
    access_basis_service·dev_act_permit_gate로 서버측 재도출한 뒤 이 함수로 caller 신고값과
    교차검증한다. 불일치 시 더 보수적(차단쪽) 값을 채택하고, 그 사실을 source로 남긴다(날조 방지).

    반환: (채택 status, source)
      authoritative 없음      → (caller_declared, "caller_declared")  — 재도출 재료 없어 자기신고 신뢰.
      caller_declared 없음    → (authoritative, "server_derived")     — 신고값 없어 재도출값만 사용.
      둘 다 같음               → (그 값, "server_derived")             — 일치 확인됨.
      불일치                   → (보수값, "server_derived_conflict_resolved")
    """
    if authoritative is None:
        return caller_declared, "caller_declared"
    if caller_declared is None:
        return authoritative, "server_derived"
    a = authoritative.strip().upper()
    c = caller_declared.strip().upper()
    if a == c:
        return a, "server_derived"
    rank_a = _STATUS_BLOCK_RANK.get(a, 2)
    rank_c = _STATUS_BLOCK_RANK.get(c, 2)
    conservative = a if rank_a >= rank_c else c
    return conservative, "server_derived_conflict_resolved"


def cap_status_by_trust(status: ArtifactStatus, gates: list[GateResult]) -> ArtifactStatus:
    """P0 게이트(P2 dev_act_permit·P4 access) 중 하나라도 caller_declared(미검증 자기신고)면
    ANALYZED 승격을 금지하고 REVIEW_REQUIRED로 강등한다 — P0 청산 날조 방지(MEDIUM-3 보수 정책).

    권위 서비스로 재도출·교차검증되지 않은 자기신고만으로는 '인간승인 대기 자격'(ANALYZED)에
    자동 도달시키지 않는다 — 인간 재검토를 강제한다. rights(P3)는 이 WP에서 항상 caller_declared
    (전용 재도출 서비스 부재, 별도 명시된 보수 게이트)이므로 이 상한의 판단 대상에서 제외한다.
    """
    if status != ArtifactStatus.ANALYZED:
        return status
    verifiable_names = {GateName.ACCESS.value, GateName.DEV_ACT_PERMIT.value}
    unverified = any(g.name in verifiable_names and g.source == "caller_declared" for g in gates)
    return ArtifactStatus.REVIEW_REQUIRED if unverified else status


def basis_status_of(artifact_status: ArtifactStatus) -> BasisStatus:
    """AUTHORIZED는 APPROVED(=인간승인 경유)에서만 성립 — 그 외 전부 ADVISORY."""
    return BasisStatus.AUTHORIZED if artifact_status == ArtifactStatus.APPROVED else BasisStatus.ADVISORY


# ── 전이 그래프 ──────────────────────────────────────────────────────────────
# assess: 어느 상태에서든 재분석 가능하나, APPROVED는 제외(승인된 결과는 evidence_changed로만
#   STALE로 내려간 뒤 재분석해야 한다 — APPROVED→ANALYZED 직행 우회를 막기 위한 설계).
_ASSESS_SOURCES = frozenset({
    ArtifactStatus.DRAFT, ArtifactStatus.ANALYZED, ArtifactStatus.REVIEW_REQUIRED, ArtifactStatus.STALE,
})
# evidence_changed: 이미 판정이 존재하는 상태에서만 의미가 있다(DRAFT는 애초에 판정이 없음).
_EVIDENCE_CHANGE_SOURCES = frozenset({
    ArtifactStatus.ANALYZED, ArtifactStatus.REVIEW_REQUIRED, ArtifactStatus.APPROVED,
})


def can_approve(
    current: ArtifactStatus, all_p0_clear: bool, approved_by: str | None,
) -> tuple[bool, str | None]:
    """인간승인 액션의 합법성 사전검사 — (허용여부, 거부사유)."""
    if not approved_by or not str(approved_by).strip():
        return False, "인간승인 액션에는 승인자(approved_by)가 필요합니다(자동 승인 금지)."
    if current == ArtifactStatus.APPROVED:
        return False, "이미 APPROVED 상태입니다(재승인 불필요 — 변경 시 재분석 후 재승인)."
    if current != ArtifactStatus.ANALYZED:
        return False, f"{current.value} 상태에서는 승인할 수 없습니다(ANALYZED 상태에서만 승인 가능)."
    if not all_p0_clear:
        return False, "P0 게이트 미충족 — AUTHORIZED(APPROVED) 불가(ADVISORY 유지)."
    return True, None


def apply_transition(current: ArtifactStatus, action: str, **ctx: Any) -> ArtifactStatus:
    """상태전이 적용 — 불법 전이는 IllegalTransitionError를 던진다(가짜 성공 반환 없음).

    action:
      "assess"           — 자동판정. ctx["all_p0_clear"](bool) 필요.
      "approve"          — 인간승인. ctx["approved_by"](str)·ctx["all_p0_clear"](bool) 필요.
      "evidence_changed" — 의존 evidence 변경 감지(자동) → STALE.
    """
    if action == "assess":
        if current not in _ASSESS_SOURCES:
            raise IllegalTransitionError(
                f"assess는 {current.value}에서 호출할 수 없습니다"
                "(APPROVED는 evidence_changed로 STALE 전환 후 재분석하십시오)."
            )
        return classify_after_assess(bool(ctx.get("all_p0_clear")))
    if action == "approve":
        ok, reason = can_approve(current, bool(ctx.get("all_p0_clear")), ctx.get("approved_by"))
        if not ok:
            raise IllegalTransitionError(reason or "승인 불가")
        return ArtifactStatus.APPROVED
    if action == "evidence_changed":
        if current not in _EVIDENCE_CHANGE_SOURCES:
            raise IllegalTransitionError(f"evidence_changed는 {current.value}에서 호출할 수 없습니다.")
        return ArtifactStatus.STALE
    raise IllegalTransitionError(f"알 수 없는 action: {action!r}")


def is_stale(old_content_hash: str | None, new_content_hash: str | None) -> bool:
    """의존 evidence content_hash 비교 — 둘 다 있고 다르면 STALE 전파 대상.

    한쪽이라도 미상이면 비교 불가로 False(무날조 — 근거 없이 STALE 단정하지 않음).
    """
    if not old_content_hash or not new_content_hash:
        return False
    return old_content_hash != new_content_hash
