#!/usr/bin/env python3
"""Stage 4 API 레이턴시 벤치마크.

목표:
- 주요 API 엔드포인트 p95 레이턴시 <= 200ms

실행:
  python scripts/perf/run_stage4_api_latency_benchmarks.py
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from uuid import UUID

import httpx


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
LEGACY_API_ROOT = ROOT_DIR / "apps" / "api"
if str(LEGACY_API_ROOT) not in sys.path:
    sys.path.insert(0, str(LEGACY_API_ROOT))
DEFAULT_OUTPUT_JSON = ROOT_DIR / "_workspace" / "review" / "perf" / "stage4_api_latency_report.json"
DEFAULT_OUTPUT_MD = ROOT_DIR / "_workspace" / "review" / "perf" / "stage4_api_latency_report.md"

DEFAULT_ENDPOINTS = (
    "/api/v1/system/integration/status",
    "/api/latest",
)
DEFAULT_AUTHENTICATED_ENDPOINTS = (
    "/api/v1/system/version",
)
DEFAULT_P95_MAX_SECONDS = 0.2  # 200ms
DEFAULT_REQUEST_TIMEOUT_SECONDS = 2.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * percentile
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


async def _measure_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    *,
    attempts: int,
    warmup: int,
    request_timeout_sec: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async def _timed_get() -> tuple[int, float, bool]:
        start = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                client.get(endpoint, headers=headers),
                timeout=request_timeout_sec,
            )
            return response.status_code, time.perf_counter() - start, False
        except TimeoutError:
            return 598, time.perf_counter() - start, True

    warmup_timeouts = 0
    for _ in range(warmup):
        _, _, timed_out = await _timed_get()
        if timed_out:
            warmup_timeouts += 1
            break

    durations: list[float] = []
    statuses: list[int] = []
    timeout_count = 0

    for _ in range(attempts):
        status_code, duration, timed_out = await _timed_get()
        durations.append(duration)
        statuses.append(status_code)
        if timed_out:
            timeout_count += 1
            # ASGI in-process deadlock 계열은 첫 timeout 이후 연속 재현되는 경우가 많아 조기 중단한다.
            break

    status_ok = (
        timeout_count == 0
        and len(statuses) == attempts
        and all(200 <= status < 400 for status in statuses)
    )
    p95 = _percentile(durations, 0.95)
    avg = statistics.fmean(durations) if durations else 0.0

    return {
        "endpoint": endpoint,
        "attempts": attempts,
        "warmup": warmup,
        "completed_attempts": len(statuses),
        "statuses": statuses,
        "status_ok": status_ok,
        "timeout_count": timeout_count,
        "warmup_timeout_count": warmup_timeouts,
        "latency": {
            "p95_sec": round(p95, 4),
            "avg_sec": round(avg, 4),
            "min_sec": round(min(durations), 4) if durations else 0.0,
            "max_sec": round(max(durations), 4) if durations else 0.0,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 4 API latency benchmark")
    parser.add_argument("--attempts", type=int, default=20, help="엔드포인트별 측정 반복 횟수")
    parser.add_argument("--warmup", type=int, default=2, help="엔드포인트별 워밍업 횟수")
    parser.add_argument(
        "--endpoints",
        nargs="+",
        default=list(DEFAULT_ENDPOINTS),
        help="측정할 API 경로 목록 (예: /health /api/v1/system/integration/status)",
    )
    parser.add_argument(
        "--p95-max-sec",
        type=float,
        default=DEFAULT_P95_MAX_SECONDS,
        help="p95 최대 허용값(초), 기본 0.2(200ms)",
    )
    parser.add_argument(
        "--include-authenticated",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="인증 필요 엔드포인트 레이턴시 측정 포함 여부 (기본 false)",
    )
    parser.add_argument(
        "--authenticated-endpoints",
        nargs="+",
        default=list(DEFAULT_AUTHENTICATED_ENDPOINTS),
        help="인증 필요 API 경로 목록 (예: /api/v1/system/version)",
    )
    parser.add_argument(
        "--auth-role",
        default="admin",
        choices=["admin", "manager", "analyst", "viewer"],
        help="인증 토큰 role 클레임 (기본 admin)",
    )
    parser.add_argument(
        "--request-timeout-sec",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        help="요청 1회당 최대 대기시간(초). 타임아웃 시 해당 엔드포인트는 즉시 FAIL 처리",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="JSON 리포트 경로",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Markdown 리포트 경로",
    )
    parser.add_argument(
        "--fail-on-target-miss",
        action="store_true",
        help="목표 미달 시 exit code 2로 실패",
    )
    return parser.parse_args()


def _build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 4 API Latency Report",
        "",
        f"- 생성 시각(UTC): {report['generated_at_utc']}",
        f"- 전체 판정: {'PASS' if report['overall_pass'] else 'FAIL'}",
        "",
        "## 목표",
        f"- API p95 <= {report['targets']['api_p95_sec_max']:.3f}초",
        f"- 요청 타임아웃 <= {report['targets']['request_timeout_sec']:.3f}초",
        f"- 인증 엔드포인트 측정 포함: {'YES' if report['authenticated_profile']['enabled'] else 'NO'}",
        "",
        "## 엔드포인트 결과",
    ]
    for item in report["endpoints"]:
        lines.append(
            (
                f"- `{item['endpoint']}` ({item['kind']}): "
                f"p95 {item['latency']['p95_sec']:.4f}초, "
                f"평균 {item['latency']['avg_sec']:.4f}초, "
                f"timeout {item['timeout_count']}회, "
                f"상태검증 {'PASS' if item['status_ok'] else 'FAIL'}, "
                f"판정 {'PASS' if item['pass_target'] else 'FAIL'}"
            )
        )
    return "\n".join(lines) + "\n"


def _build_auth_headers(*, role: str) -> dict[str, str]:
    from apps.api.auth.jwt_handler import create_access_token
    from apps.api.config import get_settings

    settings = get_settings()
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    tenant_id = UUID("22222222-2222-2222-2222-222222222222")
    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        settings=settings,
    )
    return {"Authorization": f"Bearer {token}"}


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    from apps.api.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0) as client:
        endpoint_results: list[dict[str, Any]] = []
        for endpoint in args.endpoints:
            measured = await _measure_endpoint(
                client,
                endpoint,
                attempts=args.attempts,
                warmup=args.warmup,
                request_timeout_sec=args.request_timeout_sec,
                headers=None,
            )
            measured["kind"] = "public"
            measured["pass_target"] = (
                measured["status_ok"] and measured["latency"]["p95_sec"] <= args.p95_max_sec
            )
            endpoint_results.append(measured)

        if args.include_authenticated:
            auth_headers = _build_auth_headers(role=args.auth_role)
            for endpoint in args.authenticated_endpoints:
                measured = await _measure_endpoint(
                    client,
                    endpoint,
                    attempts=args.attempts,
                    warmup=args.warmup,
                    request_timeout_sec=args.request_timeout_sec,
                    headers=auth_headers,
                )
                measured["kind"] = "authenticated"
                measured["pass_target"] = (
                    measured["status_ok"] and measured["latency"]["p95_sec"] <= args.p95_max_sec
                )
                endpoint_results.append(measured)

    overall_pass = all(item["pass_target"] for item in endpoint_results)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "targets": {
            "api_p95_sec_max": args.p95_max_sec,
            "request_timeout_sec": args.request_timeout_sec,
        },
        "authenticated_profile": {
            "enabled": bool(args.include_authenticated),
            "role": args.auth_role if args.include_authenticated else None,
            "endpoint_count": len(args.authenticated_endpoints) if args.include_authenticated else 0,
        },
        "endpoints": endpoint_results,
        "overall_pass": overall_pass,
    }


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = _parse_args()
    if args.attempts <= 0:
        raise SystemExit("--attempts must be > 0")
    if args.warmup < 0:
        raise SystemExit("--warmup must be >= 0")
    if args.p95_max_sec <= 0:
        raise SystemExit("--p95-max-sec must be > 0")
    if args.request_timeout_sec <= 0:
        raise SystemExit("--request-timeout-sec must be > 0")

    report = asyncio.run(_run(args))

    _ensure_parent(args.output_json)
    _ensure_parent(args.output_md)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(_build_markdown(report), encoding="utf-8")

    print(
        "[stage4] overall="
        + ("PASS" if report["overall_pass"] else "FAIL")
        + f", report={args.output_json}"
    )

    strict_env_enabled = __import__("os").getenv("PROPAI_STRICT_API_GATE") == "1"
    if (args.fail_on_target_miss or strict_env_enabled) and not report["overall_pass"]:
        print("[stage4] strict gate failed: API latency target miss detected")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
