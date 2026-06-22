"""sim SimMetric 래핑 — shadow_3d/skyline_protrusion을 emit 게이트(근거 강제)로 통과(후속)."""
from app.services.sim.shadow_3d import sunlight_metric
from app.services.sim.skyline_protrusion import protrusion_metric


def test_sunlight_metric_emit_and_flag():
    from app.services.sim.sim_params import SimParamSource
    sun = {"sunny_hours_9to15": 2.0,
           "rationale": {"caveats": ["근사"], "inputs": [{"name": "위도", "value": 37.5}]}}
    m = sunlight_metric(sun, params=SimParamSource(overrides={"shadow3d_min_sunny_hours": 4.0}))
    assert m.metric_id == "sunlight_3d" and m.value == 2.0
    assert m.method_trace.basis_article  # emit 게이트 — 근거 강제
    assert "sunlight_below_min" in m.flags  # 2 < 4 → 미달 표면화
    assert sunlight_metric(None) is None


def test_protrusion_metric_emit_and_flag():
    prot = {"ratio_vs_avg": 5.0, "protrusion_level": "HIGH",
            "rationale": {"caveats": [], "inputs": []}}
    m = protrusion_metric(prot)
    assert m.metric_id == "skyline_protrusion" and m.method_trace.basis_article
    assert "skyline_protrusion_high" in m.flags  # 돌출 HIGH 표면화
    assert protrusion_metric(None) is None
