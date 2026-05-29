"""Stage 3 실 IFC 온보딩 파이프라인 계약 테스트."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_SCRIPT = _BASE / "scripts" / "perf" / "onboard_real_ifc_fixtures.py"
_SOURCE = _SCRIPT.read_text(encoding="utf-8")
_REAL_SAMPLES = _BASE / "tests" / "fixtures" / "ifc" / "real_samples"


def test_onboarding_script_exposes_required_cli_options() -> None:
    assert "--incoming" in _SOURCE
    assert "--output-dir" in _SOURCE
    assert "--manifest" in _SOURCE
    assert "--source-label" in _SOURCE
    assert "--mode" in _SOURCE
    assert "--scrub-owner-data" in _SOURCE
    assert "--dry-run" in _SOURCE


def test_onboarding_script_dry_run_outputs_manifest_payload() -> None:
    result = subprocess.run(
        ["python", str(_SCRIPT), "--incoming", str(_REAL_SAMPLES), "--dry-run"],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["generated_by"].endswith("onboard_real_ifc_fixtures.py")
    assert payload["scrub_owner_data"] is True
    assert isinstance(payload["fixtures"], list)
    assert len(payload["fixtures"]) >= 3

    for fixture in payload["fixtures"]:
        assert fixture["id"]
        assert fixture["local_path"].endswith(".ifc")
        assert fixture["expected_schema"].startswith("IFC")
        assert fixture["expected_area_sqm"] > 0
        assert fixture["expected_volume_m3"] > 0
        assert fixture["expected_element_count"] > 0
        assert fixture["scrub_owner_data"] is False
        assert fixture["scrub_summary"] is None


def test_onboarding_script_writes_scrub_summary_when_enabled(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    manifest_path = tmp_path / "manifest.json"

    result = subprocess.run(
        [
            "python",
            str(_SCRIPT),
            "--incoming",
            str(_REAL_SAMPLES),
            "--output-dir",
            str(out_dir),
            "--manifest",
            str(manifest_path),
            "--id-prefix",
            "ci_fixture",
            "--mode",
            "copy",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert manifest_path.exists()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["scrub_owner_data"] is True
    assert len(payload["fixtures"]) >= 3

    for fixture in payload["fixtures"]:
        assert fixture["scrub_owner_data"] is True
        scrub_summary = fixture["scrub_summary"]
        assert isinstance(scrub_summary, dict)
        assert "person_count" in scrub_summary
        assert "organization_count" in scrub_summary
        assert "application_count" in scrub_summary
        assert "actor_count" in scrub_summary


def test_onboarding_script_disables_scrub_when_option_off(tmp_path: Path) -> None:
    out_dir = tmp_path / "out_noscrub"
    manifest_path = tmp_path / "manifest_noscrub.json"

    result = subprocess.run(
        [
            "python",
            str(_SCRIPT),
            "--incoming",
            str(_REAL_SAMPLES),
            "--output-dir",
            str(out_dir),
            "--manifest",
            str(manifest_path),
            "--id-prefix",
            "ci_fixture_noscrub",
            "--mode",
            "copy",
            "--no-scrub-owner-data",
        ],
        cwd=_BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["scrub_owner_data"] is False

    for fixture in payload["fixtures"]:
        assert fixture["scrub_owner_data"] is False
        assert fixture["scrub_summary"] is None
