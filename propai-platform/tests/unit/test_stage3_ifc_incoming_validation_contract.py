"""Stage 3 incoming IFC 검증기 계약 테스트."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_SCRIPT = _BASE / "scripts" / "perf" / "validate_real_ifc_incoming.py"
_SOURCE = _SCRIPT.read_text(encoding="utf-8")
_REAL_SAMPLES = _BASE / "tests" / "fixtures" / "ifc" / "real_samples"


def test_incoming_validator_script_exposes_required_cli_options() -> None:
    assert "--incoming" in _SOURCE
    assert "--min-ifc-files" in _SOURCE
    assert "--report" in _SOURCE
    assert "--require-positive-quantities" in _SOURCE
    assert "--fail-on-duplicate-hash" in _SOURCE
    assert "--max-file-size-mb" in _SOURCE
    assert "--dry-run" in _SOURCE


def test_incoming_validator_dry_run_passes_on_real_samples() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(_REAL_SAMPLES),
            "--min-ifc-files",
            "3",
            "--dry-run",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["file_count"] >= 3
    assert summary["parsed_count"] >= 3
    assert summary["parse_failed_count"] == 0
    assert summary["overall_pass"] is True


def test_incoming_validator_fails_when_min_file_requirement_not_met(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(tmp_path),
            "--min-ifc-files",
            "1",
            "--dry-run",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["file_count"] == 0
    assert summary["overall_pass"] is False


def test_incoming_validator_fails_on_duplicate_hash_by_default(tmp_path: Path) -> None:
    src = _REAL_SAMPLES / "residential_block_a.ifc"
    shutil.copy2(src, tmp_path / "a.ifc")
    shutil.copy2(src, tmp_path / "b.ifc")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(tmp_path),
            "--min-ifc-files",
            "2",
            "--dry-run",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["duplicate_hash_count"] >= 1
    assert summary["duplicate_pass"] is False
    assert summary["overall_pass"] is False


def test_incoming_validator_allows_duplicate_hash_when_disabled(tmp_path: Path) -> None:
    src = _REAL_SAMPLES / "residential_block_a.ifc"
    shutil.copy2(src, tmp_path / "a.ifc")
    shutil.copy2(src, tmp_path / "b.ifc")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(tmp_path),
            "--min-ifc-files",
            "2",
            "--no-fail-on-duplicate-hash",
            "--dry-run",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["duplicate_hash_count"] >= 1
    assert summary["duplicate_pass"] is True
    assert summary["overall_pass"] is True


def test_incoming_validator_fails_when_file_size_exceeds_limit(tmp_path: Path) -> None:
    src = _REAL_SAMPLES / "residential_block_a.ifc"
    shutil.copy2(src, tmp_path / src.name)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--incoming",
            str(tmp_path),
            "--min-ifc-files",
            "1",
            "--max-file-size-mb",
            "0.0001",
            "--dry-run",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["file_count"] == 1
    assert summary["size_pass"] is False
    assert summary["overall_pass"] is False
