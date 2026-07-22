"""적산 back-test 계약(W3-3, P9) — 예측(견적) vs 실적(실행내역) 정확도 계측.

record_estimate(견적 스냅샷 기록) → (공사 진행/준공 후) record_actual(실적 기록)
→ compute_accuracy(APE/MAPE/bias/outlier)의 3단 계약.

★무목업 원칙: 이 플랫폼은 아직 프로젝트 실행 내역(계약 견적 대비 실제 집행 금액)을
저장소/DB 어디에도 보유하지 않는다(스파이크 확인 — cost_estimate/cost_estimate_item 은
"견적"만 저장, "실적"을 저장하는 테이블은 이전에 없었음). 따라서 이 모듈이 제공하는 것은:
  1) 예측·실적을 나란히 적재할 수 있는 **영속 계약**(테이블 2개, cost_tables_bootstrap과
     동일한 멱등 CREATE TABLE IF NOT EXISTS 선례를 따름 — analysis_ledger_service 패턴).
  2) 실적이 실제로 쌓였을 때만 APE/MAPE/bias/outlier 를 계산하는 **순수 통계 함수**
     (compute_stats_from_pairs — DB 무의존, 단위 테스트 가능).
  3) 실적 0건(현재 상태)일 때 가짜 정확도를 만들지 않고 null + "실적 미수집" 사유를
     정직하게 반환하는 compute_accuracy().

즉 이번 세션은 "계약+수집 배선"까지다 — 실측 데이터 없이 MAPE 숫자를 날조하지 않는다.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_NO_ACTUALS_REASON = "실적(실행내역) 데이터가 아직 수집되지 않음 — back-test 불가(예측-실적 매칭 0건)"

# ── DDL(cost_tables_bootstrap._ensure_cost_tables 와 동일한 멱등 런타임 부트스트랩 패턴) ──

_DDL_BACKTEST_PREDICTION = (
    "CREATE TABLE IF NOT EXISTS cost_backtest_prediction ("
    "  id bigserial PRIMARY KEY,"
    "  estimate_id text NOT NULL,"
    "  project_id text,"
    "  tenant_id text,"
    "  predicted_total_won numeric(20,2) NOT NULL,"
    "  predicted_breakdown jsonb DEFAULT '{}'::jsonb,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_DDL_BACKTEST_PREDICTION_UQ = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cost_backtest_prediction_estimate "
    "ON cost_backtest_prediction(estimate_id)"
)

_DDL_BACKTEST_ACTUAL = (
    "CREATE TABLE IF NOT EXISTS cost_backtest_actual ("
    "  id bigserial PRIMARY KEY,"
    "  estimate_id text NOT NULL,"
    "  actual_total_won numeric(20,2) NOT NULL,"
    "  actual_breakdown jsonb DEFAULT '{}'::jsonb,"
    "  source_note text,"
    "  recorded_by text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_DDL_BACKTEST_ACTUAL_UQ = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cost_backtest_actual_estimate "
    "ON cost_backtest_actual(estimate_id)"
)

_ALL_DDL = (
    _DDL_BACKTEST_PREDICTION, _DDL_BACKTEST_PREDICTION_UQ,
    _DDL_BACKTEST_ACTUAL, _DDL_BACKTEST_ACTUAL_UQ,
)

_ENSURED = False  # 프로세스 내 1회 보장(cost_tables_bootstrap._ENSURED 와 동일 관례)


async def _ensure_backtest_tables(db: Any) -> None:
    """back-test 테이블 멱등 생성(analysis_ledger_service._ensure 패턴). 기존 데이터 무영향."""
    global _ENSURED
    if _ENSURED:
        return
    from sqlalchemy import text

    for ddl in _ALL_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _ENSURED = True


async def record_estimate(
    *,
    estimate_id: str,
    predicted_total_won: float,
    project_id: str | None = None,
    tenant_id: str | None = None,
    predicted_breakdown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """견적(예측) 스냅샷을 기록한다. estimate_id 당 최신 1건(재기록 시 덮어씀 — 재산정 허용).

    실패해도 예외를 흡수하고 ok=False 로 정직 반환한다(호출부 graceful, 견적 결과 자체는
    무손상 — cost_estimate_repository.save_estimate 와 동일 관례).
    """
    import json

    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure_backtest_tables(db)
            await db.execute(text(
                "INSERT INTO cost_backtest_prediction"
                "(estimate_id, project_id, tenant_id, predicted_total_won, predicted_breakdown)"
                " VALUES (:eid, :pid, :tid, :ptw, CAST(:pb AS jsonb))"
                " ON CONFLICT (estimate_id) DO UPDATE SET"
                "   predicted_total_won = EXCLUDED.predicted_total_won,"
                "   predicted_breakdown = EXCLUDED.predicted_breakdown,"
                "   project_id = EXCLUDED.project_id, tenant_id = EXCLUDED.tenant_id,"
                "   created_at = now()"
            ), {
                "eid": estimate_id, "pid": project_id, "tid": tenant_id,
                "ptw": predicted_total_won,
                "pb": json.dumps(predicted_breakdown or {}, ensure_ascii=False, default=str),
            })
            await db.commit()
            return {"ok": True, "estimate_id": estimate_id}
    except Exception as e:  # noqa: BLE001
        logger.warning("back-test 예측 기록 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


async def record_actual(
    *,
    estimate_id: str,
    actual_total_won: float,
    actual_breakdown: dict[str, Any] | None = None,
    source_note: str | None = None,
    recorded_by: str | None = None,
) -> dict[str, Any]:
    """실적(실행내역) 금액을 기록한다. estimate_id 당 최신 1건(공정 진행에 따른 재기록 허용).

    ★정직성: 이 함수를 호출해 실적을 넣기 전까지 compute_accuracy()는 절대 숫자를
    만들어내지 않는다(무목업).
    """
    import json

    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure_backtest_tables(db)
            await db.execute(text(
                "INSERT INTO cost_backtest_actual"
                "(estimate_id, actual_total_won, actual_breakdown, source_note, recorded_by)"
                " VALUES (:eid, :atw, CAST(:ab AS jsonb), :note, :by)"
                " ON CONFLICT (estimate_id) DO UPDATE SET"
                "   actual_total_won = EXCLUDED.actual_total_won,"
                "   actual_breakdown = EXCLUDED.actual_breakdown,"
                "   source_note = EXCLUDED.source_note, recorded_by = EXCLUDED.recorded_by,"
                "   created_at = now()"
            ), {
                "eid": estimate_id, "atw": actual_total_won,
                "ab": json.dumps(actual_breakdown or {}, ensure_ascii=False, default=str),
                "note": source_note, "by": recorded_by,
            })
            await db.commit()
            return {"ok": True, "estimate_id": estimate_id}
    except Exception as e:  # noqa: BLE001
        logger.warning("back-test 실적 기록 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


# ── 순수 통계(DB 무의존 — 단위 테스트 대상) ──

def _ape(predicted: float, actual: float) -> float | None:
    """절대백분율오차(Absolute Percentage Error, %). actual=0 이면 정의 불가(None, 나눗셈 회피)."""
    if actual == 0:
        return None
    return abs(predicted - actual) / abs(actual) * 100.0


def _bias_pct(predicted: float, actual: float) -> float | None:
    """부호 있는 편향(%) — 양수=과대추정 경향, 음수=과소추정 경향."""
    if actual == 0:
        return None
    return (predicted - actual) / actual * 100.0


def _iqr_outliers(values: list[float]) -> tuple[float | None, float | None, list[int]]:
    """IQR(사분위범위) 기준 이상치 인덱스. n<4 면 사분위 계산이 불안정해 이상치 판정을 생략한다."""
    n = len(values)
    if n < 4:
        return None, None, []
    s = sorted(values)

    def _quantile(data: list[float], q: float) -> float:
        idx = q * (len(data) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
        frac = idx - lo
        return data[lo] + (data[hi] - data[lo]) * frac

    q1, q3 = _quantile(s, 0.25), _quantile(s, 0.75)
    iqr = q3 - q1
    lo_bound, hi_bound = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outlier_idx = [i for i, v in enumerate(values) if v < lo_bound or v > hi_bound]
    return q1, q3, outlier_idx


def compute_stats_from_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """예측-실적 쌍(pairs)에서 APE/MAPE/bias/outlier(IQR)를 계산한다(순수 함수·DB 무의존).

    pairs: [{"estimate_id", "predicted_total_won", "actual_total_won"}, ...]
    실적이 0건(pairs가 빈 리스트)이면 가짜 정확도 대신 None + 사유를 반환한다(무목업).
    """
    if not pairs:
        return {
            "n_pairs": 0, "mape": None, "bias_pct": None,
            "items": [], "outliers": [], "reason": _NO_ACTUALS_REASON,
        }

    items: list[dict[str, Any]] = []
    apes: list[float] = []
    biases: list[float] = []
    for p in pairs:
        predicted = float(p.get("predicted_total_won") or 0)
        actual = float(p.get("actual_total_won") or 0)
        ape = _ape(predicted, actual)
        bias = _bias_pct(predicted, actual)
        items.append({
            "estimate_id": p.get("estimate_id"),
            "predicted_total_won": predicted, "actual_total_won": actual,
            "ape_pct": round(ape, 2) if ape is not None else None,
            "bias_pct": round(bias, 2) if bias is not None else None,
        })
        if ape is not None:
            apes.append(ape)
        if bias is not None:
            biases.append(bias)

    mape = round(sum(apes) / len(apes), 2) if apes else None
    bias_pct = round(sum(biases) / len(biases), 2) if biases else None
    q1, q3, outlier_idx = _iqr_outliers(apes) if apes else (None, None, [])
    # outlier_idx는 apes(actual!=0인 항목만) 기준 인덱스이므로, items 중 ape_pct가 있는
    # 항목만 순서대로 대응시켜 estimate_id를 역참조한다(정직 — 인덱스 착오로 엉뚱한 항목을
    # 이상치로 지목하지 않기 위함).
    ape_bearing_ids = [it["estimate_id"] for it in items if it["ape_pct"] is not None]
    outlier_ids = [ape_bearing_ids[i] for i in outlier_idx]

    return {
        "n_pairs": len(pairs),
        "mape": mape,
        "bias_pct": bias_pct,
        "items": items,
        "outliers": outlier_ids,
        "outlier_bounds": {"ape_q1": q1, "ape_q3": q3} if q1 is not None else None,
        "reason": None,
        "note": (
            "MAPE=평균절대백분율오차(과대·과소 방향 무시) · bias_pct=부호있는 평균편향"
            "(양수=견적이 실적보다 과대추정 경향) · outlier=APE의 IQR(1.5×IQR) 기준 이상치"
            " estimate_id 목록(n<4 면 이상치 판정 생략)."
        ),
    }


async def compute_accuracy(
    *, project_id: str | None = None, tenant_id: str | None = None,
) -> dict[str, Any]:
    """예측(cost_backtest_prediction) ⋈ 실적(cost_backtest_actual)을 조인해 정확도를 계산한다.

    실적이 하나도 매칭되지 않으면(현재 플랫폼 상태) 가짜 숫자 없이 null + 사유를 반환한다.
    DB 조회 실패 시에도 동일하게 정직 실패(ok=False)로 반환한다(예외 흡수 — 호출부 무중단).
    """
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure_backtest_tables(db)
            clauses = []
            params: dict[str, Any] = {}
            if project_id:
                clauses.append("p.project_id = :pid")
                params["pid"] = project_id
            if tenant_id:
                clauses.append("p.tenant_id = :tid")
                params["tid"] = tenant_id
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = (await db.execute(text(
                "SELECT p.estimate_id, p.predicted_total_won, a.actual_total_won "
                "FROM cost_backtest_prediction p "
                "JOIN cost_backtest_actual a ON a.estimate_id = p.estimate_id "
                f"{where} ORDER BY p.created_at"
            ), params)).all()
            pairs = [
                {
                    "estimate_id": r[0],
                    "predicted_total_won": float(r[1] or 0),
                    "actual_total_won": float(r[2] or 0),
                }
                for r in rows
            ]
            return {"ok": True, **compute_stats_from_pairs(pairs)}
    except Exception as e:  # noqa: BLE001
        logger.warning("back-test 정확도 계산 실패", err=str(e)[:160])
        return {
            "ok": False, "n_pairs": 0, "mape": None, "bias_pct": None,
            "items": [], "outliers": [], "reason": f"조회 실패: {str(e)[:160]}",
        }
