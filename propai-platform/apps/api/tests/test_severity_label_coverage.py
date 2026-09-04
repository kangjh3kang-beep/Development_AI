"""등급 라벨 커버리지 불변식 — 등급이 늘었는데 문구가 빠지면 원시 enum이 화면으로 샌다.

★독립 오라클을 쓴다: 라벨 맵의 정합성을 라벨 맵으로 검사하면 동어반복이다. 여기서는
  `_RANK`(등급 순위표 — 라벨과 무관한 목적으로 유지되는 별개 자료구조)를 기준으로
  라벨 맵의 키 집합을 검사한다. 등급을 추가하려면 `_RANK`를 반드시 건드려야 하므로,
  라벨을 빠뜨린 채로는 이 테스트를 통과할 수 없다.

★도메인은 합치지 않는다: 같은 토큰이 도메인마다 다른 뜻이다(POSSIBLE = 일반에선
  "개발 가능", 접도에선 "접도 가능"). 그래서 **문구**는 각자 갖되 **키 집합**만 맞춘다
  (2026-08-02 W4 교훈 14 — 평면 사전 금지).
"""
from app.services.access import access_basis_service as access
from app.services.zoning import special_parcel as sp


def test_general_domain_covers_every_rank_grade():
    """일반 개발가능성 문구가 _RANK의 모든 등급을 덮는다."""
    missing = set(sp._RANK) - set(sp._SEVERITY_LABEL_BY_GATE)
    assert not missing, f"문구 누락 등급: {sorted(missing)}"


def test_access_domain_covers_every_rank_grade():
    """접도 도메인 문구도 _RANK의 모든 등급을 덮는다."""
    missing = set(sp._RANK) - set(access._SEVERITY_LABEL)
    assert not missing, f"접도 문구 누락 등급: {sorted(missing)}"


def test_domains_keep_their_own_wording():
    """★도메인 문구를 합치지 않는다 — 합쳐졌으면 한쪽이 오역을 생산한다."""
    assert sp._SEVERITY_LABEL_BY_GATE["POSSIBLE"] != access._SEVERITY_LABEL["POSSIBLE"]
    assert "접도" in access._SEVERITY_LABEL["POSSIBLE"]
    assert "개발" in sp._SEVERITY_LABEL_BY_GATE["POSSIBLE"]


def test_unregistered_grade_is_not_leaked_raw():
    """미등재 등급은 원시 코드만 던지지 않는다 — 설명이 없다는 사실을 함께 말한다."""
    got = sp._severity_label("FUTURE_GRADE_X")
    assert "FUTURE_GRADE_X" in got
    assert got != "FUTURE_GRADE_X"
    assert "설명 준비 중" in got


def test_unregistered_grade_gets_no_invented_name():
    """모르는 등급에 그럴듯한 한국어를 지어내지 않는다."""
    got = sp._severity_label("FUTURE_GRADE_X")
    for invented in ("가능", "불가", "필요", "제한"):
        assert invented not in got.replace("설명 준비 중", "")


def test_blank_grade_is_empty_not_placeholder():
    """빈 등급은 빈 문자열 — 소비처의 조건부 표기가 종전대로 동작한다."""
    assert sp._severity_label(None) == ""
    assert sp._severity_label("   ") == ""


def test_registered_grades_render_their_wording():
    """등재 등급은 문구 그대로(대소문자·공백 정규화 포함)."""
    for grade, wording in sp._SEVERITY_LABEL_BY_GATE.items():
        assert sp._severity_label(grade) == wording
        assert sp._severity_label(f"  {grade.lower()} ") == wording


def test_end_to_end_special_parcel_reports_wording_not_code():
    """★실제 산출물에 원시 enum이 아니라 문구가 실린다 — 맵만 보고 통과하지 않게 관통 확인."""
    result = sp.detect_special_parcel({
        "land_category": "임야", "zone_type": "보전관리지역",
    })
    label = result["severity_label"]
    assert label
    assert label not in sp._RANK  # 등급 코드 그대로가 아니다
    assert label in set(sp._SEVERITY_LABEL_BY_GATE.values())
