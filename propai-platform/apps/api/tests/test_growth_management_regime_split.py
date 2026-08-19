"""성장관리**권역**(수도권정비계획법) ≠ 성장관리**계획구역**(국토계획법) 배선 락.

【이 테스트가 지키는 것】
`"성장관리" in name` 부분일치가 두 제도를 뭉개면, 수도권 성장관리권역(경기 오산·화성·평택 등
광역)에 국토계획법 지구단위계획 조문이 붙고 *"세부 도시관리계획"* 이라는 틀린 설명이 나간다.
더 위험한 것은 다음 단계였다 — 그 오인 위에서 조례 제50조(성장관리방안 30%)를 적용하면
**근거 없는 건폐율 +10%p** 가 권역 전역에 붙는다.

【픽스처 규율 — 두 모집단을 가른다】
`OSAN_REAL_DISTRICTS`(성장관리권역 실측)과 `GROWTH_PLAN_ZONE`(성장관리계획구역)은 **다른 판정**을
내야 한다. 두 집합이 같은 값을 내는 픽스처는 배선을 끊어도 초록이라 잠금이 아니다.

【그라운드 트루스】
· designation 목록은 2026-08-19 VWorld NED `getLandUseAttr` 라이브 실조회 결과
  (PNU 4137011000200660001 · 경기도 오산시 내삼미동) — 합성이 아니다.
· 법령 사실은 법제처 DRF 원문 확인:
  수도권정비계획법 제6조제1항제2호(성장관리권역)·제8조(행위 제한) /
  국토계획법 제75조의2(성장관리계획구역의 지정)·제75조의3제2항(건폐율 완화).
"""

import pytest

from app.services.legal.legal_reference_registry import legal_refs_for_districts
from app.services.zoning.district_regime import (
    is_detailed_urban_plan,
    is_growth_management_plan,
    is_metro_regime,
)

# ── 라이브 실측 designation(오산시 내삼미동) — `성장관리권역`이 실제로 실려 온다.
OSAN_REAL_DISTRICTS: tuple[str, ...] = (
    "비행안전제2구역(전술)",
    "공익용산지",
    "성장관리권역",
    "도로구역",
    "토지거래계약에관한허가구역",
    "대로1류(폭 35m~40m)",
    "도시지역",
    "가축사육제한구역",
    "보전녹지지역",
    "자연녹지지역",
)

METRO_REGIME = "성장관리권역"           # 수도권정비계획법 — 완화 근거 아님
GROWTH_PLAN_ZONE = "성장관리계획구역"   # 국토계획법 — 완화 근거


def test_fixture_premise_metro_regime_is_actually_present():
    """전제 단언 — 픽스처에 `성장관리권역`이 실제로 있어야 이 파일의 검증이 공허하지 않다."""
    assert METRO_REGIME in OSAN_REAL_DISTRICTS
    # 그리고 두 이름은 부분일치로 서로를 집지 **못한다**(판별 가능성의 전제).
    assert METRO_REGIME not in GROWTH_PLAN_ZONE
    assert GROWTH_PLAN_ZONE not in METRO_REGIME
    # ★두 이름이 공통 접두 "성장관리"를 공유한다는 사실도 못박는다 — 이 공유가 바로
    #   부분일치 판정이 뚫리는 이유다(이게 거짓이면 이 테스트의 동기 자체가 사라진다).
    assert METRO_REGIME.startswith("성장관리") and GROWTH_PLAN_ZONE.startswith("성장관리")


def test_two_populations_split_on_every_discriminator():
    """★두 모집단이 **모든** 판별자에서 반대 값을 낸다(같은 값이면 잠금이 아니다)."""
    assert is_metro_regime(METRO_REGIME) is True
    assert is_metro_regime(GROWTH_PLAN_ZONE) is False

    assert is_growth_management_plan(METRO_REGIME) is False
    assert is_growth_management_plan(GROWTH_PLAN_ZONE) is True

    assert is_detailed_urban_plan(METRO_REGIME) is False
    assert is_detailed_urban_plan(GROWTH_PLAN_ZONE) is True


