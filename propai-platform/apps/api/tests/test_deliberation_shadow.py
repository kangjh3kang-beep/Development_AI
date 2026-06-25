"""중심엔진 수렴 관측 — shadow_comparison(플랫폼 vs 엔진 판정 divergence) 서비스.

순수 함수(정규화·divergence)는 DB 불요 단위검증, record는 실 DB(없으면 skip). 마이그레이션 배선 확인.
"""
from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import text

from app.services.deliberation import shadow_integration as si
from app.services.deliberation import shadow_mappers as sm
from app.services.deliberation import shadow_service as s
from apps.api.app.routers import deliberation as delib


def test_mapper_design_audit_maps_numeric_subset_and_comparator():
    result = {"overall": {"verdict": "부적합", "verdict_en": "fail"},
              "findings": [{"check_id": "rules8_far", "current": 250.0, "limit": 200.0, "status": "fail"},
                           {"check_id": "rules8_setback", "current": 2.0, "limit": 3.0, "status": "pass"},  # >=
                           {"check_id": "qual", "current": None, "limit": None, "status": "fail"}]}  # 비수치 제외
    v, payload, val = sm.design_audit(result)
    assert v == "fail" and len(payload["rules"]) == 2  # 수치 subset worst status(far=fail)
    assert payload["rules"][0]["rule"]["rule_id"] == "rules8_far" and val == 250.0
    assert payload["rules"][0]["rule"]["comparator"] == "<="
    assert payload["rules"][1]["rule"]["comparator"] == ">="  # setback → 최소요건


def test_mapper_design_audit_verdict_is_scoped_to_numeric_subset():
    # ★scope 정합: 종합 verdict는 비수치 parking 'fail'로 부적합이나, 엔진이 보는 수치 subset은 pass뿐
    # → platform_verdict는 subset 기준 'pass'(엔진과 동일 범위, 거짓 divergence 방지). 종합 verdict_en 미사용.
    result = {"overall": {"verdict": "부적합", "verdict_en": "fail"},
              "findings": [{"check_id": "parking", "current": "5대", "limit": "8대", "status": "fail"},  # 비수치
                           {"check_id": "rules8_bcr", "current": 0.5, "limit": 0.6, "status": "pass"}]}
    v, payload, _ = sm.design_audit(result)
    assert v == "pass" and len(payload["rules"]) == 1  # 비수치 fail 제외 → subset=pass


def test_mapper_design_audit_skips_when_no_numeric():
    assert sm.design_audit({"findings": []}) is None
    assert sm.design_audit({"findings": [{"check_id": "q", "current": None, "limit": None}]}) is None
    assert sm.design_audit({"overall": None}) is None


def test_mapper_building_compliance_violations_to_rules():
    raw = {"compliant": False, "violations": [
        {"type": "building_coverage", "current_value": 0.7, "limit_value": 0.6},
        {"type": "setback", "current_value": 2.0, "limit_value": 3.0},  # 최소요건 → >=
        {"type": "qual", "current_value": None, "limit_value": None}]}   # 비수치 제외
    v, payload, val = sm.building_compliance(raw)
    assert v == "non_compliant" and len(payload["rules"]) == 2
    assert payload["rules"][0]["rule"]["comparator"] == "<=" and val == 0.7
    assert payload["rules"][1]["rule"]["comparator"] == ">="  # setback


def test_mapper_building_compliance_skips_when_compliant():
    # 적합 케이스는 비교 rule 없음 → 생략(거짓발산 방지). 위반 없는 dict도 None.
    assert sm.building_compliance({"compliant": True, "violations": []}) is None
    assert sm.building_compliance({"compliant": False, "violations": []}) is None


def test_norm_verdict_maps_equivalents():
    # 다른 표기를 동치군으로 — 거짓 divergence 방지.
    assert s.norm_verdict("COMPLIANT") == s.norm_verdict("approved") == "compliant"
    assert s.norm_verdict("NON_COMPLIANT") == s.norm_verdict("rejected") == "non_compliant"
    assert s.norm_verdict("NEEDS_REVIEW") == s.norm_verdict("conditional") == "needs_review"
    assert s.norm_verdict(None) == ""


