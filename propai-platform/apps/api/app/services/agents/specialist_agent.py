"""Phase 3 계층3 — SpecialistAgent: 결정론 도구 호출 + citation_gate grounded 발언 + 원장 cite(W4 닫기).

결정론 우선: 수치는 계층1 도구에서만 생성(불변). LLM은 해석·서술만(citation_gate가 미근거 수치/법조문을
'전문가 확인 필요'로 치환). 원장 cite는 Phase 2 모순+lineage(record_specialist_result). 도구/인터프리터/
recorder/prior_loader는 주입(테스트·LLM부재 graceful).
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

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
        panel: Callable[..., Any] | None = None,
    ) -> None:
        self.domain = domain
        self.task_type = task_type
        self._tool = tool
        self._interpreter = interpreter
        self._recorder = recorder
        self._prior_loader = prior_loader
        self._panel = panel

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

        # 2.5) RAG Memory Recall (Memory Hub Brain) — best-effort
        rag_memories = []
        try:
            from app.services.memory_hub.memory_service import MemoryHubService
            query_str = f"Domain: {self.domain}, Task: {self.task_type}, Data: {str(data)[:200]}"
            memories = await MemoryHubService().recall_experience(query=query_str, domain=self.domain, top_k=2)
            # Schema response to dict
            rag_memories = [
                {"id": str(m.id), "summary": m.summary, "score": m.score, "source_type": m.source_type}
                for m in memories
            ]
        except Exception as e:
            logger.warning("specialist memory recall 스킵(graceful)", domain=self.domain, err=str(e)[:160])

        # 3) LLM 해석(선택) + citation_gate grounded만 — 수치 비생성
        claims: list[dict[str, Any]] = []
        if self._interpreter is not None:
            try:
                from app.services.design_audit.blindspot_interpreter import citation_gate
                from app.services.ledger.prior_context import build_prior_block

                # Combine prior with RAG memories
                prior_block = build_prior_block(prior)
                if rag_memories:
                    prior_block += "\n\n[Past Agent Memories (Know-how)]\n"
                    for rm in rag_memories:
                        prior_block += f"- {rm['summary']} (Score: {rm['score']:.2f})\n"

                raw = await self._interpreter.generate_interpretation(
                    tool_out, prior_context=prior_block)
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

        # 5) 다관점 패널(선택) — 결정론 findings/원장과 별개(LLM 판단), graceful
        panel_out = None
        if self._panel is not None:
            try:
                panel_out = await self._panel(
                    self.domain, {"findings": findings, "summary": tool_out.get("summary") or {}})
            except Exception as e:  # noqa: BLE001
                logger.warning("specialist panel 스킵(graceful)", domain=self.domain, err=str(e)[:160])
                panel_out = None

        # 6) 자동 기억화 (Automatic Memory Ingestion) — best-effort
        try:
            import uuid
            # Extract consensus or summaries to save as memory
            summary_info = tool_out.get("summary") or {}
            findings_info = findings or []

            # Construct a clear, informative memory block
            memory_summary = f"Domain Agent ({self.domain}) 실행 결과 요약:\n"
            memory_summary += f"- 작업 타입: {self.task_type}\n"
            if summary_info:
                memory_summary += f"- 주요 수치 및 요약: {summary_info}\n"
            if findings_info:
                memory_summary += f"- 검출된 항목 수: {len(findings_info)}개\n"
            if panel_out:
                memory_summary += f"- 패널 종합 판정: {panel_out}\n"

            from app.tasks.memory_tasks import ingest_experience_task
            ingest_payload = {
                "project_id": project_id,
                "session_id": f"auto_session_{self.domain}_{uuid.uuid4().hex[:8]}",
                "domain": self.domain,
                "source_type": "agent_execution",
                "summary": memory_summary.strip(),
                "metadata": {
                    "pnu": pnu,
                    "address": address,
                    "findings_count": len(findings_info),
                    "claims_count": len(claims)
                }
            }
            ingest_experience_task.delay(ingest_payload)
            logger.info("specialist memory auto-ingestion task triggered", domain=self.domain)
        except Exception as e:
            logger.warning("specialist memory auto-ingestion 스킵(graceful)", domain=self.domain, err=str(e)[:160])

        return {
            "domain": self.domain, "task_type": self.task_type,
            "findings": findings, "claims": claims,
            "summary": tool_out.get("summary") or {},
            "contradictions": wb.get("contradictions"),
            "ledger": {"ok": wb.get("ok"), "version": wb.get("version"),
                       "content_hash": wb.get("content_hash")},
            "panel": panel_out,
            "rag_memories": rag_memories,
        }
