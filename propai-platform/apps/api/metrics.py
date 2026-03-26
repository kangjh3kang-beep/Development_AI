"""중앙화 Prometheus 메트릭 레지스트리.

AI 비용, 에이전트, 비즈니스, DB 풀 메트릭을 정의한다.
"""

from prometheus_client import Counter, Gauge, Histogram

# ──────────────────────────────────────
# AI 비용 메트릭
# ──────────────────────────────────────

AI_COST_TOTAL = Counter(
    "propai_ai_cost_usd_total",
    "누적 AI 비용 (USD)",
    ["service", "model"],
)

AI_TOKEN_TOTAL = Counter(
    "propai_ai_tokens_total",
    "누적 AI 토큰 수",
    ["service", "model", "direction"],
)

# ──────────────────────────────────────
# 에이전트 메트릭
# ──────────────────────────────────────

AGENT_STEP_DURATION = Histogram(
    "propai_agent_step_duration_seconds",
    "에이전트 단계별 실행 시간",
    ["step_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

AGENT_COMPLETION = Counter(
    "propai_agent_completions_total",
    "에이전트 완주 수",
    ["status"],
)

# ──────────────────────────────────────
# 비즈니스 메트릭
# ──────────────────────────────────────

PROJECT_CREATED = Counter(
    "propai_projects_created_total",
    "생성된 프로젝트 수",
)

AVM_ESTIMATES = Counter(
    "propai_avm_estimates_total",
    "AVM 추정 수",
)

WEBHOOK_DELIVERIES = Counter(
    "propai_webhook_deliveries_total",
    "웹훅 전송 수",
    ["status"],
)

# ──────────────────────────────────────
# DB 상태 메트릭
# ──────────────────────────────────────

DB_POOL_SIZE = Gauge(
    "propai_db_pool_size",
    "DB 연결 풀 크기",
)

DB_POOL_CHECKED_OUT = Gauge(
    "propai_db_pool_checked_out",
    "DB 연결 풀 사용 중",
)
