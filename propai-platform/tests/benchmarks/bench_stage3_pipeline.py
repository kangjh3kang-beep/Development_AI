"""Stage 3 통합 벤치 파이프라인 실행 검증.

실행:
  pytest tests/benchmarks/bench_stage3_pipeline.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.benchmark

_BASE = Path(__file__).resolve().parents[2]
_SCRIPT = _BASE / "scripts" / "perf" / "run_stage3_benchmarks.py"


class TestStage3BenchmarkPipeline:
    """Stage 3 자동 벤치 파이프라인 계약/실행 검증."""

    def test_stage3_script_executes_and_emits_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_json = tmp_path / "report.json"
            out_md = tmp_path / "report.md"

            result = subprocess.run(
                [
                    "python",
                    str(_SCRIPT),
                    "--attempts",
                    "2",
                    "--n-simulations",
                    "10000",
                    "--output-json",
                    str(out_json),
                    "--output-md",
                    str(out_md),
                ],
                cwd=_BASE,
                capture_output=True,
                text=True,
                check=False,
            )

            assert result.returncode == 0, result.stderr
            assert out_json.exists()
            assert out_md.exists()

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            assert "ifc_accuracy" in payload
            assert "real_ifc_fixtures" in payload
            assert "monte_carlo" in payload
            assert payload["ifc_accuracy"]["pass_target"] is True
            assert payload["real_ifc_fixtures"]["fixture_count"] >= 3
            assert payload["monte_carlo"]["n_simulations"] == 10000
            assert payload["monte_carlo"]["p95_sec"] > 0
            assert payload["targets"]["ifc_mae_max"] == 0.02
            assert payload["targets"]["monte_carlo_p95_sec_max"] == 30.0

            if os.getenv("PROPAI_STRICT_PERF_GATE") == "1":
                assert payload["overall_pass"] is True

    def test_stage3_strict_gate_fails_when_real_ifc_min_requirement_not_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_json = tmp_path / "report.json"
            out_md = tmp_path / "report.md"

            result = subprocess.run(
                [
                    "python",
                    str(_SCRIPT),
                    "--attempts",
                    "1",
                    "--n-simulations",
                    "1000",
                    "--require-real-ifc-min",
                    "99",
                    "--fail-on-target-miss",
                    "--output-json",
                    str(out_json),
                    "--output-md",
                    str(out_md),
                ],
                cwd=_BASE,
                capture_output=True,
                text=True,
                check=False,
            )

            assert result.returncode == 2
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            assert payload["real_ifc_fixtures"]["requirement_met"] is False
            assert payload["overall_pass"] is False
