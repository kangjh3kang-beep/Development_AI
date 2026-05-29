#!/usr/bin/env python3
"""Stage 3 실 IFC 샘플(파서 검증용) 생성 스크립트."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid


@dataclass(frozen=True)
class SampleSpec:
    file_name: str
    wall_area: float
    wall_volume: float
    slab_area: float
    slab_volume: float


SPECS = [
    SampleSpec("residential_block_a.ifc", wall_area=120.0, wall_volume=360.0, slab_area=240.0, slab_volume=120.0),
    SampleSpec("office_tower_b.ifc", wall_area=180.0, wall_volume=540.0, slab_area=300.0, slab_volume=150.0),
    SampleSpec("logistics_center_c.ifc", wall_area=210.0, wall_volume=630.0, slab_area=330.0, slab_volume=165.0),
]

ROOT_DIR = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT_DIR / "tests" / "fixtures" / "ifc" / "real_samples"


def _make_ifc(path: Path, spec: SampleSpec) -> tuple[float, float, int]:
    ifc = ifcopenshell.file(schema="IFC4")
    owner = ifc.create_entity("IfcOwnerHistory")

    project = ifc.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="PropAI Sample", OwnerHistory=owner)
    site = ifc.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Site", OwnerHistory=owner)
    building = ifc.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(), Name="Building", OwnerHistory=owner)
    storey = ifc.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="1F", Elevation=0.0, OwnerHistory=owner)

    ifc.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=project, RelatedObjects=[site])
    ifc.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=site, RelatedObjects=[building])
    ifc.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=building, RelatedObjects=[storey])

    wall = ifc.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall", OwnerHistory=owner)
    slab = ifc.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="Slab", OwnerHistory=owner)

    ifc.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        RelatedElements=[wall, slab],
        RelatingStructure=storey,
    )

    wall_area_q = ifc.create_entity("IfcQuantityArea", Name="NetSideArea", AreaValue=spec.wall_area)
    wall_vol_q = ifc.create_entity("IfcQuantityVolume", Name="NetVolume", VolumeValue=spec.wall_volume)
    wall_qset = ifc.create_entity(
        "IfcElementQuantity",
        GlobalId=ifcopenshell.guid.new(),
        Name="Qto_WallBaseQuantities",
        OwnerHistory=owner,
        Quantities=[wall_area_q, wall_vol_q],
    )
    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner,
        RelatedObjects=[wall],
        RelatingPropertyDefinition=wall_qset,
    )

    slab_area_q = ifc.create_entity("IfcQuantityArea", Name="GrossArea", AreaValue=spec.slab_area)
    slab_vol_q = ifc.create_entity("IfcQuantityVolume", Name="GrossVolume", VolumeValue=spec.slab_volume)
    slab_qset = ifc.create_entity(
        "IfcElementQuantity",
        GlobalId=ifcopenshell.guid.new(),
        Name="Qto_SlabBaseQuantities",
        OwnerHistory=owner,
        Quantities=[slab_area_q, slab_vol_q],
    )
    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner,
        RelatedObjects=[slab],
        RelatingPropertyDefinition=slab_qset,
    )

    ifc.write(str(path))

    total_area = spec.wall_area + spec.slab_area
    total_volume = spec.wall_volume + spec.slab_volume
    return total_area, total_volume, 2


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        out_path = OUT_DIR / spec.file_name
        area, volume, count = _make_ifc(out_path, spec)
        print(f"generated: {out_path} | area={area} | volume={volume} | elements={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
