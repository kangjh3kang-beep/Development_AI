"""자가성장 엔진 — 분석 규칙엔진(설계서 §5.1).

`analyze_window(db, window_start, window_end)` 가 platform_events / ai_feedback 를
스캔해 platform_insights 를 생성한다. **규칙 기반이 1차**, LLM narrative 는
선택적·비용가드(기본 off, 키 있고 critical 일 때만 1콜)다.

구현 규칙(DoD 3종 필수 + 보너스 1종):
- error_cluster : js_error/api_error 를 (정규화 스택해시·route·status) 로 group by,
                  top-N 빈발군. 동일 시그니처 ≥20건/시간 → warn, ≥100 → critical.
- fallback_rate : service별 fallback 이벤트 ÷ 총 llm_call. >15% → warn, >30% → critical.
- quality_drop  : service별 verify_result(fail/warn 비율) + ai_feedback(down 비율) 결합.
                  down>20% 또는 fail>15% → warn.
- latency_regression(보너스) : route/service p95 vs 직전 7일 baseline 1.5×.
                  baseline 은 platform_insights 에 저장해 다음 배치가 참조.

설계 §5.1 의 임계는 "초기값·자동보정 대상"이므로 상수로 한곳에 모은다.
판정·계산 로직은 stdlib 만으로 단위검증 가능하도록 순수 함수로 분리한다
(DB·LLM 의존 없는 _classify_*/_pXX 함수군).

결과는 platform_insights 에 INSERT(insight_type/window/metrics_json/severity/
narrative/recommended_action/status='open'). best-effort: 실패해도 배치는 죽지 않는다.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── 임계값(설계 §5.1 초기값, 향후 L1 자동보정 대상) ───────────────────────────
# error_cluster: 동일 시그니처 시간당 건수 임계.
ERR_WARN_COUNT = 20
ERR_CRIT_COUNT = 100
ERR_TOP_N = 20  # 인사이트로 승격하는 상위 빈발군 수.

# recurring_verify_error: 동일 (service, issue_type) 시간당 검출 건수 임계.
# verify_issue 는 분석당 1회로 저빈도라 error_cluster(js/api)보다 낮은 임계를 쓴다.
VERIFY_ERR_WARN_COUNT = 3
VERIFY_ERR_CRIT_COUNT = 8
VERIFY_ERR_TOP_N = 10

# fallback_rate: service별 폴백률(%) 임계.
FALLBACK_WARN_PCT = 15.0
FALLBACK_CRIT_PCT = 30.0
FALLBACK_MIN_CALLS = 10  # 분모(llm_call)가 너무 작으면 노이즈 → 판정 보류.

# quality_drop: verify fail 비율 / feedback down 비율 임계(%).
QUALITY_DOWN_PCT = 20.0
QUALITY_FAIL_PCT = 15.0
QUALITY_MIN_SAMPLES = 5  # 표본이 너무 작으면 판정 보류.

# latency_regression: 직전 baseline 대비 배수.
LATENCY_REGRESSION_FACTOR = 1.5
LATENCY_MIN_SAMPLES = 20
LATENCY_BASELINE_DAYS = 7

# LLM narrative 비용가드: critical 인사이트 1배치당 최대 콜 수.
_LLM_NARRATIVE_MAX_CALLS = 3

# 스택트레이스 정규화에서 제거할 변동요소(주소·숫자ID·hex 등).
_RE_HEX = re.compile(r"0x[0-9a-fA-F]+")
_RE_NUM = re.compile(r"\b\d+\b")
_RE_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_RE_WS = re.compile(r"\s+")


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수군 (DB/LLM 무의존 — inline 단위검증 대상)
# ════════════════════════════════════════════════════════════════════════════

def normalize_stack(raw: str | None, route: str | None, status: int | None) -> str:
    """스택트레이스/에러메시지를 변동요소 제거 후 시그니처 해시로 정규화한다.

    같은 결함이 호출마다 다른 주소·라인숫자·UUID 를 갖더라도 동일 시그니처로
    묶이도록, hex/숫자/UUID 를 placeholder 로 치환한 뒤 route·status 와 함께
    sha1 12자리 해시를 만든다.
    """
    base = raw or ""
    base = _RE_UUID.sub("<uuid>", base)
    base = _RE_HEX.sub("<hex>", base)
    base = _RE_NUM.sub("<n>", base)
    base = _RE_WS.sub(" ", base).strip().lower()
    # 메시지가 비면 route+status 만으로 군집(엔드포인트 단위 오류).
    key = f"{base}|{route or ''}|{status if status is not None else ''}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _classify_error_count(count: int) -> str | None:
    """동일 시그니처 시간당 건수 → severity. 임계 미만이면 None."""
    if count >= ERR_CRIT_COUNT:
        return "critical"
    if count >= ERR_WARN_COUNT:
        return "warn"
    return None


def _classify_verify_recurrence(count: int) -> str | None:
    """동일 (service, issue_type) 시간당 검출 건수 → severity. 임계 미만이면 None."""
    if count >= VERIFY_ERR_CRIT_COUNT:
        return "critical"
    if count >= VERIFY_ERR_WARN_COUNT:
        return "warn"
    return None


def _cluster_verify_issues(
    rows: list[tuple[Any, dict[str, Any], Any]], hours: float
) -> list[dict[str, Any]]:
    """verify_issue 이벤트[(service, payload, created_at)] → 재발오류 인사이트 목록(순수·무DB).

    payload.issue_types(리스트)를 평탄화해 (service, issue_type)별로 군집·집계한다.
    severity는 총 검출빈도(per_hour) 기준으로 산정하며, high_count(severities[idx]가
    high/critical인 건수)는 metrics·narrative 표기용(심각도 가시화)이다. 임계 미만은 제외.
    """
    clusters: dict[tuple[str, str], dict[str, Any]] = {}
    for service, payload, _created in rows:
        types = (payload or {}).get("issue_types") or []
        sevs = (payload or {}).get("severities") or []
        if not isinstance(types, list):
            continue
        for idx, t in enumerate(types):
            key = (str(service or "?"), str(t))
            c = clusters.setdefault(key, {
                "service": key[0], "issue_type": key[1], "count": 0, "high": 0,
            })
            c["count"] += 1
            sev_i = sevs[idx] if isinstance(sevs, list) and idx < len(sevs) else None
            if sev_i in ("high", "critical"):
                c["high"] += 1

    out: list[dict[str, Any]] = []
    ranked = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)[:VERIFY_ERR_TOP_N]
    for c in ranked:
        per_hour = c["count"] / hours
        sev = _classify_verify_recurrence(int(round(per_hour)))
        if sev is None:
            continue
        out.append({
            "insight_type": "recurring_verify_error",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "propose_pr" if sev == "critical" else "none",
            "metrics_json": {
                "service": c["service"], "issue_type": c["issue_type"],
                "count": c["count"], "per_hour": round(per_hour, 2),
                "high_count": c["high"],
            },
        })
    return out


def _classify_fallback(fallback: int, total_calls: int) -> tuple[str | None, float]:
    """폴백률(%) 산출 + severity. 분모 부족 시 (None, pct)."""
    if total_calls < FALLBACK_MIN_CALLS:
        return None, 0.0
    pct = round(100.0 * fallback / total_calls, 2)
    if pct > FALLBACK_CRIT_PCT:
        return "critical", pct
    if pct > FALLBACK_WARN_PCT:
        return "warn", pct
    return None, pct


def _classify_quality(
    fail: int, warn: int, verify_total: int, down: int, feedback_total: int
) -> tuple[str | None, dict[str, float]]:
    """verify fail 비율 + feedback down 비율 결합 → severity.

    down>20% 또는 fail>15% → warn. 표본 부족(둘 다 MIN 미만)이면 None.
    반환 metrics 에 fail_pct/warn_pct/down_pct 를 담는다.
    """
    fail_pct = round(100.0 * fail / verify_total, 2) if verify_total else 0.0
    warn_pct = round(100.0 * warn / verify_total, 2) if verify_total else 0.0
    down_pct = round(100.0 * down / feedback_total, 2) if feedback_total else 0.0
    metrics = {"fail_pct": fail_pct, "warn_pct": warn_pct, "down_pct": down_pct}

    enough_verify = verify_total >= QUALITY_MIN_SAMPLES
    enough_feedback = feedback_total >= QUALITY_MIN_SAMPLES
    if not enough_verify and not enough_feedback:
        return None, metrics

    severity: str | None = None
    if (enough_feedback and down_pct > QUALITY_DOWN_PCT) or (
        enough_verify and fail_pct > QUALITY_FAIL_PCT
    ):
        severity = "warn"
    return severity, metrics


def _percentile(values: list[float], pct: float) -> float:
    """단순 백분위(보간 없는 nearest-rank). p95 등 baseline 산출용."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[rank]


