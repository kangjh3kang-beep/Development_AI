"""Phase 0 — 환경설정(pydantic-settings). .env 로딩, 외부 어댑터 토글(기본 mock).

env_file은 CWD 무관 repo-root 절대경로(apps/api에서 uvicorn 실행해도 키 로드). 프로세스 env가 우선.
"""
from __future__ import annotations

import pathlib

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/settings.py → repo root(propai-review)/.env
_ENV_FILE = pathlib.Path(__file__).resolve().parents[3] / ".env"
# 스코프 시크릿 — 플랫폼 export_scoped_secrets.py가 허용목록 키만 기록(있으면 .env 위에 오버레이).
# 외부 서비스(엔진)는 자기 .env(.secrets)만 읽음 — 마스터키·금고 접근 0(경계 안 넘음).
_SECRETS_FILE = pathlib.Path(__file__).resolve().parents[3] / ".env.secrets"


class Settings(BaseSettings):
    # 튜플: 뒤쪽(.env.secrets)이 우선 — 플랫폼이 내보낸 스코프 키가 .env 기본값을 덮어씀.
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), str(_SECRETS_FILE)),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    DB_SCHEMA: str = "review"
    # ⚠️ USE_MOCK_ADAPTERS(구): 어디서도 소비되지 않는 죽은 설정이라 제거했다(전역 mock 토글로 오해 방지).
    #    mock/live 선택은 어댑터별 개별 env가 정본 — JURISDICTION_ADAPTER(mock|vworld)·SHEET_CLASSIFIER(mock|vllm)·
    #    EMBEDDER(hash|openai)·QDRANT_URL(빈=in-memory)·LIVE_NETWORK(공급측 라이브 호출). 각 키 아래 참조.
    # 비동기(Celery): 기본 eager(브로커 없는 dev는 동기 폴백). 운영은 false + worker+redis로 진짜 비동기.
    CELERY_TASK_ALWAYS_EAGER: bool = True
    # INC-14: 라이브 외부 호출(LiveNetwork) 토글 — 기본 False=mock(NetworkError). 공급측 reconcile/harvester
    # 한정(INV-13: 소비경로는 이 플래그와 무관하게 라이브 미호출). True 시 실 httpx GET.
    LIVE_NETWORK: bool = False
    # reconcile 주기잡(celery beat) 간격(초). 운영 인프라 cadence(법정 수치 아님, INV-3 비대상).
    RECONCILE_INTERVAL_SECONDS: int = 86400
    # reconcile 불일치 시 단일 관할 재분석 디스패치 상한(큐 폭주 방어). 초과분은 로깅 후 절단(무음0). 인프라 수치.
    RECONCILE_MAX_REANALYZE: int = 100
    # 유사사례 임베더: hash(결정론 폴백) | openai(실 의미 임베딩). openai는 OPENAI_API_KEY 필요.
    EMBEDDER: str = "hash"
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    # 벡터검색 저장소: 빈 값=in-memory mock. ":memory:"=실 qdrant-client 임베디드. http(s)=실 Qdrant 서버.
    QDRANT_URL: str = ""
    # 국가법령정보센터(법제처 law.go.kr DRF) — OC=MOLEG_API_KEY. 법령 교차검증 1차출처.
    MOLEG_API_KEY: str = ""
    MOLEG_BASE_URL: str = "https://www.law.go.kr/DRF"  # https — API 키 평문 전송 MITM 방지
    # 국토부 건축물대장(data.go.kr) — serviceKey=MOLIT_API_KEY. 용적률/건폐율 교차검증 1차출처.
    MOLIT_API_KEY: str = ""
    MOLIT_BLD_URL: str = "https://apis.data.go.kr/1613000/BldRgstHubService"  # https
    # VWORLD NED(공시지가/토지이용계획) — key=VWORLD_API_KEY + Referer 도메인 검증(필수).
    VWORLD_NED_URL: str = "https://api.vworld.kr/ned/data"
    VWORLD_REQ_URL: str = "https://api.vworld.kr/req"  # 지오코더(address)·2D데이터(data) 공통 base
    VWORLD_REFERER: str = "https://www.4t8t.net"  # VWORLD 키 발급 시 등록한 도메인(Referer 검증)
    # 프런트(플랫폼/콘솔)가 크로스오리진으로 /analyze 호출 — 쉼표구분 origin 목록("*"=전체).
    CORS_ORIGINS: str = "*"
    # 시트 분류기 선택: mock | vllm. vllm은 ANTHROPIC_API_KEY 있으면 실 호출, 없으면 graceful degrade.
    SHEET_CLASSIFIER: str = "mock"
    ANTHROPIC_API_KEY: str = ""
    VLLM_MODEL: str = "claude-sonnet-4-6"
    # /api/v1/analyze 베어러 토큰. 빈 값 = 개방(dev). 설정 시 'Authorization: Bearer <token>' 요구.
    API_TOKEN: str = ""
    # 클라이언트별 분당 요청 상한(레이트리밋). 0=비활성(기본). 외부 1차출처 쿼터/비용 폭주 방어.
    # ⚠️ 프로세스 로컬 카운터 — 다중 워커 분산 강제는 Redis 등 필요(app.core.rate_limit 한계 참조).
    REQUESTS_PER_MINUTE: int = 0
    # 관할 해석 외부 어댑터: mock | vworld. vworld는 VWORLD_API_KEY 있으면 실 호출, 없으면 fallback.
    JURISDICTION_ADAPTER: str = "mock"
    VWORLD_API_KEY: str = ""
    VWORLD_API_URL: str = "https://api.vworld.kr/req/data"
    # 플랫폼 관리자 시크릿 스토어(platform_secrets) 연결 — 시작 시 복호화→os.environ 오버레이.
    # 같은 propai_db 공유. 마스터키는 SECRET_STORE_KEY(우선) 또는 APP_SECRET_KEY(플랫폼과 동일해야 복호화).
    LOAD_PLATFORM_SECRETS: bool = False
    SECRET_STORE_KEY: str = ""
    APP_SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""  # 마스터키 폴백 3순위(플랫폼 _fernet 우선순위와 동일)
    # 플랫폼 .env(들)에서 마스터키를 런타임 참조(복사 없이 단일 출처). 쉼표구분 경로. 값 아님(경로).
    PLATFORM_ENV_FILE: str = ""

    @model_validator(mode="after")
    def _production_fail_closed(self) -> "Settings":
        """운영(production) 부팅 시 무인증·와일드카드 CORS 거부(무음 개방 차단)."""
        if self.ENV == "production":
            if not self.API_TOKEN:
                raise ValueError("production은 API_TOKEN 필수(인증 fail-closed)")
            if self.CORS_ORIGINS.strip() == "*":
                raise ValueError("production은 와일드카드 CORS_ORIGINS 금지(명시 도메인 목록 필요)")
        return self

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL

    @property
    def redis_url(self) -> str:
        return self.REDIS_URL


settings = Settings()


def env_or_setting(name: str) -> str:
    """런타임 os.environ 우선(시크릿 오버레이 반영), 없으면 settings 값. 키 오버레이 즉시 적용용."""
    import os

    val = os.getenv(name)
    if val:
        return val
    return str(getattr(settings, name, "") or "")
