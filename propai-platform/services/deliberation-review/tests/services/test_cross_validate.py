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


# ── P4 차용: 다출처 정량 ±상대오차(FD) 합의(대량필지 토지대장 vs 지적도) ──

def test_rel_tol_clusters_measurement_variance_as_unanimous():
    # ★정상 측정차(500 vs 502 = 0.4% < 5%)는 rel_tol 내 합의 — 거짓 CONFLICT 방지.
    r = V.validate("plot_area", [_sv("toji", 500.0), _sv("jijeok", 502.0)], rel_tol=0.05)
    assert r.status == CrossStatus.UNANIMOUS and r.confidence == 1.0 and r.dissent == []


def test_rel_tol_zero_keeps_exact_equality_no_regression():
    # rel_tol 기본 0 → 정확일치(기존 동작 불변): 500 vs 502는 불일치.
    r = V.validate("plot_area", [_sv("toji", 500.0), _sv("jijeok", 502.0)])
    assert r.status == CrossStatus.CONFLICT


def test_rel_tol_beyond_threshold_still_conflict():
    # tol 초과(20% > 5%)는 여전히 CONFLICT(실 차이 은폐 금지).
    r = V.validate("plot_area", [_sv("toji", 500.0), _sv("jijeok", 600.0)], rel_tol=0.05)
    assert r.status == CrossStatus.CONFLICT and r.needs_review


def test_rel_tol_majority_cluster_surfaces_outlier():
    r = V.validate("plot_area", [_sv("a", 500.0), _sv("b", 502.0), _sv("c", 600.0)], rel_tol=0.05)
    assert r.status == CrossStatus.MAJORITY and r.dissent == ["c"]
    assert abs(r.confidence - 2 / 3) < 1e-9


def test_rel_tol_ignored_for_nonnumeric():
    # 비수치/혼합은 rel_tol 무시·정확일치(일괄 tol의 거짓합의 차단).
    r = V.validate("zone", [_sv("a", "제2종"), _sv("b", "제3종")], rel_tol=0.5)
    assert r.status == CrossStatus.CONFLICT


def test_rel_tol_deterministic():
    vals = [_sv("a", 500.0), _sv("b", 502.0), _sv("c", 600.0)]
    assert V.validate("k", vals, rel_tol=0.05) == V.validate("k", vals, rel_tol=0.05)


def test_rel_tol_infinite_clamped_to_exact_no_false_unanimous():
    # ★inf/상한초과 rel_tol은 0.0(정확일치)로 방어 — 무관 수치를 거짓 UNANIMOUS로 흡수 금지(실 차이 은폐 차단).
    vals = [_sv("a", 500.0), _sv("b", 5000.0)]
    assert V.validate("k", vals, rel_tol=float("inf")).status == CrossStatus.CONFLICT
    assert V.validate("k", vals, rel_tol=99.0).status == CrossStatus.CONFLICT  # >1.0 상한초과 → exact


def test_nonfinite_source_value_deterministic_and_excluded():
    # nan 출처값은 수치 클러스터 정렬을 비결정화 → _is_number(math.isfinite)로 배제, 정확일치 경로(결정론).
    import math as _m
    fwd = V.validate("area", [_sv("a", 500.0), _sv("b", _m.nan), _sv("c", 502.0)], rel_tol=0.05)
    rev = V.validate("area", [_sv("c", 502.0), _sv("b", _m.nan), _sv("a", 500.0)], rel_tol=0.05)
    # 출처 순서 무관 동일 결과(결정론) + nan이 거짓 합의를 만들지 않음.
    assert fwd.status == rev.status == CrossStatus.CONFLICT
    assert fwd.sources_present == rev.sources_present == 3