def test_compute_divergence_match_and_mismatch():
    m = s.compute_divergence("COMPLIANT", "approved")  # 동치 → 일치
    assert m["matched"] is True and m["divergence_score"] == 0.0
    d = s.compute_divergence("COMPLIANT", "NON_COMPLIANT")
    assert d["matched"] is False and d["divergence_score"] == 1.0


def test_compute_divergence_quant_rel_err():
    r = s.compute_divergence("c", "c", platform_value=210.0, engine_value=200.0)
    assert r["quant_rel_err"] == pytest.approx(0.05)
    assert s.compute_divergence("c", "c")["quant_rel_err"] is None          # 수치 없음
    assert s.compute_divergence("c", "c", platform_value=True, engine_value=1)["quant_rel_err"] is None  # bool 제외


def test_migration_033_wired_into_chain():
    p = pathlib.Path(__file__).resolve().parents[1] / "database/migrations/versions/033_shadow_comparison.py"
    src = p.read_text(encoding="utf-8")
    assert 'revision = "033_shadow_comparison"' in src
    assert 'down_revision = "032_deliberation_binding"' in src
    assert "CREATE TABLE IF NOT EXISTS shadow_comparison" in src
    assert "idx_shadow_domain" in src
    assert "DROP TABLE IF EXISTS shadow_comparison" in src  # downgrade 가역


# ── shadow_integration 오케스트레이터(best-effort·운영 무중단) ──


class _FakeS:
    def __init__(self, enabled=True, url="http://engine.local"):
        self.deliberation_shadow_enabled = enabled
        self.deliberation_engine_url = url


_VALID_PAYLOAD = {"pnu": "1111010100100000002"}


def test_engine_overall_verdict_is_worst_of_findings():
    result = {"findings": [{"verdict": "COMPLIANT"}, {"verdict": "NEEDS_REVIEW"}, {"verdict": "compliant"}]}
    assert si.engine_overall_verdict(result) == "needs_review"   # 최악 우선(보수적)
    # non_compliant(sev3)가 needs_review·compliant를 이김.
    assert si.engine_overall_verdict(
        {"findings": [{"verdict": "COMPLIANT"}, {"verdict": "NON_COMPLIANT"}, {"verdict": "NEEDS_REVIEW"}]}
    ) == "non_compliant"
    assert si.engine_overall_verdict({"findings": []}) is None
    assert si.engine_overall_verdict("nope") is None


async def test_shadow_compare_noop_when_disabled(monkeypatch):
    recorded = {"n": 0}
    async def _rec(**kw):
        recorded["n"] += 1
        return {}
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS(enabled=False))
    monkeypatch.setattr(s, "record", _rec)
    out = await si.shadow_compare(tenant_id="t", domain="comprehensive",
                                  platform_verdict="COMPLIANT", engine_payload=_VALID_PAYLOAD)
    assert out is None and recorded["n"] == 0  # off → 엔진 미호출·미적재


async def test_shadow_compare_records_divergence_when_enabled(monkeypatch):
    captured = {}
    async def _post(dump, deterministic=True, tenant=None, breaker=None):
        return {"findings": [{"verdict": "NON_COMPLIANT"}], "report": {}}, "ok"
    async def _rec(**kw):
        captured.update(kw)
        return {"id": "x", "matched": kw["platform_verdict"] == "NON_COMPLIANT", "divergence_score": 0.0}
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _post)
    monkeypatch.setattr(s, "record", _rec)
    out = await si.shadow_compare(tenant_id="t", domain="design_audit",
                                  platform_verdict="REJECTED", engine_payload=_VALID_PAYLOAD)
    assert out is not None
    assert captured["domain"] == "design_audit" and captured["engine_verdict"] == "non_compliant"
    assert captured["input_hash"] and captured["detail"]["engine_reason"] == "ok"  # lineage·사유 동반
    assert captured["tenant_id"] == "t"


async def test_shadow_compare_skips_when_engine_unavailable(monkeypatch):
    async def _post(dump, deterministic=True, tenant=None, breaker=None):
        return None, "engine_unreachable"
    recorded = {"n": 0}
    async def _rec(**kw):
        recorded["n"] += 1
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _post)
    monkeypatch.setattr(s, "record", _rec)
    out = await si.shadow_compare(tenant_id="t", domain="comprehensive",
                                  platform_verdict="COMPLIANT", engine_payload=_VALID_PAYLOAD)
    assert out is None and recorded["n"] == 0


