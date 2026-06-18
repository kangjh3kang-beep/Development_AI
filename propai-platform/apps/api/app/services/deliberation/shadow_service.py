"""중심엔진 수렴(P3~P6) 관측 계층 — shadow_comparison: 플랫폼 자체 판정 vs 엔진 판정 divergence 기록.

설계 §6: 도메인 분석을 엔진으로 즉시 이관하지 않고 **shadow 병존**(플랫폼 판정은 그대로 운영, 엔진 판정을
best-effort로 함께 산출해 divergence만 적재) → 충분한 일치 관측 후 authoritative 승격. 운영 무중단.
verdict 정규화 후 일치 여부·divergence_score(0=일치 1=상이)·정량 상대오차(quant_rel_err)를 계산.
런타임 _ensure(프로세스 1회) — 스키마는 alembic 033_shadow_comparison이 1차 보장(binding_service 패턴).
"""
from __future__ import annotations

import json
import math
import uuid
from typing import Any

# verdict 어휘 정규화 — 플랫폼/엔진이 다른 표기를 써도 동치 판정군으로 묶어 거짓 divergence 방지.
_VERDICT_NORM = {
    "compliant": "compliant", "pass": "compliant", "passed": "compliant", "approved": "compliant",
    "confirmed": "compliant", "ok": "compliant", "적합": "compliant",
    "non_compliant": "non_compliant", "fail": "non_compliant", "failed": "non_compliant",
    "rejected": "non_compliant", "violation": "non_compliant", "부적합": "non_compliant",
    "needs_review": "needs_review", "conditional": "needs_review", "held": "needs_review",
    "discretion_held": "needs_review", "review": "needs_review", "조건부": "needs_review", "보류": "needs_review",
    "warning": "needs_review", "warn": "needs_review",
}

_DDL = (
    "CREATE TABLE IF NOT EXISTS shadow_comparison ("
    "  id text PRIMARY KEY,"
    "  tenant_id text NOT NULL,"
    "  domain text NOT NULL,"              # 'comprehensive' | 'design_audit' | 'area' | ...
    "  input_hash text,"                   # 엔진 input_hash(가용 시) — lineage
    "  platform_verdict text,"
    "  engine_verdict text,"
    "  matched boolean NOT NULL,"
    "  divergence_score double precision NOT NULL,"  # 0.0(일치) ~ 1.0(상이)
    "  quant_rel_err double precision,"    # 정량 상대오차(둘 다 수치일 때)
    "  detail jsonb,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_shadow_domain "
    "ON shadow_comparison(tenant_id, domain, created_at DESC)"
)

_ensured = False


def norm_verdict(v: Any) -> str:
    """verdict 문자열 정규화(소문자·동치군 매핑). None/빈값=''."""
    s = str(v or "").strip().lower()
    return _VERDICT_NORM.get(s, s)


def _rel_err(p: Any, e: Any) -> float | None:
    """정량 상대오차 |p-e|/max(|e|,eps) — 둘 다 유한 수치일 때만. bool 제외."""
    def _num(x: Any) -> float | None:
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)) and math.isfinite(x):
            return float(x)
        return None
    pv, ev = _num(p), _num(e)
    if pv is None or ev is None:
        return None
    return abs(pv - ev) / max(abs(ev), 1e-9)


def compute_divergence(platform_verdict: Any, engine_verdict: Any,
                       *, platform_value: Any = None, engine_value: Any = None) -> dict[str, Any]:
    """판정 일치 여부 + divergence_score + 정량 상대오차. 순수 함수(테스트 용이)."""
    matched = norm_verdict(platform_verdict) == norm_verdict(engine_verdict)
    return {
        "matched": matched,
        "divergence_score": 0.0 if matched else 1.0,
        "quant_rel_err": _rel_err(platform_value, engine_value),
    }


async def record(*, tenant_id: str, domain: str, platform_verdict: Any, engine_verdict: Any,
                 input_hash: str | None = None, platform_value: Any = None, engine_value: Any = None,
                 detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """divergence 계산 후 shadow_comparison에 적재. 반환=계산 결과(+id). 운영 무중단 관측 전용."""
    from sqlalchemy import text

    from app.core.database import async_session_factory

    div = compute_divergence(platform_verdict, engine_verdict,
                             platform_value=platform_value, engine_value=engine_value)
    row_id = str(uuid.uuid4())
    async with async_session_factory() as db:
        await _ensure(db)
        await db.execute(
            text(
                "INSERT INTO shadow_comparison"
                "(id, tenant_id, domain, input_hash, platform_verdict, engine_verdict,"
                " matched, divergence_score, quant_rel_err, detail) "
                "VALUES (:id, :t, :d, :ih, :pv, :ev, :m, :ds, :qe, cast(:detail as jsonb))"
            ),
            {
                "id": row_id, "t": tenant_id, "d": domain, "ih": input_hash,
                "pv": str(platform_verdict) if platform_verdict is not None else None,
                "ev": str(engine_verdict) if engine_verdict is not None else None,
                "m": div["matched"], "ds": div["divergence_score"], "qe": div["quant_rel_err"],
                "detail": json.dumps(detail) if detail is not None else None,
            },
        )
        await db.commit()
    return {"id": row_id, **div}


async def _ensure(db) -> None:
    global _ensured
    if _ensured:
        return
    from sqlalchemy import text

    await db.execute(text(_DDL))
    await db.execute(text(_IDX))
    _ensured = True
