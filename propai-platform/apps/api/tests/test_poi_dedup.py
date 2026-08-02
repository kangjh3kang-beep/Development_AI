"""dedup_school_cluster SSOT + 4소비처 수렴 단위검증 — G2 학교 POI 과카운트 근원봉합(W1-2).

라이브 analyze() 미수집(하네스 환경 DB/API 부재)이므로, SSOT와 소비처 순수로직을 직접
호출해 근본수정을 실증한다:
  (a) 모학교명 정규화 — 부속(운동장·병설유치원·체육관)·분교 접미 제거로 모학교 도출
  (b) dedup: [대보초·운동장·병설유치원·대보초 분교·구룡포초] → [대보초, 구룡포초] 2개(부속 병합·타학교 유지)
  (c) 오탐: 이름다른 근접학교 미병합·근접만으로 병합 금지
  (d) 불변식(cross_field.G2): 경로 비의존 + 변이-kill(정규화 무력화 → 과카운트 복귀 → finding 소멸)
  (e) 4소비처 수렴(comprehensive·site_score·kakao) 5→1 flip + 다른 POI(병원·지하철) 무회귀
"""

import asyncio

import pytest

from app.services.external_api import poi_dedup as pd
from app.services.external_api.poi_dedup import (
    dedup_school_cluster,
    mother_school_name,
    school_cluster_count,
)

# ── 공용 시드: 대보초 본교+부속 4개(운동장·병설유치원·체육관·분교) — 좌표는 반경 250m 이내 ──
_DAEBO5 = [
    {"name": "대보초등학교", "distance_m": 120, "x": 129.56, "y": 36.07},
    {"name": "대보초등학교 운동장", "distance_m": 130, "x": 129.5601, "y": 36.0701},
    {"name": "대보초등학교병설유치원", "distance_m": 140, "x": 129.5602, "y": 36.0702},
    {"name": "대보초등학교 체육관", "distance_m": 150, "x": 129.5603, "y": 36.0703},
    {"name": "대보초등학교 구만분교", "distance_m": 160, "x": 129.561, "y": 36.071},
]


# ────────────────────────────────────────────────────────────────────────────
# (1) SSOT mother_school_name — 접미/부속/축약 정규화
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,expected", [
    ("대보초등학교", "대보초등학교"),
    ("대보초등학교 운동장", "대보초등학교"),
    ("대보초등학교병설유치원", "대보초등학교"),
    ("대보초등학교 체육관", "대보초등학교"),
    ("대보초등학교 구만분교", "대보초등학교"),
    ("대보초 분교", "대보초등학교"),          # 축약형(초) 폴백 → 정규형으로 수렴
    ("대보초", "대보초등학교"),               # 축약형 단독(문자열 끝)
    ("구룡포초등학교", "구룡포초등학교"),      # 다른 학교(병합 대상 아님)
    ("호미곶중학교", "호미곶중학교"),
    ("중앙고등학교", "중앙고등학교"),
    ("포항제철중학교", "포항제철중학교"),      # '초'가 stem 앞에 없음 — 코어 우선
    # ★R2(R1 REVISE): 부설학교=모학교와 별개교 → 최종(최우측)코어 절단으로 분리(과병합 봉합)
    ("서울교육대학교부설초등학교", "서울교육대학교부설초등학교"),  # 최종코어 '초등학교' → 그대로
    ("서울교육대학교", "서울교육대학교"),                         # 최종코어 '대학교' → 모대학
    # 부정표본(지명) — 축약폴백 가드가 학교로 오인식하지 않아야(뒤가 non-attach)
    ("고촌", "고촌"),          # '고' 뒤 '촌'=non-attach → 미인식
    ("중구청", "중구청"),      # '중' 뒤 '구청'=non-attach → 미인식
    ("중앙동", "중앙동"),      # '중' 뒤 '앙동'=non-attach → 미인식
])
def test_mother_school_name_normalization(name, expected):
    assert mother_school_name(name) == expected


