"""R2 — 수집 오케스트레이션. Tier1 우선, 외부 실패 시 Tier3 fallback으로 적재 지속(INV-15)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.source_document import SourceDocument
from app.supply.harvester.tier1_api_harvester import Tier1ApiHarvester
from app.supply.harvester.tier3_manual_register import Tier3ManualRegister


class HarvestResult(BaseModel):
    documents: list[SourceDocument] = Field(default_factory=list)
    used_fallback: bool = False


class Harvester:
    def __init__(
        self,
        tier1: Tier1ApiHarvester | None = None,
        tier3: Tier3ManualRegister | None = None,
    ) -> None:
        self.tier1 = tier1 or Tier1ApiHarvester()
        self.tier3 = tier3 or Tier3ManualRegister()

    def run(self, jurisdiction: str = "") -> HarvestResult:
        try:
            docs = self.tier1.harvest(jurisdiction)
            return HarvestResult(documents=docs, used_fallback=False)
        except Exception:
            # 외부 API 다운 — 차단 대신 fallback으로 수집 지속.
            docs = self.tier3.register_fallback(jurisdiction)
            return HarvestResult(documents=docs, used_fallback=True)