def _classify_latency(p95: float, baseline_p95: float) -> str | None:
    """현재 p95 가 baseline 의 1.5배 초과면 warn. baseline 없으면 None(첫 배치)."""
    if baseline_p95 <= 0:
        return None
    if p95 > baseline_p95 * LATENCY_REGRESSION_FACTOR:
        return "warn"
    return None


def _severity_rank(sev: str | None) -> int:
    """정렬용 severity 가중치(critical 최상위)."""
    return {"critical": 3, "warn": 2, "info": 1}.get(sev or "", 0)


# ════════════════════════════════════════════════════════════════════════════
# DB 스캔 + 인사이트 생성
# ════════════════════════════════════════════════════════════════════════════

async def analyze_window(
    db, window_start: datetime, window_end: datetime, *, use_llm: bool | None = None
) -> list[dict[str, Any]]:
    """윈도우 내 platform_events/ai_feedback 를 스캔해 인사이트를 생성·INSERT.

    반환: 생성한 인사이트 dict 목록(테스트·로깅용). best-effort.
    """
    from sqlalchemy import text

    insights: list[dict[str, Any]] = []
    try:
        insights.extend(await _analyze_error_cluster(db, window_start, window_end))
        insights.extend(await _analyze_recurring_verify_errors(db, window_start, window_end))
        insights.extend(await _analyze_fallback_rate(db, window_start, window_end))
        insights.extend(await _analyze_quality_drop(db, window_start, window_end))
        insights.extend(await _analyze_latency_regression(db, window_start, window_end))
    except Exception as e:  # noqa: BLE001 — 스캔 실패는 배치를 죽이지 않는다.
        logger.warning("growth analyze 스캔 실패: %s", str(e)[:160])
        return insights

    # narrative: 규칙 기반이 기본. critical 인사이트에 한해 비용가드 LLM 1콜.
    do_llm = _llm_enabled() if use_llm is None else use_llm
    llm_budget = _LLM_NARRATIVE_MAX_CALLS if do_llm else 0
    for ins in insights:
        narrative = _rule_narrative(ins)
        if llm_budget > 0 and ins.get("severity") == "critical":
            llm_narr = _llm_narrative(ins)
            if llm_narr:
                narrative = llm_narr
                llm_budget -= 1
        ins["narrative"] = narrative

    # INSERT(개별 best-effort — 한 건 실패가 전체를 막지 않게 커밋은 마지막 일괄).
    inserted = 0
    insert_sql = text(
        "INSERT INTO platform_insights "
        "(tenant_id, insight_type, window_start, window_end, metrics_json, "
        " severity, narrative, recommended_action, status) "
        "VALUES (:tenant_id, :insight_type, :window_start, :window_end, "
        " CAST(:metrics_json AS jsonb), :severity, :narrative, "
        " :recommended_action, 'open')"
    )
    try:
        for ins in insights:
            await db.execute(insert_sql, {
                "tenant_id": ins.get("tenant_id"),
                "insight_type": ins["insight_type"],
                "window_start": window_start,
                "window_end": window_end,
                "metrics_json": json.dumps(
                    ins.get("metrics_json") or {}, ensure_ascii=False, default=str
                ),
                "severity": ins.get("severity"),
                "narrative": ins.get("narrative"),
                "recommended_action": ins.get("recommended_action") or "none",
            })
            inserted += 1
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("growth insight INSERT 실패(%d/%d): %s",
                       inserted, len(insights), str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()

    if insights:
        logger.info("growth analyze: 인사이트 %d건 생성(INSERT %d)", len(insights), inserted)
    return insights


async def _analyze_error_cluster(db, w0, w1) -> list[dict[str, Any]]:
    """js_error/api_error 를 정규화 시그니처로 군집해 빈발 top-N 을 인사이트화."""
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT route, status_code, severity, payload, created_at "
        "FROM platform_events "
        "WHERE event_type IN ('js_error','api_error') "
        "  AND created_at >= :w0 AND created_at < :w1"
    ), {"w0": w0, "w1": w1})).fetchall()

    # 시간 정규화 계수: 윈도우가 1시간이 아니면 "시간당 건수"로 환산해 임계 비교.
    hours = max((w1 - w0).total_seconds() / 3600.0, 1e-9)

    clusters: dict[str, dict[str, Any]] = {}
    for r in rows:
        payload = _as_dict(r[3])
        raw = (payload.get("message") or payload.get("stack")
               or payload.get("error") or "")
        sig = normalize_stack(str(raw), r[0], r[1])
        c = clusters.setdefault(sig, {
            "signature": sig, "route": r[0], "status": r[1],
            "count": 0, "sample": str(raw)[:300],
        })
        c["count"] += 1

    out: list[dict[str, Any]] = []
    ranked = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)[:ERR_TOP_N]
    for c in ranked:
        per_hour = c["count"] / hours
        sev = _classify_error_count(int(round(per_hour)))
        if sev is None:
            continue
        out.append({
            "insight_type": "error_cluster",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "propose_pr" if sev == "critical" else "none",
            "metrics_json": {
                "signature": c["signature"], "route": c["route"],
                "status_code": c["status"], "count": c["count"],
                "per_hour": round(per_hour, 2), "sample": c["sample"],
            },
        })
    return out


