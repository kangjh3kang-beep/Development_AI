"""field_audit runner 단위테스트 — W0 no-op·behavior 불변·F4a 관측전용 거버넌스.

핵심 검증:
  1) 등록규칙 0건 → 빈 리포트(is_valid=True·findings=[]) — behavior 불변.
  2) result에 'field_audit' 키만 additive 추가(그 외 무변경) — 스모크.
  3) ★F4a: growth emit이 'field_audit_observation'(≠verify_result)로만·verdict/recommended_action
     없이 나가 자동토글 루프를 구조적으로 구동 못 함.
  4) FIELD_AUDIT_ENABLED off → 완전 무력화(result 무변형).
  5) per-rule enable map(FIELD_AUDIT_DISABLED_RULES)·규칙 예외 격리.
"""

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import (
    clear_registry,
    register_audit_rule,
    registered_rule_ids,
    rule_count,
)


def _capture_events(monkeypatch):
    """capture_service.record_event를 모의해 발행 이벤트를 수집한다."""
    events = []
    monkeypatch.setattr(cap, "record_event", lambda et, props=None: events.append((et, props)))
    return events


def test_production_registers_g1_invariant():
    """W1-1 flip: 프로덕션 임포트가 cross_field.G1 불변식을 자동 등록한다(W0의 0건에서 전환).

    field_audit 패키지 임포트가 invariants를 임포트해 규칙을 등록한다. 다른 테스트가
    clear_registry로 격리했을 수 있어 register_rules로 프로덕션 등록을 재현한 뒤 확인한다(멱등).
    """
    from app.services.verification import field_audit  # noqa: F401  패키지 임포트=W1 규칙 자동등록
    from app.services.verification.field_audit.invariants.cross_field import register_rules
    register_rules()  # 멱등 — 격리 테스트가 비운 뒤라도 프로덕션 등록 재현
    assert isinstance(rule_count(), int)
    assert "G1_PROTECTION_ZONE_RISK" in registered_rule_ids()


def test_runner_noop_empty_report_and_additive(monkeypatch):
    clear_registry()  # 격리 — 다른 테스트 등록 영향 배제
    _capture_events(monkeypatch)
    result = {"zone_type": "자연녹지지역", "risk": {"risk_level": "낮음"}}
    before = {k: v for k, v in result.items()}

    report = runner.run(result, {"address": "테스트", "zone_type": "자연녹지지역"})

    # 빈 리포트(behavior 불변)
    assert report.is_valid is True
    assert report.findings == []
    # result에 'field_audit' 키만 additive 추가 — 기존 키 무변경(스모크)
    assert "field_audit" in result
    for k, v in before.items():
        assert result[k] == v  # 기존 값 불변
    assert set(result.keys()) == set(before.keys()) | {"field_audit"}
    # 부착된 리포트는 직렬화 dict
    assert result["field_audit"]["is_valid"] is True
    assert result["field_audit"]["findings"] == []
    assert "coverage" in result["field_audit"]  # 커버리지 seed 필드 존재


def test_f4a_growth_emit_is_observation_only(monkeypatch):
    """★F4a 거버넌스: correctness 판정이 서술기능(llm_narrative) 자동토글을 구동 못 함.

    field_audit은 verify_result가 아니라 구별된 event_type으로만 emit하고 verdict/
    recommended_action/down 신호를 담지 않는다 → analyzer._analyze_quality_drop
    (WHERE event_type='verify_result')에 걸리지 않아 quality_drop.down_pct·자동토글 미구동.
    """
    clear_registry()
    events = _capture_events(monkeypatch)
    result = {"zone_type": "자연녹지지역"}

    runner.run(result, {"address": "테스트", "zone_type": "자연녹지지역"})

    assert len(events) == 1, "관측 이벤트 정확히 1건 발행"
    event_type, props = events[0]
    # (a) 구별된 event_type — verify_result 계열과 충돌 금지(F4a 격리 핵심)
    assert event_type == "field_audit_observation"
    assert event_type != "verify_result"
    # (b) verdict/추천액션/quality 신호 부재 — 자동토글 미구동
    assert "verdict" not in props
    assert "recommended_action" not in props
    # severity 키 자체를 verdict(fail/warn/pass)로 쓰지 않음(생략 또는 non-verdict)
    assert props.get("severity") not in ("fail", "warn", "pass")
    # payload는 카운트·차원힌트만(값·claim·PII 미포함)
    payload = props.get("payload") or {}
    assert payload.get("finding_count") == 0
    assert payload.get("rule_count") == 0
    # ★2026-08-02 제거: 여기 있던
    #     assert "field_audit_observation" not in ("verify_result", "verify_issue", "ai_feedback")
    #   는 리터럴끼리 비교하는 **항상 참**이라 검증력이 0이었다(가짜 안전). 이 테스트는 발행측만
    #   책임지고, 소비측(analyzer가 이 event_type을 읽지 않는가)은 실제 분석기를 호출해 잠그는
    #   test_f4a_consumer_isolation.py가 맡는다.


def test_kill_switch_disables_completely(monkeypatch):
    clear_registry()
    events = _capture_events(monkeypatch)
    monkeypatch.setenv("FIELD_AUDIT_ENABLED", "0")
    result = {"zone_type": "자연녹지지역"}

    report = runner.run(result, {"zone_type": "자연녹지지역"})

    # 완전 무력화 — result 무변형(zero footprint), 관측 emit도 없음
    assert "field_audit" not in result
    assert events == []
    assert report.metadata.get("enabled") is False


def test_registered_rule_executes_and_findings_flow(monkeypatch):
    """W1 예행: 규칙 1건 등록 시 findings가 리포트·result로 흐르고 P0가 is_valid를 flip."""
    clear_registry()
    _capture_events(monkeypatch)

    @register_audit_rule("test_p0_rule", tier="A")
    def _rule(payload, ctx):
        if payload.get("risk", {}).get("risk_level") == "낮음":
            return [AuditFinding(code="TEST_G1", severity="P0", panel="risk",
                                 field="risk_level", expected="높음", observed="낮음",
                                 rule_id="test_p0_rule", tier="A")]
        return []

    result = {"risk": {"risk_level": "낮음"}}
    report = runner.run(result, {})
    assert report.is_valid is False  # P0 → flip
    assert len(report.findings) == 1
    assert result["field_audit"]["findings"][0]["code"] == "TEST_G1"
    clear_registry()  # 정리 — 프로덕션 0건 상태 복원


def test_disabled_rule_map_skips_rule(monkeypatch):
    clear_registry()
    _capture_events(monkeypatch)
    monkeypatch.setenv("FIELD_AUDIT_DISABLED_RULES", "test_skip_rule")

    @register_audit_rule("test_skip_rule", tier="A")
    def _rule(payload, ctx):
        return [AuditFinding(code="X", severity="P0", panel="p", field="f",
                             rule_id="test_skip_rule", tier="A")]

    result = {}
    report = runner.run(result, {})
    assert report.findings == []  # per-rule 비활성 → 스킵
    assert report.is_valid is True
    clear_registry()


def test_rule_exception_is_isolated(monkeypatch):
    clear_registry()
    _capture_events(monkeypatch)

    @register_audit_rule("test_boom", tier="A")
    def _rule(payload, ctx):
        raise RuntimeError("boom")

    result = {}
    # 예외가 전파되지 않고 빈 리포트로 degrade
    report = runner.run(result, {})
    assert report.findings == []
    assert "field_audit" in result
    clear_registry()
