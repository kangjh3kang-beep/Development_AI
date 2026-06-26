"""이미지 렌더 provider 추상화 — 키 있으면 실호출, 없으면 정직하게 강등(무날조).

★절대 원칙: provider 키가 없거나 호출이 실패하면 **가짜 이미지 바이트를 만들지 않는다**.
키 미설정은 {status:'provider_unconfigured', ...}, 호출 실패는 {status:'render_error', ...}로
정직하게 반환한다. 성공할 때만 실제 이미지(b64/URL)를 담는다.

키 해석: secret_store 가 os.environ 에 오버레이하므로 os.environ 을 우선 읽고(런타임 관리자
시크릿 반영), 없으면 canonical Settings 폴백 — 관리자 시크릿 게이트 패턴 준수.

backlog(이번 범위 밖): SynthID/C2PA 워터마크·출처표식, 결과 영속화, guided 재시도 루프.
"""

from __future__ import annotations

import os
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

SUPPORTED_PROVIDERS = ("openai", "gemini")

# 에러 문자열에 섞일 수 있는 키(예: URL ?key=xxx, Bearer xxx, x-goog-api-key)를 가린다.
# ★보안: 업스트림 예외 메시지에 평문 키가 들어와도 로그/응답으로 새지 않게 한다.
_SECRET_RE = re.compile(
    r"(key=)[^&\s]+|(Bearer\s+)\S+|(x-goog-api-key[\"':\s]+)\S+",
    re.IGNORECASE,
)


def _sanitize(text: str, *, limit: int = 160) -> str:
    """업스트림 에러 텍스트에서 키/토큰을 가린 뒤 길이 제한(키 유출 차단)."""
    redacted = _SECRET_RE.sub(lambda m: (m.group(1) or m.group(2) or m.group(3) or "") + "***", text)
    return redacted[:limit]


def _resolve_key(env_name: str, settings_attr: str) -> str:
    """관리자 시크릿(os.environ 오버레이) 우선 → canonical Settings 폴백으로 키 해석."""
    val = os.environ.get(env_name)
    if val:
        return val.strip()
    try:
        from app.core.config import get_settings

        return str(getattr(get_settings(), settings_attr, "") or "").strip()
    except Exception:  # noqa: BLE001 — 설정 로드 실패는 '미설정'으로 간주(정직)
        return ""


def _unconfigured(provider: str, env_name: str) -> dict[str, Any]:
    """키 미설정 정직 강등 — 가짜 이미지 없이 사유만 반환."""
    return {
        "status": "provider_unconfigured",
        "provider": provider,
        "reason": f"{env_name} 미설정(관리자 시크릿)",
        "image": None,
    }


def _prompt_from_brief(brief: dict[str, Any]) -> str:
    """구조화 브리프를 provider 프롬프트 텍스트로 평탄화(결정론).

    role + 제약 + 가드/네거티브를 한 덩어리 문자열로 직렬화한다.
    """
    parts: list[str] = []
    role = brief.get("role")
    if role:
        parts.append(str(role))
    prog = brief.get("program") or {}
    if prog.get("building_use"):
        parts.append(f"용도: {prog['building_use']}, 규모: {prog.get('scale', '')}")
    ec = brief.get("envelope_constraints") or {}
    for label, c in ec.items():
        v = c.get("value") if isinstance(c, dict) else c
        if v is not None:
            parts.append(f"{label}={v}")
    guards = brief.get("accuracy_guards") or []
    if guards:
        parts.append("준수: " + "; ".join(str(g) for g in guards))
    neg = brief.get("negative") or []
    if neg:
        parts.append("금지: " + "; ".join(str(n) for n in neg))
    return "\n".join(parts)


def _size_from_brief(brief: dict[str, Any]) -> str:
    out = brief.get("output") or {}
    res = str(out.get("resolution") or "1024x1024")
    return res if "x" in res else "1024x1024"