async def _analyze_recurring_verify_errors(db, w0, w1) -> list[dict[str, Any]]:
    """verify_issue 를 (service, issue_type) 로 군집해 반복 검출 오류를 인사이트화.

    verifier 가 자동 검출한 오류 '유형'이 특정 분석에서 반복되면 재발오류로 승격(개선 대상).
    capture(_emit_growth_issues)가 적재한 verify_issue 를 소비하는 폐루프의 분석 단계.
    """
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT service, payload, created_at FROM platform_events "
        "WHERE event_type='verify_issue' AND created_at >= :w0 AND created_at < :w1"
    ), {"w0": w0, "w1": w1})).fetchall()
    hours = max((w1 - w0).total_seconds() / 3600.0, 1e-9)
    parsed = [(r[0], _as_dict(r[1]), r[2]) for r in rows]
    return _cluster_verify_issues(parsed, hours)


async def _analyze_fallback_rate(db, w0, w1) -> list[dict[str, Any]]:
    """service별 폴백률 인사이트.

    분자(fallback): base_interpreter 는 LLM 호출 실패 시 별도 'fallback' 이벤트를
    발행하지 않고 event_type='llm_call' + payload.ok=false 로 기록한다(설계 정합).
    따라서 폴백 건수 = (event_type='fallback' 이벤트) + (llm_call 중 payload->>'ok'='false').
    분모(llm_call): service별 총 llm_call 수(성공/실패 모두 포함).
    """
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT service, "
        "  SUM(CASE WHEN event_type='fallback' THEN 1 "
        "           WHEN event_type='llm_call' AND payload->>'ok'='false' THEN 1 "
        "           ELSE 0 END) AS fb, "
        "  SUM(CASE WHEN event_type='llm_call' THEN 1 ELSE 0 END) AS calls "
        "FROM platform_events "
        "WHERE event_type IN ('fallback','llm_call') "
        "  AND created_at >= :w0 AND created_at < :w1 "
        "  AND service IS NOT NULL "
        "GROUP BY service"
    ), {"w0": w0, "w1": w1})).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        service, fb, calls = r[0], int(r[1] or 0), int(r[2] or 0)
        sev, pct = _classify_fallback(fb, calls)
        if sev is None:
            continue
        out.append({
            "insight_type": "fallback_rate",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "heal",
            "metrics_json": {
                "service": service, "fallback": fb,
                "llm_call": calls, "fallback_pct": pct,
            },
        })
    return out


