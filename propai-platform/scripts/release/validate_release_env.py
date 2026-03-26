#!/usr/bin/env python3
"""CLI wrapper for release environment validation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_hardening import validate_release_environment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate required deployment secrets and URLs.")
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="Additional env var names that must be present for this release target.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_release_environment(
        args.target,
        os.environ,
        extra_required=tuple(args.require),
    )

    print(f"Release environment validation target: {report.target}")
    if report.issues:
        for issue in report.issues:
            print(f"[{issue.level.upper()}] {issue.key}: {issue.message}")
    else:
        print("No validation issues found.")

    if report.errors:
        print("Release preflight failed.")
        return 1

    print("Release preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
