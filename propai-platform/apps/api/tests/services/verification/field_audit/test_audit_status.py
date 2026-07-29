"""field_audit audit_status() + 진단 엔드포인트 단위테스트 — 배포 회귀 가드.

핵심 검증:
  1) audit_status()가 register_all_rules 후 6모듈·8규칙을 반영(rules_registered>=8·
     핵심 rule_id 포함)·enabled True(기본).
  2) FIELD_AUDIT_ENABLED=0 → enabled False(kill switch 반영).
  3) ★멱등: audit_status() 다중호출 규칙수 불변(중복 등록 무시).
  4) 엔드포인트 200·JSON shape(enabled·rules_registered·rule_ids) 계약·무인증 공개.
  5) introspect 전용 — run()과 독립(result 부착·growth emit 없음).
"""

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.rules_registry import clear_registry

# 현재 등록되는 6모듈·8규칙(Wave 증가 시 함께 갱신). audit_status가 register_all_rules로
# 등록을 보장하므로 골든 하한(>=)으로 계약한다.
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


def test_audit_status_reports_registered_rules():
    """register_all_rules 후 8규칙·핵심 rule_id 포함·enabled True(기본)."""
    clear_registry()  # 격리 — 다른 테스트 등록 영향 배제. audit_status가 재등록 보장.
    status = runner.audit_status()

    assert status["enabled"] is True
    assert status["rules_registered"] >= _EXPECTED_MIN_RULES
    assert _EXPECTED_RULE_IDS.issubset(set(status["rule_ids"]))
    # rule_ids는 정렬 목록(계약)
    assert status["rule_ids"] == sorted(status["rule_ids"])


def test_audit_status_kill_switch_reflected(monkeypatch):
    """FIELD_AUDIT_ENABLED=0 → enabled False. 규칙 등록 상태는 여전히 introspect."""
    monkeypatch.setenv("FIELD_AUDIT_ENABLED", "0")
    status = runner.audit_status()
    assert status["enabled"] is False
    # 비활성이어도 등록 상태는 보고(무성 회귀 진단용)
    assert status["rules_registered"] >= _EXPECTED_MIN_RULES


def test_audit_status_is_idempotent():
    """★멱등: 다중 호출해도 규칙 수 불변(중복 등록 무시)."""
    clear_registry()
    first = runner.audit_status()
    second = runner.audit_status()
    third = runner.audit_status()
    assert first["rules_registered"] == second["rules_registered"] == third["rules_registered"]
    assert first["rule_ids"] == second["rule_ids"] == third["rule_ids"]


def test_audit_status_has_no_side_effects(monkeypatch):
    """introspect 전용 — result 부착·growth emit 없음(run과 독립)."""
    events = []
    monkeypatch.setattr(cap, "record_event", lambda et, props=None: events.append((et, props)))
    clear_registry()

    status = runner.audit_status()

    assert set(status.keys()) == {"enabled", "rules_registered", "rule_ids"}
    # 규칙 fn을 실행하지 않으므로 growth 관측 emit이 전혀 없다
    assert events == []


def test_field_audit_status_endpoint_contract():
    """엔드포인트 200·JSON shape 계약·무인증 공개(data_integrity 라우터 격리 마운트)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from apps.api.routers import data_integrity

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
