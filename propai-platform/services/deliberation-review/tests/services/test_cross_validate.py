"""다중출처 교차검증 — 합의 판정(만장/과반/불일치/단일/결손)·수치허용오차·결정론·무음금지."""
from app.contracts.cross_validation import CrossStatus, SourceValue
from app.services.cross_validate.validator import CrossSourceValidator

V = CrossSourceValidator()


def _sv(src, val, ref=None):
    return SourceValue(source=src, value=val, ref=ref)


def test_unanimous_max_confidence():
    r = V.validate("far_limit", [_sv("law_go_kr", 200.0), _sv("mirror", 200.0), _sv("vworld", 200.0)])
    assert r.status == CrossStatus.UNANIMOUS
    assert r.agreed_value == 200.0 and r.confidence == 1.0
    assert r.dissent == [] and not r.needs_review


def test_majority_surfaces_dissent():
    r = V.validate("far_limit", [_sv("law_go_kr", 200.0), _sv("mirror", 200.0), _sv("data_go", 250.0)])
    assert r.status == CrossStatus.MAJORITY
    assert r.agreed_value == 200.0
    assert r.dissent == ["data_go"]  # 이견 출처 표면화
    assert abs(r.confidence - 2 / 3) < 1e-9


def test_conflict_needs_review():
    # 동수 분산 → 합의 실패 → NEEDS_REVIEW(무음 오판 0).
    r = V.validate("far_limit", [_sv("law_go_kr", 200.0), _sv("mirror", 250.0)])
    assert r.status == CrossStatus.CONFLICT
    assert r.needs_review
    assert set(r.by_source.values()) == {200.0, 250.0}  # 출처별 값 모두 보존


def test_single_source_conservative():
    r = V.validate("far_limit", [_sv("law_go_kr", 200.0)])
    assert r.status == CrossStatus.SINGLE
    assert r.confidence == 0.5 and r.needs_review  # 단일 출처는 교차검증 불가


def test_absent_surfaced():
    r = V.validate("far_limit", [_sv("law_go_kr", None), _sv("mirror", None)])
    assert r.status == CrossStatus.ABSENT
    assert r.needs_review and r.sources_present == 0


def test_float_tolerance_groups():
    # 미세 부동소수 차이는 동일로 합의(반올림 정규화).
    r = V.validate("far", [_sv("a", 200.0000001), _sv("b", 200.0), _sv("c", 200.0)])
    assert r.status == CrossStatus.UNANIMOUS


def test_string_normalization():
    r = V.validate("zone", [_sv("a", "제2종일반주거"), _sv("b", " 제2종일반주거 "), _sv("c", "제2종일반주거")])
    assert r.status == CrossStatus.UNANIMOUS


def test_deterministic():
    vals = [_sv("law_go_kr", 200.0), _sv("mirror", 250.0), _sv("vworld", 200.0)]
    assert V.validate("k", vals) == V.validate("k", vals)
