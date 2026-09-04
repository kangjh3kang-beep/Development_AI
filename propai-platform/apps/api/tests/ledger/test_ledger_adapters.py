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


# ── 변동감지 계약: build_signature_parts/build_input_signature(단일 소유자) ──────

def test_build_signature_parts_order_and_normalization():
    from app.services.ledger.ledger_adapters import build_signature_parts

    parts = build_signature_parts(
        address="  서울  강남구   역삼동  ", pnu="1168010100",
        parcel_count=3, use_llm=True, options={"b": 1, "a": {"z": 2, "y": 1}},
    )
    # 순서 고정: [address_norm, pnu, parcel_count, use_llm, options_summary]
    assert parts[0] == "서울 강남구 역삼동"       # 공백 정규화(analysis_ledger_service._norm_addr)
    assert parts[1] == "1168010100"
    assert parts[2] == "3"
    assert parts[3] == "True"
    assert parts[4] == "a={y:1,z:2},b=1"          # 키 정렬(중첩 dict 포함) — 결정적


def test_build_signature_parts_defaults_are_honest_not_fake():
    from app.services.ledger.ledger_adapters import build_signature_parts

    parts = build_signature_parts(address=None, pnu=None, parcel_count=None, use_llm=None, options=None)
    assert parts == ["", "", "0", "False", ""]


def test_build_signature_parts_options_key_order_independent():
    from app.services.ledger.ledger_adapters import build_signature_parts

    p1 = build_signature_parts(address="a", options={"x": 1, "y": 2})
    p2 = build_signature_parts(address="a", options={"y": 2, "x": 1})
    assert p1 == p2  # 삽입 순서와 무관하게 동일 파트(정렬 정규화)


def test_build_input_signature_deterministic_and_sensitive_to_change():
    from app.services.ledger.ledger_adapters import build_input_signature

    parts_a = ["addr1", "pnu1", "1", "True", ""]
    parts_b = ["addr1", "pnu1", "1", "True", ""]
    parts_c = ["addr1", "pnu1", "2", "True", ""]  # parcel_count만 다름
    sig_a = build_input_signature(parts_a)
    sig_b = build_input_signature(parts_b)
    sig_c = build_input_signature(parts_c)
    assert sig_a == sig_b                          # 같은 파트 → 같은 해시(결정론)
    assert sig_a != sig_c                          # 다른 파트 → 다른 해시(변동감지)
    assert len(sig_a) == 16                         # sha256 앞 16자(짧은 결정적 해시)


async def test_record_user_analysis_attaches_signature_when_materials_given(tnt):
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.ledger_adapters import (
        build_input_signature,
        build_signature_parts,
        record_user_analysis,
    )

    pnu = "1168010100"
    res = await record_user_analysis(
        analysis_type="market_report",
        summary={"address": "서울 강남", "trade_count": 5},
        tenant_id=tnt, pnu=pnu, address="서울 강남",
        parcel_count=1, use_llm=True, options=None,
    )
    assert res["ok"] is True
    latest = await ledger.get_latest(analysis_type="market_report", tenant_id=tnt, pnu=pnu)
    payload = latest["payload"]
    expected_parts = build_signature_parts(address="서울 강남", pnu=pnu, parcel_count=1, use_llm=True)
    assert payload["signature_parts"] == expected_parts
    assert payload["input_signature"] == build_input_signature(expected_parts)
    assert payload["trade_count"] == 5              # 기존 summary 필드도 그대로 보존


async def test_record_user_analysis_omits_signature_when_no_materials_given(tnt):
    """parcel_count/use_llm/options 모두 미전달(기존 호출부) — 표준키 키 자체가 생기지 않는다(무회귀)."""
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.ledger_adapters import record_user_analysis

    pnu = "1168010101"
    res = await record_user_analysis(
        analysis_type="market_report", summary={"address": "서울 서초"},
        tenant_id=tnt, pnu=pnu, address="서울 서초",
    )
    assert res["ok"] is True
    latest = await ledger.get_latest(analysis_type="market_report", tenant_id=tnt, pnu=pnu)
    payload = latest["payload"]
    assert "signature_parts" not in payload
    assert "input_signature" not in payload
