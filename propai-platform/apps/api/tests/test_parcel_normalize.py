"""다필지 parcels 계약 공용 정규화(parcel_normalize) 회귀 테스트 — 외부콜 0·결정론.

검증 포인트:
  1. str[] → [{address}] 승격(트림·빈 제거·중복 제거).
  2. dict camelCase(areaSqm/zoneType 등) → snake 정규화가 build_integrated_context 인라인 키맵과 동일.
  3. 혼합 배열([str, dict]) 소화.
  4. ★무회귀 앵커: farPct/bcrPct/area 채운 dict 픽스처의 build_integrated_context 산출(통합면적·가중FAR)이
     정규화 도입 전후 '바이트 동일'. 도입 전 기대값을 상수로 박아 고정한다.
  5. ParcelsIn 부착 모델(comprehensive)의 str[]/dict[] 양 shape 요청이 canonical dict[]로 수렴.

모든 필지에 farPct/bcrPct/farLegalPct/bcrLegalPct를 채워 전달해 _enrich_effective_and_special
(외부 API 호출)이 트리거되지 않게 한다(결정론·네트워크 0) — test_build_integrated_context_p0_2 와 동일 관례.
"""
from __future__ import annotations

from app.routers.comprehensive_analysis import ComprehensiveAnalysisRequest
from app.services.land_intelligence.comprehensive_analysis_service import (
    build_integrated_context,
)
from app.services.land_intelligence.parcel_normalize import (
    canonicalize_parcel_row,
    normalize_parcels,
)

# canonicalize_parcel_row 가 만드는 12개 정본 키(누락·과잉 회귀 감지용).
_CANONICAL_KEYS = {
    "pnu", "address", "zone_type", "land_category", "area_sqm",
    "_far_eff", "_bcr_eff", "_far_legal", "_bcr_legal",
    "geometry", "road_side", "road_contact",
}


# ── 1) str[] → [{address}] 승격·트림·빈 제거·중복 제거 ──────────────────────────
def test_str_list_promoted_trimmed_deduped():
    rows = normalize_parcels(["  서울 A  ", "서울 A", "서울 B", "", "   "])
    # 빈/공백 문자열 제외 + "서울 A" 트림 후 중복 제거 → 2행(A, B), 순서 보존.
    assert [r["address"] for r in rows] == ["서울 A", "서울 B"]
    # 승격행도 canonical 12키 uniform shape(다운스트림 q["area_sqm"] 등 안전).
    for r in rows:
        assert set(r) == _CANONICAL_KEYS
        assert r["area_sqm"] is None  # 주소만 있어 면적 결측(정직)


def test_none_and_empty_yield_empty_list():
    assert normalize_parcels(None) == []
    assert normalize_parcels([]) == []
    # 지원하지 않는 요소 타입(int 등)은 드롭(가짜 필지 생성 금지).
    assert normalize_parcels([123, None, {"address": "서울 C"}]) == [
        canonicalize_parcel_row({"address": "서울 C"})
    ]


# ── 2) dict camelCase → snake 정규화가 build_integrated_context 인라인 키맵과 동일 ──
def test_canonicalize_camelcase_matches_inline_keymap():
    p = {
        "pnu": "P1",
        "jibunAddress": "서울 어딘가 123",   # address 폴백 체인
        "zoneType": "제2종일반주거지역",
        "landCategory": "대",
        "areaSqm": 600,
        "farPct": 200,
        "bcrPct": 60,
        "farLegalPct": 250,
        "bcrLegalPct": 60,
        "roadSide": "남",
        "roadContact": True,
        "geometry": {"type": "Polygon"},
    }
    # build_integrated_context:1659-1679 인라인 q 와 byte-동일한 값(이관이지 재작성 아님).
    assert canonicalize_parcel_row(p) == {
        "pnu": "P1",
        "address": "서울 어딘가 123",
        "zone_type": "제2종일반주거지역",
        "land_category": "대",
        "area_sqm": 600.0,
        "_far_eff": 200.0,
        "_bcr_eff": 60.0,
        "_far_legal": 250.0,
        "_bcr_legal": 60.0,
        "geometry": {"type": "Polygon"},
        "road_side": "남",
        "road_contact": True,
    }


def test_dict_merge_preserves_original_keys():
    """dict 입력은 merge(무손실) — 원본 키(zone_code/jibun/bcode 등)가 보존되어야 다른
    소비처(enrich_parcel_list·설계생성)가 그대로 읽는다(pure 치환이면 소실=회귀)."""
    rows = normalize_parcels([
        {"address": "서울 A", "zoneCode": "제2종일반주거지역", "zone_code": "UQA200",
         "zone_name": "제2종일반주거", "jibun": "산 12-3", "bcode": "1111010100",
         "ordinance_far_pct": 200, "areaSqm": 500},
    ])
    r = rows[0]
    # 정본 snake 키가 오버레이됨.
    assert r["zone_type"] == "제2종일반주거지역"  # zoneCode → zone_type
    assert r["area_sqm"] == 500.0                 # areaSqm → area_sqm
    # 원본 키는 보존(소실 금지).
    assert r["zone_code"] == "UQA200"
    assert r["zone_name"] == "제2종일반주거"
    assert r["jibun"] == "산 12-3"
    assert r["bcode"] == "1111010100"
    assert r["ordinance_far_pct"] == 200


