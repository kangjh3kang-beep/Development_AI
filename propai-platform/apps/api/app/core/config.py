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

    DATABASE_URL: str = "postgresql+asyncpg://propai:propai_dev_pass@localhost:5432/propai_db"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://propai:propai_dev_pass@localhost:5432/propai_db"
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

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # 프로덕션 환경에서 빈 비밀키 사용 차단
    if s.APP_ENV != "development" and s.APP_ENV != "test":
        if not s.APP_SECRET_KEY:
            raise RuntimeError("APP_SECRET_KEY 환경변수가 설정되지 않았습니다.")
        if not s.JWT_SECRET_KEY:
            raise RuntimeError("JWT_SECRET_KEY 환경변수가 설정되지 않았습니다.")
    # 개발 환경에서 빈 키 자동 생성 + 경고
    if not s.APP_SECRET_KEY:
        object.__setattr__(s, "APP_SECRET_KEY", secrets.token_urlsafe(32))
        warnings.warn("APP_SECRET_KEY 미설정 — 임시 키 자동 생성됨", stacklevel=2)
    if not s.JWT_SECRET_KEY:
        object.__setattr__(s, "JWT_SECRET_KEY", secrets.token_urlsafe(32))
        warnings.warn("JWT_SECRET_KEY 미설정 — 임시 키 자동 생성됨", stacklevel=2)
    return s

settings = get_settings()
