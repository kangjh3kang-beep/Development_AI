import secrets
import warnings

from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = ""
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    DATABASE_URL: str = "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://propai_user:propai_pass_dev@localhost:5432/propai_db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    VWORLD_API_KEY: str = ""
    VWORLD_BASE_URL: str = "https://api.vworld.kr/req"

    MOLIT_API_KEY: str = ""
    MOLIT_TRANSACTION_URL: str = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade"

    SEUMTER_API_KEY: str = ""
    SEUMTER_BASE_URL: str = "https://cloud.eais.go.kr/modiIntegration"

    MOLEG_API_KEY: str = ""
    MOLEG_BASE_URL: str = "http://www.law.go.kr/DRF"

    EPD_KOREA_API_KEY: str = ""
    EPD_KOREA_BASE_URL: str = "https://www.epd.or.kr/api"

    # 소상공인시장진흥공단 상가(상권)정보 API (data.go.kr B553077)
    # 신버전 baroApi 통합 엔드포인트 (resId/catId로 세부 조회 지정)
    SEMAS_API_KEY: str = ""
    SEMAS_BASE_URL: str = "http://apis.data.go.kr/B553077/api/open/sdsc2"

    # 조달청 나라장터(G2B) 입찰/낙찰 API (data.go.kr 1230000)
    # data.go.kr 인증키는 계정당 1개 공용 → 미설정 시 MOLIT_API_KEY로 폴백(get_settings)
    G2B_SERVICE_KEY: str = ""

    # 한국자산관리공사 온비드(공매) OpenAPI (data.go.kr)
    # 미설정 시 G2B/MOLIT 공용키 폴백(get_settings) → 그래도 없으면 mock 폴백.
    ONBID_SERVICE_KEY: str = ""

    # SGIS 통계지리정보서비스 (통계청)
    SGIS_CONSUMER_KEY: str = ""
    SGIS_CONSUMER_SECRET: str = ""

    # KOSIS 국가통계포털 API Key
    KOSIS_API_KEY: str = ""

    # Phase 4 위험알림·예측(선택) — 미설정 시 graceful no-op(telegram)·휴리스틱(예측).
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    RISK_MODEL_PATH: str = ""

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "propai-files"
    AWS_REGION: str = "ap-northeast-2"

    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"

    # v61 BIM/공사비/도면 경로
    BIM_IFC_UPLOAD_PATH: str = "/tmp/propai/ifc"
    EXCEL_TEMPLATE_PATH: str = "/tmp/propai/templates"
    DRAWING_EXPORT_PATH: str = "/tmp/propai/drawings"
    CODIL_API_BASE: str = "https://www.codil.or.kr/api"

    # 공개 API 베이스(프론트가 직접 호출하는 절대 오리진). 설정 시 디지털트윈 항공
    # 프록시 URL을 절대화(예: https://api.4t8t.net). 미설정 시 상대 경로 유지(프론트 절대화).
    PUBLIC_API_BASE: str = ""

    # RBAC
    RBAC_ENABLED: bool = True
    RBAC_DEFAULT_ROLE: str = "user"

    # Rate Limit
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_WINDOW_SEC: int = 60

    # 로깅
    LOG_FORMAT: str = "json"
    LOG_LEVEL: str = "INFO"

    # Prometheus
    PROMETHEUS_ENABLED: bool = True

    # Sentry
    SENTRY_DSN: str = ""

    # LiveKit 화상회의 (Phase 3) — 미설정 시 토큰/녹화 엔드포인트 503 가드(크래시 금지).
    LIVEKIT_URL: str = ""          # wss://...livekit.cloud
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    # 녹화(Egress) → S3
    LIVEKIT_EGRESS_S3_BUCKET: str = ""
    LIVEKIT_EGRESS_S3_REGION: str = ""
    LIVEKIT_EGRESS_S3_ACCESS_KEY: str = ""
    LIVEKIT_EGRESS_S3_SECRET: str = ""

    class Config:
        env_file = ".env" if __import__("os").path.exists(".env") else None
        case_sensitive = True
        extra = "ignore"

# 유출 이력이 있거나 예제/기본값으로 쓰였던 시크릿 — 어떤 환경에서도 운영 사용 금지
_KNOWN_WEAK_SECRETS = frozenset({
    "propai_jwt_secret_change_in_production",
    "propai_secret_key_change_in_production_32chars_min",
    "da4c16477278ad3bce0f32447c0804c3b5dd4a530ca78ce19366ccb63d3fe5c8",  # .env.example 유출분
    "replace-with-random-64-hex",
    "hasura_super_secret_key",
})

def _validate_secret(name: str, value: str) -> None:
    if not value:
        raise RuntimeError(f"{name} 환경변수가 설정되지 않았습니다.")
    if value in _KNOWN_WEAK_SECRETS:
        raise RuntimeError(f"{name}에 유출/예제 시크릿이 설정되어 있습니다. 새 키로 교체하세요 (openssl rand -hex 32).")
    if len(value) < 32:
        raise RuntimeError(f"{name}는 32자 이상이어야 합니다.")

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # 프로덕션 환경에서 빈/약한 비밀키 사용 차단
    if s.APP_ENV != "development" and s.APP_ENV != "test":
        _validate_secret("APP_SECRET_KEY", s.APP_SECRET_KEY)
        _validate_secret("JWT_SECRET_KEY", s.JWT_SECRET_KEY)
    # 개발 환경에서 빈 키 자동 생성 + 경고
    if not s.APP_SECRET_KEY:
        object.__setattr__(s, "APP_SECRET_KEY", secrets.token_urlsafe(32))
        warnings.warn("APP_SECRET_KEY 미설정 — 임시 키 자동 생성됨", stacklevel=2)
    if not s.JWT_SECRET_KEY:
        object.__setattr__(s, "JWT_SECRET_KEY", secrets.token_urlsafe(32))
        warnings.warn("JWT_SECRET_KEY 미설정 — 임시 키 자동 생성됨", stacklevel=2)
    # 나라장터(G2B) 키 미설정 시 동일 계정의 MOLIT 키로 폴백(data.go.kr 키 공용)
    if not s.G2B_SERVICE_KEY and s.MOLIT_API_KEY:
        object.__setattr__(s, "G2B_SERVICE_KEY", s.MOLIT_API_KEY)
    # 온비드(공매) 키 미설정 시 G2B/MOLIT 공용키로 폴백(data.go.kr 키 공용)
    if not s.ONBID_SERVICE_KEY:
        fallback = s.G2B_SERVICE_KEY or s.MOLIT_API_KEY
        if fallback:
            object.__setattr__(s, "ONBID_SERVICE_KEY", fallback)
    return s

settings = get_settings()