async def _analyze_quality_drop(db, w0, w1) -> list[dict[str, Any]]:
    """service별 verify_result(fail/warn) + ai_feedback(down) 결합 품질저하 인사이트."""
    from sqlalchemy import text

    # verify_result: severity 또는 payload.verdict 에 fail/warn 기록(수집측 정합).
    verify_rows = (await db.execute(text(
        "SELECT service, severity, payload FROM platform_events "
        "WHERE event_type='verify_result' "
        "  AND created_at >= :w0 AND created_at < :w1 AND service IS NOT NULL"
    ), {"w0": w0, "w1": w1})).fetchall()

    fb_rows = (await db.execute(text(
        "SELECT service, "
        "  SUM(CASE WHEN verdict='down' THEN 1 ELSE 0 END) AS down, "
        "  COUNT(*) AS total "
        "FROM ai_feedback "
        "WHERE created_at >= :w0 AND created_at < :w1 AND service IS NOT NULL "
        "GROUP BY service"
    ), {"w0": w0, "w1": w1})).fetchall()

    agg: dict[str, dict[str, int]] = {}
    for r in verify_rows:
        service = r[0]
        verdict = (r[1] or _as_dict(r[2]).get("verdict") or "").lower()
        a = agg.setdefault(service, {"fail": 0, "warn": 0, "vtotal": 0, "down": 0, "ftotal": 0})
        a["vtotal"] += 1
        if verdict == "fail":
            a["fail"] += 1
        elif verdict == "warn":
            a["warn"] += 1
    for r in fb_rows:
        service = r[0]
        a = agg.setdefault(service, {"fail": 0, "warn": 0, "vtotal": 0, "down": 0, "ftotal": 0})
        a["down"] += int(r[1] or 0)
        a["ftotal"] += int(r[2] or 0)

    out: list[dict[str, Any]] = []
    for service, a in agg.items():
        sev, metrics = _classify_quality(
            a["fail"], a["warn"], a["vtotal"], a["down"], a["ftotal"]
        )
        if sev is None:
            continue
        out.append({
            "insight_type": "quality_drop",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "correct",
            "metrics_json": {
                "service": service,
                "verify_total": a["vtotal"], "fail": a["fail"], "warn": a["warn"],
                "feedback_total": a["ftotal"], "down": a["down"], **metrics,
            },
        })
    return out


