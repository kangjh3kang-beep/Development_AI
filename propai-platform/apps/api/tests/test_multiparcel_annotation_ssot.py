"""다필지 통합 시 면적의존 산출물(annotations·far_optimization) 재생성 SSOT 검증.

상도동 211-444외 32필지(33필지) 시나리오 재현: 대표필지 763㎡ 문구가 통합면적 기준으로
재생성되는지(RC#1), N=1 무회귀인지 검증.
"""
from __future__ import annotations

from app.services.land_intelligence import far_tier_service as fts


def _rep_sec1() -> dict:
    """대표필지(763㎡) 기준으로 생성된 sec1 (버그 재현 입력)."""
    return {
        "national_far_pct": 250,
        "national_bcr_pct": 60,
        "ordinance_far_pct": 200,
        "ordinance_bcr_pct": 60,
        "effective_far_pct": 200,
        "effective_bcr_pct": 60,
        "annotations": [
            "국토계획법 시행령에 따른 제2종일반주거지역의 법정 건폐율 상한은 60%, 법정 용적률 상한은 250%입니다.",
            "실효 용적률은 법정상한(250%)과 조례(200%) 중 낮은 값인 200%가 적용됩니다.",
            "대지면적 763.0㎡ 기준으로 최대 연면적 1,526.0㎡ (약 462평), "
            "최대 건축면적 457.8㎡ (약 138평)까지 건축이 가능합니다.",
        ],
        "far_optimization": {"marker": "representative_763"},
    }


def test_multiparcel_regenerates_area_annotation():
    """33필지 통합(12,000㎡)이면 '763㎡ 기준' 대표문구가 사라지고 통합 문구가 들어간다."""
    out = fts.rebuild_area_dependent(
        _rep_sec1(),
        land_area=12000.0,
        effective_far=200,
        effective_bcr=60,
        zone_type="제2종일반주거지역",
        national_far=250,
        parcel_count=33,
        zone_mix=[("제2종일반주거지역", 12000.0)],
    )
    area_ann = next(a for a in out["annotations"] if "건축이 가능합니다" in a)
    assert "763" not in area_ann, "대표필지 763㎡ 문구가 잔존하면 안 됨(RC#1 버그)"
    assert "33개 필지 통합" in area_ann
    assert "12,000.0㎡" in area_ann
    # 최대 연면적 = 12,000 × 200% = 24,000㎡
    assert "24,000.0㎡" in area_ann
    # 면적 무관 문구(법정/조례)는 보존
    assert any("법정 용적률 상한은 250%" in a for a in out["annotations"])


def test_multiparcel_regenerates_far_optimization():
    """far_optimization도 통합면적 기준으로 갈아끼워진다(대표 마커 제거)."""
    out = fts.rebuild_area_dependent(
        _rep_sec1(),
        land_area=12000.0,
        effective_far=200,
        effective_bcr=60,
        zone_type="제2종일반주거지역",
        national_far=250,
        parcel_count=33,
    )
    assert out["far_optimization"].get("marker") != "representative_763"


def test_single_parcel_identity_no_regression():
    """N=1(단일필지)이면 기존 대표필지 문구 형식 그대로(무회귀)."""
    out = fts.rebuild_area_dependent(
        _rep_sec1(),
        land_area=763.0,
        effective_far=200,
        effective_bcr=60,
        zone_type="제2종일반주거지역",
        national_far=250,
        parcel_count=1,
    )
    area_ann = next(a for a in out["annotations"] if "건축이 가능합니다" in a)
    assert area_ann.startswith("대지면적 763.0㎡ 기준으로")
    assert "개 필지 통합" not in area_ann


def test_build_area_annotation_multi_vs_single():
    """공용 문구 생성기: 다필지/단일 문구 형식 분기."""
    single = fts.build_area_annotation(land_area=500.0, effective_far=200, effective_bcr=60)
    assert single.startswith("대지면적 500.0㎡ 기준으로")
    multi = fts.build_area_annotation(
        land_area=5000.0, effective_far=200, effective_bcr=60, parcel_count=10,
    )
    assert "10개 필지 통합 대지면적 5,000.0㎡" in multi
    # 혼재 용도 표기
    mixed = fts.build_area_annotation(
        land_area=5000.0, effective_far=200, effective_bcr=60, parcel_count=10,
        zone_mix=[("제2종일반주거지역", 3000), ("일반상업지역", 2000)],
    )
    assert "용도지역 혼재" in mixed


# ── P0-5(RC7): 법정/조례 비교 서술 재생성(수치-서술 충돌 제거) ──────────────

def _stale_annotations_139_6() -> list[str]:
    """라이브 재현 입력: 통합 실효치가 139.6%로 override됐는데 서술은 대표필지 100% 그대로."""
    return [
        "국토계획법 시행령에 따른 자연녹지지역의 법정 건폐율 상한은 20%, 법정 용적률 상한은 100%입니다.",
        "실효 용적률은 법정상한(100%)과 조례(100%) 중 낮은 값인 100.0%가 적용되며, 실효 건폐율은 20.0%입니다.",
        "9개 필지 통합 대지면적 9,851.0㎡ 기준으로 최대 연면적 13,752.0㎡ (약 4,161평), "
        "최대 건축면적 3,526.6㎡ (약 1,067평)까지 건축이 가능합니다.",
    ]


def test_legal_basis_annotation_regenerated_on_integrated_override():
    """블렌드 override(139.6%)와 서술(100.0% 적용) 충돌을 재생성 함수가 해소한다."""
    sec1 = {
        "national_far_pct": 100, "national_bcr_pct": 20,
        "annotations": _stale_annotations_139_6(),
    }
    out = fts.rebuild_legal_basis_annotations(
        sec1,
        effective_far=139.6, effective_bcr=35.8,
        national_far=100.0, national_bcr=20.0,
        parcel_count=9,
    )
    legal_ann = " ".join(out["annotations"])
    # 과거 충돌 문구("...중 낮은 값인 100.0%가 적용되며...")는 제거되어야 한다.
    assert "100.0%가 적용되며" not in legal_ann
    # 새 서술은 실제 override 수치(139.6%)와 일치해야 한다.
    assert "139.6%" in legal_ann
    # 면적문구(다른 문장)는 그대로 보존.
    assert any("최대 연면적 13,752.0㎡" in a for a in out["annotations"])


def test_legal_basis_annotation_single_parcel_no_regression():
    """N=1(단일필지)은 '개 필지 통합' 문구 없이 단문 형태로 재생성(무회귀 확인용 경계값)."""
    sec1 = {
        "national_far_pct": 200, "national_bcr_pct": 60,
        "annotations": [
            "국토계획법 시행령에 따른 제2종일반주거지역의 법정 건폐율 상한은 60%, 법정 용적률 상한은 200%입니다.",
            "실효 용적률은 법정상한(200%)과 조례(200%) 중 낮은 값인 200.0%가 적용되며, 실효 건폐율은 60.0%입니다.",
        ],
    }
    out = fts.rebuild_legal_basis_annotations(
        sec1, effective_far=200.0, effective_bcr=60.0, national_far=200.0, national_bcr=60.0,
        parcel_count=1,
    )
    legal_ann = " ".join(out["annotations"])
    assert "개 필지 통합" not in legal_ann
    assert "200%" in legal_ann
