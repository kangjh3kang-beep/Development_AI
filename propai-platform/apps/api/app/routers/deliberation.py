"""중심 엔진 통합 BFF — 심의/설계도면 자동분석 엔진(별도 서비스) 게이트웨이.

플랫폼은 엔진을 직접 import하지 않고(패키지명 `app` 충돌) 서버사이드 HTTP로 호출한다.
Phase 0: `GET /health` — 엔진 `/api/v1/doctor`를 인증 후 프록시하되 **화이트리스트 필드만** 재발행
(api_auth.enabled·*_key_present·master_key·model 등 보안태세 핑거프린트 비노출). 엔진 미연결 시 degraded.
설계: docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md(§4·§7 Phase0·§5).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.services.auth.auth_service import get_current_user
from apps.api.config import get_settings

router = APIRouter(prefix="/api/v1/deliberation", tags=["심의분석 엔진"])


async def _fetch_engine_doctor() -> dict[str, Any] | None:
    """엔진 `/api/v1/doctor` 조회. 미설정/실패/타임아웃 시 None(무음 단정 금지 — 호출측이 degraded 표면화).

    별도 함수로 분리해 테스트에서 monkeypatch(엔진 비의존). 외부 fetch는 여기 단일 choke point.
    """
    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None
    try:
        import httpx

        headers = {}
        if s.deliberation_engine_api_token:
            headers["Authorization"] = f"Bearer {s.deliberation_engine_api_token}"
        timeout = httpx.Timeout(
            connect=s.deliberation_engine_connect_timeout_s,
            read=s.deliberation_engine_read_timeout_s,
            write=s.deliberation_engine_read_timeout_s,
            pool=s.deliberation_engine_connect_timeout_s,
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.get(f"{base}/api/v1/doctor", headers=headers)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _whitelist_health(doctor: dict[str, Any]) -> dict[str, Any]:
    """엔진 doctor에서 **안전한 상태 필드만** 추출(핑거프린트 차단). 미지 구조는 .get으로 방어(크래시 0).

    노출: database.configured · sheet_classifier.live · jurisdiction.live · embedder.semantic.
    비노출: api_auth·*_key_present·master_key·model·mode·candidate_count 등 일체.
    """
    def _nested(key: str, sub: str) -> Any:
        node = doctor.get(key)
        return node.get(sub) if isinstance(node, dict) else None

    return {
        "database_configured": _nested("database", "configured"),
        "sheet_classifier_live": _nested("sheet_classifier", "live"),
        "jurisdiction_live": _nested("jurisdiction", "live"),
        "embedder_semantic": _nested("embedder", "semantic"),
    }


@router.get("/health")
async def deliberation_health(_user=Depends(get_current_user)) -> dict[str, Any]:
    """엔진 헬스(화이트리스트). 인증 필수. 미연결 시 degraded(무음0)."""
    doctor = await _fetch_engine_doctor()
    if doctor is None:
        return {"status": "degraded", "reason": "engine_unreachable", "engine": None}
    return {"status": "ok", "engine": _whitelist_health(doctor)}