def _first_core_truncate(name: str) -> str:
    """변이(결함) 재현 — **최초**-코어 절단(R1이 지적한 과병합 버그). 회귀 테스트 대조용.

    '서울교육대학교부설초등학교' → 최초코어 '대학교'에서 잘라 '서울교육대학교'로 붕괴(모대학과 과병합).
    실제 프로덕션 mother_school_name은 **최종**코어라 이 붕괴가 일어나지 않아야 한다.
    """
    from app.services.external_api.poi_dedup import _SCHOOL_CORE
    n = name.replace(" ", "")
    best_i, best_core = -1, ""
    for core in _SCHOOL_CORE:
        i = n.find(core)
        if i >= 0 and (best_i < 0 or i < best_i):
            best_i, best_core = i, core
    return n[:best_i] + best_core if best_i >= 0 else n


def test_affiliated_school_not_over_merged_and_mutation_kill():
    """★R2 CONFIRMED 봉합: 대학교 부설초등학교는 모대학과 별개교(과병합 금지) + 변이-kill.

    최종-코어 절단으로 '서울교육대학교부설초등학교'는 그대로 보존돼 모대학과 분리된다.
    변이(최초-코어=find 절단)면 '서울교육대학교'로 붕괴해 병합(1)되므로, 아래 값 assert가 즉시
    FAIL한다 = 봉합이 최종-코어 절단에 실제 의존함을 증명.
    """
    name = "서울교육대학교부설초등학교"
    # 변이(최초-코어)였다면 모대학으로 붕괴했을 값을 명시
    assert _first_core_truncate(name) == "서울교육대학교"          # 결함 재현(과병합 원인)
    # 실제(최종-코어)는 그대로 유지 → 모대학과 별개 키(rfind→find 회귀 시 이 줄이 FAIL)
    assert mother_school_name(name) == name
    assert mother_school_name(name) != mother_school_name("서울교육대학교")
    # dedup: 좌표<250m·좌표없음 모두 미병합(2) — 봉합 전 오답 1, 봉합 후 정답 2
    near = [
        {"name": "서울교육대학교", "x": 127.0, "y": 37.5},
        {"name": "서울교육대학교부설초등학교", "x": 127.0009, "y": 37.5},  # <250m
    ]
    assert len(dedup_school_cluster(near)) == 2
    assert len(dedup_school_cluster(
        [{"name": "서울교육대학교"}, {"name": "서울교육대학교부설초등학교"}])) == 2


def test_mother_school_name_empty():
    assert mother_school_name("") == ""
    assert mother_school_name(None) == ""


# ────────────────────────────────────────────────────────────────────────────
# (2) dedup_school_cluster — 병합·오탐·멱등
# ────────────────────────────────────────────────────────────────────────────


def test_dedup_task_verification_5names_to_2():
    """★태스크 단위검증: [대보초·운동장·병설유치원·대보초 분교·구룡포초] → [대보초, 구룡포초] 2개.

    부속 3개는 대보초로 병합, 다른 학교(구룡포초)는 유지(좌표 없이 이름만으로도).
    """
    pois = [{"name": n} for n in [
        "대보초등학교", "대보초등학교 운동장", "대보초등학교병설유치원",
        "대보초 분교", "구룡포초등학교",
    ]]
    out = dedup_school_cluster(pois)
    got = [mother_school_name(o["name"]) for o in out]
    assert len(out) == 2
    assert set(got) == {"대보초등학교", "구룡포초등학교"}


def test_dedup_fixture_shape_5_to_1():
    """fixture shape(x/y 좌표) 대보초 부속 5개 → 고유 모학교 1(입지점수 재계산 대상값)."""
    assert school_cluster_count(_DAEBO5) == 1
    rep = dedup_school_cluster(_DAEBO5)[0]
    assert "대보초등학교" in rep["name"]
    assert rep["distance_m"] == 120  # 대표 = 최근접(본교)


def test_dedup_false_positive_diff_name_nearby_not_merged():
    """★오탐 차단: 이름다른 실제 학교(대보초 vs 구룡포초)는 근접해도 병합 안 함."""
    near = [
        {"name": "대보초등학교", "x": 129.56, "y": 36.07},
        {"name": "구룡포초등학교", "x": 129.5601, "y": 36.0701},  # 근접이나 다른 학교
    ]
    assert len(dedup_school_cluster(near)) == 2


