"""종상향 — **라벨과 값은 같은 용도지역을 가리켜야 한다** 배선 락.

【무엇이 잘못돼 있었나 — 2026-08-19 실측】
`cbf16e01`("종상향 150% 천장 제거")이 상·하한을 **후보 전체의 합집합**에서 냈다.
그런데 `target_zone` 은 여전히 **대표 후보 하나**였다:

    target=제2종일반주거지역(법정 150~250)          high=300  ← 그 용도지역의 법정상한 초과
    source='지자체 도시계획조례(목표지역)'(조례 150)  high=200  ← 라벨한 조례값 초과

★후자가 더 위험하다. 출처를 붙인 채 그 출처를 넘는 값은 근거가 아니라 **거짓 근거**다.
`_target_far_pct` 는 `min(조례, 법정)` 을 이미 하고 있었고, 합집합 덮어쓰기가 그 min 을
무력화하고 있었을 뿐이다.

【이 파일이 잠그는 것】
1. 최상위 3필드(`target_zone`·`expected_far_pct_*`·`expected_far_source`)가 **내부 정합**
2. 상향 여지는 **지우지 않고** 자기 용도지역 라벨과 함께(`upside_far_*`) 낸다
3. 조례 라벨이면 값이 **조례를 넘지 않는다**(min 복원)
"""

import pytest

from app.services.zoning.legal_zone_limits import check_against_legal, legal_limits_for
from app.services.zoning.upzoning_potential import UPZONE_TARGETS, UpzoningPotentialAnalyzer

# ★손으로 고른 목록이 아니라 **상수에서 파생**한다 — 사람이 센 목록은 곧 상한이 되고,
#   새 용도지역이 `UPZONE_TARGETS` 에 추가돼도 자동으로 감시망에 들어오지 않는다(규율 A.4).
#   (실제로 처음엔 손으로 골랐다가 종상향 대상이 아닌 용도지역을 넣어 '시나리오 0건'
#    공허-진리 가드에 걸렸다 — 가드가 내 테스트 설계 오류를 잡았다.)
BASES = tuple(sorted(UPZONE_TARGETS))


@pytest.fixture
def analyzer() -> UpzoningPotentialAnalyzer:
    return UpzoningPotentialAnalyzer()


def _scenarios(analyzer, base, **kw):
    return analyzer.analyze(base, land_area_sqm=6000, **kw)["scenarios"]


def test_premise_multiple_candidates_exist():
    """전제 — 후보가 2개 이상인 base 가 있어야 '합집합 vs 대표' 문제가 성립한다."""
    multi = [b for b in BASES if len(UPZONE_TARGETS.get(b) or []) >= 2]
    assert multi, "후보가 2개 이상인 base 가 없다 — 이 파일의 검증이 공허하다"


@pytest.mark.parametrize("base", BASES)
def test_top_level_range_is_inside_its_own_target_zone(analyzer, base):
    """★최상위 상·하한이 **선언된 `target_zone`** 의 법정범위 안에 있다."""
    scenarios = _scenarios(analyzer, base)
    assert scenarios, f"{base}: 시나리오가 없다 — 검증 대상 0(공허한 통과)"
    for s in scenarios:
        legal = legal_limits_for(s["target_zone"])
        assert legal, f"{base}/{s['path_key']}: target_zone 법정범위 미상"
        hi, lo = s["expected_far_pct_high"], s["expected_far_pct_low"]
        assert hi is not None and lo is not None
        assert lo <= hi
        assert hi <= legal["max_far_pct"], (
            f"{base}/{s['path_key']}: target={s['target_zone']} high={hi} "
            f"> 법정상한 {legal['max_far_pct']}"
        )


@pytest.mark.parametrize("base", BASES)
def test_platform_own_guard_flags_nothing(analyzer, base):
    """★플랫폼 자신의 할루시네이션 가드가 **한 건도** 잡지 않는다.

    ★`check_against_legal` 은 `(zone_type, bcr_pct=None, far_pct=None, …)` 이라
      **두 번째 위치인자가 건폐율**이다. 용적률을 위치로 넘기면 60% 상한과 비교돼
      **합법값도 위반으로** 찍힌다(실측으로 겪었다) — 반드시 `far_pct=` 키워드로 준다.
    """
    checked = 0
    for s in _scenarios(analyzer, base):
        for zone, val in ((s["target_zone"], s["expected_far_pct_high"]),
                          (s.get("upside_far_zone"), s.get("upside_far_pct_high"))):
            if not zone or val is None:
                continue
            checked += 1
            hits = [i for i in check_against_legal(zone, far_pct=float(val), has_basis=False)
                    if i.get("severity") == "high"]
            assert not hits, f"{base}: {zone} @ {val}% — {hits[0]['note'][:80]}"
    assert checked, f"{base}: 검사한 쌍이 0건 — 공허한 통과"


