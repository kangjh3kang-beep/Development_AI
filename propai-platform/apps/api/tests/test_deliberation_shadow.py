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


def _ef(far, far_lim, bcr, bcr_lim, pnu="1111010100100000002"):
    return {"pnu": pnu, "effective_far": {
        "effective_far_pct": far, "effective_bcr_pct": bcr,
        "far_basis_detail": {"법정범위": {"max_far_pct": far_lim, "max_bcr_pct": bcr_lim}}}}


def test_mapper_comprehensive_compliant():
    v, payload, val = sm.comprehensive(_ef(180.0, 200.0, 50.0, 60.0))
    assert v == "compliant" and len(payload["rules"]) == 2 and payload["pnu"] == "1111010100100000002"
    assert payload["rules"][0]["rule"]["rule_id"] == "FAR" and val == 180.0


def test_mapper_comprehensive_non_compliant_on_far_over():
    v, payload, _ = sm.comprehensive(_ef(250.0, 200.0, 50.0, 60.0))
    assert v == "non_compliant"


def test_mapper_comprehensive_skips_when_no_metrics():
    assert sm.comprehensive({"effective_far": None}) is None
    assert sm.comprehensive({"effective_far": {"effective_far_pct": "x"}}) is None  # 비수치 → 룰 없음 → None


def test_mapper_comprehensive_excludes_non19_pnu():
    _, payload, _ = sm.comprehensive(_ef(180.0, 200.0, 50.0, 60.0, pnu="123"))
    assert "pnu" not in payload  # 19자리 아니면 lineage 생략(prevalidate 패턴)


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
    async def _post(dump, deterministic=True, tenant=None):
        return {"findings": [{"verdict": "NON_COMPLIANT"}], "report": {}}, "ok"
    async def _rec(**kw):
        captured.update(kw)
        return {"id": "x", "matched": kw["platform_verdict"] == "NON_COMPLIANT", "divergence_score": 0.0}
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _post)
    monkeypatch.setattr(s, "record", _rec)
    out = await si.shadow_compare(tenant_id="t", domain="comprehensive",
                                  platform_verdict="REJECTED", engine_payload=_VALID_PAYLOAD)
    assert out is not None
    assert captured["domain"] == "comprehensive" and captured["engine_verdict"] == "non_compliant"
    assert captured["input_hash"]  # lineage 동반


async def test_shadow_compare_skips_when_engine_unavailable(monkeypatch):
    async def _post(dump, deterministic=True, tenant=None):
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
    async def _boom(dump, deterministic=True, tenant=None):
        raise RuntimeError("engine blew up")
    monkeypatch.setattr(si, "get_settings", lambda: _FakeS())
    monkeypatch.setattr(delib, "_engine_post_analyze", _boom)
    # 엔진 예외도 도메인 흐름으로 전파 금지 → None.
    out = await si.shadow_compare(tenant_id="t", domain="comprehensive",
                                  platform_verdict="COMPLIANT", engine_payload=_VALID_PAYLOAD)
    assert out is None


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
            text("SELECT domain, matched, quant_rel_err, detail FROM shadow_comparison WHERE id = :i"),
            {"i": out["id"]},
        )).first()
        await db.execute(text("DELETE FROM shadow_comparison WHERE tenant_id = :t"), {"t": tnt})
        await db.commit()
    assert row is not None and row[0] == "comprehensive" and row[1] is True
    assert abs(row[2] - 0.025) < 1e-6 and row[3]["note"] == "한글 상세"
