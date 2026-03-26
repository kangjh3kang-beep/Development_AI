#!/usr/bin/env python3
"""CLI wrapper for post-deploy release smoke validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_hardening import ReleaseSmokeError, run_release_smoke


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run post-deploy release smoke checks.")
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--web-base-url", required=True)
    parser.add_argument("--access-token")
    parser.add_argument("--project-id")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument(
        "--route",
        action="append",
        default=[],
        help="Optional additional or replacement web routes to verify. Repeat as needed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    routes = tuple(args.route) if args.route else None
    try:
        checks = run_release_smoke(
            args.target,
            api_base_url=args.api_base_url,
            web_base_url=args.web_base_url,
            access_token=args.access_token,
            routes=routes,
            project_id=args.project_id,
            timeout=args.timeout,
        )
    except ReleaseSmokeError as exc:
        print(f"[FAIL] {exc}")
        return 1

    for item in checks:
        print(f"[PASS] {item}")
    print("Release smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