@pytest.mark.parametrize("base", BASES)
def test_each_candidate_is_internally_coherent(analyzer, base):
    """후보 항목도 각자 **자기 용도지역**의 범위만 담는다(상·하한 둘 다).

    ★`target_zone_candidates` **존재**를 먼저 단언한다 — 없으면 아래 순회가 0회 돌아
      공허하게 통과한다(변이로 실증: 그 키를 지워도 초록이었다).
    """
    for s in _scenarios(analyzer, base):
        cands = s.get("target_zone_candidates")
        assert cands, f"{base}/{s['path_key']}: 후보 목록이 비었다 — 순회가 공허해진다"
        assert len(cands) == len(UPZONE_TARGETS[base]), "후보 수가 상수와 어긋난다"
        for c in cands:
            legal = legal_limits_for(c["target_zone"])
            assert legal, f"후보 {c['target_zone']} 법정범위 미상"
            hi, lo = c["expected_far_pct_high"], c["expected_far_pct_low"]
            assert hi is not None and lo is not None
            assert lo <= hi
            assert hi <= legal["max_far_pct"]
            # ★하한도 그 용도지역 법정 하한과 정합해야 한다(상한만 보면 하한이 무잠금).
            assert lo >= legal["min_far_pct"]


@pytest.mark.parametrize("base", BASES)
def test_target_zone_max_names_the_last_candidate(analyzer, base):
    """`target_zone_max` 가 **가장 높은 후보**를 가리킨다 — 화면이 상한 라벨로 쓴다."""
    for s in _scenarios(analyzer, base):
        cands = s["target_zone_candidates"]
        assert s["target_zone_max"] == cands[-1]["target_zone"]
        assert s["target_zone_max"] in UPZONE_TARGETS[base]


@pytest.mark.parametrize("base", BASES)
def test_upside_triple_is_internally_consistent(analyzer, base):
    """★상향 여지 3필드(값·용도지역·출처)가 **같은 후보**를 가리킨다.

    라벨만 맞고 출처가 다른 후보 것이면 사용자가 근거를 잘못 따라간다.
    """
    for s in _scenarios(analyzer, base):
        hi, zone, src = (s["upside_far_pct_high"], s["upside_far_zone"],
                         s["upside_far_source"])
        assert hi is not None and zone and src, f"{base}/{s['path_key']}: upside 3필드 결측"
        match = [c for c in s["target_zone_candidates"] if c["target_zone"] == zone]
        assert match, f"{zone} 가 후보에 없다"
        assert match[0]["expected_far_pct_high"] == hi
        assert match[0]["expected_far_source"] == src


def test_upside_is_preserved_and_labelled(analyzer):
    """★★상향 여지를 **지우지 않았다** — 다만 어느 용도지역의 값인지 밝힌다.

    이 단언이 깨지면 `cbf16e01` 이 고치려던 사용자 불만("어떤 경로도 150%를 못 넘는다")이
    되살아난다. 값은 남기되 **라벨을 붙이는 것**이 이 교정의 요점이다.
    """
    s = next(x for x in _scenarios(analyzer, "제1종일반주거지역") if x["path_key"] == "정비사업")
    assert s["target_zone"] == "제2종일반주거지역"
    assert s["expected_far_pct_high"] == 250          # 2종 법정상한 — 라벨과 정합
    # 상향 여지는 여전히 보인다: 3종까지 가면 300.
    assert s["upside_far_pct_high"] == 300
    assert s["upside_far_zone"] == "제3종일반주거지역"
    # ★그리고 그 값은 **자기 용도지역** 안이다(라벨만 붙이고 위법값을 남기면 무의미).
    assert s["upside_far_pct_high"] <= legal_limits_for(s["upside_far_zone"])["max_far_pct"]


def test_ordinance_labelled_value_never_exceeds_the_ordinance(analyzer):
    """★출처가 '조례'면 값이 **그 조례값을 넘지 않는다**(`min(조례, 법정)` 복원).

    종전엔 source='지자체 도시계획조례(목표지역)' 인데 조례 실측 150, 산출 200 이었다 —
    값만 바꾸면 `"조례" in source` 검사도 통과해 **거짓 라벨이 고정**된다.
    """
    ORD = {"제1종일반주거지역": 150.0}

    def resolver(sigungu: str, zone_type: str):
        return ORD.get(zone_type)

    scenarios = _scenarios(analyzer, "자연녹지지역", sigungu="서울특별시",
                           ordinance_far_resolver=resolver)
    hit = [s for s in scenarios if "조례" in (s["expected_far_source"] or "")]
    assert hit, "조례 출처 시나리오가 없다 — 이 검증이 공허하다"
    for s in hit:
        assert s["expected_far_pct_high"] <= ORD[s["target_zone"]], (
            f"{s['path_key']}: 조례 라벨인데 조례값 {ORD[s['target_zone']]} 초과 "
            f"({s['expected_far_pct_high']})"
        )


def test_no_ordinance_no_ordinance_label(analyzer):
    """대조군 — resolver 없으면 출처가 조례라고 말하지 않는다(라벨의 위양성 방지)."""
    scs = _scenarios(analyzer, "자연녹지지역")
    # ★공허 진리 가드 — 시나리오가 0건이면 아래 단언이 대상 없이 참이 된다.
    assert scs, "자연녹지 시나리오 0건 — 검증 대상이 없다"
    for s in scs:
        assert "조례" not in (s["expected_far_source"] or "") or "확인 필요" in s["expected_far_source"]
    # ★양성 짝 — resolver 를 주면 **조례 출처가 실제로 붙는다**(안 붙는 이유가 resolver 부재임을 증명).
    with_ord = _scenarios(analyzer, "자연녹지지역", sigungu="서울특별시",
                          ordinance_far_resolver=lambda sg, z: 150.0)
    assert any("조례" in (x["expected_far_source"] or "") for x in with_ord)
