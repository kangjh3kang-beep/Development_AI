"""INC-DL2 — 건축설계 라이프사이클 실행기(시스템2). 시스템1 run_process 재사용(프로세스-불문).

run_design_process: AnalysisResult + design 스펙 → ProcessResult(설계 단계 로드맵 + 완결성/법규여유/검증).
provided는 산출물 존재 표시(기획/매스/배치/평면) — 단계 required_inputs 충족 판정(완결성, 무음 금지). 결정론.
"""
from __future__ import annotations

from app.contracts.analysis import AnalysisResult
from app.contracts.permit_result import ProcessResult
from app.services.design.design_spec_loader import load_design_spec
from app.services.permit.executor import run_process


def run_design_process(result: AnalysisResult, *, use_zone: str | None = None,
                       dev_type: str | None = None,
                       provided: dict | None = None) -> ProcessResult:
    """설계 라이프사이클 프로세스 — 동일 실행기에 design 스펙 주입. provided=산출물 존재 표시(완결성)."""
    return run_process(result, load_design_spec(), dev_type=dev_type, use_zone=use_zone,
                       provided_inputs=provided)