@pytest.mark.parametrize("name", ["과밀억제권역", "자연보전권역", "성장관리 권역"])
def test_all_metro_regimes_excluded_including_spaced_variant(name):
    """3권역 전부 제외 + 띄어쓰기 변형(`성장관리 권역`)도 흡수한다."""
    assert is_metro_regime(name) is True
    assert is_detailed_urban_plan(name) is False


@pytest.mark.parametrize("name", ["지구단위계획구역", "재정비촉진지구", "정비구역", "도시개발구역"])
def test_genuine_detailed_plans_still_pass(name):
    """위양성 방지의 반대편 — 진짜 세부 도시관리계획은 계속 True 여야 한다.

    (가드가 정상 케이스를 막으면 다음 사람이 가드를 지운다 — 회귀망 규율 A.6.)
    """
    assert is_detailed_urban_plan(name) is True


def test_hierarchy_does_not_file_metro_regime_under_district_unit_plan():
    """실제 소비처 락 — 규제계층에서 `성장관리권역`이 '지구단위계획' 계층에 들어가면 안 된다.

    ★소스 grep 이 아니라 **함수를 실행**해 산출물을 본다(주석처리 변이에 뚫리지 않게).
    """
    from app.services.regulation.regulation_analysis_service import (
        RegulationAnalysisService,
        _impact,
    )

    # ★행 모양을 손으로 베끼지 않고 **생산 경로와 같은 파생**으로 만든다(_impact 재사용) —
    #   베낀 픽스처는 생산 계약이 바뀌면 조용히 어긋난다(규율 A.4).
    def _row(n: str) -> dict:
        return {"name": n, "code": "", "impact": _impact(n), "status": ""}

    districts = [_row(n) for n in OSAN_REAL_DISTRICTS]
    hierarchy = RegulationAnalysisService()._hierarchy(
        "자연녹지지역", "", districts, "오산시", {}
    )
    plan_level = next(
        lv for lv in hierarchy if lv["level"] == "도시·군계획 / 지구단위계획"
    )
    names = [it["name"] for it in plan_level["items"]]
    # 공허 진리 가드 — 계층 자체는 살아 있어야 한다(항목 0이면 아래 단언이 무의미).
    assert names, "지구단위계획 계층이 비었다 — 검증 대상이 없다(공허한 통과)"
    assert METRO_REGIME not in names

    # 대조군(양성): 성장관리계획구역이 섞이면 **들어가야** 한다 — 배선이 살아 있다는 증거.
    districts_pos = [*districts, _row(GROWTH_PLAN_ZONE)]
    hierarchy_pos = RegulationAnalysisService()._hierarchy(
        "자연녹지지역", "", districts_pos, "오산시", {}
    )
    names_pos = [
        it["name"]
        for lv in hierarchy_pos
        if lv["level"] == "도시·군계획 / 지구단위계획"
        for it in lv["items"]
    ]
    assert GROWTH_PLAN_ZONE in names_pos


def test_metro_growth_regime_gets_its_own_law_not_district_unit_plan():
    """규제법령집: `성장관리권역` → 수도권정비계획법 제8조. 국토계획법 제52조가 아니다."""
    res = legal_refs_for_districts([METRO_REGIME])
    keys = res["by_district"].get(METRO_REGIME) or []
    assert keys == ["metro_growth_management"], keys
    assert METRO_REGIME not in res["unmatched"]

    ref = next(r for r in res["refs"] if r.get("key") == "metro_growth_management")
    assert ref["law_name"] == "수도권정비계획법"
    assert ref["article"] == "제8조"


