"""보고서 내러티브 상승루프 배선(P1 해소) — _gather_report_narratives 전파·부분보존.

검증 대상:
- use_verification_retry 플래그가 _gather_report_narratives → _interpret_stage로 전파되는지
- 기본값(False) 호출은 기존 파이프라인 경로 동작과 동일한지(무회귀)
- 타임아웃 시 완료된 내러티브는 보존하고 미완료만 생략·취소되는지(부분보존)
- 검증루프 경로의 캐시키 분리(":verified") 및 검증실패본 캐시 미고착
- /api/v1/reports/generate 가 품질우선(검증루프 ON + 타임아웃 상향)으로 호출하는지

asyncio_mode=auto — 마커 불요. 외부 LLM/DB 호출 없이 monkeypatch로 격리.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.routers.pipeline as pl


def _result_dict() -> dict:
    """stages 2개(site_analysis·cost)를 가진 최소 파이프라인 결과."""
    return {
        "address": "서울 테스트",
        "stages": {
            "site_analysis": {
                "stage": "site_analysis",
                "data": {"land_area_sqm": 300.0, "zone_type": "제2종일반주거지역"},
            },
            "cost": {"stage": "cost", "data": {"total_construction_cost": 1_000_000_000}},
        },
        "summary": {},
    }


# ── 1) use_verification_retry 전파 ─────────────────────────────


async def test_gather_narratives_propagates_verification_flag(monkeypatch):
    """True로 부르면 모든 단계의 _interpret_stage에 True가 전달돼야 한다."""
    seen: dict[str, bool] = {}

    async def fake_interpret(stage, data, *, use_verification_retry=False):
        seen[stage] = use_verification_retry
        return {"ok": True, "stage": stage, "sections": {"요약": "x"}}

    monkeypatch.setattr(pl, "_interpret_stage", fake_interpret)
    out = await pl._gather_report_narratives(
        _result_dict(), timeout=5.0, use_verification_retry=True)
    assert set(out) == {"site_analysis", "cost"}
    assert seen == {"site_analysis": True, "cost": True}


async def test_gather_narratives_default_is_no_verification(monkeypatch):
    """기본 호출(플래그 생략)은 기존과 동일하게 무검증 경로여야 한다(무회귀)."""
    seen: dict[str, bool] = {}

    async def fake_interpret(stage, data, *, use_verification_retry=False):
        seen[stage] = use_verification_retry
        return {"ok": True, "stage": stage, "sections": {"요약": "x"}}

    monkeypatch.setattr(pl, "_interpret_stage", fake_interpret)
    out = await pl._gather_report_narratives(_result_dict(), timeout=5.0)
    assert set(out) == {"site_analysis", "cost"}
    assert seen == {"site_analysis": False, "cost": False}


# ── 2) 타임아웃 부분보존 ──────────────────────────────────────


async def test_gather_narratives_timeout_preserves_completed(monkeypatch):
    """느린 단계가 타임아웃돼도 이미 완료된 단계 해석은 보존돼야 한다.

    (이전 wait_for(gather) 구현은 타임아웃 시 완료분까지 전량 유실 — 회귀 방지 테스트)
    """
    cancelled: dict[str, bool] = {}

    async def fake_interpret(stage, data, *, use_verification_retry=False):
        if stage == "cost":  # cost는 타임아웃보다 오래 걸리는 느린 단계로 시뮬레이션
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled[stage] = True  # 취소 정리가 실제로 도달했는지 기록
                raise
        return {"ok": True, "stage": stage, "sections": {"요약": f"{stage} 완료"}}

    monkeypatch.setattr(pl, "_interpret_stage", fake_interpret)
    out = await pl._gather_report_narratives(_result_dict(), timeout=0.3)
    assert out == {"site_analysis": {"요약": "site_analysis 완료"}}  # 완료분 보존
    assert cancelled.get("cost") is True  # 미완료 태스크는 cancel로 정리


async def test_gather_narratives_one_stage_error_keeps_others(monkeypatch):
    """한 단계가 예외로 죽어도 다른 단계 해석은 보존돼야 한다."""

    async def fake_interpret(stage, data, *, use_verification_retry=False):
        if stage == "cost":
            raise RuntimeError("단계 내부 오류")
        return {"ok": True, "stage": stage, "sections": {"요약": "ok"}}

    monkeypatch.setattr(pl, "_interpret_stage", fake_interpret)
    out = await pl._gather_report_narratives(_result_dict(), timeout=5.0)
    assert out == {"site_analysis": {"요약": "ok"}}


# ── 3) 검증경로 캐시키 분리 ───────────────────────────────────


class _FakeInterp:
    """LLM 없이 고정 섹션을 돌려주는 가짜 인터프리터."""

    def set_retry_feedback(self, txt):
        pass

    async def generate_interpretation(self, data):
        return {"요약": "본문"}


def _patch_cache(monkeypatch):
    """interpretation_cache의 get/put을 가로채 사용된 키를 기록한다."""
    from app.services.ai import interpretation_cache as ic

    keys_get: list[str] = []
    keys_put: list[str] = []

    async def fake_get(key):
        keys_get.append(key)
        return None  # 항상 캐시미스 → 생성 경로 진입

    async def fake_put(key, stage, sections):
        keys_put.append(key)

    monkeypatch.setattr(ic, "get_cached", fake_get)
    monkeypatch.setattr(ic, "put_cached", fake_put)
    return keys_get, keys_put


async def test_interpret_stage_verified_cache_key_is_separated(monkeypatch):
    """검증루프 경로는 ':verified' 접미사 키를, 무검증 경로는 기본 키를 써야 한다."""
    keys_get, keys_put = _patch_cache(monkeypatch)
    monkeypatch.setattr(pl, "_make_interpreter", lambda stage: _FakeInterp())

    async def fake_verify_retry(stage, data, interp, sections):
        return {"sections": sections, "verification": {"verdict": "pass", "issues": []},
                "regenerated": False}

    monkeypatch.setattr(pl, "_verify_and_maybe_retry", fake_verify_retry)

    r1 = await pl._interpret_stage("cost", {"a": 1}, use_verification_retry=True)
    r2 = await pl._interpret_stage("cost", {"a": 1})
    assert r1["ok"] and r2["ok"]
    assert keys_get[0].endswith(":verified")            # 검증경로 키 분리
    assert not keys_get[1].endswith(":verified")        # 무검증 경로는 기존 키 그대로
    assert keys_get[1] == keys_get[0].removesuffix(":verified")  # 동일 입력=동일 기본키
    assert keys_put == keys_get                          # 각 경로가 자기 키에 저장


async def test_interpret_stage_failed_verification_not_cached(monkeypatch):
    """1회 재생성 후에도 검증 실패(verification_warning)한 결과는 캐시에 남기지 않는다."""
    keys_get, keys_put = _patch_cache(monkeypatch)
    monkeypatch.setattr(pl, "_make_interpreter", lambda stage: _FakeInterp())

    async def fake_verify_retry(stage, data, interp, sections):
        return {"sections": sections, "verification": {"verdict": "fail", "issues": []},
                "regenerated": False,
                "verification_warning": "검증에 실패했고 1회 재생성 후에도 통과하지 못해 원본을 유지합니다."}

    monkeypatch.setattr(pl, "_verify_and_maybe_retry", fake_verify_retry)

    out = await pl._interpret_stage("cost", {"a": 1}, use_verification_retry=True)
    assert out["ok"] and "verification_warning" in out   # 응답에는 경고배지 유지(정직표기)
    assert keys_put == []                                # 실패본은 캐시 고착 금지


# ── 4) /reports/generate 배선(품질우선 경로) ──────────────────


async def test_reports_generate_uses_verification_retry_and_longer_timeout(monkeypatch):
    """보고서 생성 엔드포인트는 검증루프 ON + 타임아웃 상향(55s)으로 내러티브를 수집해야 한다."""
    from app.services.ledger import analysis_ledger_service as ledger_mod
    from app.services.report import render as render_mod
    from apps.api.routers import reports as reports_mod

    # 원장: 최신 pipeline payload가 있는 것으로 시뮬레이션
    async def fake_get_latest(**kwargs):
        return {"payload": _result_dict()}

    monkeypatch.setattr(ledger_mod, "get_latest", fake_get_latest)

    # 내러티브 수집 호출 인자 캡처(실제 LLM 호출 없음)
    captured: dict = {}

    async def fake_gather(result_dict, timeout=28.0, *, use_verification_retry=False):
        captured["timeout"] = timeout
        captured["use_verification_retry"] = use_verification_retry
        return {}

    monkeypatch.setattr(pl, "_gather_report_narratives", fake_gather)

    # 렌더 엔진: 더미 바이트 반환(무거운 렌더 생략)
    monkeypatch.setattr(render_mod, "build_report_model_from_pipeline",
                        lambda rd, narratives=None: {"model": True})
    monkeypatch.setattr(render_mod, "render_report",
                        lambda model, fmt="pdf": (b"%PDF-dummy", "application/pdf", "pdf"))

    req = reports_mod.ReportGenerateRequest(project_id="p-1", format="pdf")
    resp = await reports_mod.generate_report_pdf(req, current=SimpleNamespace(tenant_id="t-1"))

    assert resp.status_code == 200
    assert captured["use_verification_retry"] is True   # 보고서=품질우선 경로
    assert captured["timeout"] >= 55.0                  # 재생성 여유 타임아웃 상향
