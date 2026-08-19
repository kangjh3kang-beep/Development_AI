"""조례 **조건부 값 × 부지 조건** 매칭 — 이 캠페인의 원래 목표.

【발단】오산 내삼미동 77필지 종합분석이 자연녹지 건폐율 20%로 나왔는데, 조례에는
`자연녹지지역` 이 **6개 조에 값이 다르게** 나온다(실측). 파서는 기본값을 골라내고 나머지를
`conditional` 로 보관하는 데까지 왔지만 **그 값이 파서 함수 밖으로 나가지 못했다** —
`_parse_bcr_far_from_text` 반환 계약에 **키 자체가 없었다**("소비처 0"보다 한 단계 이른 상태).

【이 파일이 잠그는 것】
1. `conditional_limits` 가 **반환 계약으로 나온다**(그 한 줄이 없으면 전부 무의미)
2. 조건의 정체는 **조제목**에서 온다(조각 텍스트에는 없다 — 용도지역명 뒤에서 잘린다)
3. ★★수도권 `성장관리권역` 으로는 **매칭되지 않는다** — 이 캠페인 최초 오진의 정면 차단
4. **강화** 조항(오산시 제47조 실재)은 상향 여지가 아니다
5. 건축물 용도·연혁 조건은 **판정 불가**로 정직하게 분리한다
6. `applied: False` — 후보일 뿐 적용값이 아니다(#704 와 같은 계약)

【그라운드 트루스】`tests/fixtures/ordinance_osan_2097518.xml`(오산시 조례 원문 94KB) ·
VWorld NED 실조회 designation(화성시 정남면 문학리 1 = 성장관리권역 + 성장관리계획구역).
"""

import re

import pytest

from app.services.land_intelligence.ordinance_service import OrdinanceService
from app.services.zoning.ordinance_conditional import (
    classify_article,
    find_article,
    match_site_conditions,
)

PLAN_ZONE = "성장관리계획구역"      # 국토계획법 — 조례 제50조가 걸리는 조건
METRO_REGIME = "성장관리권역"       # 수도권정비계획법 — 걸리면 안 된다


@pytest.fixture(scope="module")
def parsed() -> dict:
    svc = OrdinanceService.__new__(OrdinanceService)
    with open("tests/fixtures/ordinance_osan_2097518.xml", encoding="utf-8") as f:
        xml = f.read()
    r = svc._parse_bcr_far_from_text(xml, "자연녹지지역", "오산시")
    assert r is not None, "픽스처 파싱이 통째로 실패했다 — 아래 검증이 전부 공허해진다"
    return r


def test_premise_fixture_has_multiple_conditional_values(parsed):
    """전제 — 조건부 값이 실제로 여럿이어야 이 파일의 검증이 의미를 갖는다."""
    assert parsed["bcr"] == 20, "기본값이 제45조①16호(20%)가 아니다"
    cond = parsed["conditional_limits"]
    assert len(cond) >= 4, f"조건부 값이 {len(cond)}건뿐 — 분류·매칭 검증이 얕아진다"
    # ★값이 실제로 갈려야 한다(전부 같으면 매칭을 끊어도 결과가 같다).
    assert len({c["value"] for c in cond}) >= 2, "조건부 값이 전부 같다 — 픽스처가 두 모집단을 못 가른다"


def test_conditional_limits_actually_leave_the_parser(parsed):
    """★반환 계약 락 — 이 키가 없으면 값이 함수 밖으로 나가지 못한다(종전 상태)."""
    assert "conditional_limits" in parsed
    assert parsed["conditional_limits"], "조건부 값이 비었다 — 전파가 끊겼다"


def test_growth_management_article_is_classified(parsed):
    """조제목 앵커 — 제50조가 성장관리 조건으로 분류된다."""
    hit = [c for c in parsed["conditional_limits"]
           if c.get("condition_key") == "growth_management_plan"]
    assert hit, "성장관리 조항을 분류하지 못했다"
    c = hit[0]
    assert c["article"] == "제50조"
    assert "성장관리방안" in c["article_title"]
    assert c["value"] == 30 and c["kind"] == "bcr"
    assert c["condition_kind"] == "site"


