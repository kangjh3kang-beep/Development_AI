"""INC-10 — 추출 오케스트레이터 산출 번들 + 단계 trace.

인라인 비전블록(0a 도면추출 / P-A.2 calc_target / 0b 이중경로)을 명시적 에이전트 파이프라인으로
실체화한 산출. 취합가(④)는 LLM이 아니라 결정론 합의(CrossSourceValidator) — 추출가만 LLM,
취합가는 결정론이라 동일 캐시입력(INC-8) → 동일 합의(INV-1). 단계별 타이밍·강등사유를 trace로
노출(관측성). 단계 skipped/강등은 trace + skipped로 표면화(무음0). 동일 입력 동일 산출(INV-1).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.bim import ExtractionResult


class ExtractionStage(BaseModel):
    """추출 파이프라인 단계 1건의 관측 기록(에이전트 협업 실체화 + 관측성).

    - stage: role_resolve | extract | aggregate | calc_target | dual_path | verify
    - status: OK | SKIPPED | CONFLICT | DEMOTED
    - elapsed_ms: 단계 소요(관측용). 비결정 — AnalysisResult.extraction_trace엔 미승계(INV-1 보존).
    - detail: 단계별 결정론 provenance(소스/요소수/합의분포/매칭수 등).
    """

    stage: str
    status: str = "OK"
    elapsed_ms: float = 0.0
    notes: list[str] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)


class ExtractionBundle(BaseModel):
    """orchestrate_extraction 산출 — 도면/calc_target/이중경로 + 단계 trace.

    skipped는 기존 인라인 블록과 byte 동일한 문자열·순서로 채워져 파이프라인 skipped에 합류한다(INV-1).
    """

    drawing_source: str | None = None       # VLLM_VISION | HINTS | none | None(도면 미입력)
    drawing_elements: list[dict] = Field(default_factory=list)  # to_pipeline_elements 형식(auto_elements)
    drawing_elements_n: int = 0
    calc_targets: list[dict] = Field(default_factory=list)
    calc_targets_source: str | None = None   # INPUT | DRAWING_AUTO | None
    extraction: ExtractionResult             # 이중경로 산출(source/bim/semantic_elements)
    skipped: list[str] = Field(default_factory=list)
    trace: list[ExtractionStage] = Field(default_factory=list)

    def deterministic_trace(self) -> list[dict]:
        """AnalysisResult 승계용 결정론 투영 — 비결정 elapsed_ms 제외(INV-1, 완전동치 보존)."""
        return [
            {"stage": s.stage, "status": s.status, "notes": s.notes, "detail": s.detail}
            for s in self.trace
        ]
