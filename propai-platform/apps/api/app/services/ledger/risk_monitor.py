"""Phase 4 — 능동 위험감지(risk_monitor): 원장을 스캔해 위험 이벤트를 결정론으로 탐지.

Phase 2(contradiction/lineage)·P5(staleness)를 소비. 고심각 모순·판정 fail·staleness를 위험
이벤트로 표면화한다. 원장·수치 불변(read·표면화 전용), LLM 비개입.

실시간 이벤트: evaluate_chain_risk를 append 훅으로 호출하면 이벤트 구동(이 slice는 on-demand/scan
API; 이벤트 버스·push 채널은 후속 Phase 4.2).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_LEVEL_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_FAIL_VERDICTS = {"부적합", "fail", "위반", "escalate"}
_FAIL_STATUSES = {"fail", "부적합", "위반"}


def _is_fail_verdict(v: Any) -> bool:
    return isinstance(v, str) and v.strip().lower() in {x.lower() for x in _FAIL_VERDICTS}


def _has_fail_finding(latest: dict[str, Any]) -> bool:
    fb = (latest or {}).get("findings_brief")
    if isinstance(fb, list):
        for f in fb:
            if isinstance(f, dict) and str(f.get("status") or "").strip().lower() in _FAIL_STATUSES:
                return True
    return False


def classify_risks(*, latest: dict[str, Any] | None, contradictions: dict[str, Any] | None,
                   age_days: float | None, max_age_days: int = 90) -> list[dict[str, Any]]:
    """순수 결정론: latest payload + 모순 + age → 위험 이벤트 목록."""
    latest = latest or {}
    contradictions = contradictions or {}
    risks: list[dict[str, Any]] = []
    if contradictions.get("max_severity") == "high":
        n = (contradictions.get("counts") or {}).get("high", 0)
        risks.append({"type": "contradiction_high", "severity": "high",
                      "detail": f"직전 대비 고심각 모순 {n}건", "recommend": "재검토/재분석"})
    if _is_fail_verdict(latest.get("verdict")) or _has_fail_finding(latest):
        risks.append({"type": "status_fail", "severity": "high",
                      "detail": f"판정 위험: verdict={latest.get('verdict')}", "recommend": "검토 필요"})
    if age_days is not None and age_days > max_age_days:
        risks.append({"type": "stale", "severity": "medium",
                      "detail": f"{age_days:.0f}일 경과(>{max_age_days}일)", "recommend": "갱신 재분석"})
    return risks


def _risk_level(risks: list[dict[str, Any]]) -> str:
    level = "none"
    for r in risks:
        if _LEVEL_ORDER.get(r.get("severity"), 0) > _LEVEL_ORDER[level]:
            level = r["severity"]
    return level


async def evaluate_chain_risk(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None, max_age_days: int = 90,
) -> dict[str, Any]:
    """단일 체인 능동 위험평가 — get_latest + lineage 엣지(max_severity) + age → classify."""
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        from app.services.ledger import lineage
        from app.services.ledger.staleness import _age_days
        latest = await ledger.get_latest(analysis_type=analysis_type, tenant_id=tenant_id,
                                         pnu=pnu, address=address, project_id=project_id)
        if not latest:
            return {"analysis_type": analysis_type, "risks": [], "risk_level": "none", "reason": "no_data"}
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tenant_id)
        edge = parents[0] if parents else None
        ms = edge.get("max_severity") if edge else None
        contradictions = {"max_severity": ms,
                          "counts": {"high": int(edge.get("contradiction_count") or 0)} if ms == "high" else {}}
        age = await _age_days(analysis_type=analysis_type, tenant_id=tenant_id,
                              pnu=pnu, address=address, project_id=project_id)
        risks = classify_risks(latest=latest.get("payload") or {}, contradictions=contradictions,
                               age_days=age, max_age_days=max_age_days)
        return {"analysis_type": analysis_type, "version": latest.get("version"),
                "risks": risks, "risk_level": _risk_level(risks)}
    except Exception as e:  # noqa: BLE001
        logger.warning("risk 평가 실패(graceful)", analysis_type=analysis_type, err=str(e)[:160])
        return {"analysis_type": analysis_type, "risks": [], "risk_level": "none", "reason": "error"}


async def scan_project_risks(
    *, tenant_id: str | None = None, project_id: str | None = None, max_age_days: int = 90,
) -> dict[str, Any]:
    """프로젝트 전 체인 능동 스캔 — 위험 체인만 집계(능동 위험감지)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        from app.services.ledger.analysis_ledger_service import _ensure
        async with async_session_factory() as db:
            await _ensure(db)
            tsql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            psql = "project_id = :pid" if project_id else "project_id IS NULL"
            rows = (await db.execute(text(
                f"SELECT DISTINCT analysis_type, pnu, address_norm FROM analysis_ledger "
                f"WHERE {tsql} AND {psql}"), {"tid": tenant_id, "pid": project_id})).all()
        chains: list[dict[str, Any]] = []
        for atype, pnu, addr in rows:
            ev = await evaluate_chain_risk(analysis_type=atype, tenant_id=tenant_id,
                                           pnu=pnu, address=addr, project_id=project_id,
                                           max_age_days=max_age_days)
            if ev.get("risks"):
                chains.append(ev)
        level = "none"
        for c in chains:
            if _LEVEL_ORDER.get(c["risk_level"], 0) > _LEVEL_ORDER[level]:
                level = c["risk_level"]
        return {"project_id": project_id, "chains_at_risk": len(chains),
                "risk_level": level, "chains": chains}
    except Exception as e:  # noqa: BLE001
        logger.warning("risk 스캔 실패(graceful)", project_id=project_id, err=str(e)[:160])
        return {"project_id": project_id, "chains_at_risk": 0, "risk_level": "none", "reason": "error"}


