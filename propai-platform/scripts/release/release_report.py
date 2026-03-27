"""Release evidence report generation helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

EXPECTED_EVIDENCE_FILES = (
    "rollout-api.log",
    "rollout-web.log",
    "rollout-worker.log",
    "kubectl-overview.txt",
    "kubectl-pods.json",
    "kubectl-events.log",
    "release-smoke.log",
    "observability-smoke.log",
)


@dataclass(slots=True)
class ReleaseArtifact:
    name: str
    size_bytes: int


@dataclass(slots=True)
class ReleaseEvidenceReport:
    target: str
    workflow_name: str
    git_ref: str
    commit_sha: str
    generated_at: str
    namespace: str | None = None
    workflow_run_url: str | None = None
    step_statuses: dict[str, str] = field(default_factory=dict)
    image_refs: dict[str, str] = field(default_factory=dict)
    artifacts: list[ReleaseArtifact] = field(default_factory=list)
    missing_expected_artifacts: list[str] = field(default_factory=list)
    recommendation: str = ""


def _normalize_status(value: str | None) -> str:
    if not value:
        return "skipped"
    normalized = value.strip().lower()
    if normalized in {"success", "failure", "cancelled", "skipped"}:
        return normalized
    return "unknown"


def _build_recommendation(
    step_statuses: dict[str, str],
    missing_artifacts: list[str],
) -> str:
    values = set(step_statuses.values())
    if "failure" in values or "cancelled" in values:
        return "Hold release: at least one rehearsal gate failed."
    if missing_artifacts:
        return "Manual review required: rehearsal evidence is incomplete."
    if "skipped" in values:
        return "Proceed with caution: at least one rehearsal gate was skipped."
    return "Ready for cutover review: rehearsal evidence is complete and all coded gates passed."


def build_release_evidence_report(
    *,
    target: str,
    workflow_name: str,
    git_ref: str,
    commit_sha: str,
    artifact_dir: Path,
    step_statuses: dict[str, str],
    image_refs: dict[str, str],
    namespace: str | None = None,
    workflow_run_url: str | None = None,
) -> ReleaseEvidenceReport:
    normalized_steps = {key: _normalize_status(value) for key, value in step_statuses.items()}
    artifacts = [
        ReleaseArtifact(name=path.name, size_bytes=path.stat().st_size)
        for path in sorted(artifact_dir.glob("*"))
        if path.is_file()
    ]
    artifact_names = {artifact.name for artifact in artifacts}
    missing_artifacts = [name for name in EXPECTED_EVIDENCE_FILES if name not in artifact_names]

    report = ReleaseEvidenceReport(
        target=target,
        workflow_name=workflow_name,
        git_ref=git_ref,
        commit_sha=commit_sha,
        namespace=namespace,
        workflow_run_url=workflow_run_url,
        generated_at=datetime.now(UTC).isoformat(),
        step_statuses=normalized_steps,
        image_refs={key: value for key, value in image_refs.items() if value},
        artifacts=artifacts,
        missing_expected_artifacts=missing_artifacts,
    )
    report.recommendation = _build_recommendation(normalized_steps, missing_artifacts)
    return report


def render_release_markdown(report: ReleaseEvidenceReport) -> str:
    lines = [
        f"# {report.target.title()} Release Rehearsal Report",
        "",
        f"- Workflow: `{report.workflow_name}`",
        f"- Git ref: `{report.git_ref}`",
        f"- Commit: `{report.commit_sha}`",
        f"- Generated at: `{report.generated_at}`",
    ]
    if report.namespace:
        lines.append(f"- Namespace: `{report.namespace}`")
    if report.workflow_run_url:
        lines.append(f"- Workflow run: {report.workflow_run_url}")

    lines.extend(["", "## Step Status", ""])
    for key, value in report.step_statuses.items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Images", ""])
    if report.image_refs:
        for key, value in report.image_refs.items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No image refs recorded.")

    lines.extend(["", "## Artifacts", ""])
    if report.artifacts:
        for artifact in report.artifacts:
            lines.append(f"- `{artifact.name}` ({artifact.size_bytes} bytes)")
    else:
        lines.append("- No artifacts captured.")

    lines.extend(["", "## Missing Expected Artifacts", ""])
    if report.missing_expected_artifacts:
        for name in report.missing_expected_artifacts:
            lines.append(f"- `{name}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Recommendation", "", report.recommendation, ""])
    return "\n".join(lines)


def write_release_report(
    report: ReleaseEvidenceReport,
    *,
    markdown_path: Path,
    json_path: Path,
) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_release_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(asdict(report), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