# ── 3) 혼합 배열([str, dict]) 소화 ──────────────────────────────────────────────
def test_mixed_str_and_dict_array():
    rows = normalize_parcels([
        "서울 A",
        {"address": "서울 B", "areaSqm": 400, "zoneType": "제3종일반주거지역"},
    ])
    assert [r["address"] for r in rows] == ["서울 A", "서울 B"]
    assert rows[0]["area_sqm"] is None          # str 승격 → 면적 결측
    assert rows[1]["area_sqm"] == 400.0         # dict → 정규화
    assert rows[1]["zone_type"] == "제3종일반주거지역"


# ── 4) ★무회귀 앵커: build_integrated_context 산출이 정규화 도입 전후 동일 ──────────
#     아래 상수는 정규화 도입 '전' 실측값(2필지 혼합용도, camelCase 입력, enrich 미발동).
async def test_build_integrated_context_no_regression_anchor():
    parcels = [
        {"pnu": "A", "address": "서울 A", "zoneType": "제2종일반주거지역", "areaSqm": 600.0,
         "farPct": 200.0, "bcrPct": 60.0, "farLegalPct": 250.0, "bcrLegalPct": 60.0,
         "landCategory": "대"},
        {"pnu": "B", "address": "서울 B", "zoneType": "제3종일반주거지역", "areaSqm": 400.0,
         "farPct": 250.0, "bcrPct": 50.0, "farLegalPct": 300.0, "bcrLegalPct": 50.0,
         "landCategory": "대"},
    ]
    out = await build_integrated_context(parcels)
    assert out is not None
    # 도입 전 실측 상수(면적가중 통합) — 정규화(normalize_parcels 재사용) 후에도 불변이어야 한다.
    assert out["total_area_sqm"] == 1000.0
    assert out["dominant_zone"] == "제2종일반주거지역"
    assert out["blended_far_eff_pct"] == 220.0      # (600·200 + 400·250)/1000
    assert out["blended_bcr_eff_pct"] == 56.0       # (600·60 + 400·50)/1000
    assert out["blended_far_legal_pct"] == 270.0    # (600·250 + 400·300)/1000
    assert out["blended_bcr_legal_pct"] == 56.0
    assert out["integrated_gfa_sqm"] == 2200.0      # 600·2.0 + 400·2.5
    assert out["integrated_footprint_sqm"] == 560.0  # 600·0.6 + 400·0.5
    assert out["land_area_effective_sqm"] == 1000.0
    assert out["parcel_count"] == 2


async def test_build_integrated_context_dict_and_snake_equivalent():
    """camelCase 입력과 동등한 snake_case 입력이 같은 통합집계를 낸다(계약 수렴)."""
    camel = [
        {"address": "서울 A", "zoneType": "제2종일반주거지역", "areaSqm": 600.0,
         "farPct": 200.0, "bcrPct": 60.0, "farLegalPct": 250.0, "bcrLegalPct": 60.0},
        {"address": "서울 B", "zoneType": "제3종일반주거지역", "areaSqm": 400.0,
         "farPct": 250.0, "bcrPct": 50.0, "farLegalPct": 300.0, "bcrLegalPct": 50.0},
    ]
    snake = [
        {"address": "서울 A", "zone_type": "제2종일반주거지역", "area_sqm": 600.0,
         "_far_eff": 200.0, "_bcr_eff": 60.0, "_far_legal": 250.0, "_bcr_legal": 60.0},
        {"address": "서울 B", "zone_type": "제3종일반주거지역", "area_sqm": 400.0,
         "_far_eff": 250.0, "_bcr_eff": 50.0, "_far_legal": 300.0, "_bcr_legal": 50.0},
    ]
    out_camel = await build_integrated_context(camel)
    out_snake = await build_integrated_context(snake)
    for k in ("total_area_sqm", "blended_far_eff_pct", "integrated_gfa_sqm", "dominant_zone"):
        assert out_camel[k] == out_snake[k]


# ── 5) ParcelsIn 부착 모델(comprehensive)의 str[]/dict[] 양 shape 수렴 ──────────────
def test_parcelsin_attached_model_converges_both_shapes():
    # str[] 입력도 422 없이 canonical dict[]로 수렴(과거: 무음 드롭/폴백 은폐).
    req_str = ComprehensiveAnalysisRequest(address="서울시청", parcels=["서울 A ", "서울 A", "서울 B"])
    assert [p["address"] for p in req_str.parcels] == ["서울 A", "서울 B"]  # 트림·중복 제거
    for p in req_str.parcels:
        assert set(p) >= _CANONICAL_KEYS  # canonical 키 존재(다운스트림 계약 충족)

    # dict[] camelCase 입력도 canonical 로 수렴 + 원본 키 보존(merge).
    req_dict = ComprehensiveAnalysisRequest(
        address="서울시청",
        parcels=[{"address": "서울 A", "areaSqm": 600, "zoneType": "제2종일반주거지역"}],
    )
    p0 = req_dict.parcels[0]
    assert p0["area_sqm"] == 600.0 and p0["zone_type"] == "제2종일반주거지역"
    assert p0["areaSqm"] == 600  # 원본 키 보존

    # 미지정 시 기존 기본값(None) 보존(무회귀).
    assert ComprehensiveAnalysisRequest(address="서울시청").parcels is None
