"""W1-E 법령 위계 precedence resolver 테스트.

검증 범위(작업지시서 §3):
①위계 서열(조례/시행령/법률) ②시행일 필터(미시행·폐지) ③특별법 우선
④위임 한계(조례>법정 → 법정 우선) ⑤동위계 동시행일 상충=CONFLICT(양측 보존)
⑥trace 근거 비어있지 않음 ⑦실효FAR 어댑터 2케이스.
"""
from __future__ import annotations

from datetime import date

from app.services.legal.precedence_resolver import (
    AuthorityLevel,
    LegalSource,
    PrecedenceStatus,
    detect_conflicts,
    explain_far_precedence,
    resolve_precedence,
)


def _src(**kwargs) -> LegalSource:
    """테스트용 LegalSource 생성 헬퍼 — 공통 기본값(effective_from)만 채워준다."""
    kwargs.setdefault("effective_from", date(2020, 1, 1))
    return LegalSource(**kwargs)


# ── ①위계 서열 ──────────────────────────────────────────────────────────
def test_authority_order_law_beats_decree_and_ordinance():
    """법률 > 시행령 > 자치법규 — 위임·특정성 관계가 없을 때 상위법이 이긴다."""
    law = _src(source_id="law", title="법률근거", authority_level=AuthorityLevel.LAW, value=10)
    decree = _src(source_id="decree", title="시행령근거", authority_level=AuthorityLevel.ENFORCEMENT_DECREE, value=20)
    ordinance = _src(source_id="ord", title="조례근거", authority_level=AuthorityLevel.ORDINANCE, value=30)

    result = resolve_precedence([law, decree, ordinance])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner is not None
    assert result.winner.source_id == "law"


def test_authority_order_decree_beats_ordinance():
    """시행령 > 자치법규(조례) — 위임 관계 없이 두 근거만 있을 때."""
    decree = _src(source_id="decree", title="시행령근거", authority_level=AuthorityLevel.ENFORCEMENT_DECREE, value=100)
    ordinance = _src(source_id="ord", title="조례근거", authority_level=AuthorityLevel.ORDINANCE, value=80)

    result = resolve_precedence([decree, ordinance])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "decree"


def test_authority_order_rule_beats_admrule():
    """시행규칙 > 행정규칙(고시 등)."""
    rule = _src(source_id="rule", title="시행규칙근거", authority_level=AuthorityLevel.ENFORCEMENT_RULE, value=1)
    admrule = _src(source_id="adm", title="고시근거", authority_level=AuthorityLevel.ADMIN_RULE, value=2)

    result = resolve_precedence([rule, admrule])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "rule"


# ── ②시행일 필터(미시행·폐지) ───────────────────────────────────────────
def test_effective_date_filter_excludes_not_yet_effective():
    """시행일이 기준일보다 미래인(미시행) 근거는 후보에서 제외된다."""
    current = _src(
        source_id="current", title="현행규정", authority_level=AuthorityLevel.LAW,
        effective_from=date(2020, 1, 1), value=100,
    )
    future = _src(
        source_id="future", title="미시행규정", authority_level=AuthorityLevel.LAW,
        effective_from=date(2099, 1, 1), value=999,
    )

    result = resolve_precedence([current, future], as_of=date(2026, 7, 22))
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "current"
    assert all(c.source_id != "future" for c in result.candidates)


def test_effective_date_filter_excludes_repealed():
    """effective_to가 기준일보다 과거인(폐지된) 근거는 후보에서 제외된다."""
    repealed = _src(
        source_id="repealed", title="폐지규정", authority_level=AuthorityLevel.LAW,
        effective_from=date(2010, 1, 1), effective_to=date(2020, 1, 1), value=1,
    )
    current = _src(
        source_id="current", title="현행규정", authority_level=AuthorityLevel.LAW,
        effective_from=date(2020, 1, 2), value=2,
    )

    result = resolve_precedence([repealed, current], as_of=date(2026, 7, 22))
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "current"


def test_effective_date_filter_no_source_when_all_repealed_or_future():
    """전원이 미시행/폐지면 임의값을 지어내지 않고 NO_SOURCE로 정직 표기한다."""
    repealed = _src(
        source_id="r1", title="폐지1", authority_level=AuthorityLevel.LAW,
        effective_from=date(2010, 1, 1), effective_to=date(2020, 1, 1),
    )
    future = _src(
        source_id="f1", title="미시행1", authority_level=AuthorityLevel.LAW,
        effective_from=date(2099, 1, 1),
    )
    result = resolve_precedence([repealed, future], as_of=date(2026, 7, 22))
    assert result.status == PrecedenceStatus.NO_SOURCE
    assert result.winner is None


# ── ③특별법 우선 ────────────────────────────────────────────────────────
def test_specificity_special_law_beats_general_law_same_authority():
    """같은 위계(법률)라도 특별법으로 표식된 근거가 일반법보다 우선한다(lex specialis)."""
    general = _src(
        source_id="general", title="일반법", authority_level=AuthorityLevel.LAW,
        specificity="일반법", value=100,
    )
    special = _src(
        source_id="special", title="특별법", authority_level=AuthorityLevel.LAW,
        specificity="특별법", value=200,
    )
    result = resolve_precedence([general, special])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "special"
    assert any("특정성" in t for t in result.trace)


