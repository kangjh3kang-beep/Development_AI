"""Cutover checklist generation helpers for release rehearsal evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts.release.release_report import ReleaseEvidenceReport

UTC = timezone.utc


@dataclass(slots=True)
class CutoverChecklistItem:
    key: str
    title: str
    status: str
    detail: str


@dataclass(slots=True)
class ReleaseCutoverChecklist:
    target: str
    generated_at: str
    source_report_generated_at: str
    source_recommendation: str
    overall_status: str
    blockers: list[str] = field(default_factory=list)
    items: list[CutoverChecklistItem] = field(default_factory=list)


def _status_from_step(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "success":
        return "done"
    if normalized in {"failure", "cancelled"}:
        return "blocked"
    return "manual-review"


def _detail_from_step(step_name: str, value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "success":
        return f"{step_name} passed."
    if normalized in {"failure", "cancelled"}:
        return f"{step_name} did not complete successfully."
    if normalized == "skipped":
        return f"{step_name} was skipped and needs operator review."
    return f"{step_name} outcome is unavailable."


def load_release_report(path: Path) -> ReleaseEvidenceReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReleaseEvidenceReport(
        target=payload["target"],
        workflow_name=payload["workflow_name"],
        git_ref=payload["git_ref"],
        commit_sha=payload["commit_sha"],
        generated_at=payload["generated_at"],
        namespace=payload.get("namespace"),
        workflow_run_url=payload.get("workflow_run_url"),
        step_statuses=dict(payload.get("step_statuses", {})),
        image_refs=dict(payload.get("image_refs", {})),
        artifacts=[],
        missing_expected_artifacts=list(payload.get("missing_expected_artifacts", [])),
        recommendation=payload.get("recommendation", ""),
    )


def build_cutover_checklist(report: ReleaseEvidenceReport) -> ReleaseCutoverChecklist:
    items: list[CutoverChecklistItem] = []

    for key, title in (
        ("preflight", "Release environment contract"),
        ("build", "Deploy images built and pinned"),
        ("rollout", "Kubernetes rollout completed"),
        ("release_smoke", "Post-deploy release smoke"),
        ("observability_smoke", "Observability smoke"),
    ):
        step_value = report.step_statuses.get(key, "")
        items.append(
            CutoverChecklistItem(
                key=key,
                title=title,
                status=_status_from_step(step_value),
                detail=_detail_from_step(title, step_value),
            )
        )

    image_count = sum(1 for value in report.image_refs.values() if value)
    image_status = "done" if image_count == 3 else "manual-review"
    items.append(
        CutoverChecklistItem(
            key="image_refs",
            title="Release image references recorded",
            status=image_status,
            detail=(
                "API, web, and worker image refs were recorded."
                if image_status == "done"
                else "One or more release image refs are missing."
            ),
        )
    )

    evidence_status = "done" if not report.missing_expected_artifacts else "blocked"
    items.append(
        CutoverChecklistItem(
            key="evidence_bundle",
            title="Release evidence bundle complete",
            status=evidence_status,
            detail=(
                "All expected rollout, smoke, and kubectl artifacts are present."
                if evidence_status == "done"
                else "Missing evidence: " + ", ".join(report.missing_expected_artifacts)
            ),
        )
    )

    blockers = [item.title for item in items if item.status == "blocked"]
    manual_review_items = [item.title for item in items if item.status == "manual-review"]

    if blockers:
        overall_status = "no-go"
    elif manual_review_items:
        overall_status = "manual-review"
    else:
        overall_status = "ready-for-review"

    return ReleaseCutoverChecklist(
        target=report.target,
        generated_at=datetime.now(UTC).isoformat(),
        source_report_generated_at=report.generated_at,
        source_recommendation=report.recommendation,
        overall_status=overall_status,
        blockers=blockers,
        items=items,
    )


def render_cutover_markdown(checklist: ReleaseCutoverChecklist) -> str:
    lines = [
        f"# {checklist.target.title()} Cutover Checklist",
        "",
        f"- Overall status: `{checklist.overall_status}`",
        f"- Generated at: `{checklist.generated_at}`",
        f"- Source report generated at: `{checklist.source_report_generated_at}`",
        f"- Source recommendation: {checklist.source_recommendation}",
        "",
        "## Blocking Items",
        "",
    ]
    if checklist.blockers:
        for blocker in checklist.blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- None")

    lines.extend(["", "## Checklist", ""])
    for item in checklist.items:
        checkbox = "[x]" if item.status == "done" else "[ ]"
        lines.append(f"- {checkbox} {item.title} (`{item.status}`)")
        lines.append(f"  {item.detail}")

    lines.append("")
    return "\n".join(lines)


def write_cutover_checklist(
    checklist: ReleaseCutoverChecklist,
    *,
    markdown_path: Path,
    json_path: Path,
) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_cutover_markdown(checklist), encoding="utf-8")
    json_path.write_text(
        json.dumps(asdict(checklist), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
