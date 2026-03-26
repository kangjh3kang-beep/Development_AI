#!/usr/bin/env python3
"""Validate static release rehearsal assets and deployment contracts."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_hardening import validate_release_assets


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    report = validate_release_assets(repo_root)

    print("Release asset validation")
    for issue in report.issues:
        print(f"[{issue.level.upper()}] {issue.key}: {issue.message}")
    if not report.issues:
        print("No release asset issues found.")

    if report.errors:
        print("Release asset validation failed.")
        return 1

    print("Release asset validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
