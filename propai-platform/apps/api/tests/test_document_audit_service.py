"""SP3-4: 자료교환 8엔진 투입 서비스 — 요약·라우팅(결정론, 실엔진/ezdxf 불필요).

orchestrator.run은 use_llm을 폐기하는 결정론 전용이라 본 서비스도 LLM=0. 변환기·오케스트레이터를
주입해 DXF/IFC 라우팅과 결과 요약을 검증한다(문서형식은 unsupported 정직 표기).
"""

import asyncio

from app.services.collaboration.document_audit_service import (
    run_design_document_audit,
    summarize_audit,
)

RESULT = {
    "findings": [{"status": "pass"}, {"status": "warning"}, {"status": "skipped"}],
    "overall": {
        "verdict": "조건부적합",
        "verdict_en": "conditional",
        "counts": {"pass": 1, "warning": 1, "skipped": 1},
    },
    "engines": {
        "rules8": "ok", "design_review": "ok", "permit": "ok",
        "parking": "failed", "solar_envelope": "failed",
    },
}


class _FakeOrch:
    def __init__(self, result):
        self.result = result
        self.kw = None

    async def run(self, db, **kw):
        self.kw = kw
        return self.result


class TestSummarizeAudit:
    def test_extracts_verdict_counts_engines(self):
        s = summarize_audit(RESULT)
        assert s["verdict"] == "조건부적합"
        assert s["verdict_en"] == "conditional"
        assert s["findings_count"] == 3
        assert s["engines_run"] == 3        # ok 엔진 수
        assert s["engines_skipped"] == 2    # ok 아닌 엔진 수(failed 등)
        assert s["counts"] == {"pass": 1, "warning": 1, "skipped": 1}

    def test_empty_result_safe(self):
        s = summarize_audit({})
        assert s["findings_count"] == 0
        assert s["engines_run"] == 0
        assert s["engines_skipped"] == 0
        assert s["verdict"] is None


class TestRouting:
    def test_document_format_unsupported_no_orchestrator(self):
        # PDF 등 문서는 8엔진 미투입 — unsupported(정직). 오케스트레이터 호출 안 함.
        st, summ = asyncio.run(
            run_design_document_audit(None, filename="traffic-report.pdf", data=b"x")
        )
        assert st == "unsupported"
        assert summ is None

    def test_dxf_invokes_orchestrator_with_geometry(self):
        orch = _FakeOrch(RESULT)
        st, summ = asyncio.run(
            run_design_document_audit(
                None,
                filename="plan.dxf",
                data=b"DXFBYTES",
                convert_dxf=lambda data: ({"shapes": [1, 2]}, [{"id": "r1"}]),
                orchestrator=orch,
            )
        )
        assert st == "completed"
        assert summ["findings_count"] == 3
        assert orch.kw["geometry"] == {"shapes": [1, 2]}
        assert orch.kw["rooms"] == [{"id": "r1"}]

    def test_ifc_invokes_orchestrator_with_path(self):
        orch = _FakeOrch(RESULT)
        st, summ = asyncio.run(
            run_design_document_audit(
                None, filename="model.IFC", data=b"IFCDATA", orchestrator=orch
            )
        )
        assert st == "completed"
        assert "ifc_file_url" in orch.kw
        assert orch.kw["ifc_file_url"].endswith(".ifc")
