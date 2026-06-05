"""D2 기성고 EVM 실구현 — PV/EV/AC · SPI/CPI · 과다청구 이상탐지 · 해시체인.

비전문가(재개발·재건축·지역주택조합 등 조합)가 시공 중 과다청구·과도한 추가공사를
미연방지하도록 기성(progress_billings)을 실제 영속·집계·이상탐지한다.

재사용:
 - cost_tables_bootstrap._ensure_cost_tables (progress_billings 멱등 생성 + 컬럼 보강)
 - unit_price_repository (계약/표준단가 SSOT — 청구단가 이탈 탐지 근거)
 - analysis_ledger_service.append_analysis (해시체인 변조탐지 적재, best-effort)

정직성: 단가 출처·임계치를 명시하고, 경고는 "검토 권장 사항·확정 아님"으로 표기한다.
데이터 부재 시 정직 표기(no_data)한다. 기존 cost 엔드포인트·계산 무파괴(신규 경로).
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── 이상탐지 임계치(검토 권장 기준 — 확정 아님) ──
UNIT_PRICE_DEVIATION_PCT = 15.0   # 청구단가가 계약/표준단가 대비 +15% 이탈 시 경고
SPI_CPI_WARN = 0.9                # SPI/CPI < 0.9 시 일정/원가 효율 경고
CLAIM_SURGE_PCT = 50.0            # 전회比 청구 +50% 급증 시 경고

# progress_billings 에 본 서비스가 추가로 쓰는 컬럼(기존 테이블에 없으면 멱등 보강).
_DDL_ADD_COLUMNS = (
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS work_type varchar(100)",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS contract_amount numeric(18,2) DEFAULT 0",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS claimed_amount numeric(18,2) DEFAULT 0",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS claimed_qty numeric(18,4)",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS unit_price numeric(18,2)",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS progress_pct double precision DEFAULT 0",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS contract_unit_price numeric(18,2)",
    "ALTER TABLE progress_billings ADD COLUMN IF NOT EXISTS ledger_hash varchar(80)",
)

_NOTE = (
    "기성·EVM·과다청구 경고는 표준품셈/계약 단가 대비 검토 권장 사항이며 확정·법적 판정이 아닙니다. "
    "실제 정산 전 계약서·설계변경·물가변동 조건과 대조하세요."
)


async def _ensure_billing_columns(db) -> None:
    """progress_billings 에 D2 컬럼을 멱등 보강(IF NOT EXISTS). 기존 데이터 무영향."""
    from sqlalchemy import text

    from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables

    await _ensure_cost_tables(db)  # progress_billings 테이블 자체 보장
    for ddl in _DDL_ADD_COLUMNS:
        await db.execute(text(ddl))


def compute_evm(claims: list[dict[str, Any]], contract_total: float) -> dict[str, Any]:
    """회차별 기성 목록에서 EVM 집계.

    PV(계획가치) = 계획공정률(progress_pct, 누적 가정) × 계약총액
    EV(획득가치) = 실제완료액(회차별 claimed_amount 중 계약범위 — 여기선 claimed_amount 합)
    AC(실제투입) = 누적 청구액(claimed_amount 합)

    회차별 곡선(누적 PV/EV/AC)을 함께 반환한다. progress_pct 는 해당 회차 시점의
    계획 누적 공정률(%)로 해석한다(없으면 직전 유지).
    """
    curve: list[dict[str, Any]] = []
    cum_ac = 0.0
    cum_ev = 0.0
    last_pct = 0.0
    pv = ev = ac = 0.0
    for c in sorted(claims, key=lambda x: x.get("round", 0)):
        rnd = int(c.get("round", 0))
        claimed = float(c.get("claimed_amount", 0) or 0)
        pct = c.get("progress_pct")
        pct = float(pct) if pct is not None else last_pct
        last_pct = pct
        # PV: 누적 계획 공정률 × 계약총액
        pv = round(contract_total * pct / 100.0, 2) if contract_total > 0 else 0.0
        # EV: 실제 완료(회차 청구액 누적 — 계약 단가 기반 완료액 근사)
        cum_ev += claimed
        ev = round(cum_ev, 2)
        # AC: 누적 실제 투입(청구액 누적)
        cum_ac += claimed
        ac = round(cum_ac, 2)
        curve.append({"round": rnd, "pv": pv, "ev": ev, "ac": ac})

    spi = round(ev / pv, 4) if pv > 0 else None
    cpi = round(ev / ac, 4) if ac > 0 else None
    return {"pv": pv, "ev": ev, "ac": ac, "spi": spi, "cpi": cpi, "curve": curve}


def detect_anomalies(
    claims: list[dict[str, Any]],
    contract_total: float,
    evm: dict[str, Any],
    standard_unit_prices: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """과다청구 이상탐지.

    ① 청구단가가 계약단가(contract_unit_price) 또는 표준단가 대비 +임계% 이탈
    ② 누적 청구액 > 계약총액
    ③ SPI/CPI < 0.9
    ④ 전회比 청구 급증(+임계%)
    각 경고는 {level, type, detail, evidence(근거수치)}.
    """
    standard_unit_prices = standard_unit_prices or {}
    anomalies: list[dict[str, Any]] = []
    sorted_claims = sorted(claims, key=lambda x: x.get("round", 0))

    # ① 청구단가 이탈
    for c in sorted_claims:
        rnd = int(c.get("round", 0))
        wt = c.get("work_type")
        up = c.get("unit_price")
        if up is None:
            continue
        up = float(up)
        ref = c.get("contract_unit_price")
        ref_src = "계약단가"
        if ref is None and wt and wt in standard_unit_prices:
            ref = standard_unit_prices[wt]
            ref_src = "표준단가(품셈)"
        if ref is None or float(ref) <= 0:
            continue
        ref = float(ref)
        dev = (up - ref) / ref * 100.0
        if dev > UNIT_PRICE_DEVIATION_PCT:
            anomalies.append({
                "level": "high" if dev > UNIT_PRICE_DEVIATION_PCT * 2 else "warn",
                "type": "unit_price_overclaim",
                "detail": f"{rnd}회차 '{wt or '항목'}' 청구단가가 {ref_src} 대비 {dev:.1f}% 초과(임계 +{UNIT_PRICE_DEVIATION_PCT:.0f}%).",
                "evidence": {"round": rnd, "work_type": wt, "claimed_unit_price": up,
                             "reference_unit_price": ref, "reference_source": ref_src,
                             "deviation_pct": round(dev, 1)},
            })

    # ② 누적 청구 > 계약총액
    cum = sum(float(c.get("claimed_amount", 0) or 0) for c in sorted_claims)
    if contract_total > 0 and cum > contract_total:
        over = cum - contract_total
        anomalies.append({
            "level": "high",
            "type": "cumulative_over_contract",
            "detail": f"누적 청구액이 계약총액을 초과({over:,.0f}원 초과). 추가공사·설계변경 정당성 검토 필요.",
            "evidence": {"cumulative_claimed": round(cum, 2), "contract_total": contract_total,
                         "over_amount": round(over, 2)},
        })

    # ③ SPI/CPI < 0.9
    spi = evm.get("spi")
    cpi = evm.get("cpi")
    if spi is not None and spi < SPI_CPI_WARN:
        anomalies.append({
            "level": "warn",
            "type": "low_spi",
            "detail": f"일정성과지수 SPI={spi} (< {SPI_CPI_WARN}). 계획 대비 진척 지연 가능.",
            "evidence": {"spi": spi, "threshold": SPI_CPI_WARN},
        })
    if cpi is not None and cpi < SPI_CPI_WARN:
        anomalies.append({
            "level": "warn",
            "type": "low_cpi",
            "detail": f"원가성과지수 CPI={cpi} (< {SPI_CPI_WARN}). 투입원가 대비 획득가치 저조(과다투입 의심).",
            "evidence": {"cpi": cpi, "threshold": SPI_CPI_WARN},
        })

    # ④ 전회比 청구 급증
    prev_amt: float | None = None
    for c in sorted_claims:
        amt = float(c.get("claimed_amount", 0) or 0)
        if prev_amt is not None and prev_amt > 0:
            surge = (amt - prev_amt) / prev_amt * 100.0
            if surge > CLAIM_SURGE_PCT:
                anomalies.append({
                    "level": "warn",
                    "type": "claim_surge",
                    "detail": f"{int(c.get('round', 0))}회차 청구가 전회比 {surge:.0f}% 급증(임계 +{CLAIM_SURGE_PCT:.0f}%).",
                    "evidence": {"round": int(c.get("round", 0)),
                                 "prev_claimed": round(prev_amt, 2), "claimed": round(amt, 2),
                                 "surge_pct": round(surge, 1)},
                })
        prev_amt = amt

    return anomalies


async def _standard_unit_prices() -> dict[str, float]:
    """표준단가 SSOT(work_type 키 → 자재+노무+경비 합산 단가). 실패 시 빈 dict."""
    out: dict[str, float] = {}
    try:
        from app.services.cost.unit_price_repository import UnitPriceRepository

        repo = UnitPriceRepository()
        prices = await repo.get_prices()
        for key, p in prices.items():
            out[key] = float(p.get("mat_unit", 0)) + float(p.get("labor_unit", 0)) + float(p.get("exp_unit", 0))
    except Exception as e:  # noqa: BLE001
        logger.warning("표준단가 조회 실패 — 단가이탈 탐지 일부 생략", err=str(e)[:160])
    return out


async def register_billing(
    *,
    project_id: str,
    billing_no: int,
    work_type: str | None,
    contract_amount: float,
    claimed_amount: float,
    claimed_qty: float | None,
    unit_price: float | None,
    contract_unit_price: float | None,
    progress_pct: float,
    period_from: str | None,
    period_to: str | None,
    contract_total: float | None,
    tenant_id: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """기성 1회차를 progress_billings 에 영속하고, 등록 즉시 트리거된 이상경고를 반환.

    해시체인: analysis_ledger.append_analysis(analysis_type="progress_billing") best-effort.
    """
    import uuid as _uuid

    try:
        _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return {"ok": False, "message": "project_id 가 유효한 UUID 가 아닙니다(영속화 불가)."}

    ledger_hash: str | None = None
    # 해시체인 적재(best-effort — 변조탐지 기반)
    try:
        from app.services.ledger import analysis_ledger_service

        res = await analysis_ledger_service.append_analysis(
            analysis_type="progress_billing",
            payload={
                "billing_no": billing_no, "work_type": work_type,
                "contract_amount": contract_amount, "claimed_amount": claimed_amount,
                "claimed_qty": claimed_qty, "unit_price": unit_price,
                "progress_pct": progress_pct,
                "period": f"{period_from or ''} ~ {period_to or ''}",
            },
            tenant_id=tenant_id, project_id=str(project_id),
            source="cost_billing", created_by=created_by,
        )
        if isinstance(res, dict) and res.get("ok"):
            ledger_hash = res.get("content_hash")
    except Exception as e:  # noqa: BLE001
        logger.warning("기성 해시체인 적재 실패(무시)", err=str(e)[:160])

    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure_billing_columns(db)
            row = (await db.execute(text(
                "INSERT INTO progress_billings"
                "(project_id, billing_no, period_from, period_to, work_entries,"
                " work_type, contract_amount, claimed_amount, claimed_qty, unit_price,"
                " contract_unit_price, progress_pct, planned_value, earned_value, actual_cost, ledger_hash)"
                " VALUES (:pid,:bno,:pf,:pt,CAST(:we AS jsonb),"
                " :wt,:ca,:cl,:cq,:up,:cup,:pp,:pv,:ev,:ac,:lh)"
                " RETURNING id"), {
                "pid": str(project_id), "bno": billing_no,
                "pf": period_from or None, "pt": period_to or None,
                "we": json.dumps([], ensure_ascii=False),
                "wt": work_type, "ca": contract_amount, "cl": claimed_amount,
                "cq": claimed_qty, "up": unit_price, "cup": contract_unit_price,
                "pp": progress_pct,
                # 회차 단건 EVM 근사(전체 곡선은 GET 시 누적 재집계)
                "pv": round((contract_total or contract_amount or 0) * progress_pct / 100.0, 2),
                "ev": claimed_amount, "ac": claimed_amount,
                "lh": ledger_hash,
            })).first()
            await db.commit()
            claim_id = int(row[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("기성 영속화 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}

    # 등록 후 전체 누적 기준으로 이상탐지(이번 회차가 유발한 경고 식별)
    summary = await get_billing_summary(project_id=project_id, contract_total=contract_total)
    triggered = [a for a in summary.get("anomalies", [])
                 if (a.get("evidence", {}) or {}).get("round") == billing_no
                 or a.get("type") in ("cumulative_over_contract", "low_spi", "low_cpi")]
    return {"ok": True, "claim_id": claim_id, "ledger_hash": ledger_hash,
            "anomalies_triggered": triggered}


async def get_billing_summary(
    *, project_id: str, contract_total: float | None = None,
) -> dict[str, Any]:
    """프로젝트 기성 목록 + EVM summary + 곡선 + 이상경고."""
    import uuid as _uuid

    try:
        _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return {"ok": True, "status": "no_data", "contract_total": 0.0, "claims": [],
                "evm": {"pv": 0, "ev": 0, "ac": 0, "spi": None, "cpi": None, "curve": []},
                "anomalies": [], "badges": {"note": _NOTE, "data": "유효 project_id 아님"}}

    claims: list[dict[str, Any]] = []
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure_billing_columns(db)
            rows = (await db.execute(text(
                "SELECT billing_no, work_type, contract_amount, claimed_amount, claimed_qty,"
                " unit_price, contract_unit_price, progress_pct, period_from, period_to, ledger_hash"
                " FROM progress_billings WHERE project_id = :pid ORDER BY billing_no ASC"),
                {"pid": str(project_id)})).all()
            for r in rows:
                claims.append({
                    "round": int(r[0]), "work_type": r[1],
                    "contract_amount": float(r[2] or 0), "claimed_amount": float(r[3] or 0),
                    "claimed_qty": float(r[4]) if r[4] is not None else None,
                    "unit_price": float(r[5]) if r[5] is not None else None,
                    "contract_unit_price": float(r[6]) if r[6] is not None else None,
                    "progress_pct": float(r[7] or 0),
                    "period": f"{r[8] or ''} ~ {r[9] or ''}".strip(" ~"),
                    "ledger_hash": r[10],
                })
    except Exception as e:  # noqa: BLE001
        logger.warning("기성 목록 조회 실패", err=str(e)[:160])
        return {"ok": False, "status": "error", "message": str(e)[:160],
                "contract_total": 0.0, "claims": [],
                "evm": {"pv": 0, "ev": 0, "ac": 0, "spi": None, "cpi": None, "curve": []},
                "anomalies": [], "badges": {"note": _NOTE}}

    # 계약총액: 인자 우선, 없으면 회차 계약액 합(work_type 단위 계약액 가정)
    ct = float(contract_total) if contract_total else sum(c["contract_amount"] for c in claims)
    evm = compute_evm(claims, ct)
    std_prices = await _standard_unit_prices()
    anomalies = detect_anomalies(claims, ct, evm, std_prices)

    status = "no_data" if not claims else "ok"
    return {
        "ok": True,
        "status": status,
        "contract_total": ct,
        "claims": claims,
        "evm": evm,
        "anomalies": anomalies,
        "badges": {
            "note": _NOTE,
            "unit_price_source": "표준품셈2025 / 계약단가",
            "thresholds": {
                "unit_price_deviation_pct": UNIT_PRICE_DEVIATION_PCT,
                "spi_cpi_warn": SPI_CPI_WARN,
                "claim_surge_pct": CLAIM_SURGE_PCT,
            },
            "data": "no_data" if not claims else f"{len(claims)}개 회차",
        },
    }


async def get_anomalies(
    *, project_id: str, contract_total: float | None = None,
) -> dict[str, Any]:
    """과다청구 이상탐지 단독 조회."""
    summary = await get_billing_summary(project_id=project_id, contract_total=contract_total)
    return {
        "ok": summary.get("ok", True),
        "status": summary.get("status"),
        "contract_total": summary.get("contract_total"),
        "anomalies": summary.get("anomalies", []),
        "evm": summary.get("evm"),
        "badges": summary.get("badges"),
    }
