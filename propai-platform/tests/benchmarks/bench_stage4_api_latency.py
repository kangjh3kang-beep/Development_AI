"""Stage 4 API p95 레이턴시 벤치 실행 검증."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.benchmark

_BASE = Path(__file__).resolve().parents[2]
_SCRIPT = _BASE / "scripts" / "perf" / "run_stage4_api_latency_benchmarks.py"
_API_VENV_PYTHON = _BASE / "apps" / "api" / ".venv" / "bin" / "python"


def _python_command() -> str:
    return str(_API_VENV_PYTHON) if _API_VENV_PYTHON.exists() else "python"


class TestStage4ApiLatencyBenchmark:
    def test_api_latency_targets_are_measured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_json = tmp_path / "stage4_api_latency_report.json"
            out_md = tmp_path / "stage4_api_latency_report.md"

            result = subprocess.run(
                [
                    _python_command(),
                    str(_SCRIPT),
                    "--attempts",
                    "8",
                    "--warmup",
                    "1",
                    "--output-json",
                    str(out_json),
                    "--output-md",
                    str(out_md),
                ],
                cwd=_BASE,
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )

            assert result.returncode == 0, result.stderr
            payload = json.loads(out_json.read_text(encoding="utf-8"))

            assert payload["targets"]["api_p95_sec_max"] == 0.2
            assert payload["authenticated_profile"]["enabled"] is False
            assert len(payload["endpoints"]) >= 2
            assert all(item["kind"] == "public" for item in payload["endpoints"])
            assert all(item["status_ok"] for item in payload["endpoints"])
            assert all(item["latency"]["p95_sec"] > 0 for item in payload["endpoints"])
            assert all(item["timeout_count"] == 0 for item in payload["endpoints"])