def test_every_conditional_carries_its_article(parsed):
    """모든 조건부 값이 **어느 조문의 것인지** 말한다 — 없으면 근거를 못 따라간다."""
    for c in parsed["conditional_limits"]:
        assert c.get("article"), f"조문 없음: {c}"
        assert c.get("article_title"), f"조제목 없음: {c}"
        assert c.get("condition_key") and c.get("condition_kind") and c.get("direction")


# ── 매칭 ─────────────────────────────────────────────────────────────────────


def test_site_in_growth_management_plan_zone_matches(parsed):
    """★부지가 성장관리계획구역이면 제50조 30%가 **매칭된다**(원래 목표)."""
    m = match_site_conditions(parsed["conditional_limits"], [PLAN_ZONE, "도시지역"])
    assert [(x["value"], x["condition_key"]) for x in m["matched"]] == [
        (30, "growth_management_plan")
    ]
    assert m["applied"] is False, "후보일 뿐 적용값이 아니다"


def test_metro_regime_alone_matches_nothing(parsed):
    """★★수도권 `성장관리권역` 만으로는 **아무것도 매칭되지 않는다**.

    이 한 줄이 이 캠페인 최초의 오진을 막는다 — 그대로 갔으면 경기 성장관리권역 전역에
    근거 없는 건폐율 +10%p 가 붙었다(#703 참조).
    """
    m = match_site_conditions(parsed["conditional_limits"], [METRO_REGIME, "도시지역"])
    assert m["matched"] == []
    # 공허 진리 가드 — 대상 자체는 있어야 "0건"이 의미를 갖는다.
    assert m["unmatched_site"] or m["undecidable"], "조건부 값이 하나도 안 들어왔다"


def test_use_based_conditions_are_undecidable(parsed):
    """건축물 용도·연혁 조건은 **설계 없이는 판정 불가**로 분리한다(단정 금지)."""
    m = match_site_conditions(parsed["conditional_limits"], [PLAN_ZONE])
    keys = {x["condition_key"] for x in m["undecidable"]}
    assert "existing_factory" in keys, "기존 공장 조항이 판정불가로 분리되지 않았다"
    for x in m["undecidable"]:
        assert x.get("why"), "판정 불가 사유가 없다 — 사용자가 다음 행동을 못 정한다"


def test_designated_district_is_not_asserted(parsed):
    """★'그 밖에 용도지구·구역 등'(제46조)은 어느 지구인지 못 가르므로 **충족 단정 금지**."""
    m = match_site_conditions(parsed["conditional_limits"], [PLAN_ZONE, "취락지구"])
    assert all(x["condition_key"] != "designated_district" for x in m["matched"])


# ── 분류기 자체(순수함수) ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "key", "kind", "direction"),
    [
        ("성장관리방안 수립지역에서의 건폐율 완화", "growth_management_plan", "site", "relax"),
        ("방화지구에서의 건폐율의 완화", "fire_district", "site", "relax"),
        ("그 밖에 용도지구·구역 등의 건폐율", "designated_district", "site", "relax"),
        ("생산녹지지역 등에서 기존 공장의 건폐율 완화", "existing_factory", "use", "relax"),
        ("용도지역에서의 건폐율", "unclassified", "unknown", "relax"),
    ],
)
def test_classify_article(title, key, kind, direction):
    assert classify_article(title) == (key, kind, direction)


def test_strengthening_article_is_not_an_upside():
    """★★오산시 `제47조(건폐율의 **강화**)` 가 실재한다 — 조건부가 곧 완화는 아니다.

    강화 조항 값을 상향 여지로 표시하면 **기본값보다 낮은 값**을 여지라 부르는 과대낙관이다.
    """
    key, kind, direction = classify_article("건폐율의 강화")
    assert direction == "strengthen"

    m = match_site_conditions(
        [{"kind": "bcr", "value": 15, "condition_key": key,
          "condition_kind": kind, "direction": direction}],
        [PLAN_ZONE],
    )
    assert m["matched"] == []
    assert any("강화" in x["why"] for x in m["undecidable"])


def test_find_article_picks_the_nearest_preceding_heading():
    """조제목 앵커는 **직전** 조문이어야 한다 — 뒤 조문을 집으면 귀속이 뒤집힌다."""
    section = "제45조(용도지역에서의 건폐율) 자연녹지지역 20퍼센트 제50조(성장관리방안 수립지역에서의 건폐율 완화) 자연녹지지역 30퍼센트"
    pos = section.rindex("자연녹지지역")
    assert find_article(section, pos) == {
        "article": "제50조", "article_title": "성장관리방안 수립지역에서의 건폐율 완화",
    }
    # 대조군 — 첫 값 위치에서는 제45조가 나와야 한다.
    first = section.index("자연녹지지역")
    assert find_article(section, first)["article"] == "제45조"