def test_dedup_proximity_only_diff_name_not_merged():
    """★근접만으로 병합 금지: 같은 좌표라도 모학교명 다르면 별개(이름정규화 일치 필수)."""
    same_coord = [
        {"name": "대보초등학교", "x": 129.56, "y": 36.07},
        {"name": "호미곶중학교", "x": 129.56, "y": 36.07},  # 동일 좌표·다른 학교
    ]
    assert len(dedup_school_cluster(same_coord)) == 2


def test_dedup_same_name_far_apart_kept_separate():
    """같은 모학교명이라도 반경 밖(>250m)이면 보수적으로 별개(좌표 가드)."""
    far = [
        {"name": "중앙초등학교", "x": 129.56, "y": 36.07},
        {"name": "중앙초등학교", "x": 129.60, "y": 36.10},  # 수 km 밖
    ]
    assert len(dedup_school_cluster(far)) == 2


def test_dedup_idempotent():
    """멱등: 이미 dedup된 목록을 다시 넣어도 동일 수(원천 dedup + 소비처 dedup 이중 안전)."""
    once = dedup_school_cluster(_DAEBO5)
    assert school_cluster_count(once) == len(once) == 1


def test_dedup_empty_and_none():
    assert dedup_school_cluster([]) == []
    assert dedup_school_cluster(None) == []


# ────────────────────────────────────────────────────────────────────────────
# (3) 불변식(cross_field.G2) — 경로 비의존 + 변이-kill
# ────────────────────────────────────────────────────────────────────────────


def test_invariant_reads_multiple_shapes():
    """불변식이 poi.*·education.*·infrastructure.*·평면 shape 모두에서 판정(경로 비의존)."""
    from app.services.verification.field_audit.invariants.cross_field import (
        _g2_school_poi_dedup,
    )
    for payload in [
        {"poi": {"schools": _DAEBO5, "school_count": 5}},
        {"education": {"schools": _DAEBO5, "school_count": 5}},
        {"infrastructure": {"schools": _DAEBO5}, "school_count": 5},
        # ★2026-08-02 추가 — **프로덕션 analyze() 실제 shape**(location 밑에 education이 들어간다).
        #   이 shape가 빠져 있어서 "경로 비의존"이라는 이 테스트의 제목이 참이 아니었다: 위 3개는
        #   전부 골든/보조 경로이고, 정작 사용자가 보는 종합분석 응답 경로에서는 규칙이 학교
        #   카운트를 찾지 못해 **한 번도 발동할 수 없었다**. 라이브 응답으로 실측 확인한 자리다.
        {"location": {"education": {"schools": _DAEBO5, "school_count": 5}}},
    ]:
        findings = _g2_school_poi_dedup(payload, {})
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "G2_SCHOOL_POI_DEDUP" and f.severity == "P1" and f.tier == "A"
        assert f.expected == 1 and f.observed == 5 and f.field == "school_count"
    # 근본수정 후(이미 dedup된 카운트) → 무발동
    fixed = {"poi": {"schools": dedup_school_cluster(_DAEBO5), "school_count": 1}}
    assert _g2_school_poi_dedup(fixed, {}) == []
    # 카운트 미산출 → 무발동(정상 필지 배지 인플레 방지)
    assert _g2_school_poi_dedup({"poi": {"schools": _DAEBO5}}, {}) == []


def test_mutation_defeating_normalization_kills_g2_finding(monkeypatch):
    """★변이-kill: 이름정규화를 무력화(identity)하면 과카운트가 복귀(5→5)해 G2 finding이 사라진다.

    골든 flip이 dedup_school_cluster의 모학교 정규화에 **실제로 의존**함을 증명(가드가 죽는지 확인).
    """
    from app.services.verification.field_audit.invariants.cross_field import (
        _g2_school_poi_dedup,
    )
    payload = {"poi": {"schools": _DAEBO5, "school_count": 5}}
    # 기준선: 정규화 정상 → dedup 1 ≠ 5 → G2 발동
    assert len(_g2_school_poi_dedup(payload, {})) == 1

    # 변이: 모학교명 정규화를 raw identity로 교체(부속·분교 접미 미제거) → 5개 distinct 키
    monkeypatch.setattr(pd, "mother_school_name", lambda name: (name or ""))
    assert school_cluster_count(_DAEBO5) == 5             # 변이 반영(과카운트 복귀)

    # 이제 expected(5) == observed(5) → G2 무발동(가드가 죽음 = 변이-kill 성립)
    assert _g2_school_poi_dedup(payload, {}) == []


