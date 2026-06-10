"""애플리케이션 설정 관리.

Pydantic Settings 기반 환경 변수 관리.
.env 파일 또는 시스템 환경 변수에서 값을 읽는다.
"""

from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """전역 설정. 환경 변수에서 자동 로딩."""

    model_config = SettingsConfigDict(
        env_file=".env" if __import__("os").path.exists(".env") else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 앱 기본 ──
    app_name: str = "PropAI"
    app_version: str = "62.0.0"
    debug: bool = False
    environment: str = Field(default="development", description="development | staging | production")

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: Any) -> bool:
        """배포 모드 문자열까지 포함해 DEBUG 값을 bool로 정규화한다.

        일부 로컬 셸/IDE 환경에서 ``DEBUG=release`` 같은 문자열이 주입된다.
        v30 테스트/런타임은 이를 bool로 해석하지 못해 설정 초기화 단계에서
        바로 실패하므로, 명시적으로 허용 가능한 별칭을 매핑한다.
        """
        if isinstance(value, bool):
            return value

        if value is None:
            return False

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            normalized = value.strip().lower()

            if normalized in {"1", "true", "yes", "y", "on", "debug", "dev", "development"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", "release", "prod", "production", "staging"}:
                return False

        raise ValueError("debug must be a boolean or boolean-like string")

    # ── 데이터베이스 ──
    database_url: str = "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db"
    timescale_url: str = Field(
        default="postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5445/propai_db",
        validation_alias=AliasChoices("timescale_url", "TIMESCALEDB_URL"),
    )
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    rate_limit_per_minute: int = 120  # SRE 대시보드 메트릭 참조(누락 시 AttributeError→500)
    grafana_embed_url: str = ""  # SRE 대시보드 임베드 URL(선택)
    db_use_pgbouncer: bool = Field(
        default=False,
        description="Supabase pgBouncer 사용 시 True (prepared statements 비활성화)",
    )

    # ── Supabase ──
    supabase_url: str = Field(default="", description="Supabase 프로젝트 URL (예: https://xxx.supabase.co)")
    supabase_anon_key: str = Field(default="", description="Supabase 익명 키 (클라이언트용)")
    supabase_service_role_key: str = Field(default="", description="Supabase 서비스 역할 키 (서버용)")
    supabase_storage_bucket: str = Field(default="propai-uploads", description="Supabase Storage 버킷명")

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_url: str = "redis://localhost:6379/1"

    # ── GraphQL ──
    hasura_admin_secret: str = Field(
        default="hasura_super_secret_key",
        validation_alias=AliasChoices("hasura_admin_secret", "HASURA_GRAPHQL_ADMIN_SECRET"),
    )
    hasura_url: str = "http://localhost:8088/v1/graphql"

    # ── AI 모델 API ──
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    replicate_api_token: str = ""
    ai_cache_ttl_seconds: int = 3600
    ai_daily_token_budget: int = 1_000_000

    # ── 공공 API 키 ──
    vworld_api_key: str = ""
    molit_api_key: str = ""
    applyhome_api_key: str = ""  # 청약홈(한국부동산원) 분양정보 조회 API. 미설정 시 molit_api_key 폴백

    # ── 알림 발송(알리고 ALIGO — 문자 + 카카오 알림톡). 미설정 시 인앱만 동작 ──
    aligo_api_key: str = ""            # 알리고 문자 API Key
    aligo_user_id: str = ""            # 알리고 사용자 ID
    aligo_sender: str = ""            # 등록된 발신번호
    aligo_kakao_senderkey: str = ""    # 알림톡 발신프로필 키(플러스친구). 미설정 시 SMS 폴백
    aligo_kakao_tpl_code: str = ""     # 승인된 알림톡 템플릿 코드
    kma_api_key: str = ""
    hug_api_key: str = ""
    lh_api_key: str = ""
    court_api_key: str = ""
    nice_api_key: str = ""
    kepco_api_key: str = ""
    rtms_api_key: str = ""

    # H01-H18 Halucination 방어를 위한 실존 공공 API(국가온실가스, 행안부) 강제
    gir_api_key: str = ""
    mois_api_key: str = ""

    # ── STEP 4 외부 API (세움터, ECOS, KCCI, K-ETS) ──
    seumter_api_key: str = ""
    ecos_api_key: str = ""
    kcci_api_key: str = ""
    kets_api_key: str = ""
    seumter_permit_rules_path: str = Field(
        default="",
        description="세움터 인허가 규칙 JSON 경로(비어 있으면 기본 내장 규칙 사용)",
    )
    gresb_benchmarks_path: str = Field(
        default="",
        description="GRESB 벤치마크 JSON 경로(비어 있으면 기본 내장 벤치마크 사용)",
    )
    carbon_factors_path: str = Field(
        default="",
        description="IFC 탄소계수 JSON 경로(비어 있으면 기본 내장 계수 사용)",
    )

    # ── 블록체인 (Polygon Amoy testnet) ──
    polygon_node_url: str = "https://rpc-amoy.polygon.technology/"
    escrow_contract_address: str = "0x961cba4A27D3080d8450789c91D4f30ff72E82E6"
    private_key: str = ""

    # ── IoT/드론 ──
    mqtt_broker: str = Field(
        default="localhost",
        validation_alias=AliasChoices("mqtt_broker", "MQTT_BROKER_URL"),
    )
    emqx_password: str = "emqx_pass"
    roboflow_api_key: str = ""

    # ── 카카오 OAuth ──
    kakao_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("kakao_client_id", "KAKAO_REST_API_KEY"),
    )
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = "http://localhost:3000/auth/kakao/callback"

    # ── CORS ──
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001,https://propai.kr,https://www.propai.kr,https://propai-web.pages.dev,https://4t8t.net,https://www.4t8t.net",
        validation_alias=AliasChoices("cors_origins", "ALLOWED_ORIGINS"),
    )

    # ── 보안 ──
    jwt_secret: str = Field(
        default="complex_jwt_secret_key_change_in_prod",
        validation_alias=AliasChoices("jwt_secret", "JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("jwt_access_token_expire_minutes", "JWT_EXPIRE_MINUTES"),
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        validation_alias=AliasChoices("jwt_refresh_token_expire_days", "REFRESH_TOKEN_EXPIRE_DAYS"),
    )
    encryption_key: str = ""

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def warn_default_jwt_secret(cls, value: str) -> str:
        """프로덕션 환경에서 기본 JWT 시크릿 사용 시 시작 차단."""
        import os
        if value == "complex_jwt_secret_key_change_in_prod":
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env in {"production", "staging"}:
                raise ValueError(
                    "JWT_SECRET이 기본값입니다. 프로덕션/스테이징 환경에서는 반드시 고유한 시크릿을 설정하세요. "
                    "환경변수 JWT_SECRET_KEY를 설정해주세요."
                )
            import warnings
            warnings.warn(
                "JWT_SECRET이 기본값입니다. 프로덕션 환경에서는 반드시 변경하세요!",
                stacklevel=2,
            )
        return value

    # ── 스토리지 ──
    minio_url: str = Field(
        default="http://localhost:9000",
        validation_alias=AliasChoices("minio_url", "MINIO_ENDPOINT"),
    )
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_bim: str = "propai-bim"
    minio_bucket_docs: str = "propai-docs"

    # ── MLOps/모니터링 ──
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "propai-avm"
    sentry_dsn: str = ""
    slack_webhook_url: str = ""
    log_level: str = "INFO"

    # ── OpenTelemetry / 분산 추적 ──
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "propai-api"
    otel_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    otel_enabled: bool = False

    # ── LangSmith / LLM 관측·평가 ──
    # 기본 OFF. LANGSMITH_API_KEY(관리자 시크릿/.env)가 있고 tracing=true일 때만 활성.
    # 활성 시 LangChain 전 ainvoke 호출이 LangSmith로 자동 추적(인터프리터 9개+전문가패널+RAG).
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias=AliasChoices("langsmith_tracing", "LANGSMITH_TRACING"),
    )
    langsmith_project: str = Field(
        default="propai-prod",
        validation_alias=AliasChoices("langsmith_project", "LANGSMITH_PROJECT"),
    )
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("langsmith_endpoint", "LANGSMITH_ENDPOINT"),
    )
    # APAC/EU 등 org-스코프 키는 워크스페이스(tenant) ID가 있어야 트레이스 전송 가능.
    # SDK(0.1.x)가 X-Tenant-Id를 안 보내므로 observability가 Client 헤더에 주입한다.
    langsmith_workspace_id: str = Field(
        default="",
        validation_alias=AliasChoices("langsmith_workspace_id", "LANGSMITH_WORKSPACE_ID"),
    )
    # 프로덕션 단일워커(1GB) 보호용 샘플링(1.0=전수, 0.1=10%). 추적 자체는 비동기라 영향 미미.
    langsmith_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("langsmith_sample_rate", "LANGSMITH_SAMPLE_RATE"),
    )

    # ── Qdrant ──
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_url: str = "http://localhost:6333"

    # ── v44 CAD 편집기 / 법규 보정 엔진 (G96~G99) ──
    cad_snap_grid_size_m: float = 0.1
    cad_max_points_per_design: int = 500
    compliance_check_debounce_ms: int = 500
    compliance_default_zone: str = "2R"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환. 앱 전체에서 이 함수를 통해 접근한다."""
    return Settings()
