"""대지 규제 카드 수집 — 토지특성 + 토지이용계획(중첩 용도지역)을 1건으로 통합.

PNU → VWORLD NED 토지특성(지목/면적/형상/경사/도로접면/용도지역/이용상황/공시지가) +
토지이용계획(중첩 용도지역지구 전체). 결손은 None/빈으로 표면화. 어느 출처도 없으면 None.
"""
from __future__ import annotations

from datetime import date

from app.adapters.regulation.vworld_building import build_vworld_building
from app.adapters.regulation.vworld_landchar import build_vworld_landchar
from app.adapters.regulation.vworld_landuse import build_vworld_landuse
from app.contracts.land_card import LandCard


def collect_land_card(pnu: str, stdr_year: str = "2024",
                      as_of: date | None = None) -> LandCard | None:
    char_ad = build_vworld_landchar()
    lu_ad = build_vworld_landuse()
    bld_ad = build_vworld_building()
    char = char_ad.fetch(pnu, stdr_year)
    zones = lu_ad.land_use_zones(pnu)
    building = bld_ad.existing_building(pnu)
    if char is None and not zones and building is None:
        return None  # 어느 출처도 없음 → 결손(무음 단정 금지)

    sources: list[str] = []
    notes: list[str] = []
    # 결과 없음 시 '키 설정됨(외부 장애/결손 미상 — 무규제 단정 금지)' vs '키 미설정(mock)' 구분(무음 오판 0).
    if char is not None:
        sources.append("vworld_landchar")
    elif char_ad.available:
        notes.append("토지특성 조회 결과 없음 — 키 설정됨(외부 장애/결손 미상, 무규제 단정 금지)")
    else:
        notes.append("토지특성 어댑터 미설정(키 없음)")
    if zones:
        sources.append("vworld_landuse")
    elif lu_ad.available:
        notes.append("토지이용계획 조회 결과 없음 — 키 설정됨(외부 장애/결손 미상)")
    else:
        notes.append("토지이용계획 어댑터 미설정(키 없음)")
    if building is not None:
        sources.append("vworld_building")
    elif bld_ad.available:
        notes.append("기존 건물 조회 결과 없음 — 키 설정됨(나대지 또는 외부 장애 미상)")
    else:
        notes.append("기존 건물 어댑터 미설정(키 없음)")

    c = char or {}
    # 잔여 개발용량(현행 법정한도 − 기존 용적률) — 용도지역+대지면적+기존 연면적 있을 때.
    rc = None
    upz = None
    existing_floor = building.get("total_floor_area") if building else None
    if c.get("use_zone") and c.get("area"):
        from app.services.land.remaining_capacity import remaining_capacity
        from app.services.land.upzoning import (
            multipath_scenarios,
            upzoning_scenarios,
            upzoning_signals,
        )
        existing_bcr = building.get("bcr_pct") if building else None
        rc = remaining_capacity(c["use_zone"], c["area"], existing_floor, pnu, as_of, existing_bcr)
        if rc is not None:
            sources.append("zone_limits")
        # 종상향 시나리오 + 가능성 신호 + 다중경로(지구단위/정비/역세권/사전협상/입규최소) — 다층/다각.
        scen = upzoning_scenarios(c["use_zone"], c["area"], existing_floor)
        if scen is not None:
            sig = upzoning_signals(zones)
            multipath = multipath_scenarios(c["use_zone"], c["area"], sig, pnu, as_of=as_of)
            upz = {**scen, **sig}
            if multipath is not None:
                upz["multipath"] = multipath["pathways"]

    return LandCard(
        existing_building=building,
        remaining_capacity=rc,
        upzoning=upz,
        pnu=pnu,
        jimok=c.get("jimok"),
        use_zone=c.get("use_zone"),
        use_zones_all=zones or [],
        use_situation=c.get("use_situation"),
        slope=c.get("slope"),
        shape=c.get("shape"),
        road_contact=c.get("road_contact"),
        area=c.get("area"),
        land_price=c.get("land_price"),
        stdr_year=c.get("stdr_year") or stdr_year,
        sources=sources,
        notes=notes,
    )
