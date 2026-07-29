"""field_audit audit_status() + 진단 엔드포인트 단위테스트 — 배포 회귀 가드.

핵심 검증:
  1) healthy 앱(register_all_rules로 정상 등록 재현) → audit_status가 8규칙·핵심 rule_id
     반영·enabled True(기본).
  2) FIELD_AUDIT_ENABLED=0 → enabled False(kill switch 반영).
  3) ★멱등·read-only: audit_status() 다중호출 규칙수 불변(레지스트리 무변이).
  4) ★회귀 정직보고: 등록이 무성 파손(clear_registry로 재현)되면 rules_registered=0을
     자가치유 없이 정직 보고(가드의 핵심 계약 — false-healthy masking 금지).
  5) ★부작용 0: audit_status 호출 전후 레지스트리 불변(프로브가 상태를 변이하지 않음).
  6) 엔드포인트 200·JSON shape(enabled·rules_registered·rule_ids) 계약·무인증 공개.
"""

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.invariants import register_all_rules
from app.services.verification.field_audit.rules_registry import clear_registry, iter_rules

# 현재 등록되는 6모듈·8규칙(Wave 증가 시 함께 갱신). audit_status는 read-only이므로 테스트가
# arrange에서 register_all_rules로 healthy 앱 상태를 명시 구성한 뒤 하한(>=)으로 계약한다.
_EXPECTED_MIN_RULES = 8
_EXPECTED_RULE_IDS = {
    "G1_PROTECTION_ZONE_RISK",
    "G2_SCHOOL_POI_DEDUP",
    "G3_ZONE_COVERAGE_GAP",
    "PROV_UNKNOWN_SOURCE",
    "PROV_STALE_DATA",
    "MARKET_PRICE_METHODOLOGY",
    "SALE_PRICE_POINT_ESTIMATE",
    "TERRAIN_SLOPE_COLLECTION_GAP",
}


def _arrange_healthy() -> None:
    """정상 앱 상태 재현 — 격리 초기화 후 프로덕션 규칙 전량 등록(멱등)."""
    clear_registry()
    register_all_rules()


def test_audit_status_reports_registered_rules():
    """healthy 앱(register_all_rules) → 8규칙·핵심 rule_id 포함·enabled True(기본)."""
    _arrange_healthy()
    status = runner.audit_status()

    assert status["enabled"] is True
    assert status["rules_registered"] >= _EXPECTED_MIN_RULES
    assert _EXPECTED_RULE_IDS.issubset(set(status["rule_ids"]))
    # rule_ids는 정렬 목록(계약)
    assert status["rule_ids"] == sorted(status["rule_ids"])


def test_audit_status_kill_switch_reflected(monkeypatch):
    """FIELD_AUDIT_ENABLED=0 → enabled False. 규칙 등록 상태는 여전히 introspect."""
    _arrange_healthy()
    monkeypatch.setenv("FIELD_AUDIT_ENABLED", "0")
    status = runner.audit_status()
    assert status["enabled"] is False
    # 비활성이어도 라이브 등록 상태는 있는 그대로 보고(무성 회귀 진단용)
    assert status["rules_registered"] >= _EXPECTED_MIN_RULES


def test_audit_status_is_idempotent_and_read_only():
    """★멱등·read-only: 다중 호출해도 규칙 수 불변·레지스트리 변이 없음."""
    _arrange_healthy()
    before = len(iter_rules())
    first = runner.audit_status()
    second = runner.audit_status()
    third = runner.audit_status()
    assert first["rules_registered"] == second["rules_registered"] == third["rules_registered"]
    assert first["rule_ids"] == second["rule_ids"] == third["rule_ids"]
    # 프로브는 레지스트리를 변이하지 않는다(read-only)
    assert len(iter_rules()) == before


def test_audit_status_reports_zero_on_broken_registration():
    """★회귀 정직보고: 등록 무성 파손(빈 레지스트리) → rules_registered=0 정직 보고.

    ★가드의 핵심 계약. run()(analyze 경로)이 규칙 0으로 퇴화 실행 중일 때 audit_status가
    자가치유로 8을 되살려 green을 내면(false-healthy) 회귀가 masking된다. read-only 프로브는
    참 0을 보고해 스모크(rules_registered>0)가 실패하고 회귀를 적발한다.
    """
    clear_registry()  # 무성 등록 파손 재현 — 자가치유 없음
    status = runner.audit_status()
    assert status["rules_registered"] == 0
    assert status["rule_ids"] == []
    # 프로브 호출 후에도 레지스트리는 여전히 비어 있어야 한다(변이 금지)
    assert len(iter_rules()) == 0


def test_audit_status_has_no_side_effects(monkeypatch):
    """★부작용 0: growth emit 없음 + 호출 전후 레지스트리 불변(프로브 무변이)."""
    events = []
    monkeypatch.setattr(cap, "record_event", lambda et, props=None: events.append((et, props)))
    _arrange_healthy()
    before = len(iter_rules())

    status = runner.audit_status()

    assert set(status.keys()) == {"enabled", "rules_registered", "rule_ids"}
    # 규칙 fn을 실행하지 않으므로 growth 관측 emit이 전혀 없다
    assert events == []
    # ★레지스트리 불변 — audit_status는 등록/해제하지 않는다(read-only 계약)
    assert len(iter_rules()) == before


def test_field_audit_status_endpoint_contract():
    """엔드포인트 200·JSON shape 계약·무인증 공개(data_integrity 라우터 격리 마운트)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from apps.api.routers import data_integrity

    _arrange_healthy()  # healthy 앱 상태 명시 구성(프로세스 전역 레지스트리)

    app = FastAPI()
    app.include_router(data_integrity.router, prefix="/api/v1")
    client = TestClient(app)

    # 무인증 — 자격증명 없이 호출 가능해야 한다(배포 스모크가 curl로 확인)
    resp = client.get("/api/v1/data-integrity/field-audit-status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"enabled", "rules_registered", "rule_ids"}
    assert isinstance(body["enabled"], bool)
    assert isinstance(body["rules_registered"], int)
    assert isinstance(body["rule_ids"], list)
    assert body["rules_registered"] >= _EXPECTED_MIN_RULES
    assert "G1_PROTECTION_ZONE_RISK" in body["rule_ids"]
    assert "SALE_PRICE_POINT_ESTIMATE" in body["rule_ids"]