def test_growth_management_plan_zone_maps_to_kookto_75_2():
    """대조군(다른 모집단): 성장관리**계획구역** → 국토계획법 제75조의2."""
    res = legal_refs_for_districts([GROWTH_PLAN_ZONE])
    keys = res["by_district"].get(GROWTH_PLAN_ZONE) or []
    assert keys == ["growth_management_zone"], keys

    ref = next(r for r in res["refs"] if r.get("key") == "growth_management_zone")
    assert ref["law_name"] == "국토의 계획 및 이용에 관한 법률"
    assert ref["article"] == "제75조의2"


def test_two_regimes_never_share_a_law_key():
    """★두 제도가 같은 법령키를 물면 화면에서 다시 뭉개진다 — 교집합 0을 못박는다."""
    a = set(legal_refs_for_districts([METRO_REGIME])["by_district"].get(METRO_REGIME) or [])
    b = set(
        legal_refs_for_districts([GROWTH_PLAN_ZONE])["by_district"].get(GROWTH_PLAN_ZONE) or []
    )
    assert a and b, "한쪽이 비면 교집합 0이 공허하게 참이 된다"
    assert not (a & b)


# ── 변이감사(2026-08-19)가 드러낸 무잠금 3건을 닫는다 ──────────────────────────
#   생존 변이: 자연보전권역 법령행 · 성장관리 별칭 문자열 · `_norm` 의 dict 분기.
#   "생존이 곧 결함은 아니다"지만 이 셋은 **설명할 수 없는 생존**이었다(진짜 구멍).


@pytest.mark.parametrize(
    ("name", "expect_key", "expect_article"),
    [
        ("과밀억제권역", "metro_overconcentration", "제7조"),
        ("성장관리권역", "metro_growth_management", "제8조"),
        ("자연보전권역", "metro_nature_conservation", "제9조"),
    ],
)
def test_each_metro_regime_maps_to_its_own_article(name, expect_key, expect_article):
    """수도권 3권역이 **각자 다른 조문**을 문다 — 한 조문으로 뭉개지면 근거가 틀린다."""
    res = legal_refs_for_districts([name])
    assert res["by_district"].get(name) == [expect_key]
    ref = next(r for r in res["refs"] if r.get("key") == expect_key)
    assert ref["law_name"] == "수도권정비계획법"
    assert ref["article"] == expect_article


@pytest.mark.parametrize("alias", ["성장관리계획구역", "성장관리계획", "성장관리방안"])
def test_growth_management_aliases_all_map(alias):
    """구 명칭 `성장관리방안`(2021 개정 전)도 국계법 제75조의2로 붙어야 한다.

    조례 본문은 아직 구 명칭을 쓴다(오산시 제50조 실측) — 별칭이 끊기면 그 조문을 못 찾는다.
    """
    assert is_growth_management_plan(alias) is True
    assert legal_refs_for_districts([alias])["by_district"].get(alias) == [
        "growth_management_zone"
    ]


@pytest.mark.parametrize("key", ["district_name", "name"])
def test_norm_extracts_the_name_from_dict_designations(key):
    """VWorld designation 은 dict 로도 흐른다 — 이름을 **꺼내는지**를 직접 본다.

    ★이 테스트의 앞 판(2026-08-19)은 **공허했다**: `_norm` 의 dict 분기를 꺼도
      `str(dict)` = `"{'district_name': '성장관리권역'}"` 안에 이름이 그대로 남아
      부분일치 판정이 전부 통과했다(변이 생존으로 적발). 그래서 하류 불리언이 아니라
      **정규화 산출물 자체**를 단언한다 — 이것이 그 분기를 실제로 잠근다.
    """
    from app.services.zoning.district_regime import _norm

    assert _norm({key: "성장관리권역"}) == "성장관리권역"
    assert _norm({key: "지구단위 계획구역"}) == "지구단위계획구역"   # 공백 정규화도 함께
    # 하류 판정도 유지(계약 회귀 방지).
    assert is_metro_regime({key: "성장관리권역"}) is True
    assert is_detailed_urban_plan({key: "성장관리권역"}) is False
    assert is_detailed_urban_plan({key: "지구단위계획구역"}) is True