async def test_shadow_compare_skips_on_bad_mapping(monkeypatch):
    # prevalidate 부적합(엔진 enum 위반 입력) → shadow 생략(무영향).
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    out = await si.shadow_compare(tenant_id="t", domain="comprehensive", platform_verdict="x",
                                  engine_payload={"pnu": "1111010100100000002",
                                                  "calc_targets": [{"target": "BOGUS"}]})
    assert out is None


async def test_shadow_compare_never_raises(monkeypatch):
    async def _boom(dump, deterministic=True, tenant=None, breaker=None):
        raise RuntimeError("engine blew up")
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _boom)
    # 엔진 예외도 도메인 흐름으로 전파 금지 → None.
    out = await si.shadow_compare(tenant_id="t", domain="design_audit",
                                  platform_verdict="COMPLIANT", engine_payload=_VALID_PAYLOAD)
    assert out is None


async def test_shadow_compare_normalizes_tenant(monkeypatch):
    # 도메인별 hex/대시형 불일치 정규화(32자 무대시 소문자) — per-tenant 집계 분열 방지.
    captured = {}
    async def _post(dump, deterministic=True, tenant=None, breaker=None):
        captured["tenant_header"] = tenant
        return {"findings": [{"verdict": "COMPLIANT"}], "report": {}}, "ok"
    async def _rec(**kw):
        captured.update(kw)
        return {"id": "x"}
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _post)
    monkeypatch.setattr(s, "record", _rec)
    await si.shadow_compare(tenant_id="12345678-90AB-cdef-1234-567890ABCDEF",  # 대시·대문자
                            domain="design_audit", platform_verdict="pass", engine_payload=_VALID_PAYLOAD)
    assert captured["tenant_id"] == "1234567890abcdef1234567890abcdef"  # hex 정규화
    assert captured["tenant_header"] == "1234567890abcdef1234567890abcdef"  # 엔진 X-Tenant-Id도 동일


async def test_fire_shadow_compare_is_nonblocking(monkeypatch):
    # fire-and-forget — 즉시 task 반환(도메인 응답 비차단), await 시 적재 완료.
    rec = {"n": 0}
    async def _post(dump, deterministic=True, tenant=None, breaker=None):
        return {"findings": [{"verdict": "COMPLIANT"}], "report": {}}, "ok"
    async def _rec(**kw):
        rec["n"] += 1
        return {"id": "x"}
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _post)
    monkeypatch.setattr(s, "record", _rec)
    task = si.fire_shadow_compare(tenant_id="t", domain="design_audit",
                                  platform_verdict="pass", engine_payload=_VALID_PAYLOAD)
    assert task is not None and not task.done()  # 즉시 반환(아직 미완 — 비차단)
    await task
    assert rec["n"] == 1  # 백그라운드 적재 완료


def test_observe_fires_with_domain_and_unpacks_tuple(monkeypatch):
    # 후킹 공통 글루 — 매퍼 3-튜플을 domain과 함께 fire로 정확히 전달(domain 오타·인자 누락 회귀 고정).
    captured = {}
    monkeypatch.setattr(si, "fire_shadow_compare", lambda **kw: captured.update(kw) or "task")
    out = si.observe("building_compliance", "tnt", ("non_compliant", {"rules": [1]}, 0.7))
    assert out == "task"
    assert captured["domain"] == "building_compliance" and captured["tenant_id"] == "tnt"
    assert captured["platform_verdict"] == "non_compliant" and captured["platform_value"] == 0.7
    assert captured["engine_payload"] == {"rules": [1]}


def test_observe_noop_when_no_mapping_or_tenant(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(si, "fire_shadow_compare", lambda **kw: calls.__setitem__("n", calls["n"] + 1))
    assert si.observe("d", "t", None) is None        # 매퍼 None(매핑 불가) → no-op
    assert si.observe("d", None, ("v", {}, 1)) is None  # 테넌트 없음 → no-op
    assert calls["n"] == 0


async def test_shadow_compare_never_raises_on_record_failure(monkeypatch):
    # ★운영 무중단 핵심 — DB record 장애도 도메인 흐름으로 전파 금지(엔진 예외와 함께 가장 흔한 실패축).
    async def _post(dump, deterministic=True, tenant=None, breaker=None):
        return {"findings": [{"verdict": "COMPLIANT"}], "report": {}}, "ok"
    async def _rec_fail(**kw):
        raise RuntimeError("db down")
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _post)
    monkeypatch.setattr(s, "record", _rec_fail)
    out = await si.shadow_compare(tenant_id="t", domain="design_audit",
                                  platform_verdict="pass", engine_payload=_VALID_PAYLOAD)
    assert out is None  # record 예외 삼킴(never-raise)


