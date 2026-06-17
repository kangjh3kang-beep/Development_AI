"""R0 — 관할 해석(JurisdictionResolver). fallback chain + 복수 용도지역 보존.

외부API > 공부 > 수기입력. 실패해도 비차단(blocked=False), 미확정은 assumed=True로 전파(A5).
복수 zone 시 단일값으로 붕괴 금지 + stricter_applied 플래그(더 엄격기준 적용, INV-2).
"""
from __future__ import annotations

from app.contracts.enums import JurisdictionSource
from app.contracts.preflight import JurisdictionContext, Zone
from app.services.preflight.adapters import (
    CadastralAdapter,
    JurisdictionAdapter,
)


class JurisdictionResolver:
    def __init__(
        self,
        external: JurisdictionAdapter | None = None,
        cadastral: JurisdictionAdapter | None = None,
    ) -> None:
        if external is not None:
            self.external = external
        else:
            # 설정 기반 선택(기본 mock=ExternalJurisdictionAdapter, JURISDICTION_ADAPTER=vworld 시 실 VWORLD).
            from app.adapters.jurisdiction import build_external_jurisdiction
            self.external = build_external_jurisdiction()
        self.cadastral = cadastral or CadastralAdapter()

    def resolve(self, pnu: str, manual: dict | None = None) -> JurisdictionContext:
        raw: dict | None = None
        source = JurisdictionSource.MANUAL
        assumed = False

        try:
            raw = self.external.lookup(pnu)
            source = JurisdictionSource.EXTERNAL
        except Exception:
            try:
                raw = self.cadastral.lookup(pnu)
                source = JurisdictionSource.CADASTRAL
                assumed = True
            except Exception:
                if manual is not None:
                    raw = manual
                    source = JurisdictionSource.MANUAL
                    assumed = True

        if raw is None:
            # 전 체인 실패 — 비차단, 전 항목 미확정으로 전파(후속 게이트가 판단).
            return JurisdictionContext(
                pnu=pnu, zones=[], stricter_applied=False,
                source=JurisdictionSource.MANUAL, assumed=True, blocked=False,
            )

        zones = [Zone(**z) for z in raw.get("zones", [])]
        return JurisdictionContext(
            pnu=pnu,
            sido_code=raw.get("sido_code"),
            sigungu_code=raw.get("sigungu_code"),
            zones=zones,
            stricter_applied=len(zones) >= 2,
            source=source,
            assumed=assumed,
            blocked=False,
        )