# ── ④위임 한계(조례>법정 → 법정 우선 / 조례<=법정 → 조례 우선) ─────────────
def test_delegation_child_within_limit_wins():
    """위임받은 하위(조례)가 상위(시행령) 한도 이내로 구체화하면 하위가 우선한다."""
    parent = _src(
        source_id="parent", title="시행령상한", authority_level=AuthorityLevel.ENFORCEMENT_DECREE, value=100,
    )
    child = _src(
        source_id="child", title="조례구체화", authority_level=AuthorityLevel.ORDINANCE,
        delegation_parent="parent", value=80,
    )
    result = resolve_precedence([parent, child])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "child"
    assert any("위임 구체화" in t for t in result.trace)


def test_delegation_child_exceeding_limit_loses_to_parent():
    """위임받은 하위(조례)가 상위 한도를 초과(더 완화)하면 상위(법정)가 우선한다."""
    parent = _src(
        source_id="parent", title="시행령상한", authority_level=AuthorityLevel.ENFORCEMENT_DECREE, value=100,
    )
    child = _src(
        source_id="child", title="조례초과", authority_level=AuthorityLevel.ORDINANCE,
        delegation_parent="parent", value=150,
    )
    result = resolve_precedence([parent, child])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner.source_id == "parent"
    assert any("위임 한계 초과" in t for t in result.trace)


# ── ⑤동위계 동시행일 상충=CONFLICT(양측 보존) ───────────────────────────
def test_same_authority_same_date_conflicting_values_surfaces_conflict():
    """위임·특정성·위계로도 못 가르는 동위계 상충은 임의 승자 없이 CONFLICT + 양측 보존."""
    a = _src(source_id="a", title="근거A", authority_level=AuthorityLevel.ORDINANCE, value=100)
    b = _src(source_id="b", title="근거B", authority_level=AuthorityLevel.ORDINANCE, value=200)

    result = resolve_precedence([a, b])
    assert result.status == PrecedenceStatus.CONFLICT
    assert result.winner is None
    conflicting_ids = {c.source_id for c in result.conflicting}
    assert conflicting_ids == {"a", "b"}


def test_same_authority_same_date_agreeing_values_is_not_conflict():
    """값이 실제로 같으면(합의) 상충이 아니다 — 임의 승자 선정과 다름(동일 결론 대표 채택)."""
    a = _src(source_id="a", title="근거A", authority_level=AuthorityLevel.ORDINANCE, value=100)
    b = _src(source_id="b", title="근거B", authority_level=AuthorityLevel.ORDINANCE, value=100)

    result = resolve_precedence([a, b])
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner is not None


def test_detect_conflicts_collects_only_conflicting_groups():
    """detect_conflicts는 여러 그룹 중 CONFLICT인 것만 골라 반환한다(rule graph 소비용)."""
    resolved_group = [
        _src(source_id="r1", title="법률", authority_level=AuthorityLevel.LAW, value=1),
        _src(source_id="r2", title="조례", authority_level=AuthorityLevel.ORDINANCE, value=2),
    ]
    conflict_group = [
        _src(source_id="c1", title="조례A", authority_level=AuthorityLevel.ORDINANCE, value=10),
        _src(source_id="c2", title="조례B", authority_level=AuthorityLevel.ORDINANCE, value=20),
    ]
    conflicts = detect_conflicts([resolved_group, conflict_group])
    assert len(conflicts) == 1
    assert conflicts[0].status == PrecedenceStatus.CONFLICT
    assert {c.source_id for c in conflicts[0].conflicting} == {"c1", "c2"}


# ── ⑥trace 근거 비어있지 않음 ───────────────────────────────────────────
def test_trace_is_never_empty_across_scenarios():
    """단독/위임/특정성/위계/상충 — 어느 경로를 타도 trace는 최소 1건 이상 남는다."""
    scenarios = [
        [_src(source_id="only", title="단독근거", authority_level=AuthorityLevel.LAW)],
        [
            _src(source_id="p", title="상위", authority_level=AuthorityLevel.ENFORCEMENT_DECREE, value=100),
            _src(source_id="c", title="하위", authority_level=AuthorityLevel.ORDINANCE,
                 delegation_parent="p", value=50),
        ],
        [
            _src(source_id="x", title="X", authority_level=AuthorityLevel.ORDINANCE, value=1),
            _src(source_id="y", title="Y", authority_level=AuthorityLevel.ORDINANCE, value=2),
        ],
    ]
    for sources in scenarios:
        result = resolve_precedence(sources)
        assert len(result.trace) > 0


# ── ⑦실효FAR 어댑터 ─────────────────────────────────────────────────────
def test_explain_far_precedence_ordinance_within_limit_wins():
    """조례 80% <= 법정 100% → 위임 범위 내 구체화 → 조례 우선."""
    result = explain_far_precedence(national_far_pct=100, ordinance_far_pct=80, zone_type="제2종일반주거지역")
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner is not None
    assert result.winner.source_id == "ordinance_far"
    assert any("위임 구체화" in t for t in result.trace)


def test_explain_far_precedence_ordinance_exceeding_limit_national_wins():
    """조례 5000% > 법정 1300% → 위임 한계 초과 → 법정상한 우선."""
    result = explain_far_precedence(national_far_pct=1300, ordinance_far_pct=5000, zone_type="준주거지역")
    assert result.status == PrecedenceStatus.RESOLVED
    assert result.winner is not None
    assert result.winner.source_id == "national_far_decree"
    assert any("위임 한계 초과" in t for t in result.trace)
