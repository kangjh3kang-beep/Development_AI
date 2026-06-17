"""통합 상태 점검 — 어댑터별 live/mock + 키 보유 여부(bool만, 값 노출 금지).

env 우선(시크릿 오버레이 반영). 키 없으면 정직하게 'mock/degraded'로 보고(은폐 금지).
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


def integration_status() -> dict:
    from app.services.secrets.platform_secret_loader import (
        has_master_key,
        master_key_candidates,
    )

    sheet_mode = env_or_setting("SHEET_CLASSIFIER") or settings.SHEET_CLASSIFIER
    jur_mode = env_or_setting("JURISDICTION_ADAPTER") or settings.JURISDICTION_ADAPTER
    vllm_key = bool(env_or_setting("ANTHROPIC_API_KEY"))
    vworld_key = bool(env_or_setting("VWORLD_API_KEY"))
    local_master = bool(
        env_or_setting("SECRET_STORE_KEY")
        or env_or_setting("APP_SECRET_KEY")
        or env_or_setting("JWT_SECRET_KEY")
    )
    candidate_count = len(master_key_candidates())  # 값 아님 — 후보 개수만
    return {
        "sheet_classifier": {
            "mode": sheet_mode,
            "vllm_key_present": vllm_key,
            "live": sheet_mode == "vllm" and vllm_key,
            "model": env_or_setting("VLLM_MODEL") or settings.VLLM_MODEL,
        },
        "jurisdiction": {
            "mode": jur_mode,
            "vworld_key_present": vworld_key,
            "live": jur_mode == "vworld" and vworld_key,
        },
        "embedder": {
            "mode": env_or_setting("EMBEDDER") or "hash",
            "openai_key_present": bool(env_or_setting("OPENAI_API_KEY")),
            "semantic": (env_or_setting("EMBEDDER") == "openai" and bool(env_or_setting("OPENAI_API_KEY"))),
        },
        "platform_secrets": {
            "load_enabled": settings.LOAD_PLATFORM_SECRETS,
            "master_key_present": has_master_key(),
            "master_key_local": local_master,
            "master_key_via_platform_file": has_master_key() and not local_master,
            "candidate_count": candidate_count,
        },
        "database": {"configured": bool(settings.DATABASE_URL)},
        "api_auth": {"enabled": bool(settings.API_TOKEN)},
    }
