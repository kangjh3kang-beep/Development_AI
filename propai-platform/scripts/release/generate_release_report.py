#!/usr/bin/env python3
"""Generate markdown and JSON evidence for a release rehearsal run."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_report import build_release_evidence_report, write_release_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate release rehearsal evidence artifacts.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--git-ref", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--namespace")
    parser.add_argument("--workflow-run-url")
    parser.add_argument("--preflight-status")
    parser.add_argument("--build-status")
    parser.add_argument("--rollout-status")
    parser.add_argument("--release-smoke-status")
    parser.add_argument("--observability-smoke-status")
    parser.add_argument("--api-image")
    parser.add_argument("--web-image")
    parser.add_argument("--worker-image")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_release_evidence_report(
        target=args.target,
        workflow_name=args.workflow_name,
        git_ref=args.git_ref,
        commit_sha=args.commit_sha,
        namespace=args.namespace,
        workflow_run_url=args.workflow_run_url,
        artifact_dir=Path(args.artifact_dir),
        step_statuses={
            "preflight": args.preflight_status or "",
            "build": args.build_status or "",
            "rollout": args.rollout_status or "",
            "release_smoke": args.release_smoke_status or "",
            "observability_smoke": args.observability_smoke_status or "",
        },
        image_refs={
            "api": args.api_image or "",
            "web": args.web_image or "",
            "worker": args.worker_image or "",
        },
    )
    markdown_path = Path(args.markdown_output)
    json_path = Path(args.json_output)
    write_release_report(report, markdown_path=markdown_path, json_path=json_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    print(markdown)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
