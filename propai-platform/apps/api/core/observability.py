"""LangSmith 기반 LLM 관측(트레이싱) 활성화.

LangChain은 환경변수(LANGCHAIN_TRACING_V2 / LANGCHAIN_API_KEY / LANGCHAIN_PROJECT /
LANGCHAIN_ENDPOINT)가 설정돼 있으면 모든 ChatModel.ainvoke 호출을 LangSmith로
자동 전송한다. 우리 플랫폼의 모든 LLM 호출은 LangChain ChatModel을 경유하므로
(BaseInterpreter 9종 + 전문가패널 + 법규 RAG) 이 한 번의 설정으로 전수 추적된다.

★기본 OFF: LANGSMITH_API_KEY(관리자 시크릿 또는 .env)가 있고 tracing=true일 때만 켜진다.
  키가 없으면 아무 일도 하지 않으므로(완전 무해) 운영에 영향이 없다.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

# LangSmith 활성 여부(다른 모듈이 참조 가능: 예 _invoke 메타데이터 부착 가드)
_LANGSMITH_ENABLED = False


def langsmith_enabled() -> bool:
    """현재 LangSmith 추적이 활성 상태인지."""
    return _LANGSMITH_ENABLED


def init_langsmith() -> dict:
    """LangSmith 자동 추적을 활성화한다(조건 충족 시).

    호출 위치: main.py lifespan에서 secret_store.load_into_env() **이후**.
    (관리자 화면에서 입력한 LANGSMITH_API_KEY가 os.environ에 올라온 뒤 읽어야 하므로.)

    Returns:
        활성화 결과 dict — 로깅/헬스 표기용.
    """
    global _LANGSMITH_ENABLED

    from apps.api.config import get_settings

    settings = get_settings()

    # 키: 관리자 시크릿(load_into_env) 또는 .env. LANGSMITH_* / LANGCHAIN_* 양쪽 허용.
    key = (
        os.environ.get("LANGSMITH_API_KEY")
        or os.environ.get("LANGCHAIN_API_KEY")
        or ""
    ).strip()

    # tracing 플래그: 환경변수(런타임 시크릿) 우선, 없으면 설정값.
    env_flag = os.environ.get("LANGSMITH_TRACING", "").strip().lower()
    tracing = env_flag in {"1", "true", "yes", "on"} or bool(settings.langsmith_tracing)

    if not tracing or not key:
        _LANGSMITH_ENABLED = False
        logger.info(
            "LangSmith 비활성",
            reason="키 없음" if not key else "tracing=off",
        )
        return {"enabled": False, "has_key": bool(key), "tracing": tracing}

    # LangChain이 읽는 표준 환경변수 설정.
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = key
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    # 샘플링(프로덕션 1GB 단일워커 보호) — LangChain이 인식하는 표준 변수.
    if settings.langsmith_sample_rate < 1.0:
        os.environ["LANGCHAIN_TRACING_SAMPLING_RATE"] = str(settings.langsmith_sample_rate)

    _LANGSMITH_ENABLED = True
    logger.info(
        "LangSmith 활성화",
        project=settings.langsmith_project,
        endpoint=settings.langsmith_endpoint,
        sample_rate=settings.langsmith_sample_rate,
    )
    return {
        "enabled": True,
        "project": settings.langsmith_project,
        "sample_rate": settings.langsmith_sample_rate,
    }
