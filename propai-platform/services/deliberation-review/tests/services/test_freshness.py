"""INC-12 — 수집 신선도 게이트 검증.

as_of(신청일) 대비 노후 출처를 합의 직전 표면화(STALE→needs_review 보수화, 무음 사용 금지).
메타 비교는 결정론. as_of 미전달 시 기존 동작 보존(후방호환).
"""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.cross_validation import SourceValue
from app.services.cross_validate.validator import CrossSourceValidator
from app.services.pipeline.analysis_pipeline import run_analysis


def test_source_value_is_stale():
    sv = SourceValue(source="a", value=1, data_vintage=date(2020, 1, 1), max_age_days=365)
    assert sv.is_stale(date(2026, 1, 1)) is True          # ~6년 > 365일
    assert sv.is_stale(date(2020, 6, 1)) is False          # 365일 이내
    assert sv.is_stale(None) is False                      # as_of 없음 → 미평가
    assert SourceValue(source="b", value=1).is_stale(date(2026, 1, 1)) is False  # max_age 없음


def test_validator_staleness_marks_needs_review():
    # 값은 만장일치여도 노후 출처가 있으면 needs_review(보수화). status는 합의 결과 정직 보존.
    svs = [SourceValue(source="old", value=250, data_vintage=date(2019, 1, 1), max_age_days=365),
           SourceValue(source="new", value=250, data_vintage=date(2025, 12, 1), max_age_days=365)]
    cv = CrossSourceValidator().validate("far", svs, as_of=date(2026, 1, 1))
    assert cv.status.value == "UNANIMOUS"
    assert cv.stale_sources == ["old"]
    assert cv.needs_review is True


def test_validator_no_as_of_backward_compat():
    # as_of 미전달 → 신선도 미평가(기존 호출자·vision_consensus 무영향).
    svs = [SourceValue(source="old", value=250, data_vintage=date(2019, 1, 1), max_age_days=365),
           SourceValue(source="y", value=250)]
    cv = CrossSourceValidator().validate("far", svs)
    assert cv.stale_sources == []
    assert cv.needs_review is False


def test_validator_deterministic():
    svs = [SourceValue(source="old", value=250, data_vintage=date(2019, 1, 1), max_age_days=365),
           SourceValue(source="new", value=250, data_vintage=date(2025, 12, 1), max_age_days=365)]
    a = CrossSourceValidator().validate("far", svs, as_of=date(2026, 1, 1))
    b = CrossSourceValidator().validate("far", svs, as_of=date(2026, 1, 1))
    assert a == b


def test_land_card_is_stale():
    from app.contracts.land_card import LandCard
    lc = LandCard(pnu="1" * 19, stdr_year="2020", max_age_days=365)
    assert lc.is_stale(date(2026, 1, 1)) is True
    assert lc.is_stale(date(2020, 6, 1)) is False                                # 365일 이내
    assert lc.is_stale(None) is False                                            # as_of 없음
    assert LandCard(pnu="1" * 19, stdr_year="2020").is_stale(date(2026, 1, 1)) is False  # max_age 없음
    assert LandCard(pnu="1" * 19, max_age_days=365).is_stale(date(2026, 1, 1)) is False  # stdr_year 없음


def test_pipeline_cross_validation_staleness_surfaced():
    # 파이프라인 cross_facts — 노후 출처(2020 자료)가 신청일(2026) 대비 STALE → needs_review(무음0).
    inp = AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        cross_facts=[{"fact_key": "far", "sources": [
            {"source": "a", "value": 250, "data_vintage": "2020-01-01", "max_age_days": 365},
            {"source": "b", "value": 250, "data_vintage": "2025-12-01", "max_age_days": 365},
        ]}])
    r = run_analysis(inp)
    cv = next(c for c in r.cross_validations if c.fact_key == "far")
    assert cv.status.value == "UNANIMOUS"
    assert cv.stale_sources == ["a"] and cv.needs_review is True
