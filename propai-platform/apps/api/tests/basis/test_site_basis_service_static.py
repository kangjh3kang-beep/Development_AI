"""부지기반(site basis) 서비스 정적 검증 — 원장 무결성(⑥) + 하류 결선 순수함수 테스트.

⑥ 원장 무결성 훼손 0: site_basis_service.py의 신규 DDL이 analysis_ledger 테이블을 절대
   건드리지 않는지(스키마 변경 0) 소스 텍스트 수준에서 검증한다. 라이브 DB 없이도 결정적으로
   확인 가능한 정적 계약 테스트다(원 지시 "결정적 픽스처만" 원칙 준수).

추가로 gate_design_entry(하류 설계생성 진입점 additive 결선)가 어떤 입력에도 AUTHORIZED를
반환하지 않음을 확인한다(자동경로는 인간승인을 거치지 않으므로 구조적으로 ADVISORY 고정).
"""
from __future__ import annotations

import inspect

from app.services.basis import site_basis_service
from app.services.basis.site_basis_service import gate_design_entry


def test_new_ddl_never_references_analysis_ledger_table():
    """신규 projection·이벤트 테이블 DDL이 analysis_ledger 테이블명을 참조하지 않는다."""
    ddl_blob = site_basis_service._STATE_DDL + site_basis_service._EVENT_DDL
    assert "analysis_ledger" not in ddl_blob
    # 신규 테이블은 별도 이름(가변 상태 = projection, 감사이력 = append-only 이벤트).
    assert "site_basis_state" in site_basis_service._STATE_DDL
    assert "site_basis_transition_event" in site_basis_service._EVENT_DDL


def test_source_contains_no_mutating_statement_against_ledger_table():
    """모듈 전체 소스에 analysis_ledger 대상 UPDATE/ALTER/DELETE 구문이 없다(원장 append-only 보존)."""
    source = inspect.getsource(site_basis_service)
    forbidden = ("UPDATE analysis_ledger", "ALTER TABLE analysis_ledger", "DELETE FROM analysis_ledger",
                 "DROP TABLE analysis_ledger")
    for stmt in forbidden:
        assert stmt not in source, f"원장 변이 금지 위반 의심 구문 발견: {stmt}"


def test_event_table_is_insert_only_in_source():
    """site_basis_transition_event 대상 구문은 INSERT만 존재(UPDATE/DELETE 없음 — append-only)."""
    source = inspect.getsource(site_basis_service)
    assert "UPDATE site_basis_transition_event" not in source
    assert "DELETE FROM site_basis_transition_event" not in source
    assert "INSERT INTO site_basis_transition_event" in source


def test_gate_design_entry_never_returns_authorized_when_all_clear():
    """하류 결선(설계생성 진입) — 전건 P0 충족 입력이어도 자동경로는 ADVISORY 고정."""
    result = gate_design_entry(access_status="PASS", dev_act_status="CONDITIONAL", rights_confirmed=True)
    assert result["basis_status"] == "ADVISORY"
    assert result["all_p0_clear"] is True
    assert result["artifact_status"] == "ANALYZED"


def test_gate_design_entry_reports_review_required_when_blocked():
    """게이트 미충족 입력이면 REVIEW_REQUIRED로 정직 강등(ADVISORY 유지)."""
    result = gate_design_entry(access_status=None, dev_act_status="BLOCKED", rights_confirmed=None)
    assert result["basis_status"] == "ADVISORY"
    assert result["all_p0_clear"] is False
    assert result["artifact_status"] == "REVIEW_REQUIRED"
    assert len(result["gates"]) == 3
