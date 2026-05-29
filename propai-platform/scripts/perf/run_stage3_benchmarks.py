#!/usr/bin/env python3
"""Stage 3 성능/정확도 자동 벤치 리포트 생성기.

측정 항목:
1) IFC 골든셋 기반 물량산출 오차(MAE%)
2) Monte Carlo 10,000회 실행시간(p95)

출력:
- JSON 리포트
- Markdown 요약 리포트
- (옵션) cProfile 결과
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from apps.api.app.services.feasibility.monte_carlo_engine import MCVariable, run_monte_carlo

IFC_MAE_TARGET = 0.02
MONTE_CARLO_MAX_SECONDS = 30.0

DEFAULT_DATASET_PATH = ROOT_DIR / "tests" / "fixtures" / "ifc" / "golden_quantity_reference.v1.json"
DEFAULT_REAL_IFC_MANIFEST_PATH = ROOT_DIR / "tests" / "fixtures" / "ifc" / "real_ifc_manifest.v1.json"
DEFAULT_OUTPUT_JSON = ROOT_DIR / "_workspace" / "review" / "perf" / "stage3_benchmark_report.json"
DEFAULT_OUTPUT_MD = ROOT_DIR / "_workspace" / "review" / "perf" / "stage3_benchmark_report.md"
DEFAULT_PROFILE_PATH = ROOT_DIR / "_workspace" / "review" / "perf" / "stage3_monte_carlo.prof"


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = pos - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _load_ifc_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "cases" not in payload or not isinstance(payload["cases"], list):
        raise ValueError("IFC 골든셋 파일에 cases 배열이 필요합니다.")
    if len(payload["cases"]) == 0:
        raise ValueError("IFC 골든셋 cases가 비어 있습니다.")
    return payload


def _evaluate_ifc_accuracy(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[float] = []
    rows: list[dict[str, Any]] = []

    for case in payload["cases"]:
        area_expected = float(case["expected_area_sqm"])
        area_actual = float(case["actual_area_sqm"])
        volume_expected = float(case["expected_volume_m3"])
        volume_actual = float(case["actual_volume_m3"])

        if area_expected <= 0 or volume_expected <= 0:
            raise ValueError(f"기대 물량 값이 0 이하입니다: {case.get('id', 'unknown')}")

        area_error = abs(area_actual - area_expected) / area_expected
        volume_error = abs(volume_actual - volume_expected) / volume_expected

        errors.extend([area_error, volume_error])
        rows.append(
            {
                "id": case.get("id", "unknown"),
                "area_error_pct": round(area_error * 100, 4),
                "volume_error_pct": round(volume_error * 100, 4),
                "max_error_pct": round(max(area_error, volume_error) * 100, 4),
            }
        )

    mae = sum(errors) / len(errors)
    return {
        "dataset_version": payload.get("dataset_version", "unknown"),
        "case_count": len(payload["cases"]),
        "mae": mae,
        "mae_pct": round(mae * 100, 4),
        "target": IFC_MAE_TARGET,
        "pass_target": mae <= IFC_MAE_TARGET,
        "cases": rows,
    }


def _parse_ifc_quantities(local_path: Path) -> tuple[float, float, int, str]:
    import ifcopenshell

    ifc_file = ifcopenshell.open(str(local_path))
    ifc_version = str(getattr(ifc_file, "schema", "unknown"))

    total_volume = 0.0
    total_area = 0.0
    element_count = 0

    for element in ifc_file.by_type("IfcBuildingElement"):
        element_count += 1
        volume = 0.0
        area = 0.0
        defined_by = getattr(element, "IsDefinedBy", None) or []
        for definition in defined_by:
            if not definition.is_a("IfcRelDefinesByProperties"):
                continue
            prop_set = getattr(definition, "RelatingPropertyDefinition", None)
            if prop_set is None or not prop_set.is_a("IfcElementQuantity"):
                continue
            for quantity in prop_set.Quantities:
                if quantity.is_a("IfcQuantityVolume"):
                    volume = float(quantity.VolumeValue or 0.0)
                elif quantity.is_a("IfcQuantityArea"):
                    area = float(quantity.AreaValue or 0.0)

        total_volume += volume
        total_area += area

    return total_area, total_volume, element_count, ifc_version


def _evaluate_real_ifc_manifest(
    path: Path,
    *,
    min_required_parsed: int,
) -> dict[str, Any]:
    if not path.exists():
        return {
            "manifest_path": str(path),
            "status": "missing_manifest",
            "fixture_count": 0,
            "available_count": 0,
            "parsed_count": 0,
            "missing_count": 0,
            "parse_failed_count": 0,
            "parser_available": False,
            "parser_error": "manifest_not_found",
            "mae": None,
            "mae_pct": None,
            "target": IFC_MAE_TARGET,
            "pass_target": min_required_parsed == 0,
            "requirement_min_parsed": min_required_parsed,
            "requirement_met": min_required_parsed == 0,
            "fixtures": [],
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures", [])
    if not isinstance(fixtures, list):
        raise ValueError("real IFC manifest의 fixtures는 배열이어야 합니다.")

    rows: list[dict[str, Any]] = []
    errors: list[float] = []
    available_count = 0
    parsed_count = 0
    parse_failed_count = 0

    parser_available = True
    parser_error: str | None = None
    try:
        import ifcopenshell  # noqa: F401
    except Exception as exc:
        parser_available = False
        parser_error = str(exc)

    for fixture in fixtures:
        local_path = ROOT_DIR / str(fixture["local_path"])
        exists = local_path.exists()
        if exists:
            available_count += 1

        expected_area = float(fixture.get("expected_area_sqm", 0.0))
        expected_volume = float(fixture.get("expected_volume_m3", 0.0))
        row: dict[str, Any] = {
            "id": fixture.get("id", "unknown"),
            "local_path": str(local_path),
            "exists": exists,
            "source": fixture.get("source", ""),
            "expected_schema": fixture.get("expected_schema", ""),
            "expected_area_sqm": expected_area,
            "expected_volume_m3": expected_volume,
            "parse_status": "not_attempted",
        }

        if exists and parser_available:
            try:
                area_sqm, volume_m3, element_count, schema = _parse_ifc_quantities(local_path)
                parsed_count += 1

                row["parse_status"] = "parsed"
                row["parsed_schema"] = schema
                row["parsed_area_sqm"] = round(area_sqm, 4)
                row["parsed_volume_m3"] = round(volume_m3, 4)
                row["parsed_element_count"] = element_count

                if expected_area > 0 and expected_volume > 0:
                    area_error = abs(area_sqm - expected_area) / expected_area
                    volume_error = abs(volume_m3 - expected_volume) / expected_volume
                    errors.extend([area_error, volume_error])
                    row["area_error_pct"] = round(area_error * 100, 4)
                    row["volume_error_pct"] = round(volume_error * 100, 4)
                    row["max_error_pct"] = round(max(area_error, volume_error) * 100, 4)
                else:
                    row["error"] = "invalid_expected_values"
            except Exception as exc:
                parse_failed_count += 1
                row["parse_status"] = "parse_failed"
                row["error"] = str(exc)
        elif exists and not parser_available:
            row["parse_status"] = "parser_unavailable"
            row["error"] = parser_error
        elif not exists:
            row["parse_status"] = "file_missing"

        rows.append(row)

    mae = (sum(errors) / len(errors)) if errors else None
    requirement_met = parsed_count >= min_required_parsed
    target_met = (mae is None or mae <= IFC_MAE_TARGET) and requirement_met

    if not fixtures:
        status = "empty"
    elif available_count == 0:
        status = "ready_no_local_files"
    elif not parser_available:
        status = "parser_unavailable"
    elif parsed_count > 0:
        status = "parsed"
    else:
        status = "ready"

    return {
        "manifest_path": str(path),
        "status": status,
        "manifest_version": payload.get("manifest_version", "unknown"),
        "fixture_count": len(fixtures),
        "available_count": available_count,
        "parsed_count": parsed_count,
        "missing_count": max(0, len(fixtures) - available_count),
        "parse_failed_count": parse_failed_count,
        "parser_available": parser_available,
        "parser_error": parser_error,
        "mae": mae,
        "mae_pct": round(mae * 100, 4) if mae is not None else None,
        "target": IFC_MAE_TARGET,
        "pass_target": target_met,
        "requirement_min_parsed": min_required_parsed,
        "requirement_met": requirement_met,
        "fixtures": rows,
    }


def _npv_calculation(vars_dict: dict[str, float]) -> float:
    revenue = vars_dict["revenue_krw"]
    cost = vars_dict["cost_krw"]
    discount_rate = max(vars_dict["discount_rate"], 0.001)
    vacancy_rate = min(max(vars_dict["vacancy_rate"], 0.0), 0.95)

    total_investment = 45_000_000_000.0
    analysis_years = 12
    exit_value_ratio = 1.18

    net_income = revenue * (1.0 - vacancy_rate) - cost
    npv = -total_investment

    for year in range(1, analysis_years + 1):
        npv += net_income / ((1.0 + discount_rate) ** year)

    npv += (total_investment * exit_value_ratio) / ((1.0 + discount_rate) ** analysis_years)
    return npv


def _run_monte_carlo_once(n_simulations: int, seed: int) -> dict[str, Any]:
    variables = [
        MCVariable(name="revenue_krw", mean=12_000_000_000.0, std=1_440_000_000.0),
        MCVariable(name="cost_krw", mean=7_200_000_000.0, std=576_000_000.0),
        MCVariable(name="discount_rate", mean=0.08, std=0.015),
        MCVariable(name="vacancy_rate", mean=0.05, std=0.05),
    ]

    return run_monte_carlo(
        calculate_fn=_npv_calculation,
        variables=variables,
        n_simulations=n_simulations,
        seed=seed,
    )


def _evaluate_monte_carlo_performance(
    *,
    attempts: int,
    n_simulations: int,
    profile_path: Path | None,
) -> dict[str, Any]:
    durations: list[float] = []
    latest_result: dict[str, Any] = {}

    for idx in range(attempts):
        seed = 42 + idx
        start = time.perf_counter()

        if profile_path is not None and idx == 0:
            profiler = cProfile.Profile()
            profiler.enable()
            latest_result = _run_monte_carlo_once(n_simulations=n_simulations, seed=seed)
            profiler.disable()
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profiler.dump_stats(str(profile_path))
        else:
            latest_result = _run_monte_carlo_once(n_simulations=n_simulations, seed=seed)

        durations.append(time.perf_counter() - start)

    p95 = _percentile(durations, 0.95)
    return {
        "attempts": attempts,
        "n_simulations": n_simulations,
        "durations_sec": [round(x, 4) for x in durations],
        "min_sec": round(min(durations), 4),
        "avg_sec": round(sum(durations) / len(durations), 4),
        "p95_sec": round(p95, 4),
        "max_sec": round(max(durations), 4),
        "target_sec": MONTE_CARLO_MAX_SECONDS,
        "pass_target": p95 <= MONTE_CARLO_MAX_SECONDS,
        "result_snapshot": {
            "mean_npv": round(float(latest_result.get("mean", 0.0)), 2),
            "std_npv": round(float(latest_result.get("std", 0.0)), 2),
            "p5_npv": round(float(latest_result.get("p5", 0.0)), 2),
            "p50_npv": round(float(latest_result.get("p50", 0.0)), 2),
            "p95_npv": round(float(latest_result.get("p95", 0.0)), 2),
            "positive_ratio": round(float(latest_result.get("probability_positive", 0.0)), 6),
            "convergence_ratio": round(float(latest_result.get("convergence_ratio", 0.0)), 6),
        },
    }


def _build_report(
    *,
    ifc_eval: dict[str, Any],
    real_ifc_eval: dict[str, Any],
    monte_eval: dict[str, Any],
    dataset_path: Path,
    real_ifc_manifest_path: Path,
    profile_path: Path | None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    overall_pass = bool(
        ifc_eval["pass_target"]
        and monte_eval["pass_target"]
        and real_ifc_eval.get("pass_target", True)
    )

    return {
        "generated_at_utc": generated_at,
        "dataset_path": str(dataset_path),
        "targets": {
            "ifc_mae_max": IFC_MAE_TARGET,
            "monte_carlo_p95_sec_max": MONTE_CARLO_MAX_SECONDS,
        },
        "ifc_accuracy": ifc_eval,
        "real_ifc_fixtures": real_ifc_eval,
        "monte_carlo": monte_eval,
        "real_ifc_manifest_path": str(real_ifc_manifest_path),
        "profile_output": str(profile_path) if profile_path else None,
        "overall_pass": overall_pass,
    }


def _write_markdown(report: dict[str, Any], output_md: Path) -> None:
    ifc_eval = report["ifc_accuracy"]
    real_ifc_eval = report["real_ifc_fixtures"]
    monte_eval = report["monte_carlo"]

    real_ifc_lines = [
        "## Real IFC Fixture 준비도",
        f"- manifest 상태: {real_ifc_eval['status']}",
        f"- 등록 fixture: {real_ifc_eval['fixture_count']}개",
        f"- 로컬 사용가능: {real_ifc_eval['available_count']}개",
        f"- 파싱 성공: {real_ifc_eval['parsed_count']}개",
        f"- 최소 요구 파싱 수: {real_ifc_eval['requirement_min_parsed']}개 "
        f"(충족: {real_ifc_eval['requirement_met']})",
    ]
    if real_ifc_eval["mae_pct"] is not None:
        real_ifc_lines.extend(
            [
                f"- 실 IFC MAE: {real_ifc_eval['mae_pct']}% (목표 <= 2.0%)",
                f"- 실 IFC 판정: {'PASS' if real_ifc_eval['pass_target'] else 'FAIL'}",
            ]
        )

    lines = [
        "# Stage 3 Benchmark Report",
        "",
        f"- 생성 시각(UTC): {report['generated_at_utc']}",
        f"- 전체 판정: {'PASS' if report['overall_pass'] else 'FAIL'}",
        "",
        "## IFC 정확도",
        f"- MAE: {ifc_eval['mae_pct']}% (목표 <= {round(IFC_MAE_TARGET * 100, 2)}%)",
        f"- 케이스 수: {ifc_eval['case_count']}",
        f"- 판정: {'PASS' if ifc_eval['pass_target'] else 'FAIL'}",
        "",
        "## Monte Carlo 성능",
        f"- 시뮬레이션: {monte_eval['n_simulations']}회 x {monte_eval['attempts']}회",
        f"- p95 시간: {monte_eval['p95_sec']}초 (목표 <= {MONTE_CARLO_MAX_SECONDS:.1f}초)",
        f"- 평균 시간: {monte_eval['avg_sec']}초",
        f"- 판정: {'PASS' if monte_eval['pass_target'] else 'FAIL'}",
        "",
        *real_ifc_lines,
        "",
        "## 참고",
        f"- 골든셋: `{report['dataset_path']}`",
        f"- 실 IFC manifest: `{report['real_ifc_manifest_path']}`",
    ]

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 3 성능/정확도 벤치 리포트 생성")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--real-ifc-manifest", type=Path, default=DEFAULT_REAL_IFC_MANIFEST_PATH)
    parser.add_argument(
        "--require-real-ifc-min",
        type=int,
        default=0,
        help="실 IFC 파싱 최소 요구 개수(0이면 비강제)",
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--n-simulations", type=int, default=10_000)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument(
        "--profile",
        action="store_true",
        help="첫 실행을 cProfile로 기록",
    )
    parser.add_argument(
        "--profile-path",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="cProfile 출력 경로",
    )
    parser.add_argument(
        "--fail-on-target-miss",
        action="store_true",
        help="목표 미달 시 종료 코드 2로 실패 처리",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.attempts <= 0:
        raise ValueError("--attempts는 1 이상이어야 합니다.")
    if args.n_simulations <= 0:
        raise ValueError("--n-simulations는 1 이상이어야 합니다.")
    if args.require_real_ifc_min < 0:
        raise ValueError("--require-real-ifc-min은 0 이상이어야 합니다.")

    dataset_payload = _load_ifc_dataset(args.dataset)
    ifc_eval = _evaluate_ifc_accuracy(dataset_payload)
    real_ifc_eval = _evaluate_real_ifc_manifest(
        args.real_ifc_manifest,
        min_required_parsed=args.require_real_ifc_min,
    )

    profile_path = args.profile_path if args.profile else None
    monte_eval = _evaluate_monte_carlo_performance(
        attempts=args.attempts,
        n_simulations=args.n_simulations,
        profile_path=profile_path,
    )

    report = _build_report(
        ifc_eval=ifc_eval,
        real_ifc_eval=real_ifc_eval,
        monte_eval=monte_eval,
        dataset_path=args.dataset,
        real_ifc_manifest_path=args.real_ifc_manifest,
        profile_path=profile_path,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_markdown(report, args.output_md)

    print(f"[stage3] report json: {args.output_json}")
    print(f"[stage3] report md:   {args.output_md}")
    print(f"[stage3] overall:     {'PASS' if report['overall_pass'] else 'FAIL'}")
    strict_gate = args.fail_on_target_miss or os.getenv("PROPAI_STRICT_PERF_GATE") == "1"
    if strict_gate and not report["overall_pass"]:
        print("[stage3] strict gate failed: performance target miss detected")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