# ── ★양성 대조군 확보(2026-08-19 라이브 실측) ─────────────────────────────────────
#   앞선 커밋 시점에는 국토계획법 성장관리계획구역의 **VWorld 실제 표기를 한 번도 못 봤다**.
#   판별자의 그 방향은 "우리가 쓰는 표기 가정" 위에 있었고, 그 사실을 PR 에 정직하게 적었다.
#   이후 VWorld NED `getLandUseAttr` 로 실제 지정 필지를 찾아 **가정을 사실로 바꿨다**.
#
#   · 경기 화성시 정남면 문학리 1 (생산관리지역)
#       → ['성장관리권역', '성장관리권역', '성장관리계획구역', '성장관리권역']
#       ★★**한 필지가 두 제도를 동시에** 갖는다 — 수도권이면서 성장관리계획구역이다.
#         부분일치 판정이었다면 이 필지에서 두 제도가 완전히 뒤섞인다.
#   · 충남 아산시 음봉면 산동리 1 (계획관리지역) → ['성장관리계획구역']
#       충남은 수도권 밖이라 권역이 없다 — 계획구역만 단독으로 나타나는 대조.

HWASEONG_REAL_DISTRICTS: tuple[str, ...] = (
    "성장관리권역",
    "성장관리권역",
    "성장관리계획구역",
    "성장관리권역",
)
ASAN_REAL_DISTRICTS: tuple[str, ...] = ("성장관리계획구역",)


def test_vworld_actually_spells_it_seongjang_gwanri_gyehoek_guyeok():
    """★가정이 아니라 실측 — VWorld 가 국계법 구역을 `성장관리계획구역` 으로 표기한다."""
    assert GROWTH_PLAN_ZONE in HWASEONG_REAL_DISTRICTS
    assert GROWTH_PLAN_ZONE in ASAN_REAL_DISTRICTS


def test_one_parcel_carrying_both_regimes_is_split_correctly():
    """★★같은 필지의 두 designation 이 **서로 다른 제도**로 갈린다(실측 화성시).

    부분일치였다면 이 필지에서 수도권 권역이 지구단위계획으로 분류되고, 동시에 존재하는
    진짜 완화근거와 뒤섞여 **어느 쪽이 건폐율을 정하는지 알 수 없게** 된다.
    """
    metro = [d for d in HWASEONG_REAL_DISTRICTS if is_metro_regime(d)]
    plan = [d for d in HWASEONG_REAL_DISTRICTS if is_growth_management_plan(d)]

    # 공허 진리 가드 — 양쪽이 실제로 존재해야 '갈렸다'가 의미를 갖는다.
    assert metro and plan, "한쪽이 비면 분리 검증이 공허하다"
    assert set(metro) == {METRO_REGIME}
    assert set(plan) == {GROWTH_PLAN_ZONE}
    assert not (set(metro) & set(plan))          # 교집합 0

    # 세부 도시관리계획으로 올라가는 것은 **계획구역뿐**이다.
    assert [d for d in HWASEONG_REAL_DISTRICTS if is_detailed_urban_plan(d)] == [GROWTH_PLAN_ZONE]


def test_each_real_designation_gets_its_own_law():
    """실측 designation 이 각자 옳은 근거법을 문다 — 화성(둘 다)·아산(계획구역만)."""
    res = legal_refs_for_districts(list(HWASEONG_REAL_DISTRICTS))
    assert res["by_district"][METRO_REGIME] == ["metro_growth_management"]
    assert res["by_district"][GROWTH_PLAN_ZONE] == ["growth_management_zone"]

    asan = legal_refs_for_districts(list(ASAN_REAL_DISTRICTS))
    assert asan["by_district"][GROWTH_PLAN_ZONE] == ["growth_management_zone"]
    # 수도권 밖 필지에 수도권정비계획법이 붙으면 안 된다.
    assert "metro_growth_management" not in {r.get("key") for r in asan["refs"]}
