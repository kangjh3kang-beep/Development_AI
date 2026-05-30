#!/usr/bin/env python3
"""실 IFC 교체 파이프라인 오케스트레이터.

단계:
1) incoming IFC 품질게이트 검증
2) incoming IFC -> real_samples 온보딩(+scrub)
3) Stage3 strict benchmark 실행
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INCOMING_DIR = ROOT_DIR / "tests" / "fixtures" / "ifc" / "incoming"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "tests" / "fixtures" / "ifc" / "real_samples"
DEFAULT_MANIFEST_PATH = ROOT_DIR / "tests" / "fixtures" / "ifc" / "real_ifc_manifest.v1.json"
DEFAULT_REPORT_PATH = ROOT_DIR / "_workspace" / "review" / "perf" / "stage3_benchmark_report.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="실 IFC 교체 + Stage3 strict benchmark 파이프라인")
    parser.add_argument("--incoming", type=Path, default=DEFAULT_INCOMING_DIR, help="입력 IFC 폴더")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="출력 IFC 폴더")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="출력 manifest 경로")
    parser.add_argument("--source-label", type=str, default="internal-anonymized", help="manifest source 라벨")
    parser.add_argument("--mode", choices=["copy", "move"], default="copy", help="온보딩 처리 방식")
    parser.add_argument("--id-prefix", type=str, default="real_ifc", help="fixture id prefix")
    parser.add_argument("--keep-original-name", action="store_true", help="파일명 익명화 비활성화")
    parser.add_argument(
        "--scrub-owner-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="소유자/조직/애플리케이션 식별정보 익명화 적용 (기본: true)",
    )
    parser.add_argument("--attempts", type=int, default=3, help="Monte Carlo 반복 횟수")
    parser.add_argument("--n-simulations", type=int, default=10000, help="Monte Carlo 시뮬레이션 횟수")
    parser.add_argument("--require-real-ifc-min", type=int, default=3, help="실 IFC 최소 파싱 요구 개수")
    parser.add_argument(
        "--validate-incoming",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="incoming IFC 품질게이트 실행 (기본: true)",
    )
    parser.add_argument("--min-ifc-files", type=int, default=None, help="incoming 최소 IFC 파일 개수 (기본: require-real-ifc-min)")
    parser.add_argument(
        "--incoming-validation-report",
        type=Path,
        default=ROOT_DIR / "_workspace" / "review" / "perf" / "ifc_incoming_validation_report.json",
        help="incoming 검증 리포트 저장 경로",
    )
    parser.add_argument(
        "--fail-on-duplicate-hash",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="incoming에 동일 SHA-256 파일이 있으면 실패 (기본: true)",
    )
    parser.add_argument(
        "--max-file-size-mb",
        type=float,
        default=512.0,
        help="incoming 파일 크기 상한(MB), 0 이하 시 크기 제한 비활성화",
    )
    parser.add_argument(
        "--expect-incoming-empty-after-move",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="mode=move 실행 후 incoming에 IFC 파일이 남아있으면 실패 (기본: true)",
    )
    parser.add_argument("--profile", action="store_true", help="Stage3 cProfile 결과 생성")
    parser.add_argument("--skip-benchmark", action="store_true", help="온보딩만 수행")
    parser.add_argument("--dry-run", action="store_true", help="온보딩 dry-run만 수행")
    return parser


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def _run_onboarding(args: argparse.Namespace) -> None:
    cmd = [
        "python",
        "scripts/perf/onboard_real_ifc_fixtures.py",
        "--incoming",
        str(args.incoming),
        "--output-dir",
        str(args.output_dir),
        "--manifest",
        str(args.manifest),
        "--source-label",
        args.source_label,
        "--mode",
        args.mode,
        "--id-prefix",
        args.id_prefix,
    ]
    if args.keep_original_name:
        cmd.append("--keep-original-name")
    if args.scrub_owner_data:
        cmd.append("--scrub-owner-data")
    else:
        cmd.append("--no-scrub-owner-data")
    if args.dry_run:
        cmd.append("--dry-run")

    result = _run(cmd)
    if result.stdout:
        sys.stdout.write(result.stdout)


def _count_ifc_files(path: Path) -> int:
    if not path.exists():
        return 0
    return len([p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".ifc"])


def _run_incoming_validation(args: argparse.Namespace) -> None:
    min_ifc_files = args.min_ifc_files
    if min_ifc_files is None:
        min_ifc_files = max(1, int(args.require_real_ifc_min))

    cmd = [
        "python",
        "scripts/perf/validate_real_ifc_incoming.py",
        "--incoming",
        str(args.incoming),
        "--min-ifc-files",
        str(min_ifc_files),
        "--report",
        str(args.incoming_validation_report),
        "--max-file-size-mb",
        str(args.max_file_size_mb),
    ]
    if args.fail_on_duplicate_hash:
        cmd.append("--fail-on-duplicate-hash")
    else:
        cmd.append("--no-fail-on-duplicate-hash")
    if args.dry_run:
        cmd.append("--dry-run")

    result = _run(cmd)
    if result.stdout:
        sys.stdout.write(result.stdout)


def _run_benchmark(args: argparse.Namespace) -> None:
    cmd = [
        "python",
        "scripts/perf/run_stage3_benchmarks.py",
        "--attempts",
        str(args.attempts),
        "--n-simulations",
        str(args.n_simulations),
        "--require-real-ifc-min",
        str(args.require_real_ifc_min),
        "--fail-on-target-miss",
    ]
    if args.profile:
        cmd.append("--profile")

    result = _run(cmd)
    if result.stdout:
        sys.stdout.write(result.stdout)

    if DEFAULT_REPORT_PATH.exists():
        payload = json.loads(DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))
        print(
            "[refresh] summary:",
            json.dumps(
                {
                    "overall_pass": payload.get("overall_pass"),
                    "ifc_mae_pct": payload.get("ifc_accuracy", {}).get("mae_pct"),
                    "monte_carlo_p95_sec": payload.get("monte_carlo", {}).get("p95_sec"),
                    "real_ifc_parsed_count": payload.get("real_ifc_fixtures", {}).get("parsed_count"),
                },
                ensure_ascii=False,
            ),
        )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.validate_incoming:
        _run_incoming_validation(args)

    _run_onboarding(args)

    if args.mode == "move" and not args.dry_run and args.expect_incoming_empty_after_move:
        remaining_ifc = _count_ifc_files(args.incoming)
        if remaining_ifc > 0:
            raise RuntimeError(
                f"mode=move 이후 incoming에 IFC 파일이 남아있습니다: {args.incoming} (remaining={remaining_ifc})"
            )
        print(f"[refresh] incoming cleared after move: {args.incoming}")

    if args.dry_run or args.skip_benchmark:
        return 0

    _run_benchmark(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
