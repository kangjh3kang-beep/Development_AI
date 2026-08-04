"""미분석 표식이 **사용자가 보는 표면까지** 도달하는지 — 그리고 정상 필지를 오판하지 않는지.

★왜 이 파일이 있나(2026-08-03 R2 적대검증 + 그 봉합이 만든 오탐):

  ① 백엔드가 미분석 필지를 정직하게 강등해 놓고, 그 신호를 **API 응답에 안 실어 보냈다.**
     프론트는 `analysis_status === "unanalyzed"` 일 때 "판정 불가(미분석)" 배지를 띄우도록
     작성돼 있었는데, 그 배지를 먹여줄 두 표면이 모두 키를 빼먹어 **한 번도 뜬 적 없는
     죽은 코드**였다. 게다가 매트릭스는 신호가 없으면 POSSIBLE/YES로 하드 폴백해, 못 본
     필지를 **"가능·PASS"(일상 개발부지)** 로 표기했다 — 같은 응답의 면적 3계층은 그 필지를
     conditional로 세는데 판정 칸만 "가능"이라 표면끼리 모순이었다.

  ② ①을 고치는 과정에서 **반대 방향 오탐**을 내가 직접 만들었다. 표식이 없는 입력을 하류가
     스스로 판정하게 했는데, per_parcel 엔트리가 zone_type을 싣지 않는다는 이유로 지목이
     빈 **정상 필지를 미분석으로 오판**했다(설계 제안이 통째로 잠정 강등). 백엔드 전체
     스위트 8939건이 이걸 못 잡았다 — 숫자를 기준선과 대조해서야 드러났다.

  그래서 두 방향을 같이 잠근다. 강등 누락과 과잉강등은 같은 계약의 양면이다.
"""
import pytest

from app.services.zoning.special_parcel import build_multi_parcel_report, detect_multi_parcel

ANALYZED_A = {"pnu": "a", "area_sqm": 400.0, "zone_type": "제2종일반주거지역", "land_category": "대"}
ANALYZED_B = {"pnu": "b", "area_sqm": 600.0, "zone_type": "제2종일반주거지역", "land_category": "대"}
UNANALYZED_B = {"pnu": "b", "area_sqm": 600.0}
# ★내가 만든 오탐의 정확한 형상: 용도지역은 아는데 지목이 비어 있다(설계 생성 경로가 이렇다).
ZONE_ONLY_B = {"pnu": "b", "area_sqm": 600.0, "zone_type": "제2종일반주거지역", "land_category": ""}


def _row(matrix, pnu):
    return next(r for r in matrix if r["pnu"] == pnu)


def test_per_parcel_declares_verdict_both_ways():
    """★표식은 양방향으로 선언한다 — 부재가 '분석됨'인지 '판정 안 함'인지 모호하면 안 된다."""
    out = detect_multi_parcel([ANALYZED_A, UNANALYZED_B])
    statuses = [p.get("analysis_status") for p in out["per_parcel"]]
    assert statuses == ["analyzed", "unanalyzed"]
    assert None not in statuses


def test_zone_known_but_category_empty_is_not_downgraded():
    """★과잉강등 금지 — 용도지역을 아는 필지는 지목이 비어도 정상이다(내가 낸 오탐의 재현)."""
    out = detect_multi_parcel([ANALYZED_A, ZONE_ONLY_B])
    usable = out["usable_area"]
    assert usable["usable_confirmed_sqm"] == 1000.0
    assert usable["usable_conditional_sqm"] == 0.0
    assert [p.get("analysis_status") for p in out["per_parcel"]] == ["analyzed", "analyzed"]


def test_matrix_carries_status_to_the_surface():
    """★프론트 배지가 읽는 키가 실제로 응답에 실린다 — 죽은 코드였던 것을 살린다."""
    matrix = build_multi_parcel_report([ANALYZED_A, UNANALYZED_B])["matrix"]
    assert _row(matrix, "b")["analysis_status"] == "unanalyzed"
    assert _row(matrix, "a")["analysis_status"] == "analyzed"


def test_matrix_does_not_label_unseen_parcel_as_developable():
    """★'신호 부재'를 '가능'으로 덮지 않는다 — 판정 칸과 면적 계층이 어긋나지 않아야 한다."""
    matrix = build_multi_parcel_report([ANALYZED_A, UNANALYZED_B])["matrix"]
    row = _row(matrix, "b")
    assert row["developability"] == "UNKNOWN"
    assert row["resolvable"] == "UNKNOWN"
    assert row["gate"] != "PASS"
    # 같은 응답 안에서 두 칸이 서로 다른 말을 하지 않는다.
    assert row["usable_tier"] == "conditional"


def test_matrix_control_is_unchanged():
    """정상 2필지는 종전과 동일 — 오탐 0."""
    matrix = build_multi_parcel_report([ANALYZED_A, ANALYZED_B])["matrix"]
    for pnu in ("a", "b"):
        row = _row(matrix, pnu)
        assert row["developability"] == "POSSIBLE"
        assert row["gate"] == "PASS"
        assert row["usable_tier"] == "confirmed"


@pytest.mark.parametrize("parcels,expected", [
    ([ANALYZED_A, ANALYZED_B], 0.0),
    ([ANALYZED_A, UNANALYZED_B], 600.0),
])
def test_conditional_area_tracks_unanalyzed_area(parcels, expected):
    """조건부 면적이 미분석 면적과 정확히 일치한다 — '값이 있다'가 아니라 '값이 변했다'."""
    usable = detect_multi_parcel(parcels)["usable_area"]
    assert usable["usable_conditional_sqm"] == expected
