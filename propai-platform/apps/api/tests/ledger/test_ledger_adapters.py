"""산출물→원장 어댑터 — 순수 매퍼(무DB) + 기록 래퍼(DB). schema_version/backlink/findings_brief 포함."""


def test_design_audit_to_ledger_with_schema_brief_and_backlink():
    from app.services.ledger.ledger_adapters import design_audit_to_ledger

    result = {
        "schema_version": "design_audit/v1",
        "zone_type": "제2종일반주거",
        "sigungu": "강남구",
        "overall": {"verdict": "조건부적합", "counts": {"pass": 5, "warning": 2}},
        "engines": {"far": "ok", "bcr": "ok"},
        "findings": [
            {"check_id": "far_limit", "status": "warning", "current": 250, "limit": 200},
            {"check_id": "height", "status": "pass", "current": 10, "limit": 12},
        ],
    }
    p = design_audit_to_ledger(result, audit_id="AUD-1")
    assert p == {
        "kind": "design_audit",
        "schema_version": "design_audit/v1",
        "zone_type": "제2종일반주거",
        "sigungu": "강남구",
        "verdict": "조건부적합",
        "counts": {"pass": 5, "warning": 2},
        "engines": {"far": "ok", "bcr": "ok"},
        "findings_count": 2,
        "findings_brief": [
            {"check_id": "far_limit", "status": "warning", "current": 250, "limit": 200},
            {"check_id": "height", "status": "pass", "current": 10, "limit": 12},
        ],
        "audit_id": "AUD-1",
    }


def test_design_audit_to_ledger_missing_keys_and_omits_audit_id():
    from app.services.ledger.ledger_adapters import design_audit_to_ledger

    p = design_audit_to_ledger({})
    assert p["kind"] == "design_audit"
    assert p["schema_version"] == "design_audit/v1"     # 기본값
    assert p["verdict"] is None and p["counts"] == {} and p["findings_count"] == 0
    assert p["findings_brief"] == []
    assert "audit_id" not in p                          # 미지정 시 키 생략(가짜키 금지)


def test_feasibility_commit_to_ledger():
    from app.services.ledger.ledger_adapters import feasibility_commit_to_ledger

    commit = {
        "sha": "abc123", "parent_sha": "def456",
        "message": "init", "author": "u1", "timestamp": "2026-06-15T00:00:00",
    }
    p = feasibility_commit_to_ledger(commit)
    assert p == {
        "kind": "feasibility_commit",
        "schema_version": "feasibility_vcs/v1",
        "sha": "abc123", "parent_sha": "def456",
        "message": "init", "author": "u1", "timestamp": "2026-06-15T00:00:00",
    }


def test_domain_agent_task_to_ledger():
    from app.services.ledger.ledger_adapters import domain_agent_task_to_ledger

    task = {
        "domain": "finance", "task_type": "analysis", "status": "completed",
        "confidence_score": 0.82, "recommendation": "review",
        "requires_approval": True, "id": "TASK-9",
    }
    p = domain_agent_task_to_ledger(task)
    assert p == {
        "kind": "domain_agent_task",
        "schema_version": "domain_agent/v1",
        "domain": "finance", "task_type": "analysis", "status": "completed",
        "confidence_score": 0.82, "recommendation": "review",
        "requires_approval": True, "task_id": "TASK-9",
    }


def test_adapter_types_do_not_collide_with_read_loop_keys():
    # read 성장루프(bank_report·pipeline)가 소비하는 키와 어댑터 analysis_type이 겹치면 리포트 오염.
    read_keys = {"feasibility", "site_analysis", "design", "esg", "permit"}
    adapter_types = {"design_audit", "feasibility_vcs", "domain_agent"}
    assert read_keys.isdisjoint(adapter_types)


async def test_record_design_audit_appends_to_ledger(tnt):
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.ledger_adapters import record_design_audit

    res = await record_design_audit(
        result={"schema_version": "design_audit/v1", "overall": {"verdict": "적합"}},
        tenant_id=tnt, project_id="PRJ-9", created_by="u1",
    )
    assert res["ok"] is True
    latest = await ledger.get_latest(
        analysis_type="design_audit", tenant_id=tnt, project_id="PRJ-9"
    )
    assert latest is not None and latest["payload"]["verdict"] == "적합"