async def _render_openai(brief: dict[str, Any]) -> dict[str, Any]:
    """OpenAI gpt-image-1 실호출 — 키 있을 때만. 성공 시 b64 이미지 반환.

    design_ingest(vector_store)가 AsyncOpenAI(api_key=...)를 쓰는 auth 패턴을 미러한다.
    """
    key = _resolve_key("OPENAI_API_KEY", "OPENAI_API_KEY")
    if not key:
        return _unconfigured("openai", "OPENAI_API_KEY")
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key)
        resp = await client.images.generate(
            model="gpt-image-1",
            prompt=_prompt_from_brief(brief),
            size=_size_from_brief(brief),
            n=1,
        )
        datum = resp.data[0]
        b64 = getattr(datum, "b64_json", None)
        url = getattr(datum, "url", None)
        if not b64 and not url:
            return {"status": "render_error", "provider": "openai",
                    "reason": "응답에 이미지가 없습니다", "image": None}
        return {
            "status": "rendered",
            "provider": "openai",
            "model": "gpt-image-1",
            "image": {"b64_json": b64, "url": url},
            # backlog: SynthID/C2PA 출처표식은 이번 범위 밖.
        }
    except Exception as e:  # noqa: BLE001 — 실호출 실패는 정직 강등(가짜 금지)
        safe = _sanitize(str(e))
        logger.warning("c2r openai 렌더 실패", err=safe)
        return {"status": "render_error", "provider": "openai",
                "reason": safe, "image": None}


async def _render_gemini(brief: dict[str, Any]) -> dict[str, Any]:
    """Google Gemini(generativelanguage REST) 이미지 렌더 — 키 있을 때만 실호출.

    문서화된 REST 계약(generativelanguage.googleapis.com .../models/<m>:generateContent,
    inlineData base64)으로 호출 코드를 작성하되, 키가 없으면 실호출하지 않고 강등한다.
    """
    key = _resolve_key("GEMINI_API_KEY", "GEMINI_API_KEY")
    if not key:
        return _unconfigured("gemini", "GEMINI_API_KEY")
    try:
        import base64

        import httpx

        # Gemini 이미지 생성 모델(generativelanguage REST). 응답 inlineData(base64 png).
        # 모델명은 미설정 시 기본값(프리뷰명은 변경 가능 → Settings/env로 재정의 가능).
        model = _resolve_key("GEMINI_IMAGE_MODEL", "GEMINI_IMAGE_MODEL") or (
            "gemini-2.0-flash-preview-image-generation"
        )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": _prompt_from_brief(brief)}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        }
        # ★보안: 키는 URL 쿼리(?key=)가 아니라 헤더로 전달 — 에러/로그에 키가 새지 않게.
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers={"x-goog-api-key": key})
            r.raise_for_status()
            body = r.json()
        # 응답에서 inlineData(base64) 추출 — 문서화된 계약.
        b64 = None
        for cand in body.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    b64 = inline["data"]
                    break
            if b64:
                break
        if not b64:
            return {"status": "render_error", "provider": "gemini",
                    "reason": "응답에 inlineData 이미지가 없습니다", "image": None}
        # base64 유효성만 확인(바이트 위조 아님 — provider가 실제 생성한 데이터).
        base64.b64decode(b64, validate=True)
        return {
            "status": "rendered",
            "provider": "gemini",
            "model": model,
            "image": {"b64_json": b64, "url": None},
            # backlog: SynthID 워터마크(Gemini는 SynthID 내장)·C2PA 표식은 이번 범위 밖.
        }
    except Exception as e:  # noqa: BLE001 — 실호출 실패는 정직 강등(가짜 금지)
        safe = _sanitize(str(e))
        logger.warning("c2r gemini 렌더 실패", err=safe)
        return {"status": "render_error", "provider": "gemini",
                "reason": safe, "image": None}


async def render_image(
    brief: dict[str, Any],
    *,
    provider: str = "openai",
    settings: dict[str, Any] | None = None,  # noqa: ARG001 — 향후 size/quality 등 확장 슬롯
) -> dict[str, Any]:
    """브리프 → 이미지 렌더(provider 추상화). 키 없으면 provider_unconfigured(정직).

    Args:
        brief:    synthesize_brief 산출 구조화 브리프.
        provider: 'openai' | 'gemini'. 미지원 값은 unsupported_provider.
        settings: 향후 해상도/품질 등 provider 옵션 확장용(현재 미사용).

    Returns:
        성공: {status:'rendered', provider, model, image:{b64_json|url}}.
        미설정: {status:'provider_unconfigured', provider, reason, image:None}.
        실패: {status:'render_error', provider, reason, image:None}.
    """
    p = (provider or "openai").strip().lower()
    if p == "openai":
        return await _render_openai(brief)
    if p == "gemini":
        return await _render_gemini(brief)
    return {
        "status": "unsupported_provider",
        "provider": p,
        "reason": f"지원하지 않는 provider: {p} (지원: {', '.join(SUPPORTED_PROVIDERS)})",
        "image": None,
    }