async def test_design_audit_router_hook_invokes_observe(monkeypatch):
    # ★거짓-green 해소 — 실제 라우터(_execute_run)가 enable 시 observe를 정확한 domain/verdict로 1회 호출.
    import app.services.ledger.ledger_adapters as la
    import app.services.ledger.prior_context as pc
    import apps.api.config as cfg
    from apps.api.app.routers import design_audit as da

    class _Orch:
        async def run(self, db, **kw):
            return {"overall": {"verdict_en": "fail"}, "derived_signals": {},
                    "findings": [{"check_id": "rules8_far", "current": 250.0, "limit": 200.0, "status": "fail"}]}
    monkeypatch.setattr(da, "_get_orchestrator", lambda: _Orch())

    async def _save(*a, **k):
        return "aid"
    async def _none(**k):
        return None
    monkeypatch.setattr(da, "_save_audit", _save)
    monkeypatch.setattr(pc, "load_prior", _none)
    monkeypatch.setattr(la, "record_design_audit", _none)
    monkeypatch.setattr(cfg, "get_settings", lambda: _FakeS(enabled=True))
    captured = {}
    monkeypatch.setattr(si, "observe", lambda *a, **k: captured.update(args=a))
    req = da.RunRequest(use_llm=False, project_id="p1")
    current = type("U", (), {"tenant_id": "tnt-1", "user_id": "u1"})()
    out = await da._execute_run(req, current, object())
    assert out["ok"] is True                                  # 도메인 응답 정상(무중단)
    assert captured["args"][0] == "design_audit"              # domain 문자열
    assert captured["args"][1] == "tnt-1"                     # tenant
    assert captured["args"][2][0] == "fail"                   # mapped verdict(subset worst status)


