"""LangSmith 기반 LLM 관측(트레이싱) 활성화.

LangChain은 환경변수(LANGCHAIN_TRACING_V2 / LANGCHAIN_API_KEY / LANGCHAIN_PROJECT /
LANGCHAIN_ENDPOINT)가 설정돼 있으면 모든 ChatModel.ainvoke 호출을 LangSmith로
자동 전송한다. 우리 플랫폼의 모든 LLM 호출은 LangChain ChatModel을 경유하므로
(BaseInterpreter 9종 + 전문가패널 + 법규 RAG) 이 한 번의 설정으로 전수 추적된다.

★기본 OFF: LANGSMITH_API_KEY(관리자 시크릿 또는 .env)가 있고 tracing=true일 때만 켜진다.
  키가 없으면 아무 일도 하지 않으므로(완전 무해) 운영에 영향이 없다.

★워크스페이스 헤더 주입: APAC/EU org-스코프 키는 워크스페이스(tenant) ID가 있어야
  /runs 전송이 허용된다(없으면 403). 그런데 langsmith 0.1.x SDK는 X-Tenant-Id 헤더를
  보내지 않는다. 따라서 LANGSMITH_WORKSPACE_ID가 있으면 langsmith Client 세션 헤더에
  X-Tenant-Id를 주입하도록 Client.__init__을 가드 패치한다(라이브 검증으로 확인된 경로).

★설정은 os.environ에서 직접 읽는다: settings는 import 시점에 캐시되는데, 관리자 키는
  부팅 중 load_into_env()가 os.environ에 올리므로 settings에는 반영되지 않는다.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

_LANGSMITH_ENABLED = False
_TENANT_PATCH_APPLIED = False


def langsmith_enabled() -> bool:
    """현재 LangSmith 추적이 활성 상태인지."""
    return _LANGSMITH_ENABLED


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _inject_tenant_header(workspace_id: str) -> None:
    """langsmith Client가 만드는 모든 HTTP 세션에 X-Tenant-Id를 주입한다.

    SDK가 자체적으로 보내지 않는 헤더라, org-스코프 키로 워크스페이스 트레이스를
    전송하려면 필요하다. Client.__init__을 한 번만 가드 패치한다(중복 방지).
    """
    global _TENANT_PATCH_APPLIED
    if _TENANT_PATCH_APPLIED:
        return
    try:
        from langsmith import client as _ls_client

        _orig_init = _ls_client.Client.__init__

        def _patched_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _orig_init(self, *args, **kwargs)
            try:
                sess = getattr(self, "session", None)
                if sess is not None:
                    sess.headers["X-Tenant-Id"] = workspace_id
            except Exception:  # noqa: BLE001
                pass

        _ls_client.Client.__init__ = _patched_init  # type: ignore[assignment]
        _TENANT_PATCH_APPLIED = True
        logger.info("LangSmith 워크스페이스 헤더 주입 활성", workspace_id=workspace_id[:8] + "…")
    except Exception as e:  # noqa: BLE001
        logger.warning("LangSmith 워크스페이스 헤더 주입 실패", error=str(e)[:120])


def init_langsmith() -> dict:
    """LangSmith 자동 추적을 활성화한다(조건 충족 시).

    호출 위치: main.py lifespan에서 secret_store.load_into_env() **이후**.

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

    # tracing 플래그: 환경변수(런타임 시크릿) 우선, 없으면 설정값. LangSmith 표준
    # `LANGSMITH_TRACING` 과 LangChain 표준 `LANGCHAIN_TRACING_V2` 를 **둘 다** 활성 토글로 인정한다
    # (운영자가 둘 중 무엇을 켜든 동일 동작 — 실측 기반 토글). 기본 OFF: 셋 다 미설정이면 비활성.
    tracing = (
        _truthy(os.environ.get("LANGSMITH_TRACING"))
        or _truthy(os.environ.get("LANGCHAIN_TRACING_V2"))
        or bool(settings.langsmith_tracing)
    )

    if not tracing or not key:
        _LANGSMITH_ENABLED = False
        logger.info("LangSmith 비활성", reason="키 없음" if not key else "tracing=off")
        return {"enabled": False, "has_key": bool(key), "tracing": tracing}

    # 설정값은 os.environ 우선(부팅 중 DB시크릿이 여기로 올라옴), 없으면 settings 기본.
    endpoint = (
        os.environ.get("LANGSMITH_ENDPOINT")
        or os.environ.get("LANGCHAIN_ENDPOINT")
        or settings.langsmith_endpoint
    ).strip()
    project = (os.environ.get("LANGSMITH_PROJECT") or settings.langsmith_project).strip()
    workspace_id = (
        os.environ.get("LANGSMITH_WORKSPACE_ID") or settings.langsmith_workspace_id
    ).strip()
    sample_rate = (os.environ.get("LANGSMITH_SAMPLE_RATE") or "").strip()

    # LangChain이 읽는 표준 환경변수 설정.
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = key
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    os.environ["LANGCHAIN_PROJECT"] = project
    if sample_rate:
        os.environ["LANGCHAIN_TRACING_SAMPLING_RATE"] = sample_rate

    # org-스코프 키 → 워크스페이스 헤더 주입(있을 때만).
    if workspace_id:
        _inject_tenant_header(workspace_id)

    _LANGSMITH_ENABLED = True
    logger.info(
        "LangSmith 활성화",
        project=project,
        endpoint=endpoint,
        workspace=bool(workspace_id),
        sample_rate=sample_rate or "1.0",
    )
    return {
        "enabled": True,
        "project": project,
        "endpoint": endpoint,
        "workspace": bool(workspace_id),
    }
