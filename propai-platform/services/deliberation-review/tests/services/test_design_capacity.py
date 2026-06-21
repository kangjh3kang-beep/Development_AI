"""MASS1 — 검증형 매스 캐파: SSOT(용적/건폐) 최대 캐파 산정 + 제공 매스 적정성 검증(생성 아님)·근거·e2e."""
from datetime import date
from types import SimpleNamespace

from app.contracts.analysis import AnalysisInput
from app.contracts.legal_quantity import LegalQuantity
from app.services.design.capacity import capacity_envelope
from app.services.design.design_executor import run_design_process
from app.services.pipeline.analysis_pipeline import run_analysis

_ZONE = "제2종일반주거지역"   # far 250% / bcr 60%


def _res(plot=None):
    lqs = [LegalQuantity(variable_id="plot_area", value=plot)] if plot is not None else []
    return SimpleNamespace(legal_quantities=lqs, qualitative=[])


def test_capacity_envelope_from_ssot():
    env = capacity_envelope(_res(plot=1000.0), _ZONE)
    assert env.max_gfa_sqm == 2500.0          # 1000 × 250%
    assert env.max_footprint_sqm == 600.0     # 1000 × 60%
    assert env.legal_basis and all(r.source for r in env.legal_basis)   # 근거+링크(§78/§77)


def test_proposed_massing_within_capacity_is_compliant():
    env = capacity_envelope(_res(plot=1000.0), _ZONE, proposed_gfa=2000.0)
    assert env.conformance == "부합" and env.margin_sqm == 500.0


def test_proposed_massing_over_capacity_is_noncompliant():
    env = capacity_envelope(_res(plot=1000.0), _ZONE, proposed_gfa=3000.0)
    assert env.conformance == "미흡"


def test_no_plot_or_no_proposed_is_held_not_fabricated():
    assert capacity_envelope(_res(plot=None), _ZONE, proposed_gfa=2000.0).conformance == "미상"  # 대지 부재
    assert capacity_envelope(_res(plot=1000.0), _ZONE).conformance == "미상"                      # 제공 매스 부재


def test_design_process_attaches_capacity_to_massing_stage():
    inp = AnalysisInput(pnu="1111010100100000060", application_date=date(2026, 1, 1),
                        calc_targets=[{"target": "plot_area", "payload": {"parcel_area": 1000.0},
                                       "elements": []}])
    out = run_design_process(run_analysis(inp), use_zone=_ZONE,
                             provided={"massing": True, "proposed_gfa": 2000.0})
    massing = next(s for s in out.stages if s.stage_id == "massing")
    assert massing.capacity is not None
    assert massing.capacity.far_pct == 250.0 and massing.capacity.bcr_pct == 60.0
    # 다른 단계엔 capacity 미부착(설계 massing 전용)
    assert all(s.capacity is None for s in out.stages if s.stage_id != "massing")
