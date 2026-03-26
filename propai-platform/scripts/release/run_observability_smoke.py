#!/usr/bin/env python3
"""CLI wrapper for post-deploy observability smoke validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.release_hardening import ReleaseSmokeError, run_observability_smoke


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run post-deploy observability smoke checks.")
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--alertmanager-url", required=True)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--grafana-api-key")
    parser.add_argument("--timeout", type=float, default=8.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        checks = run_observability_smoke(
            args.target,
            prometheus_url=args.prometheus_url,
            alertmanager_url=args.alertmanager_url,
            grafana_url=args.grafana_url,
            grafana_api_key=args.grafana_api_key,
            timeout=args.timeout,
        )
    except ReleaseSmokeError as exc:
        print(f"[FAIL] {exc}")
        return 1

    for item in checks:
        print(f"[PASS] {item}")
    print("Observability smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
