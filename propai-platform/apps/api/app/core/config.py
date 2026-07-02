import secrets
import warnings
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 환경 판별 정합(3단계-a): 자매 Settings(apps/api/config.py `environment`)와 동일하게
    # ENVIRONMENT → APP_ENV 우선순위로 해석한다 — 한쪽 var 만 설정한 배포에서 두 클래스가
    # 다른 환경으로 갈라져 프로덕션 가드(P1-4)·시크릿 검증이 우회되던 드리프트 차단.
    # 계약 테스트: tests/test_settings_env_consistency.py. 단일 클래스 전면 통합은 별도 트랙.
    APP_ENV: str = Field(default="development",
                         validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV"))
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

    # C2R(Coordinate-to-Render) 이미지 렌더 provider — Google Gemini(generativelanguage REST).
    # ★extra='ignore'라 Settings에 필드가 없으면 prod env의 GEMINI_API_KEY가 무시되므로 명시 선언.
    #   미설정(빈 문자열)이면 c2r 렌더는 가짜 이미지를 만들지 않고 정직하게 provider_unconfigured 반환.
    GEMINI_API_KEY: str = ""

    # C2R 렌더 가드 — '검증 안 된 브리프(geometry_hash 없음/불일치)'로 이미지가 렌더되는
    # 오염 경로를 막는다. ★1차는 shadow(기본 False): 차단하지 않고 경고 로그만 남겨 노출빈도를
    # 측정한다. 충분히 안전하다고 확인되면 True로 올려 실제 차단(enforce)으로 승격한다(무회귀).
    C2R_RENDER_GUARD_ENFORCE: bool = False

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # 벡터 검색(Qdrant) — 성장 뇌(MemoryHub) 의미 회상·design retrieval에 사용.
    # ★전수감사 보강: Settings에 필드가 없으면 extra='ignore'로 prod env(QDRANT_HOST)가 무시되어
    #   qdrant_client.getattr가 항상 None→:memory: 폴백(워커↔API 교차 불가·의미회상 영구 휴면)이었음.
    #   필드를 선언해 prod에서 환경변수로 실제 Qdrant 서비스를 가리킬 수 있게 한다(미설정 시 ""→:memory:).
    QDRANT_HOST: str = ""
    QDRANT_PORT: int = 6333

    VWORLD_API_KEY: str = ""
    VWORLD_BASE_URL: str = "https://api.vworld.kr/req"

    MOLIT_API_KEY: str = ""
    MOLIT_TRANSACTION_URL: str = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade"

    SEUMTER_API_KEY: str = ""
    SEUMTER_BASE_URL: str = "https://cloud.eais.go.kr/modiIntegration"

    MOLEG_API_KEY: str = ""
    MOLEG_BASE_URL: str = "http://www.law.go.kr/DRF"

    # AI Hub(aihub.or.kr) 데이터 자동 다운로드 — apikey(마이페이지 발급) + 데이터셋 활용신청 승인 전제.
    #   건축 도면 데이터(48,033장) 등을 design_ingest 시드로 자동 다운로드·인제스트.
    AIHUB_API_KEY: str = ""
    AIHUB_BASE_URL: str = "https://api.aihub.or.kr"
    # ★AI Hub 다운로드는 한국 ISP IP만 허용(클라우드/해외 IP 502 차단). 한국 프록시(http(s)://host:port)
    #   를 지정하면 aihubshell 다운로드를 그 IP로 경유한다(목록은 비차단이라 프록시 불필요).
    AIHUB_PROXY: str = ""

    EPD_KOREA_API_KEY: str = ""
    EPD_KOREA_BASE_URL: str = "https://www.epd.or.kr/api"

    # 심의분석엔진(deliberation-review) — 인·허가/심의 프로세스 호출. 미설정 시 심의 에이전트 graceful(미연동).
    # ★토큰 키는 호스트 .env·BFF(apps/api/config.deliberation_engine_api_token)와 동일하게
    #   DELIBERATION_ENGINE_API_TOKEN 으로 통일(불일치 시 토큰 미전달 → 엔진 401).
    DELIBERATION_ENGINE_URL: str = ""
    DELIBERATION_ENGINE_API_TOKEN: str = ""

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

    # 배포 전(샌드박스/개발) 여부 — True면 라이브 DB·공공API·LLM 실호출이 불가한 환경으로 보고
    #   결과물에 '배포 환경에서만 동작' 정직 표기(deploy_pending)를 단다. 라이브 배포 시 false로
    #   설정하면 자기 라이브성을 과소표기하지 않는다(기본 True=보수적).
    DEPLOY_PENDING: bool = True

    # 로깅
    LOG_FORMAT: str = "json"
    LOG_LEVEL: str = "INFO"

    # 기하 불변식 하드게이트(설계 매스/폴리곤 무효결과 차단) — 기본 False=그림자(shadow).
    #   False면 점검은 하되 경고 로그만 남기고 절대 차단하지 않는다(정상 산출 흐름 불변·무회귀).
    #   True면 FAIL(0세대·면적불보존·법정초과 등) 시 배선부가 결과에 차단 표기를 단다.
    GEOMETRY_INVARIANT_ENFORCE: bool = False

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

@lru_cache
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
