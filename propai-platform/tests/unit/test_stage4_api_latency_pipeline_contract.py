"""Stage 4 API 레이턴시 벤치 파이프라인 계약 테스트."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_SCRIPT = _BASE / "scripts" / "perf" / "run_stage4_api_latency_benchmarks.py"
_API_VENV_PYTHON = _BASE / "apps" / "api" / ".venv" / "bin" / "python"


def _python_command() -> str:
    return str(_API_VENV_PYTHON) if _API_VENV_PYTHON.exists() else "python"


class TestStage4ApiLatencyPipeline:
    def test_stage4_script_emits_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_json = tmp_path / "report.json"
            out_md = tmp_path / "report.md"

            result = subprocess.run(
                [
                    _python_command(),
                    str(_SCRIPT),
                    "--attempts",
                    "5",
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
                env={**os.environ, "PROPAI_STRICT_API_GATE": "0"},
            )

            assert result.returncode == 0, result.stderr
            assert out_json.exists()
            assert out_md.exists()

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            assert "targets" in payload
            assert payload["targets"]["api_p95_sec_max"] == 0.2
            assert payload["authenticated_profile"]["enabled"] is False
            assert "endpoints" in payload
            assert len(payload["endpoints"]) >= 2
            assert all(item["kind"] == "public" for item in payload["endpoints"])
            assert all("latency" in item for item in payload["endpoints"])
            assert all("p95_sec" in item["latency"] for item in payload["endpoints"])
            assert all(item["timeout_count"] == 0 for item in payload["endpoints"])

    def test_stage4_strict_gate_fail_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_json = tmp_path / "report.json"
            out_md = tmp_path / "report.md"

            result = subprocess.run(
                [
                    _python_command(),
                    str(_SCRIPT),
                    "--attempts",
                    "3",
                    "--warmup",
                    "0",
                    "--p95-max-sec",
                    "0.000001",
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
                timeout=90,
                env={**os.environ, "PROPAI_STRICT_API_GATE": "0"},
            )

            assert result.returncode == 2
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            assert payload["overall_pass"] is False

    def test_stage4_authenticated_mode_is_timeout_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            out_json = tmp_path / "report.json"
            out_md = tmp_path / "report.md"

            result = subprocess.run(
                [
                    _python_command(),
                    str(_SCRIPT),
                    "--attempts",
                    "1",
                    "--warmup",
                    "0",
                    "--include-authenticated",
                    "--authenticated-endpoints",
                    "/api/v1/system/version",
                    "--request-timeout-sec",
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
                env={**os.environ, "PROPAI_STRICT_API_GATE": "0"},
            )

            assert result.returncode == 0, result.stderr
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            assert payload["authenticated_profile"]["enabled"] is True
            assert any(item["kind"] == "authenticated" for item in payload["endpoints"])
