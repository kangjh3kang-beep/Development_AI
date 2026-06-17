"""Phase 1 성장루프 read SSOT — 원장 prior를 read하고 인터프리터 근거블록으로 포맷한다.

읽기·포맷 한 가지 책임. 결정론 판정/수치는 절대 만들지 않는다(비교·근거 표면화 전용).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def load_prior(
    *, analysis_type: str, tenant_id: str | None = None,
    pnu: str | None = None, address: str | None = None, project_id: str | None = None,
) -> dict[str, Any] | None:
    """동일 체인의 직전 분석을 best-effort로 회수. DB 부재/오류 시 None(분석 무중단)."""
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        return await ledger.get_latest(
            analysis_type=analysis_type, tenant_id=tenant_id,
            pnu=pnu, address=address, project_id=project_id,
        )
    except Exception as e:  # noqa: BLE001 — read 실패는 분석을 막지 않음(정직 degrade)
        logger.warning("prior_context read 실패 — prior 없이 진행", analysis_type=analysis_type, err=str(e)[:160])
        return None


def prior_numbers(prior: dict[str, Any] | None) -> list[float]:
    """citation_gate grounded corpus용 — prior payload의 수치를 평탄 추출."""
    out: list[float] = []
    if not prior:
        return out
    payload = prior.get("payload") or {}

    def _walk(obj: Any) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            out.append(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _walk(v)

    _walk(payload)
    return out


def build_prior_block(prior: dict[str, Any] | None) -> str:
    """prior payload → 인터프리터 프롬프트 말미에 붙일 근거블록(+모순명시 규칙).

    spec: prior_context 근거블록 + '이전결론 모순 시 명시'. 결정론 비교핵심(findings_brief/
    verdict/counts)만 표면화하고 LLM이 새 수치를 만들지 않도록 지시한다.
    """
    if not prior or not prior.get("payload"):
        return ""
    payload = prior["payload"]
    version = prior.get("version")
    atype = prior.get("analysis_type") or payload.get("kind") or "분석"
    created = prior.get("created_at") or ""
    lines: list[str] = [
        f"## 이전 분석 기록(원장 prior · {atype} v{version} · {created})",
        "아래는 같은 대상의 직전 분석 결과다. 이번 분석은 이 기록을 참고하되, "
        "**제공된 현재 데이터에서만 수치를 인용**하고 새 수치를 만들지 마라. "
        "**이번 결론이 이전 결론과 모순되면 그 사실과 사유를 명시**하라.",
    ]
    if payload.get("verdict") is not None:
        lines.append(f"- 이전 종합판정: {payload.get('verdict')} / counts: {payload.get('counts') or {}}")
    brief = payload.get("findings_brief") or []
    if brief:
        lines.append("- 이전 주요 항목(check_id·status·current/limit):")
        for f in brief[:12]:
            lines.append(
                f"  - {f.get('check_id')}: {f.get('status')} "
                f"(current={f.get('current')}, limit={f.get('limit')})"
            )
    # 재무/원가 요약(summary·total_revenue_10k 등)도 있으면 표면화
    for k in ("summary", "total_revenue_10k", "net_profit_won", "grade"):
        if k in payload:
            lines.append(f"- 이전 {k}: {payload.get(k)}")
    return "\n".join(lines)