async def _analyze_latency_regression(db, w0, w1) -> list[dict[str, Any]]:
    """route/service p95 vs 직전 7일 baseline. baseline 은 insights 에 저장·참조."""
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT COALESCE(route, service) AS k, latency_ms FROM platform_events "
        "WHERE event_type IN ('api_call','llm_call') "
        "  AND latency_ms IS NOT NULL "
        "  AND created_at >= :w0 AND created_at < :w1 "
        "  AND COALESCE(route, service) IS NOT NULL"
    ), {"w0": w0, "w1": w1})).fetchall()

    by_key: dict[str, list[float]] = {}
    for r in rows:
        by_key.setdefault(r[0], []).append(float(r[1]))

    # 직전 baseline(latest latency_regression insight per key) 조회.
    base_rows = (await db.execute(text(
        "SELECT DISTINCT ON (metrics_json->>'key') "
        "  metrics_json->>'key' AS k, "
        "  (metrics_json->>'baseline_p95')::float AS bp95 "
        "FROM platform_insights "
        "WHERE insight_type='latency_regression' "
        "  AND created_at >= :since "
        "ORDER BY metrics_json->>'key', created_at DESC"
    ), {"since": w1 - timedelta(days=LATENCY_BASELINE_DAYS)})).fetchall()
    baselines = {r[0]: float(r[1] or 0.0) for r in base_rows}

    out: list[dict[str, Any]] = []
    for key, vals in by_key.items():
        if len(vals) < LATENCY_MIN_SAMPLES:
            continue
        p95 = round(_percentile(vals, 95.0), 2)
        baseline_p95 = baselines.get(key, 0.0)
        sev = _classify_latency(p95, baseline_p95)
        # baseline 없으면(첫 관측) 정보성 baseline 적재만(트리거 없음).
        out.append({
            "insight_type": "latency_regression",
            "severity": sev or "info",
            "tenant_id": None,
            "recommended_action": "heal" if sev else "none",
            "metrics_json": {
                "key": key, "p95_ms": p95, "samples": len(vals),
                # 다음 배치가 baseline 으로 참조(자가보정 기반): 이번 p95 를 저장.
                "baseline_p95": p95,
                "prev_baseline_p95": baseline_p95,
            },
        })
    return out