# ────────────────────────────────────────────────────────────────────────────
# (4) 소비처①: comprehensive_analysis_service._analyze_location → education.school_count
# ────────────────────────────────────────────────────────────────────────────


def test_comprehensive_location_dedups_schools():
    """★근원봉합 flip: 대보초 5개교 raw → education.school_count 1. 학군 서술도 '우수'(3개↑) 아님."""
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )
    svc = ComprehensiveAnalysisService()
    base = {"infrastructure": {"schools": list(_DAEBO5),
                               "nearest_subway": {"name": "포항역", "distance_m": 400}}}
    out = asyncio.run(svc._analyze_location(base))
    assert out["education"]["school_count"] == 1                    # 5→1 flip
    assert out["transportation"]["nearest_subway"]["name"] == "포항역"  # 지하철 무회귀
    # 학군 서술이 '보통(1개소)' — 과대('우수' 3개↑) 아님
    joined = " ".join(out["score_breakdown"])
    assert "1개소" in joined and "학군 우수" not in joined


def test_comprehensive_no_regression_distinct_schools():
    """★무회귀: 서로 다른 실제 학교 2개는 2로 유지(과병합 없음)."""
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )
    svc = ComprehensiveAnalysisService()
    schools2 = [
        {"name": "대보초등학교", "distance_m": 120, "x": 129.56, "y": 36.07},
        {"name": "구룡포초등학교", "distance_m": 800, "x": 129.60, "y": 36.10},
    ]
    out = asyncio.run(svc._analyze_location({"infrastructure": {"schools": schools2}}))
    assert out["education"]["school_count"] == 2


# ────────────────────────────────────────────────────────────────────────────
# (5) 소비처②: site_score_service.compute_site_score → school factor
# ────────────────────────────────────────────────────────────────────────────


def test_site_score_dedups_schools():
    """site_score 학군 factor가 고유 모학교 수(1)를 쓴다(raw 5개 → 1개)."""
    from app.services.site_score.site_score_service import compute_site_score
    out = compute_site_score({"infrastructure": {"schools": list(_DAEBO5)},
                              "zone_type": "자연녹지지역"})
    sf = next(f for f in out["factors"] if f["key"] == "school")
    assert "/1개" in sf["raw"]              # school_n = 1 (5→1)
    assert "반경 내 1개" in sf["note"]


# ────────────────────────────────────────────────────────────────────────────
# (6) 소비처③: kakao_local_service.poi_inventory SC4 dedup + 다른 카테고리 무회귀
# ────────────────────────────────────────────────────────────────────────────


def test_kakao_poi_inventory_dedups_sc4_only(monkeypatch):
    """★전역 스윕: SC4(학교)만 dedup(5→1), 다른 POI(HP8 병원)는 카운트·항목 무회귀."""
    import app.services.external_api.kakao_local_service as kls

    monkeypatch.setattr(kls, "_rest_key", lambda: "fake-key")  # 네트워크 없이 분기 진입
    school_items = [dict(s, lat=s["y"], lon=s["x"]) for s in _DAEBO5]
    hospitals = {"count": 3, "nearest_m": 200, "items": [
        {"name": "포항병원", "distance_m": 200, "lat": 36.07, "lon": 129.56},
        {"name": "호미곶의원", "distance_m": 300, "lat": 36.071, "lon": 129.561},
        {"name": "대보의원", "distance_m": 400, "lat": 36.072, "lon": 129.562},
    ]}

    async def fake_cat(self, lat, lon, code, radius=1000, size=15):
        if code == "SC4":
            return {"count": 5, "nearest_m": 120, "items": school_items}
        return hospitals

    monkeypatch.setattr(kls.KakaoLocalService, "category_search", fake_cat)
    svc = kls.KakaoLocalService()
    out = asyncio.run(svc.poi_inventory(36.07, 129.56,
                                        categories=[("SC4", "학교"), ("HP8", "병원")]))
    sc4 = out["categories"]["SC4"]
    hp8 = out["categories"]["HP8"]
    assert sc4["count"] == 1 and len(sc4["items"]) == 1     # 학교 dedup 5→1
    assert hp8["count"] == 3 and len(hp8["items"]) == 3     # ★병원 무회귀(dedup 미적용)
