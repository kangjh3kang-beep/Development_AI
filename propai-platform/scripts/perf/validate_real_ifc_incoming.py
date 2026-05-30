#!/usr/bin/env python3
"""incoming IFC 품질게이트 검증 스크립트."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INCOMING_DIR = ROOT_DIR / "tests" / "fixtures" / "ifc" / "incoming"
DEFAULT_REPORT_PATH = ROOT_DIR / "_workspace" / "review" / "perf" / "ifc_incoming_validation_report.json"


def _parse_ifc_quantities(local_path: Path) -> tuple[float, float, int, str]:
    import ifcopenshell

    ifc_file = ifcopenshell.open(str(local_path))
    schema = str(getattr(ifc_file, "schema", "unknown"))

    total_area = 0.0
    total_volume = 0.0
    element_count = 0

    for element in ifc_file.by_type("IfcBuildingElement"):
        element_count += 1
        area = 0.0
        volume = 0.0

        for relation in getattr(element, "IsDefinedBy", None) or []:
            if not relation.is_a("IfcRelDefinesByProperties"):
                continue
            quantity_set = getattr(relation, "RelatingPropertyDefinition", None)
            if quantity_set is None or not quantity_set.is_a("IfcElementQuantity"):
                continue
            for quantity in quantity_set.Quantities:
                if quantity.is_a("IfcQuantityArea"):
                    area = float(quantity.AreaValue or 0.0)
                elif quantity.is_a("IfcQuantityVolume"):
                    volume = float(quantity.VolumeValue or 0.0)

        total_area += area
        total_volume += volume

    return total_area, total_volume, element_count, schema


def _sha256_file(local_path: Path) -> str:
    digest = hashlib.sha256()
    with local_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="incoming IFC 품질게이트 검증")
    parser.add_argument("--incoming", type=Path, default=DEFAULT_INCOMING_DIR, help="입력 IFC 폴더")
    parser.add_argument("--min-ifc-files", type=int, default=1, help="최소 IFC 파일 개수")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="검증 리포트 저장 경로")
    parser.add_argument(
        "--require-positive-quantities",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="면적/체적이 0보다 커야 통과 (기본: true)",
    )
    parser.add_argument(
        "--fail-on-duplicate-hash",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="동일 SHA-256 파일(중복 IFC) 존재 시 실패 처리 (기본: true)",
    )
    parser.add_argument(
        "--max-file-size-mb",
        type=float,
        default=512.0,
        help="파일 크기 상한(MB). 0 이하 입력 시 크기 검증 비활성화",
    )
    parser.add_argument("--dry-run", action="store_true", help="리포트 파일 저장 없이 stdout 출력")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    incoming_dir = args.incoming
    if not incoming_dir.exists():
        raise FileNotFoundError(f"incoming 폴더가 없습니다: {incoming_dir}")

    files = sorted([p for p in incoming_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ifc"])

    rows: list[dict[str, object]] = []
    parsed_count = 0
    parse_failed_count = 0
    positive_quantity_count = 0
    size_pass_count = 0
    hash_to_files: dict[str, list[str]] = {}

    for path in files:
        size_bytes = path.stat().st_size
        size_mb = size_bytes / (1024.0 * 1024.0)
        size_limit_enabled = args.max_file_size_mb > 0
        size_ok = (not size_limit_enabled) or (size_mb <= args.max_file_size_mb)

        file_hash = _sha256_file(path)
        hash_to_files.setdefault(file_hash, []).append(path.name)

        row: dict[str, object] = {
            "file_name": path.name,
            "file_path": str(path),
            "size_bytes": size_bytes,
            "size_mb": round(size_mb, 6),
            "size_ok": size_ok,
            "sha256": file_hash,
            "parse_status": "not_attempted",
        }
        if size_ok:
            size_pass_count += 1

        try:
            area, volume, element_count, schema = _parse_ifc_quantities(path)
            parsed_count += 1
            is_positive = area > 0 and volume > 0
            if is_positive:
                positive_quantity_count += 1
            row.update(
                {
                    "parse_status": "parsed",
                    "schema": schema,
                    "element_count": element_count,
                    "area_sqm": round(area, 4),
                    "volume_m3": round(volume, 4),
                    "positive_quantities": is_positive,
                }
            )
        except Exception as exc:
            parse_failed_count += 1
            row.update(
                {
                    "parse_status": "parse_failed",
                    "error": str(exc),
                }
            )
        rows.append(row)

    file_count = len(files)
    min_file_pass = file_count >= args.min_ifc_files
    parse_pass = parse_failed_count == 0 and parsed_count == file_count
    quantity_pass = True
    if args.require_positive_quantities:
        quantity_pass = positive_quantity_count == file_count
    size_pass = size_pass_count == file_count
    duplicate_groups = [
        {"sha256": sha, "files": names, "count": len(names)}
        for sha, names in sorted(hash_to_files.items())
        if len(names) > 1
    ]
    duplicate_hash_count = len(duplicate_groups)
    duplicate_pass = (duplicate_hash_count == 0) if args.fail_on_duplicate_hash else True

    overall_pass = min_file_pass and parse_pass and quantity_pass and size_pass and duplicate_pass

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_by": "scripts/perf/validate_real_ifc_incoming.py",
        "incoming_dir": str(incoming_dir),
        "min_ifc_files": args.min_ifc_files,
        "require_positive_quantities": args.require_positive_quantities,
        "fail_on_duplicate_hash": args.fail_on_duplicate_hash,
        "max_file_size_mb": args.max_file_size_mb,
        "summary": {
            "file_count": file_count,
            "parsed_count": parsed_count,
            "parse_failed_count": parse_failed_count,
            "positive_quantity_count": positive_quantity_count,
            "size_pass_count": size_pass_count,
            "duplicate_hash_count": duplicate_hash_count,
            "min_file_pass": min_file_pass,
            "parse_pass": parse_pass,
            "quantity_pass": quantity_pass,
            "size_pass": size_pass,
            "duplicate_pass": duplicate_pass,
            "overall_pass": overall_pass,
        },
        "duplicate_hash_groups": duplicate_groups,
        "files": rows,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not args.dry_run:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0 if overall_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
