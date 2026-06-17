"""AT-4/AT-5 — 복수 용도지역 보존 + 외부 API 다운 시 fallback 비차단."""
from app.contracts.enums import JurisdictionSource
from app.services.preflight.adapters import AdapterTimeout, ExternalJurisdictionAdapter
from app.services.preflight.jurisdiction import JurisdictionResolver

PNU_MULTIZONE = "1111010100100000001"
PNU_SINGLE = "1111010100100000002"


def test_multi_zone_not_collapsed():
    ctx = JurisdictionResolver().resolve(pnu=PNU_MULTIZONE)
    assert len(ctx.zones) >= 2  # 단일값으로 붕괴 금지
    assert ctx.stricter_applied is True  # 더 엄격기준 플래그


def test_external_down_uses_fallback(monkeypatch):
    def boom(self, pnu):
        raise AdapterTimeout("external down")

    monkeypatch.setattr(ExternalJurisdictionAdapter, "lookup", boom)
    ctx = JurisdictionResolver().resolve(pnu=PNU_SINGLE)
    assert ctx.source in (JurisdictionSource.CADASTRAL, JurisdictionSource.MANUAL)
    assert ctx.blocked is False  # 비차단
