"""Stage 3 실 IFC 교체 오케스트레이션 계약 테스트."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_SCRIPT = _BASE / "scripts" / "perf" / "refresh_real_ifc_pipeline.py"
_SOURCE = _SCRIPT.read_text(encoding="utf-8")
_REAL_SAMPLES = _BASE / "tests" / "fixtures" / "ifc" / "real_samples"


def test_refresh_pipeline_script_exposes_required_cli_options() -> None:
    assert "--incoming" in _SOURCE
    assert "--output-dir" in _SOURCE
    assert "--manifest" in _SOURCE
    assert "--source-label" in _SOURCE
    assert "--validate-incoming" in _SOURCE
    assert "--min-ifc-files" in _SOURCE
    assert "--incoming-validation-report" in _SOURCE
    assert "--fail-on-duplicate-hash" in _SOURCE
    assert "--max-file-size-mb" in _SOURCE
    assert "--expect-incoming-empty-after-move" in _SOURCE
    assert "--require-real-ifc-min" in _SOURCE
    assert "--skip-benchmark" in _SOURCE
    assert "--dry-run" in _SOURCE


def test_refresh_pipeline_supports_dry_run_onboarding() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(_REAL_SAMPLES),
            "--no-validate-incoming",
            "--dry-run",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["generated_by"].endswith("onboard_real_ifc_fixtures.py")
    assert isinstance(payload["fixtures"], list)
    assert len(payload["fixtures"]) >= 3


def test_refresh_pipeline_move_mode_clears_incoming(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    output_dir = tmp_path / "real_samples"
    manifest_path = tmp_path / "manifest.json"
    validation_report_path = tmp_path / "incoming_validation_report.json"

    incoming.mkdir(parents=True, exist_ok=True)
    for src in sorted(_REAL_SAMPLES.glob("*.ifc")):
        shutil.copy2(src, incoming / src.name)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(incoming),
            "--output-dir",
            str(output_dir),
            "--manifest",
            str(manifest_path),
            "--incoming-validation-report",
            str(validation_report_path),
            "--keep-original-name",
            "--mode",
            "move",
            "--source-label",
            "contract-test",
            "--skip-benchmark",
            "--require-real-ifc-min",
            "3",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert manifest_path.exists()
    remaining = list(incoming.glob("*.ifc"))
    assert len(remaining) == 0


def test_refresh_pipeline_fails_when_move_mode_does_not_clear_incoming(tmp_path: Path) -> None:
    workspace = tmp_path / "same_dir"
    workspace.mkdir(parents=True, exist_ok=True)

    for src in sorted(_REAL_SAMPLES.glob("*.ifc")):
        shutil.copy2(src, workspace / src.name)

    manifest_path = tmp_path / "manifest_same_dir.json"
    validation_report_path = tmp_path / "incoming_validation_same_dir.json"

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(workspace),
            "--output-dir",
            str(workspace),
            "--manifest",
            str(manifest_path),
            "--incoming-validation-report",
            str(validation_report_path),
            "--keep-original-name",
            "--mode",
            "move",
            "--source-label",
            "contract-test",
            "--skip-benchmark",
            "--require-real-ifc-min",
            "3",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "mode=move 이후 incoming에 IFC 파일이 남아있습니다" in result.stderr
