"""AI 비용 자동 기록 유틸리티.

모든 LLM 호출의 토큰 사용량과 추정 비용을 DB에 기록한다.
"""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.metrics import AI_COST_TOTAL, AI_TOKEN_TOTAL

logger = structlog.get_logger(__name__)

# 모델별 토큰 단가 (USD per 1K tokens, 2026-03 기준)
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
    "claude-opus-4-6": {"input": 0.015, "output": 0.075},
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
}


async def track_ai_usage(
    db: AsyncSession,
    tenant_id: UUID,
    service: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    project_id: UUID | None = None,
) -> None:
    """AI 사용량을 DB에 기록한다.

    Args:
        db: 데이터베이스 세션
        tenant_id: 테넌트 ID
        service: 호출 서비스명 (design_ai, tax_ai, regulation, etc.)
        model: 사용 모델명
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수
        project_id: 프로젝트 ID (선택)
    """
    # 비용 추정
    pricing = _MODEL_PRICING.get(model, {"input": 0.003, "output": 0.015})
    cost_usd = (
        input_tokens / 1000 * pricing["input"]
        + output_tokens / 1000 * pricing["output"]
    )

    # Prometheus 메트릭 기록
    AI_COST_TOTAL.labels(service=service, model=model).inc(cost_usd)
    AI_TOKEN_TOTAL.labels(service=service, model=model, direction="input").inc(input_tokens)
    AI_TOKEN_TOTAL.labels(service=service, model=model, direction="output").inc(output_tokens)

    try:
        await db.execute(
            text(
                "INSERT INTO ai_usage_log "
                "(id, tenant_id, project_id, service_name, model_name, "
                "input_tokens, output_tokens, cost_usd) "
                "VALUES (gen_random_uuid(), :tid, :pid, :svc, :model, "
                ":in_tok, :out_tok, :cost)"
            ),
            {
                "tid": str(tenant_id),
                "pid": str(project_id) if project_id else None,
                "svc": service,
                "model": model,
                "in_tok": input_tokens,
                "out_tok": output_tokens,
                "cost": round(cost_usd, 6),
            },
        )
        await db.commit()

        logger.debug(
            "AI 비용 기록",
            service=service,
            model=model,
            tokens=input_tokens + output_tokens,
            cost_usd=f"${cost_usd:.4f}",
        )
    except Exception:
        # 비용 기록 실패가 서비스 장애로 이어지지 않도록
        logger.debug("AI 비용 기록 실패 — 무시", service=service)
