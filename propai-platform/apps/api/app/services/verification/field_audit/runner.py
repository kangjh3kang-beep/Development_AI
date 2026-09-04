"""field_audit runner — 등록 규칙 순회·리포트 조립·result 부착(경로 비의존).

계약: `run(result: dict, ctx: dict) -> AuditReport`. result+ctx만 받고 특정 호출부(analyze)에
결합하지 않는다 → 다중 삽입점(analyze·재초환·비례율·부담금 엔진) 재사용.

거버넌스(안전):
  - `FIELD_AUDIT_ENABLED`(기본 on) — off면 즉시 완전 무력화(result 무변형·zero footprint).
  - per-rule enable map(`FIELD_AUDIT_DISABLED_RULES`) 뒤에 규칙 배치 — 규칙별 즉시 롤백.
  - best-effort: 어떤 예외도 삼켜 analyze()로 전파하지 않는다(정직 degrade).

★F4a 거버넌스(최중요) — growth emit은 관측전용(observation-only):
  플랫폼엔 인간개입 없는 스케줄 변이 루프가 이미 존재한다 —
    verifier_service._emit_growth_verdict → capture_service.record_event("verify_result", …)
    → analyzer._analyze_quality_drop(WHERE event_type='verify_result')가 down_pct 산출
    → growth.feature_flags.evaluate(down_pct ≥ 임계 → llm_narrative 자동 비활성)
    → analyzer._llm_enabled live-read로 서술기능이 꺼진다.
  field_audit의 ①원천/②파생 correctness 판정을 이 신호에 흘리면, correctness(①②) 판정이
  서술기능(③)을 끄는 **카테고리 오류**가 된다. 따라서 field_audit은:
    (a) 절대 verifier_service._emit_growth_verdict / "verify_result" / verdict / down 신호를
        쓰지 않는다.
    (b) capture_service.record_event를 **구별된 event_type "field_audit_observation"** 으로만
        emit한다 — 이 event_type은 _analyze_quality_drop 쿼리(event_type='verify_result')에
        걸리지 않아 quality_drop.down_pct·자동토글을 구동할 수 없다(구조적 격리).
    (c) recommended_action 없이, severity를 verdict(fail/warn/pass)로 쓰지 않고 관측 카운트만
        담는다 → L1 자가수정 루프가 이를 조치신호로 소비하지 못한다.
  correctness→서술토글 배선은 **인간 승격 전까지 관측전용**(계획 §11.1 F4a-1).
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from app.services.verification.field_audit.contracts import AuditFinding, AuditReport
from app.services.verification.field_audit.rules_registry import iter_rules

logger = structlog.get_logger(__name__)

# growth 관측 이벤트 타입 — **verify_result와 반드시 구별**(F4a 격리의 핵심). 이 값을
# 변경하면 quality_drop 쿼리와 충돌할 수 있으니 verify_result·feedback 계열과 겹치지 말 것.
_OBSERVATION_EVENT_TYPE = "field_audit_observation"

_RESULT_KEY = "field_audit"


def _enabled() -> bool:
    """FIELD_AUDIT_ENABLED — 기본 on. '0'/'false'/'off'만 무력화(즉시 kill switch)."""
    raw = os.getenv("FIELD_AUDIT_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def audit_status() -> dict[str, Any]:
    """field_audit 등록/활성 상태를 introspect만(read-only·부작용 0·run과 독립).

    배포 회귀 가드용 진단: 배포된 백엔드에서 이 상태를 즉시 조회해 자가검증 레이어가
    프로덕션에서 **비활성/미등록으로 무성(silent) 회귀**했는지 스모크로 assert한다.

    ★라이브 레지스트리를 있는 그대로 보고한다 — 절대 재등록/변이하지 않는다. healthy 배포는
    field_audit 패키지 임포트 부작용으로 규칙이 이미 등록돼 있으므로(각 invariants 모듈이
    임포트 시 register_rules() 자동 호출) 참 카운트를 보고한다. 등록이 무성 파손되면
    rules_registered=0을 **정직 보고**해 스모크가 실패하고 회귀가 적발된다. 여기서 register_
    all_rules를 호출해 자가치유하면 run()(analyze 경로)이 규칙 0으로 퇴화 실행 중인데도
    프로브만 8로 green을 내는 false-healthy 오보고가 되므로 절대 하지 않는다(R1 HIGH 봉합).

    반환:
      - enabled: FIELD_AUDIT_ENABLED 반영(기본 on).
      - rules_registered: 라이브 등록된 불변식 수(healthy=현재 6모듈·8규칙, 파손=0).
      - rule_ids: 라이브 등록된 rule_id 정렬 목록.
    """
    rules = iter_rules()
    return {
        "enabled": _enabled(),
        "rules_registered": len(rules),
        "rule_ids": sorted(r.rule_id for r in rules),
    }


def _disabled_rule_ids() -> set[str]:
    """FIELD_AUDIT_DISABLED_RULES — 콤마구분 rule_id 집합(규칙별 즉시 롤백). 기본 빈 집합."""
    raw = os.getenv("FIELD_AUDIT_DISABLED_RULES", "").strip()
    if not raw:
        return set()
    return {r.strip() for r in raw.split(",") if r.strip()}


def _emit_observation(finding_count: int, rule_count: int, ctx: dict[str, Any]) -> None:
    """F4a: 관측전용 growth emit(best-effort·논블로킹·로직불변).

    ★verify_result가 아니라 구별된 event_type으로만 발행하고, verdict/recommended_action/
    down 신호를 담지 않는다 → quality_drop·자동토글 루프를 구조적으로 구동할 수 없다.
    payload는 카운트·차원 힌트만(값·claim·PII 제외). 어떤 예외도 삼킨다.
    """
    try:
        from app.services.growth import capture_service

        # severity 키는 의도적으로 생략(verdict 신호 금지). analysis_type 라벨도 부여하지
        # 않아 verify_result 라벨 상속(F4a 미해결질문③)을 원천 차단한다.
        capture_service.record_event(_OBSERVATION_EVENT_TYPE, {
            "surface": "api",
            "service": "field_audit",
            "payload": {
                "finding_count": finding_count,
                "rule_count": rule_count,
                # 차원 힌트(값 아님) — 이후 커버리지 원장 상관용. 자유서술 미포함.
                "zone_type": ctx.get("zone_type"),
            },
        })
    except Exception as e:  # noqa: BLE001 — 관측 실패가 주경로/리포트에 영향 없음.
        logger.debug("field_audit 관측 emit 무시: %s", str(e)[:120])


def run(result: dict[str, Any], ctx: dict[str, Any]) -> AuditReport:
    """등록 규칙을 순회해 AuditReport를 조립하고 result["field_audit"]에 부착한다.

    W0: 등록 규칙 0건 → 빈 findings → is_valid=True. result에는 'field_audit' 키만 추가되어
    **behavior 불변**(그 외 무변경). FIELD_AUDIT_ENABLED off면 result 무변형·빈 리포트 반환.

    best-effort: 규칙 개별 예외는 격리(해당 규칙만 스킵), 전체 실패는 빈 리포트로 degrade.
    """
    if not _enabled():
        # 즉시 kill switch — DISABLED 경로에 한해 zero footprint(result 무변형·emit 0건).
        # ★ENABLED 경로는 zero footprint가 아니다: analyze()마다 (1)result에 'field_audit' 키
        #   additive 추가 (2)bounded deque에 관측이벤트 1건(F4a-1 승인된 observation-only emit).
        #   둘 다 계약된 additive이지 behavior/additive-계약 위반이 아니다.
        return AuditReport(metadata={"enabled": False})

    findings: list[AuditFinding] = []
    disabled = _disabled_rule_ids()
    rules = iter_rules()
    executed = 0
    for r in rules:
        if r.rule_id in disabled:  # per-rule enable map 뒤 배치(규칙별 롤백)
            continue
        try:
            out = r.fn(result, ctx) or []
            findings.extend(out)
            executed += 1
        except Exception as e:  # noqa: BLE001 — 규칙 1건 실패는 나머지 감사를 막지 않는다.
            logger.debug("field_audit 규칙 실패(격리): %s / %s", r.rule_id, str(e)[:120])

    report = AuditReport.from_findings(
        findings,
        metadata={
            "enabled": True,
            "rules_registered": len(rules),
            "rules_executed": executed,
            # ctx 힌트(경로 비의존 — 삽입점이 무엇을 넣든 관측만).
            "zone_type": ctx.get("zone_type"),
        },
        # 커버리지 원장 seed — W0는 구조만(빈 dict라도 필드 존재). 이후 Phase가 채운다.
        coverage={},
    )

    # result 부착 — additive. 'field_audit' 키만 추가(behavior 불변).
    try:
        result[_RESULT_KEY] = report.to_dict()
    except Exception as e:  # noqa: BLE001 — result가 dict가 아니어도 리포트는 반환.
        logger.debug("field_audit 부착 무시: %s", str(e)[:120])

    # F4a 관측전용 emit(성장엔진) — verdict/토글 미구동.
    _emit_observation(len(findings), len(rules), ctx)

    return report