async def test_design_audit_router_hook_skips_when_disabled(monkeypatch):
    import app.services.ledger.ledger_adapters as la
    import app.services.ledger.prior_context as pc
    import apps.api.config as cfg
    from apps.api.app.routers import design_audit as da

    class _Orch:
        async def run(self, db, **kw):
            return {"overall": {"verdict_en": "fail"}, "derived_signals": {}, "findings": []}
    async def _save(*a, **k):
        return "aid"
    async def _none(**k):
        return None
    monkeypatch.setattr(da, "_get_orchestrator", lambda: _Orch())
    monkeypatch.setattr(da, "_save_audit", _save)
    monkeypatch.setattr(pc, "load_prior", _none)
    monkeypatch.setattr(la, "record_design_audit", _none)
    monkeypatch.setattr(cfg, "get_settings", lambda: _FakeS(enabled=False))  # gate off
    calls = {"n": 0}
    monkeypatch.setattr(si, "observe", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    req = da.RunRequest(use_llm=False, project_id="p1")
    current = type("U", (), {"tenant_id": "tnt-1", "user_id": "u1"})()
    await da._execute_run(req, current, object())
    assert calls["n"] == 0  # gate-first: off면 매퍼/observe 미발생


async def test_shadow_compare_timeout_is_skipped(monkeypatch):
    # 느린 엔진(상한 초과) → wait_for 타임아웃 → None(도메인 흐름 무영향, 거짓적재 없음).
    import asyncio as _aio

    async def _slow(dump, deterministic=True, tenant=None, breaker=None):
        await _aio.sleep(0.2)
        return {"findings": []}, "ok"

    class _S(_FakeS):
        deliberation_shadow_engine_timeout_s = 0.01  # 10ms 상한
    monkeypatch.setattr(si, "get_settings", lambda: _S())
    monkeypatch.setattr(delib, "_engine_post_analyze", _slow)
    out = await si.shadow_compare(tenant_id="t", domain="design_audit",
                                  platform_verdict="pass", engine_payload=_VALID_PAYLOAD)
    assert out is None  # 타임아웃 → 생략


# ── 실 DB 적재 라운드트립(없으면 skip — 거짓통과 금지) ──


@pytest.fixture
async def shadow_db():
    from app.core.database import async_session_factory, engine

    await engine.dispose()
    try:
        async with async_session_factory() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 미가용 — shadow 통합테스트 skip: {str(e)[:80]}")
    monkey = s._ensured
    s._ensured = False  # 테스트 DB에 _ensure 재실행 보장
    yield
    s._ensured = monkey


async def test_record_persists_divergence(shadow_db):
    import uuid as _uuid

    from app.core.database import async_session_factory
    tnt = f"test-{_uuid.uuid4().hex[:12]}"
    out = await s.record(tenant_id=tnt, domain="comprehensive",
                         platform_verdict="CONDITIONAL", engine_verdict="NEEDS_REVIEW",
                         input_hash="ih1", platform_value=205.0, engine_value=200.0,
                         detail={"note": "한글 상세"})
    assert out["matched"] is True and out["divergence_score"] == 0.0  # 동치군 일치
    async with async_session_factory() as db:
        row = (await db.execute(
            text("SELECT domain, matched, quant_rel_err, detail, platform_verdict, engine_verdict, "
                 "divergence_score, input_hash FROM shadow_comparison WHERE id = :i"),
            {"i": out["id"]},
        )).first()
        await db.execute(text("DELETE FROM shadow_comparison WHERE tenant_id = :t"), {"t": tnt})
        await db.commit()
    assert row is not None and row[0] == "comprehensive" and row[1] is True
    assert abs(row[2] - 0.025) < 1e-6 and row[3]["note"] == "한글 상세"
    # 컬럼-매핑 바인딩 회귀 가드: 핵심 산출 컬럼 전수 라운드트립.
    assert row[4] == "CONDITIONAL" and row[5] == "NEEDS_REVIEW"  # 원문 verdict 보존
    assert row[6] == 0.0 and row[7] == "ih1"                      # divergence_score·lineage


async def test_record_persists_null_verdict(shadow_db):
    # platform_verdict=None → 컬럼 NULL 저장(str(None) 오저장 회귀 방지). matched=False(None≠'x').
    import uuid as _uuid

    from app.core.database import async_session_factory
    tnt = f"test-{_uuid.uuid4().hex[:12]}"
    out = await s.record(tenant_id=tnt, domain="design_audit",
                         platform_verdict=None, engine_verdict="compliant")
    assert out["matched"] is False
    async with async_session_factory() as db:
        row = (await db.execute(
            text("SELECT platform_verdict, divergence_score FROM shadow_comparison WHERE id = :i"),
            {"i": out["id"]},
        )).first()
        await db.execute(text("DELETE FROM shadow_comparison WHERE tenant_id = :t"), {"t": tnt})
        await db.commit()
    assert row[0] is None and row[1] == 1.0  # NULL 저장·불일치


async def test_divergence_stats_aggregates(shadow_db):
    # stage3 승격 근거 — 도메인별 관측수·일치율 집계. 같은 테넌트에 일치 2 + 불일치 1 → match_rate 2/3.
    import uuid as _uuid

    from app.core.database import async_session_factory
    tnt = f"test-{_uuid.uuid4().hex[:12]}"
    await s.record(tenant_id=tnt, domain="design_audit", platform_verdict="fail", engine_verdict="fail")        # 일치
    await s.record(tenant_id=tnt, domain="design_audit", platform_verdict="pass", engine_verdict="compliant")  # 동치
    await s.record(tenant_id=tnt, domain="design_audit", platform_verdict="fail", engine_verdict="compliant")   # 불일치
    try:
        stats = await s.divergence_stats(tenant_id=tnt, domain="design_audit")
        assert len(stats) == 1
        st = stats[0]
        assert st["domain"] == "design_audit" and st["n"] == 3 and st["matched_n"] == 2
        assert abs(st["match_rate"] - 2 / 3) < 1e-9
        assert abs(st["avg_divergence"] - 1 / 3) < 1e-9  # (0+0+1)/3
        # min_n 게이트: 4 이상만 → 제외(승격 전 충분 관측 강제).
        assert await s.divergence_stats(tenant_id=tnt, domain="design_audit", min_n=4) == []
    finally:
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM shadow_comparison WHERE tenant_id = :t"), {"t": tnt})
            await db.commit()
