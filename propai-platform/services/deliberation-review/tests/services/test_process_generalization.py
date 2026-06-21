"""INC-DL1 — process-agnostic 일반화: 일반 명칭(ProcessSpec/ProcessResult/run_process) + permit 별칭 동일성."""
from app.contracts.permit_process import PermitProcessSpec, ProcessSpec
from app.contracts.permit_result import PermitProcessResult, ProcessResult
from app.services.permit.executor import run_permit_process, run_process


def test_generic_aliases_are_identical_to_permit_names():
    # 후방호환: 별칭이 동일 객체(시스템1 permit 코드 무파손) + 일반 명칭 제공(design 재사용).
    assert ProcessSpec is PermitProcessSpec
    assert ProcessResult is PermitProcessResult
    assert run_process is run_permit_process


def test_process_spec_constructs_under_generic_name():
    spec = ProcessSpec(spec_id="design-default", version="v1", effective_date="2026-01-01", stages=[])
    assert spec.spec_id == "design-default" and isinstance(spec, PermitProcessSpec)
