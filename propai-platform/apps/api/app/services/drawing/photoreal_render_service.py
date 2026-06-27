"""AI 포토리얼 렌더 서비스 — 3D 뷰포트 이미지를 ControlNet으로 사실적 외관 이미지로 변환.

핵심 원칙(정직·비파괴):
- 외부 렌더 API 키(REPLICATE_API_TOKEN)가 없으면 **가짜 이미지를 만들지 않고**
  status="no_key" 안내만 돌려준다(에러 아님, 정상 200 응답).
- 원본 3D/설계 모델은 절대 바꾸지 않는다(이미지만 새로 생성하는 비파괴 작업).
- 키·토큰은 로그·응답에 평문으로 절대 노출하지 않는다.

동작:
1. platform_secrets→env 순으로 렌더 API 키를 찾는다(secret_store가 시작 시 env에 오버레이).
2. 키가 있으면 Replicate REST API(ControlNet 계열)에 입력 이미지(구조 보존)+스타일
   프롬프트로 예측을 요청하고, 완료까지 폴링해 결과 이미지 URL을 받는다.
3. 외부 호출이 실패하면 status="error"로 사유를 정직하게 알린다(가짜 이미지 없음).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# 렌더 API 키를 찾는 환경변수 후보(우선순위). secret_store가 DB→env로 오버레이해 둔다.
_KEY_ENV_CANDIDATES = ("REPLICATE_API_TOKEN", "REPLICATE_API_KEY")

# Replicate ControlNet 모델 — 입력 이미지의 구조(깊이/윤곽)를 보존하며 사실적으로 재질감 입힘.
# 버전 해시는 변동될 수 있어 env(REPLICATE_RENDER_VERSION)로 덮어쓸 수 있게 한다.
_DEFAULT_MODEL_VERSION = (
    "435061a1b5a4c1e26740464bf786efdfa9cb3a3ac488595a2de23e143fdb0117"  # lucataco/sdxl-controlnet (canny)
)

# 스타일(한국어 라벨)→영문 프롬프트 보강어. 기본은 '실사'.
_STYLE_PROMPT = {
    "주간": "bright daylight, clear blue sky, soft natural shadows",
    "야간": "night scene, warm interior lights glowing, dusk sky, cinematic exterior lighting",
    "실사": "photorealistic daylight, realistic materials, ultra detailed",
}

_BASE_PROMPT = (
    "photorealistic architectural exterior rendering of a modern korean building, "
    "high quality, professional architecture photography, realistic glass and concrete materials"
)
_NEGATIVE_PROMPT = "cartoon, sketch, lowres, blurry, distorted, watermark, text, people"

# 서버측 폴링 정책 — Prefer:wait(60s) 한도를 넘겨 202(미완료 prediction)가 와도
# 에러가 아니라 '접수됨'이므로 여기서 완료까지 이어서 기다린다.
_POLL_INTERVAL_S = 2.0  # 폴링 간격(초)
_POLL_MAX_S = 120.0  # 서버측 폴링 최대 대기(초) — 초과 시 status="pending" 정직 반환


def get_render_api_key() -> str | None:
    """렌더 API 키 조회(platform_secrets가 오버레이한 env에서). 없으면 None.

    secret_store.load_into_env()가 앱 시작 시 DB 암호화 키를 os.environ에 덮어쓰므로
    여기서는 env만 보면 'DB 설정 키'와 '.env 키'를 모두 자연스럽게 포함한다.
    """
    for name in _KEY_ENV_CANDIDATES:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return None


def _style_prompt(style: str) -> str:
    extra = _STYLE_PROMPT.get((style or "").strip(), _STYLE_PROMPT["실사"])
    return f"{_BASE_PROMPT}, {extra}"


def _ensure_data_uri(image_base64: str) -> str:
    """프론트가 순수 base64만 보내면 data URI로 감싼다(Replicate는 data URI 허용)."""
    s = (image_base64 or "").strip()
    if s.startswith("data:"):
        return s
    return f"data:image/png;base64,{s}"


async def render_photoreal(
    image_base64: str,
    *,
    style: str = "실사",
    strength: float = 0.6,
    timeout_s: float = 90.0,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """3D 뷰포트 이미지를 포토리얼 렌더로 변환. 비파괴(원본 불변).

    provider:
    - None 또는 "replicate": 기존 Replicate REST(ControlNet) 경로 그대로(후방호환·회귀 0).
    - "openai" / "google": 공용 image_provider로 img2img(3D 캡처를 입력 이미지로 구조 보존).

    반환 status:
    - "no_key":  키 미설정 → 정직 안내(가짜 이미지 없음).
    - "ok":      image_url(replicate) 또는 image_base64(openai/google) 포함(렌더 성공).
    - "pending": 서버측 폴링 한도(_POLL_MAX_S) 내 미완료 — 렌더 지연 안내 +
                 prediction_id 포함(가짜 이미지 없음, 에러로 단정하지 않음).
    - "error":   외부 호출 실패 사유(가짜 이미지 없음).
    """
    # openai/google 선택 시 공용 image_provider 경로로 분기(img2img·정직 강등).
    if provider in ("openai", "google"):
        return await _render_via_image_provider(image_base64, style, provider, model, timeout_s)

    # provider None/"replicate" — 아래 기존 Replicate 경로 그대로(미변경·회귀 0).
    api_key = get_render_api_key()
    if not api_key:
        return {
            "status": "no_key",
            "message": "AI 렌더 API 키가 설정되지 않았습니다. 관리자 키 설정 후 이용 가능합니다.",
        }

    if not (image_base64 or "").strip():
        return {"status": "error", "message": "입력 3D 이미지가 비어 있습니다."}

    # strength(0~1) 보정 — ControlNet conditioning 가중치로 사용(구조 보존 강도).
    try:
        cond_scale = max(0.0, min(1.0, float(strength)))
    except (TypeError, ValueError):
        cond_scale = 0.6

    model_version = (os.getenv("REPLICATE_RENDER_VERSION") or "").strip() or _DEFAULT_MODEL_VERSION
    image_uri = _ensure_data_uri(image_base64)

    payload = {
        "version": model_version,
        "input": {
            "image": image_uri,
            "prompt": _style_prompt(style),
            "negative_prompt": _NEGATIVE_PROMPT,
            "condition_scale": cond_scale,
            "num_inference_steps": 30,
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",  # 토큰은 헤더에만, 로그/응답 미노출
        "Content-Type": "application/json",
        "Prefer": "wait",  # 가능하면 완료까지 대기(빠른 모델은 단일 호출로 종료)
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                "https://api.replicate.com/v1/predictions", json=payload, headers=headers
            )
            # 202 = Prefer:wait(60s) 한도 내 미완료 — 에러가 아니라 '접수됨'.
            # 201도 starting/processing 상태로 올 수 있어 동일하게 폴링으로 이어간다.
            if resp.status_code not in (200, 201, 202):
                # 외부 사유는 노출하되 키는 포함되지 않는 본문만(요약).
                logger.warning("포토리얼 렌더 외부호출 비정상", code=resp.status_code)
                return {
                    "status": "error",
                    "message": f"렌더 서버 응답 오류(HTTP {resp.status_code}). 잠시 후 다시 시도해 주세요.",
                }
            data = resp.json()
            return await _resolve_prediction(client, data, headers)
    except httpx.HTTPError as e:
        logger.warning("포토리얼 렌더 통신 오류", err=str(e)[:120])
        return {"status": "error", "message": "렌더 서버에 연결하지 못했습니다. 네트워크를 확인해 주세요."}
    except Exception as e:  # noqa: BLE001
        logger.warning("포토리얼 렌더 처리 오류", err=str(e)[:120])
        return {"status": "error", "message": "렌더 처리 중 오류가 발생했습니다."}


async def _render_via_image_provider(
    image_base64: str,
    style: str,
    provider: str,
    model: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    """openai/google 프로바이더로 img2img 렌더(공용 image_provider 경유).

    3D 캡처를 input_image_b64로 넘겨 구조를 보존(편집/변형)한다. 키/SDK 부재나
    외부 오류는 가짜 이미지 없이 정직 강등(no_key/error)으로 매핑한다.
    """
    # ★기존 가드 유지: 입력 3D 이미지가 비면 먼저 정직 에러(외부 호출 전 차단).
    if not (image_base64 or "").strip():
        return {"status": "error", "message": "입력 3D 이미지가 비어 있습니다.", "provider": provider}

    from app.services.ai.image_provider import ImageGenerationError, generate_image

    try:
        out = await generate_image(
            provider,
            prompt=_style_prompt(style),
            model=model,
            input_image_b64=image_base64,
            size="1024x1024",
            timeout=timeout_s,
        )
    except ImageGenerationError as e:
        # 정직 강등: 키/패키지 부재→no_key, 그 외(api_error 등)→error(가짜 이미지 금지).
        status = "no_key" if e.error_type in ("key_not_configured", "package_missing") else "error"
        logger.warning("포토리얼 렌더 이미지 프로바이더 오류", provider=provider, err_type=e.error_type)
        return {"status": status, "message": str(e), "provider": provider}

    imgs = out.get("images") or []
    urls = out.get("image_urls") or []
    # images(base64) 우선, 없으면 image_urls(URL) — 공용 계약(소비처 동일 처리).
    if imgs:
        return {"status": "ok", "image_base64": imgs[0], "provider": provider, "model": out.get("model")}
    if urls:
        return {"status": "ok", "image_url": urls[0], "provider": provider, "model": out.get("model")}
    return {"status": "error", "message": "이미지 생성 결과가 비어 있습니다.", "provider": provider}


async def _resolve_prediction(
    client: httpx.AsyncClient, data: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    """prediction 객체를 종결 상태까지 해석해 응답 dict로 변환(정직 — 가짜 이미지 없음).

    - succeeded        → {"status": "ok", "image_url": ...} (즉시완료 200/201 포함)
    - failed/canceled  → {"status": "error", ...} 사유 안내
    - starting/processing → urls.get을 _POLL_INTERVAL_S 간격으로 재조회,
      _POLL_MAX_S 초과 시 {"status": "pending", "prediction_id": ...} 반환
      (외부에서 렌더가 계속 진행 중일 수 있어 에러로 단정하지 않는다).
    """
    deadline = asyncio.get_event_loop().time() + _POLL_MAX_S
    auth_header = {"Authorization": headers["Authorization"]}  # 토큰은 헤더에만, 로그 미노출
    while True:
        status = data.get("status")
        if status == "succeeded":
            image_url = _extract_image_url(data.get("output"))
            if not image_url:
                return {
                    "status": "error",
                    "message": "렌더가 완료됐지만 결과 이미지 URL이 없습니다. 잠시 후 다시 시도해 주세요.",
                }
            return {"status": "ok", "image_url": image_url}
        if status in ("failed", "canceled"):
            logger.warning("포토리얼 렌더 외부 실패", pred_status=status)
            return {
                "status": "error",
                "message": f"외부 렌더가 완료되지 못했습니다(상태: {status}). 잠시 후 다시 시도해 주세요.",
            }
        # 진행 중(starting/processing) — 폴링 URL이 없으면 더 기다릴 수 없다(정직 에러).
        get_url = (data.get("urls") or {}).get("get")
        if not get_url:
            return {
                "status": "error",
                "message": "렌더 진행 상태를 조회할 수 없습니다(폴링 URL 없음).",
            }
        if asyncio.get_event_loop().time() >= deadline:
            return {
                "status": "pending",
                "message": "렌더 지연 — 잠시 후 재시도해 주세요.",
                "prediction_id": data.get("id"),
            }
        await asyncio.sleep(_POLL_INTERVAL_S)
        r = await client.get(get_url, headers=auth_header)
        if r.status_code != 200:
            logger.warning("포토리얼 렌더 상태조회 비정상", code=r.status_code)
            return {
                "status": "error",
                "message": f"렌더 상태 조회 오류(HTTP {r.status_code}). 잠시 후 다시 시도해 주세요.",
            }
        data = r.json()


def _extract_image_url(output: Any) -> str | None:
    """Replicate output(문자열 또는 리스트)에서 첫 이미지 URL을 꺼낸다."""
    if isinstance(output, str) and output.startswith("http"):
        return output
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str) and item.startswith("http"):
                return item
    return None