# ════════════════════════════════════════════════════════════════════════════
# narrative (규칙 기본 + 선택적 LLM)
# ════════════════════════════════════════════════════════════════════════════

def _rule_narrative(ins: dict[str, Any]) -> str:
    """규칙 기반 narrative(LLM 없이도 항상 채워지는 한국어 요약)."""
    m = ins.get("metrics_json") or {}
    t = ins["insight_type"]
    sev = ins.get("severity")
    if t == "error_cluster":
        return (f"[{sev}] 오류 군집 {m.get('signature')} — route={m.get('route')} "
                f"status={m.get('status_code')} 시간당 {m.get('per_hour')}건"
                f"(총 {m.get('count')}건).")
    if t == "recurring_verify_error":
        return (f"[{sev}] {m.get('service')} 재발 검증오류 '{m.get('issue_type')}' — "
                f"시간당 {m.get('per_hour')}건(총 {m.get('count')}건, 심각 {m.get('high_count')}건). "
                f"반복 검출 오류 — 원인 점검·개선 권장.")
    if t == "fallback_rate":
        return (f"[{sev}] {m.get('service')} 폴백률 {m.get('fallback_pct')}% "
                f"(폴백 {m.get('fallback')}/{m.get('llm_call')}콜).")
    if t == "quality_drop":
        return (f"[{sev}] {m.get('service')} 품질저하 — verify fail "
                f"{m.get('fail_pct')}%/warn {m.get('warn_pct')}%, "
                f"feedback down {m.get('down_pct')}%.")
    if t == "latency_regression":
        return (f"[{sev}] {m.get('key')} p95 {m.get('p95_ms')}ms "
                f"(이전 baseline {m.get('prev_baseline_p95')}ms, 표본 {m.get('samples')}).")
    return f"[{sev}] {t}"


def _llm_enabled() -> bool:
    """LLM narrative 활성 여부. 기본 off. GROWTH_LLM_NARRATIVE=1 + 키 존재 시만."""
    if os.getenv("GROWTH_LLM_NARRATIVE", "0").strip() not in ("1", "true", "True"):
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _llm_narrative(ins: dict[str, Any]) -> str | None:
    """critical 인사이트 1건을 LLM 1콜로 요약(base_interpreter LLM 경로 재사용).

    실패/미설치/타임아웃은 None 반환 → 호출처가 규칙 narrative 로 폴백.
    """
    try:
        from app.services.ai.llm_provider import get_llm

        llm = get_llm(timeout=20, max_tokens=200)
        prompt = (
            "다음 플랫폼 운영 인사이트를 한국어 2문장으로 요약하고 권고조치를 덧붙여라. "
            "과장 금지, 지표 근거만.\n"
            + json.dumps(ins.get("metrics_json") or {}, ensure_ascii=False, default=str)
        )
        resp = llm.invoke(prompt)
        # 계측: 동기 호출도 토큰·과금 기록(실행 루프 있으면 예약, 없으면 생략·best-effort)
        from app.services.ai.base_interpreter import record_llm_response_billing_sync
        record_llm_response_billing_sync(llm, resp, service="growth_analyze")
        text_out = getattr(resp, "content", None) or str(resp)
        return str(text_out).strip()[:1000] or None
    except Exception as e:  # noqa: BLE001
        logger.debug("growth LLM narrative 폴백: %s", str(e)[:120])
        return None


def _as_dict(v: Any) -> dict[str, Any]:
    """payload(JSONB → dict 또는 문자열)를 안전하게 dict 로."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def default_window(hours: int = 1) -> tuple[datetime, datetime]:
    """기본 분석 윈도우(now-기준 직전 N시간). 태스크 진입점 편의."""
    now = datetime.now(UTC)
    return now - timedelta(hours=hours), now


__all__ = [
    "analyze_window",
    "normalize_stack",
    "default_window",
    # 순수 판정 함수(단위검증용 공개).
    "_classify_error_count",
    "_classify_fallback",
    "_classify_quality",
    "_classify_latency",
    "_percentile",
]
