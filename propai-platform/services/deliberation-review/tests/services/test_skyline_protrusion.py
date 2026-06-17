"""스카이라인 돌출도 — 신축안 vs 주변 평균/최고, 등급화·결손 None."""
from app.services.sim.skyline_protrusion import skyline_protrusion


def test_protrusion_levels():
    sky = {"avg_floors": 5.0, "max_floors": 10}
    # 주변 최고 이내 → LOW.
    low = skyline_protrusion(sky, 8)
    assert low["protrusion_level"] == "LOW" and low["exceeds_context_max"] is False
    assert low["ratio_vs_avg"] == round(8 / 5.0, 2)
    # 최고 초과 ~2배 이내 → MEDIUM.
    assert skyline_protrusion(sky, 15)["protrusion_level"] == "MEDIUM"
    # 최고 2배 초과 → HIGH.
    hi = skyline_protrusion(sky, 25)
    assert hi["protrusion_level"] == "HIGH" and hi["exceeds_context_max"] is True


def test_protrusion_missing_returns_none():
    assert skyline_protrusion(None, 10) is None
    assert skyline_protrusion({"avg_floors": 5.0, "max_floors": 10}, None) is None
    assert skyline_protrusion({"avg_floors": 5.0, "max_floors": 10}, 0) is None


def test_protrusion_partial_skyline():
    # 평균/최고 결손이어도 가능한 항목만 산출(무음 결손 아님).
    out = skyline_protrusion({"avg_floors": None, "max_floors": None}, 12)
    assert out["proposed_floors"] == 12
    assert "ratio_vs_avg" not in out and "protrusion_level" not in out