def test_find_article_returns_none_without_heading():
    assert find_article("자연녹지지역 20퍼센트", 5) is None


@pytest.mark.parametrize("districts", [None, [], "성장관리계획구역"])
def test_absent_or_scalar_districts_match_nothing(parsed, districts):
    """designation 이 없거나 문자열 통짜면 매칭 0(글자 단위 순회 금지)."""
    assert match_site_conditions(parsed["conditional_limits"], districts)["matched"] == []


def test_fixture_really_contains_the_strengthening_article():
    """전제 — 오산시 조례에 `건폐율의 강화` 조문이 실제로 있어야 위 경계가 가상이 아니다."""
    with open("tests/fixtures/ordinance_osan_2097518.xml", encoding="utf-8") as f:
        xml = f.read()
    assert re.search(r"제\d+조\s*\(\s*건폐율의 강화", xml), "강화 조문이 픽스처에 없다"


# ── 소비처 락 — `calc_effective_far` 가 실제로 매칭을 낸다 ─────────────────────────
#   ★순수함수만 맞고 배선이 없으면 화면엔 아무것도 안 간다. 이 캠페인이 내내 고쳐 온
#     결함("정의만 하고 소비처 0")을 여기서 내가 재발시키지 않는다.


def _calc(districts, cond_limits):
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    return calc_effective_far(
        {
            "zone_limits": {},
            "special_districts": districts,
            "local_ordinance": {"conditional_limits": cond_limits},
        },
        "자연녹지지역",
        1000.0,
    )


def test_far_tier_emits_the_match(parsed):
    """소비처가 매칭 결과를 낸다 — 배선이 끊기면 화면이 조건부 값을 영원히 모른다."""
    oc = _calc([PLAN_ZONE], parsed["conditional_limits"])["ordinance_conditional"]
    assert oc is not None, "far_tier_service 가 ordinance_conditional 을 싣지 않는다(배선 끊김)"
    assert [(x["value"], x["condition_key"]) for x in oc["matched"]] == [
        (30, "growth_management_plan")
    ]
    assert oc["applied"] is False


def test_far_tier_key_exists_even_when_absent():
    """★조건부 값이 없어도 **키는 있다**(None) — 소비처가 `in` 으로 분기하지 않게."""
    out = _calc([PLAN_ZONE], [])
    assert "ordinance_conditional" in out
    assert out["ordinance_conditional"] is None


def test_zone_unmatched_early_return_carries_the_key(parsed):
    """형제 미러 — 용도지역 미매칭 조기반환에도 키가 있다."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    out = calc_effective_far(
        {"zone_limits": {}, "special_districts": [PLAN_ZONE],
         "local_ordinance": {"conditional_limits": parsed["conditional_limits"]}},
        "존재하지않는용도지역",
        1000.0,
    )
    assert out.get("far_basis") == "zone_unmatched", "미매칭 경로를 타지 않았다"
    assert "ordinance_conditional" in out and out["ordinance_conditional"] is None


def test_effective_values_are_untouched_by_the_match(parsed):
    """★★무회귀의 핵심 — 매칭돼도 **실효값은 바뀌지 않는다**.

    적용 요건(성장관리계획 본문에 건폐율이 정해져 있을 것)을 확인할 수 없으므로 올리면
    날조다. 이 단언이 깨지면 누군가 '후보'를 실효값으로 승격시킨 것이다.
    """
    matched = _calc([PLAN_ZONE], parsed["conditional_limits"])
    none_ = _calc([METRO_REGIME], parsed["conditional_limits"])

    # 공허 진리 가드 — 한쪽은 실제로 매칭돼 있어야 비교가 의미를 갖는다.
    assert matched["ordinance_conditional"]["matched"]
    assert not none_["ordinance_conditional"]["matched"]

    assert matched["effective_bcr_pct"] == none_["effective_bcr_pct"] == 20
    assert matched["effective_far_pct"] == none_["effective_far_pct"]
