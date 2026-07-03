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


def _format_recall_block(rag_memories: list[dict[str, Any]]) -> str:
    """회상된 과거 경험(MemoryHub)을 prior_context 뒤에 덧붙일 텍스트 블록으로 정규화.

    ★interpreter와 디커플: 회상 자체는 LLM 유무와 무관히 계산·표면화되고(run 반환·ingest provenance),
    이 블록은 LLM 해석기가 있을 때만 prompt에 주입된다(없으면 미사용 — 결정론 수치 불변식엔 무영향).
    포맷·score 안전화는 공용 헬퍼 단일경유(memory_hub.recall_format — expert_panel과 동일 계약)."""
    from app.services.memory_hub.recall_format import format_recall_block
    return format_recall_block(rag_memories, header="[Past Agent Memories (Know-how)]")


class SpecialistAgent:
    """단일 도메인 전문가 에이전트. 결정론 도구 → prior → (LLM+citation_gate) → 원장 cite."""

    def __init__(
        self, *, domain: str, task_type: str,
        tool: Callable[[dict[str, Any]], Any],
        interpreter: Any | None = None,
        recorder: Callable[..., Any] | None = None,
        prior_loader: Callable[..., Any] | None = None,
        panel: Callable[..., Any] | None = None,
        recaller: Callable[..., Any] | None = None,
        ingester: Callable[..., Any] | None = None,
    ) -> None:
        self.domain = domain
        self.task_type = task_type
        self._tool = tool
        self._interpreter = interpreter
        self._recorder = recorder
        self._prior_loader = prior_loader
        self._panel = panel
        # ★recaller/ingester 주입(recorder·prior_loader와 동일 DI 패턴) — 미주입 시 MemoryHub 기본.
        #   하드 import를 run()에서 떼어내 테스트·graceful·교체를 일원화(인프라 부재 시 기본이 import 실패→graceful).
        self._recaller = recaller
        self._ingester = ingester

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

        # 2.5) RAG Memory Recall (Memory Hub Brain) — best-effort. 회상은 interpreter 유무와 무관히
        #   계산되어 run() 반환·ingest provenance로 표면화된다(아래) — '계산 후 버림' 단절 차단(#2 디커플).
        rag_memories: list[dict[str, Any]] = []
        try:
            recaller = self._recaller
            if recaller is None:
                from app.services.memory_hub.memory_service import get_memory_hub
                recaller = get_memory_hub().recall_experience
            query_str = f"Domain: {self.domain}, Task: {self.task_type}, Data: {str(data)[:200]}"
            memories = await recaller(query=query_str, domain=self.domain, top_k=2)
            # MemoryRecallResponse → dict(소비처 단순화)
            rag_memories = [
                {"id": str(m.id), "summary": m.summary, "score": m.score, "source_type": m.source_type}
                for m in (memories or [])
            ]
        except Exception as e:  # noqa: BLE001 — 임베딩/Qdrant/인프라 부재는 graceful(분석 무중단)
            logger.warning("specialist memory recall 스킵(graceful)", domain=self.domain, err=str(e)[:160])

        # 3) LLM 해석(선택) + citation_gate grounded만 — 수치 비생성
        claims: list[dict[str, Any]] = []
        if self._interpreter is not None:
            try:
                from app.services.design_audit.blindspot_interpreter import citation_gate
                from app.services.ledger.prior_context import build_prior_block

                # prior + 회상 과거경험을 결합(회상 블록은 헬퍼로 정규화 — interpreter와 디커플)
                prior_block = build_prior_block(prior) + _format_recall_block(rag_memories)
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
        # ★원장 payload는 결정론 산출(수치·findings·claims)만 — 회상결과(rag_memories)는 의도적 제외.
        #   메모리 스토어 상태에 따라 변동(id·score) → content_hash 멱등성·모순탐지(detect_contradictions)
        #   오염 방지(결정론 불변식 보존). 회상은 advisory로 run() 반환·ingest provenance에만 표면화(6단계).
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

            ingester = self._ingester
            if ingester is None:
                from app.tasks.memory_tasks import ingest_experience_task
                ingester = ingest_experience_task.delay
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
                    "claims_count": len(claims),
                    # ★#2 디커플: 이번 실행이 회상한 과거 경험을 함께 기록(회상→저장 provenance 연결).
                    #   interpreter 유무와 무관히 저장돼, 회상이 '계산 후 버림'으로 단절되지 않게 한다.
                    "recalled_memory_ids": [rm.get("id") for rm in rag_memories],
                    "recalled_count": len(rag_memories),
                }
            }
            ingester(ingest_payload)
            logger.info("specialist memory auto-ingestion task triggered", domain=self.domain)
        except Exception as e:  # noqa: BLE001 — Celery/인프라 부재는 graceful(분석 무중단)
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
