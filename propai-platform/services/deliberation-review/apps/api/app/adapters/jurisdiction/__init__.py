"""관할 외부 어댑터 — mock | vworld 팩토리. JurisdictionAdapter 계약(lookup(pnu)->dict) 준수."""
from __future__ import annotations

from app.adapters.jurisdiction.vworld import VWorldJurisdictionAdapter
from app.services.preflight.adapters import ExternalJurisdictionAdapter
from app.settings import env_or_setting


def build_external_jurisdiction():
    """설정 기반 관할 어댑터. 기본 mock(AT 그린). JURISDICTION_ADAPTER=vworld 시 실 VWORLD."""
    if env_or_setting("JURISDICTION_ADAPTER") == "vworld":
        return VWorldJurisdictionAdapter()
    return ExternalJurisdictionAdapter()
