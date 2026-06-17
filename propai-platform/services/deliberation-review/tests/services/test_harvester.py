"""AT-7 — 외부 API 다운 시 harvester fallback(공부/수기)로 적재 지속."""
from app.supply.harvester.harvester import Harvester
from app.supply.harvester.tier1_api_harvester import Tier1ApiHarvester


def test_harvester_fallback_on_api_down(monkeypatch):
    def boom(self, jurisdiction=""):
        raise TimeoutError("tier1 api down")

    monkeypatch.setattr(Tier1ApiHarvester, "harvest", boom)
    result = Harvester().run("1111011111")
    assert result.used_fallback is True
    assert result.documents  # fallback 적재 지속


def test_harvester_default_uses_fallback_in_mock_env():
    # dev/mock: LiveNetwork 비활성 → 기본 실행도 fallback 경로.
    result = Harvester().run("1111011111")
    assert result.used_fallback is True
