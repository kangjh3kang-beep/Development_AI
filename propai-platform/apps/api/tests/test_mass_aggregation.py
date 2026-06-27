"""mass_backbone D1 — 건축물대장→건축물종류별 매스 집계 단위테스트(순수·무 DB/API).

classify_building_type(주용도→종류)·aggregate_mass_templates(중앙값 통계·표본·무목업·결정론) 검증.
"""
from app.services.mass_backbone.mass_aggregation import (
    aggregate_mass_templates,
    classify_building_type,
    fill_bcr_far_from_recap,
)


def test_classify_building_type():
    assert classify_building_type("아파트") == "공동주택"
    assert classify_building_type("제2종근린생활시설") == "근린생활시설"
    assert classify_building_type("오피스텔") == "업무시설"
    assert classify_building_type("다가구주택") == "단독주택"
    assert classify_building_type("") == "기타"        # 빈값 → 기타(가짜 분류 금지)
    assert classify_building_type(None) == "기타"
    assert classify_building_type("창고") == "기타"     # 미매칭 → 기타


def _rec(purpose, bcr=None, far=None, floors=None, area=None):
    return {"main_purpose": purpose, "bcr_pct": bcr, "far_pct": far,
            "ground_floors": floors, "total_area_sqm": area}


def test_aggregate_median_and_provenance():
    records = [
        _rec("아파트", bcr=18, far=200, floors=20, area=50000),
        _rec("아파트", bcr=22, far=240, floors=25, area=60000),
        _rec("연립주택", bcr=50, far=120, floors=4, area=800),   # 공동주택 동일군(중앙값 산정 대상)
        _rec("제1종근린생활시설", bcr=60, far=150, floors=5, area=1200),
    ]
    out = aggregate_mass_templates(records, region="동탄2", zone_code="3종일반주거")
    by_type = {t["building_type"]: t for t in out}

    # 공동주택 3건(아파트2+연립1) median: bcr=median(18,22,50)=22·far=median(200,240,120)=200·floors=median(20,25,4)=20
    apt = by_type["공동주택"]
    assert apt["sample_count"] == 3
    assert apt["median_bcr_pct"] == 22.0
    assert apt["median_far_pct"] == 200.0
    assert apt["median_floors"] == 20.0
    assert apt["region"] == "동탄2" and apt["zone_code"] == "3종일반주거"
    assert apt["source"] == "building_registry"
    assert apt["metadata"]["bcr_n"] == 3   # provenance: 지표별 표본수
    # 근린생활시설 1건
    assert by_type["근린생활시설"]["sample_count"] == 1
    # ★대표 종류 우선 정렬(표본 많은 공동주택 먼저)
    assert out[0]["building_type"] == "공동주택"


def test_aggregate_no_mockup_missing_metrics_are_none():
    # 일부 지표 결측·0·음수는 평균에서 제외(가짜 0 금지) → 해당 지표 None, 그래도 표본엔 포함.
    out = aggregate_mass_templates(
        [_rec("아파트", bcr=0, far=None, floors=15, area=-1)],  # bcr=0·area<0·far None → 제외, floors만 유효
        region="세종",
    )
    apt = next(t for t in out if t["building_type"] == "공동주택")
    assert apt["sample_count"] == 1            # floors 실측 보유 → 표본 1
    assert apt["median_floors"] == 15.0
    assert apt["median_bcr_pct"] is None       # 0 제외 → None(가짜 표준 금지)
    assert apt["median_far_pct"] is None
    assert apt["median_total_area_sqm"] is None


def test_aggregate_empty_and_min_samples():
    assert aggregate_mass_templates([], region="위례") == []
    # 지표 전무(분류만 가능) record → 유효표본 0 → min_samples 미달로 제외
    out = aggregate_mass_templates([_rec("아파트")], region="위례", min_samples=1)
    assert out == []


def test_aggregate_deterministic():
    recs = [_rec("아파트", bcr=20, far=200, floors=20, area=50000),
            _rec("오피스텔", bcr=60, far=600, floors=15, area=9000)]
    assert aggregate_mass_templates(recs, region="마곡") == aggregate_mass_templates(recs, region="마곡")


def test_fill_bcr_far_from_recap():
    # 표제부 공동주택: 건폐/용적 결측(None)·층수/면적 보유. 총괄표제부: 건폐/용적 충실.
    base = aggregate_mass_templates([_rec("아파트", bcr=0, far=0, floors=20, area=5000)], region="분당구")
    apt = next(t for t in base if t["building_type"] == "공동주택")
    assert apt["median_bcr_pct"] is None and apt["median_far_pct"] is None   # 결측 확인
    recap = aggregate_mass_templates([_rec("아파트", bcr=18, far=220, floors=0, area=90000)], region="분당구")

    fill_bcr_far_from_recap(base, recap)
    apt = next(t for t in base if t["building_type"] == "공동주택")
    assert apt["median_bcr_pct"] == 18.0 and apt["median_far_pct"] == 220.0   # 총괄에서 보강
    assert apt["median_total_area_sqm"] == 5000.0   # ★면적은 표제부 기준 유지(총괄 90000 미혼입)
    assert apt["metadata"]["bcr_far_source"] == "recap_title"   # provenance


def test_fill_bcr_far_from_recap_keeps_existing_and_skips_missing():
    # 표제부에 이미 건폐/용적이 있으면 총괄로 덮지 않음. 총괄에도 없으면 None 유지(가짜 생성 금지).
    base = aggregate_mass_templates([_rec("아파트", bcr=25, far=250, floors=20, area=5000)], region="분당구")
    recap = aggregate_mass_templates([_rec("아파트", bcr=18, far=220, floors=0, area=90000)], region="분당구")
    fill_bcr_far_from_recap(base, recap)
    apt = next(t for t in base if t["building_type"] == "공동주택")
    assert apt["median_bcr_pct"] == 25.0 and apt["median_far_pct"] == 250.0   # 기존 유지(덮지 않음)
    assert "bcr_far_source" not in apt.get("metadata", {})   # 보강 안 했으면 provenance 미표기

    base2 = aggregate_mass_templates([_rec("아파트", bcr=0, far=0, floors=20, area=5000)], region="분당구")
    fill_bcr_far_from_recap(base2, [])   # 총괄 없음 → None 유지
    apt2 = next(t for t in base2 if t["building_type"] == "공동주택")
    assert apt2["median_bcr_pct"] is None and apt2["median_far_pct"] is None
