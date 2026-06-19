"""P3+ — 규제 SSOT read 표면(GET /api/v1/reg/zone-limits) + all_zone_limits 제공자.

엔진 1차출처(national_zone_limits.json)를 플랫폼이 자신의 ZONE_LIMITS와 대조(reg-source divergence·P5)
하는 read-only 소비원. 결정론·INV-3(데이터파일 백업) 검증.
"""
from app.api import deps
from app.services.legal_calc import zone_limit_provider as zlp


def test_all_zone_limits_structure_and_values():
    out = zlp.all_zone_limits()
    assert "meta" in out and "zones" in out
    assert "시행령" in (out["meta"].get("source") or "")
    z = out["zones"]["제2종일반주거지역"]
    assert z["far_floor_area"]["value"] == 250.0 and z["far_floor_area"]["unit"] == "%"
    assert z["building_area"]["value"] == 60.0  # 건폐율
    assert "제2종일반주거지역" in z["far_floor_area"]["source"]
    # 대표 용도지역 전수 노출(시행령 21개 이상).
    assert len(out["zones"]) >= 20
    assert out["zones"]["일반상업지역"]["far_floor_area"]["value"] == 1300.0


def test_all_zone_limits_reflects_override():
    try:
        zlp.set_zone_override("제2종일반주거지역", {"far_pct": 220})
        out = zlp.all_zone_limits()
        assert out["zones"]["제2종일반주거지역"]["far_floor_area"]["value"] == 220.0
    finally:
        zlp._override.pop("제2종일반주거지역", None)


def test_reg_zone_limits_endpoint_returns_ssot(client):
    resp = client.get("/api/v1/reg/zone-limits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["zones"]["제3종일반주거지역"]["far_floor_area"]["value"] == 300.0
    assert "version" in body["meta"]


def test_reg_zone_limits_requires_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    assert client.get("/api/v1/reg/zone-limits").status_code == 401
    ok = client.get("/api/v1/reg/zone-limits", headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200