# ── Phase 4.2: append 이벤트 훅 + 알림 채널(best-effort, 등록형) ──

import inspect  # noqa: E402

_NOTIFIERS: list = []


def register_notifier(fn) -> None:
    """알림 채널 등록(sync/async 콜러블 alert→None)."""
    if fn not in _NOTIFIERS:
        _NOTIFIERS.append(fn)


def clear_notifiers() -> None:
    _NOTIFIERS.clear()


def _min_alert_level() -> str:
    """알림 최소 발송 레벨(env RISK_ALERT_MIN_LEVEL, 기본 medium). 알 수 없는 값은 medium 폴백."""
    try:
        from app.core.config import settings
        v = str(getattr(settings, "RISK_ALERT_MIN_LEVEL", "medium") or "medium").strip().lower()
    except Exception:  # noqa: BLE001
        v = "medium"
    return v if v in _LEVEL_ORDER else "medium"


async def dispatch_risk_alert(*, project_id: Any, analysis_type: str, risk: dict[str, Any]) -> dict[str, Any]:
    """위험수준이 설정 최소레벨(RISK_ALERT_MIN_LEVEL, 기본 medium) 이상이면 등록 notifier로
    알림(best-effort). 그 미만은 미발송(정직)."""
    level = (risk or {}).get("risk_level", "none")
    min_level = _min_alert_level()
    if _LEVEL_ORDER.get(level, 0) < _LEVEL_ORDER[min_level]:
        return {"dispatched": 0, "level": level, "min_level": min_level, "skipped": True}
    alert = {"project_id": project_id, "analysis_type": analysis_type,
             "risk_level": level, "risks": (risk or {}).get("risks", [])}
    sent = 0
    for fn in list(_NOTIFIERS):
        try:
            r = fn(alert)
            if inspect.isawaitable(r):
                await r
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("risk 알림 채널 실패(graceful)", err=str(e)[:120])
    logger.warning("RISK_ALERT", project_id=str(project_id), analysis_type=analysis_type, level=level)
    return {"dispatched": sent, "level": level}


async def on_analysis_appended(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None,
) -> dict[str, Any]:
    """append 이벤트 훅 — 체인 위험평가 + 고위험 알림(이벤트 구동). best-effort."""
    risk = await evaluate_chain_risk(analysis_type=analysis_type, tenant_id=tenant_id,
                                     pnu=pnu, address=address, project_id=project_id)
    try:
        notify = await dispatch_risk_alert(project_id=project_id, analysis_type=analysis_type, risk=risk)
    except Exception as e:  # noqa: BLE001
        logger.warning("risk 알림 디스패치 실패(graceful)", err=str(e)[:120])
        notify = {"dispatched": 0, "error": True}
    return {**risk, "notify": notify}


_LEVEL_KO = {"high": "심각", "medium": "주의", "low": "낮음", "none": "없음"}
_ALERT_MAX_DETAILS = 5


def _format_alert_text(alert: dict[str, Any]) -> str:
    """알림 본문(한국어) — 순수 결정론 포맷. classify_risks의 detail/recommend(한국어)를 그대로 표면화."""
    alert = alert or {}
    level = str(alert.get("risk_level") or "none")
    level_ko = _LEVEL_KO.get(level, level)
    icon = "🚨" if level == "high" else "⚠️"
    risks = [r for r in (alert.get("risks") or []) if isinstance(r, dict)]
    lines = [f"{icon} 사통팔땅 위험알림 [{level_ko}]",
             f"분석: {alert.get('analysis_type')}",
             f"프로젝트: {alert.get('project_id')}",
             f"위험신호 {len(risks)}건"]
    for r in risks[:_ALERT_MAX_DETAILS]:
        detail = r.get("detail") or r.get("type") or "?"
        rec = r.get("recommend")
        lines.append(f"· {detail}" + (f" → {rec}" if rec else ""))
    if len(risks) > _ALERT_MAX_DETAILS:
        lines.append(f"· 외 {len(risks) - _ALERT_MAX_DETAILS}건")
    return "\n".join(lines)


async def _telegram_notifier(alert: dict[str, Any]) -> None:
    """텔레그램 webhook 알림(설정 시, 한국어 본문). 무설정 시 no-op(정직)."""
    try:
        from app.core.config import settings
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        chat = getattr(settings, "TELEGRAM_CHAT_ID", None)
    except Exception:  # noqa: BLE001
        return
    if not (token and chat):
        return
    import httpx
    async with httpx.AsyncClient(timeout=5) as c:
        await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                     json={"chat_id": chat, "text": _format_alert_text(alert)})


def _ws_notifier(alert: dict[str, Any]):
    """WebSocket 브로드캐스트(매니저 존재 시). 부재 시 no-op(정직). 반환은 awaitable일 수 있음."""
    try:
        from app.services.realtime.ws_manager import broadcast_risk_alert
    except Exception:  # noqa: BLE001
        return None
    return broadcast_risk_alert(alert)


def setup_default_notifiers() -> None:
    """앱 시작 시 호출 — telegram/ws 기본 채널 등록(둘 다 graceful·env-gated)."""
    register_notifier(_telegram_notifier)
    register_notifier(_ws_notifier)
