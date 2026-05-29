#!/usr/bin/env python3
"""실 IFC fixture 온보딩 자동화.

역할:
1) incoming 폴더의 IFC 파일 수집
2) 익명화된 파일명으로 real_samples 폴더에 copy/move
3) IFC 물량(면적/체적)과 schema를 파싱해 manifest 자동 생성
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INCOMING_DIR = ROOT_DIR / "tests" / "fixtures" / "ifc" / "incoming"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "tests" / "fixtures" / "ifc" / "real_samples"
DEFAULT_MANIFEST_PATH = ROOT_DIR / "tests" / "fixtures" / "ifc" / "real_ifc_manifest.v1.json"


def _sanitize_identifier(value: str) -> str:
    lowered = value.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    normalized = re.sub(r"_+", "_", replaced).strip("_")
    return normalized or "fixture"


def _manifest_local_path(local_path: Path) -> str:
    """manifest에는 저장소 상대경로를 우선 저장하고, 외부 경로는 절대경로로 보존한다."""
    resolved = local_path.resolve()
    root_resolved = ROOT_DIR.resolve()
    try:
        return str(resolved.relative_to(root_resolved))
    except ValueError:
        return str(resolved)


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


def _set_if_present(entity: object, attribute: str, value: object) -> None:
    if hasattr(entity, attribute):
        try:
            setattr(entity, attribute, value)
        except Exception:
            return


def _scrub_owner_data(local_path: Path) -> dict[str, int]:
    import ifcopenshell

    model = ifcopenshell.open(str(local_path))
    scrubbed = {
        "person_count": 0,
        "organization_count": 0,
        "application_count": 0,
        "actor_count": 0,
    }

    for person in model.by_type("IfcPerson"):
        scrubbed["person_count"] += 1
        _set_if_present(person, "Identification", None)
        _set_if_present(person, "FamilyName", None)
        _set_if_present(person, "GivenName", None)
        _set_if_present(person, "MiddleNames", None)
        _set_if_present(person, "PrefixTitles", None)
        _set_if_present(person, "SuffixTitles", None)

    for idx, organization in enumerate(model.by_type("IfcOrganization"), start=1):
        scrubbed["organization_count"] += 1
        _set_if_present(organization, "Identification", f"ORG-{idx:03d}")
        _set_if_present(organization, "Name", "ANON_ORGANIZATION")
        _set_if_present(organization, "Description", None)

    for application in model.by_type("IfcApplication"):
        scrubbed["application_count"] += 1
        _set_if_present(application, "ApplicationFullName", "ANON_APPLICATION")
        _set_if_present(application, "ApplicationIdentifier", "ANON_APP")
        _set_if_present(application, "Version", None)

    for actor in model.by_type("IfcActor"):
        scrubbed["actor_count"] += 1
        _set_if_present(actor, "Name", "ANON_ACTOR")
        _set_if_present(actor, "Description", None)

    model.write(str(local_path))
    return scrubbed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="실 IFC fixture 온보딩 자동화")
    parser.add_argument("--incoming", type=Path, default=DEFAULT_INCOMING_DIR, help="입력 IFC 폴더")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="출력 IFC 폴더")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="출력 manifest 경로")
    parser.add_argument("--source-label", type=str, default="internal-anonymized", help="manifest source 라벨")
    parser.add_argument(
        "--mode",
        choices=["copy", "move"],
        default="copy",
        help="입력 IFC 파일 처리 방식",
    )
    parser.add_argument("--id-prefix", type=str, default="real_ifc", help="fixture id prefix")
    parser.add_argument("--keep-original-name", action="store_true", help="파일명 익명화 비활성화")
    parser.add_argument(
        "--scrub-owner-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="소유자/조직/애플리케이션 식별정보 익명화 적용 (기본: true)",
    )
    parser.add_argument("--dry-run", action="store_true", help="파일 반영 없이 manifest 미리보기")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    incoming_dir = args.incoming
    output_dir = args.output_dir
    manifest_path = args.manifest

    if not incoming_dir.exists():
        raise FileNotFoundError(f"incoming 폴더가 없습니다: {incoming_dir}")

    incoming_files = sorted(
        [p for p in incoming_dir.iterdir() if p.is_file() and p.suffix.lower() == ".ifc"]
    )
    if not incoming_files:
        raise ValueError(f"incoming 폴더에 IFC 파일이 없습니다: {incoming_dir}")

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    fixtures: list[dict[str, object]] = []

    for index, src_path in enumerate(incoming_files, start=1):
        if args.keep_original_name:
            out_name = src_path.name
            fixture_id = _sanitize_identifier(src_path.stem)
        else:
            fixture_id = f"{_sanitize_identifier(args.id_prefix)}_{index:03d}"
            out_name = f"{fixture_id}.ifc"

        out_path = output_dir / out_name

        scrub_summary: dict[str, int] | None = None
        if not args.dry_run:
            if args.mode == "copy":
                shutil.copy2(src_path, out_path)
            else:
                shutil.move(src_path, out_path)
            if args.scrub_owner_data:
                scrub_summary = _scrub_owner_data(out_path)

        parse_target = src_path if args.dry_run else out_path
        area_sqm, volume_m3, element_count, schema = _parse_ifc_quantities(parse_target)

        fixtures.append(
            {
                "id": fixture_id,
                "local_path": _manifest_local_path(out_path),
                "source": args.source_label,
                "expected_schema": schema,
                "expected_area_sqm": round(area_sqm, 4),
                "expected_volume_m3": round(volume_m3, 4),
                "expected_element_count": element_count,
                "scrub_owner_data": bool(args.scrub_owner_data and not args.dry_run),
                "scrub_summary": scrub_summary,
            }
        )

    manifest_payload = {
        "manifest_version": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": "실 IFC fixture 자동 온보딩 결과",
        "generated_by": "scripts/perf/onboard_real_ifc_fixtures.py",
        "incoming_dir": str(incoming_dir),
        "output_dir": str(output_dir),
        "mode": args.mode,
        "scrub_owner_data": args.scrub_owner_data,
        "fixtures": fixtures,
    }

    if args.dry_run:
        print(json.dumps(manifest_payload, ensure_ascii=False, indent=2))
        return 0

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[onboard] manifest: {manifest_path}")
    print(f"[onboard] fixtures: {len(fixtures)}")
    for item in fixtures:
        print(f" - {item['id']} -> {item['local_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
