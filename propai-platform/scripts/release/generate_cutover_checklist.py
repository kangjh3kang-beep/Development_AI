#!/usr/bin/env python3
"""Generate markdown and JSON cutover checklist artifacts from a release report."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.cutover_checklist import (
    build_cutover_checklist,
    load_release_report,
    render_cutover_markdown,
    write_cutover_checklist,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate cutover checklist artifacts.")
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--json-output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_release_report(Path(args.report_json))
    checklist = build_cutover_checklist(report)
    markdown_path = Path(args.markdown_output)
    json_path = Path(args.json_output)
    write_cutover_checklist(checklist, markdown_path=markdown_path, json_path=json_path)

    markdown = render_cutover_markdown(checklist)
    print(markdown)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as handle:
            handle.write("\n")
            handle.write(markdown)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
