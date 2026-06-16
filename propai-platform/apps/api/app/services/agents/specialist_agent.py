"""Phase 3 계층3 — SpecialistAgent: 결정론 도구 호출 + citation_gate grounded 발언 + 원장 cite(W4 닫기).

결정론 우선: 수치는 계층1 도구에서만 생성(불변). LLM은 해석·서술만(citation_gate가 미근거 수치/법조문을
'전문가 확인 필요'로 치환). 원장 cite는 Phase 2 모순+lineage(record_specialist_result). 도구/인터프리터/
recorder/prior_loader는 주입(테스트·LLM부재 graceful).
"""
from __future__ import annotations

import inspect
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


def _to_items(raw: Any) -> list[dict[str, Any]]:
    """인터프리터 출력 → citation_gate 입력 items([{claim, basis, confidence}])로 정규화."""
    if isinstance(raw, dict):
        items = raw.get("items")
        if isinstance(items, list):
            return [it for it in items if isinstance(it, dict)]
    if isinstance(raw, list):
        return [it for it in raw if isinstance(it, dict)]
    return []


class SpecialistAgent:
    """단일 도메인 전문가 에이전트. 결정론 도구 → prior → (LLM+citation_gate) → 원장 cite."""

    def __init__(
        self, *, domain: str, task_type: str,
        tool: Callable[[dict[str, Any]], Any],
        interpreter: Any | None = None,
        recorder: Callable[..., Any] | None = None,
        prior_loader: Callable[..., Any] | None = None,
    ) -> None:
        self.domain = domain
        self.task_type = task_type
        self._tool = tool
        self._interpreter = interpreter
        self._recorder = recorder
        self._prior_loader = prior_loader

    @property
    def analysis_type(self) -> str:
        return f"domain_agent_{self.domain}"

    async def run(
        self, data: dict[str, Any], *, tenant_id: str | None = None,
        project_id: str | None = None, pnu: str | None = None,
        address: str | None = None, created_by: str | None = None,
    ) -> dict[str, Any]:
        # 1) 계층1 결정론 도구 — 수치는 여기서만 생성(불변)
        tool_out = self._tool(data)
        if inspect.isawaitable(tool_out):
            tool_out = await tool_out
        tool_out = tool_out if isinstance(tool_out, dict) else {}
        findings = tool_out.get("findings") or []

        # 2) prior read(Phase 1) — best-effort
        loader = self._prior_loader
        if loader is None:
            from app.services.ledger.prior_context import load_prior as loader
        prior = None
        try:
            prior = await loader(analysis_type=self.analysis_type, tenant_id=tenant_id,
                                 pnu=pnu, address=address, project_id=project_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("specialist prior read 실패(graceful)", domain=self.domain, err=str(e)[:160])
            prior = None

        # 3) LLM 해석(선택) + citation_gate grounded만 — 수치 비생성
        claims: list[dict[str, Any]] = []
        if self._interpreter is not None:
            try:
                from app.services.design_audit.blindspot_interpreter import citation_gate
                from app.services.ledger.prior_context import build_prior_block
                raw = await self._interpreter.generate_interpretation(
                    tool_out, prior_context=build_prior_block(prior))
                claims = citation_gate(_to_items(raw), findings, prior_evidence=prior)
            except Exception as e:  # noqa: BLE001
                logger.warning("specialist LLM 해석 스킵(graceful)", domain=self.domain, err=str(e)[:160])
                claims = []

        # 4) 원장 cite(Phase 2: prior 모순 + lineage)
        recorder = self._recorder
        if recorder is None:
            from app.services.ledger.ledger_adapters import record_specialist_result as recorder
        payload = {
            "kind": "domain_agent", "schema_version": "domain_agent/v2",
            "domain": self.domain, "task_type": self.task_type,
            "summary": tool_out.get("summary") or {},
            "findings_brief": findings,
            "claims": claims,
        }
        wb = await recorder(
            analysis_type=self.analysis_type, payload=payload,
            tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
            source=f"specialist_{self.domain}", created_by=created_by)
        wb = wb if isinstance(wb, dict) else {}
        return {
            "domain": self.domain, "task_type": self.task_type,
            "findings": findings, "claims": claims,
            "summary": tool_out.get("summary") or {},
            "contradictions": wb.get("contradictions"),
            "ledger": {"ok": wb.get("ok"), "version": wb.get("version"),
                       "content_hash": wb.get("content_hash")},
        }
