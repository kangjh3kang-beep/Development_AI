"""계획 상한이 **있어야 하는데 수치가 없다**를 말한다 — 침묵이 오독의 원인이었다.

【실측 2026-08-19 — 계층 하나가 통째로 죽어 있다】
`far_tier_service` 는 산정 계층을 이렇게 선언한다:
  1) 법정범위 → 2) 조례 적용값 → **3) 도시·군관리계획/지구단위계획 상한(최우선)** → 4) 인센티브
그런데 3계층은 페이로드에서 `plan_far_pct`·`상한용적률` 같은 키를 찾는데,
**그 키를 넣는 생산자가 코드베이스 전역에 0건**이다(전부 소비처·주석).
주소 키워드 휴리스틱(`auto_zoning_service._detect_special_districts`)이 내는 키는
`bonus_far` 로 `_PLAN_FAR_KEYS` 에 **없다**.
→ "최우선 적용"이라 불리는 계층이 **실데이터로 한 번도 발화한 적이 없다.**
   이 저장소가 반복해 데인 "정의만 하고 소비처 0"의 **거울상** — 소비처만 있고 생산자 0.

【그래서 사용자에게 무슨 일이 일어났나】
필지가 실제로 지구단위계획 결정고시 대상인데, 화면은 조례·법정값(자연녹지 80%)을
**그것이 지배 한도인 양** 보여 줬다. 실제 계획값은 200%·30층이었다.

【무날조 처방 — 수치를 지어내지 않는다】
VWorld 지구단위계획 레이어는 고시코드·조서번호·면적을 줄 뿐 **용적률을 주지 않는다**.
그래서 값을 채우는 대신 **"지배 한도가 따로 있고 우리는 그 수치를 모른다"** 를 낸다.
이 파일이 잠그는 것의 절반은 #704 와 같다 — **무엇을 하지 않는가**.
"""

import pytest

from app.services.land_intelligence.far_tier_service import calc_effective_far

DU = "지구단위계획구역"
METRO_REGIME = "성장관리권역"      # 수도권정비계획법 — 계획이 한도를 정하는 구역이 **아니다**


def _calc(zone: str, districts, **base_extra):
    return calc_effective_far(
        {
            "zone_limits": {},
            "special_districts": districts,
            "local_ordinance": {},
            **base_extra,
        },
        zone,
        1000.0,
    )


def test_district_unit_plan_parcel_says_the_number_is_not_the_governing_limit():
    """★지구단위계획구역이면 **아래 수치가 지배 한도가 아님**을 명시한다."""
    out = _calc("자연녹지지역", [DU, "도시지역"])
    plu = out["plan_limit_unknown"]

    assert plu is not None, "계획 상한 미확보 신호가 없다 — 침묵이 곧 오독의 원인이었다"
    assert plu["districts"] == [DU]
    assert plu["applied"] is False
    assert "우선" in plu["note"]
    assert "단정하지 마십시오" in plu["note"]
    assert any("고시" in r for r in plu["requires"])


def test_the_notice_is_the_first_annotation():
    """★고지가 **가장 앞**에 온다 — 뒤 문장들을 읽기 전에 전제를 알아야 오독하지 않는다."""
    out = _calc("자연녹지지역", [DU])
    annotations = out["annotations"]
    assert annotations, "annotations 가 비었다 — 검증 대상이 없다(공허한 통과)"
    assert annotations[0] == out["plan_limit_unknown"]["note"]


def test_no_signal_when_no_such_district():
    """대조군(음성) — 해당 구역이 없으면 신호가 **꺼진다**(가드 위양성 방지)."""
    out = _calc("자연녹지지역", ["도시지역", "가축사육제한구역"])
    assert out["plan_limit_unknown"] is None
    # 공허 진리 가드 — 산출 자체는 살아 있어야 한다.
    assert out["effective_far_pct"] is not None


def test_metro_regime_does_not_trigger_it():
    """★★수도권 `성장관리권역` 은 계획이 한도를 정하는 구역이 **아니다**.

    #703 의 판별자를 재사용하므로 이름이 비슷해도 걸리지 않는다. 여기서 걸리면
    경기 성장관리권역 전역에 "지배 한도가 따로 있다"는 틀린 고지가 붙는다.
    """
    assert _calc("자연녹지지역", [METRO_REGIME])["plan_limit_unknown"] is None
    # ★양성 짝 — 같은 실행에서 **발화할 수 있다**는 것을 증명한다(없으면 항상 None 이어도 통과).
    assert _calc("자연녹지지역", [DU])["plan_limit_unknown"] is not None


def test_growth_management_plan_zone_does_trigger_it():
    """대조군(양성) — 성장관리계획구역은 계획이 건폐율·용적률을 정한다(법 제75조의3제1항제2호)."""
    out = _calc("계획관리지역", ["성장관리계획구역"])
    assert out["plan_limit_unknown"] is not None
    assert out["plan_limit_unknown"]["districts"] == ["성장관리계획구역"]


@pytest.mark.parametrize("key", ["district_name", "name"])
def test_dict_designations_are_labelled_by_each_key(key):
    """★두 키를 **각각** 확인한다 — 섞어 쓰면 한쪽이 죽어도 다른 쪽이 통과시킨다(변이 생존)."""
    out = _calc("자연녹지지역", [{key: DU}])
    assert out["plan_limit_unknown"]["districts"] == [DU]


def test_duplicate_designations_are_listed_once():
    """같은 이름이 여러 번 와도 한 번만 나열한다(VWorld 가 중복 반환한다)."""
    out = _calc("자연녹지지역", [{"district_name": DU}, {"name": DU}, DU])
    assert out["plan_limit_unknown"]["districts"] == [DU]


def test_reason_states_what_is_missing():
    """★`reason` 도 화면에 나가는 문장이다 — 무엇이 없는지 말해야 다음 행동이 나온다."""
    plu = _calc("자연녹지지역", [DU])["plan_limit_unknown"]
    assert "직접 정하는 구역" in plu["reason"]
    assert "내용을 확보하지 못했습니다" in plu["reason"]
    # note 도 '왜 아래 수치를 믿으면 안 되는지'를 담는다.
    assert "반영하지 못한" in plu["note"]


def test_the_plan_governs_uses_not_only_numbers():
    """★★계획은 **수치만이 아니라 허용용도까지** 정한다 — 그것을 말해야 한다.

    근거(법제처 원문): 국토계획법 **제52조제1항제4호** 지구단위계획은 "건축물의 **용도제한**,
    건폐율 또는 용적률, 높이의 최고한도 또는 최저한도"를 정한다.
    제75조의3제1항제2호 성장관리계획도 "건축물의 용도제한, 건폐율 또는 용적률".

    ★왜 중요한가: 수치에만 경고를 붙이면 정작 더 비싼 오답 — **불허 용도를 추천**하는 것 —
      이 아무 표시 없이 나간다(사용자 신고: 고시상 단독주택 불허인데 357세대 추천).
    """
    plu = _calc("자연녹지지역", [DU])["plan_limit_unknown"]
    assert "건축물 용도제한" in plu["governs"]
    assert "건폐율" in plu["governs"] and "용적률" in plu["governs"]
    assert "허용용도" in plu["note"]
    assert "허용용도로도 단정하지 마십시오" in plu["note"]
    # 무엇을 확인해야 하는지에 **용도**가 들어 있어야 다음 행동이 나온다.
    assert any("허용용도" in r for r in plu["requires"])
    # ★두 항목을 **각각** 잠근다 — `any()` 하나로 묶으면 한쪽이 죽어도 통과한다(변이 생존).
    assert any("상한용적률·건폐율 확인" in r for r in plu["requires"])
    assert len(plu["requires"]) == 2


def test_signal_disappears_when_the_plan_number_is_actually_known():
    """★수치가 **있으면** 미확보 신호는 꺼지고 3계층이 실제로 발화한다.

    이 단언이 "생산자 0" 상태를 고정하지 않는다 — 나중에 진짜 생산자가 생기면
    (고시 조서 입력 등) 그 경로가 살아 있는지 여기서 확인된다.
    """
    out = _calc("자연녹지지역", [{"district_name": DU, "plan_far_pct": 200}])
    assert out["plan_limit_unknown"] is None
    assert out["effective_far_pct"] == 200
    assert "최우선 적용" in out["far_basis"]


def test_effective_values_are_untouched_by_the_notice():
    """★★무회귀 — 고지를 붙여도 **수치는 바뀌지 않는다**(값을 지어내지 않았다는 증명)."""
    noticed = _calc("자연녹지지역", [DU])
    silent = _calc("자연녹지지역", ["도시지역"])

    # 공허 진리 가드 — 한쪽은 실제로 고지가 붙어 있어야 비교가 의미를 갖는다.
    assert noticed["plan_limit_unknown"] is not None
    assert silent["plan_limit_unknown"] is None

    assert noticed["effective_far_pct"] == silent["effective_far_pct"]
    assert noticed["effective_bcr_pct"] == silent["effective_bcr_pct"]


def test_zone_unmatched_early_return_carries_the_key():
    """형제 미러 — 용도지역 미매칭 조기반환에도 키가 있다(소비처 KeyError 방지)."""
    out = _calc("존재하지않는용도지역", [DU])
    assert out.get("far_basis") == "zone_unmatched", "미매칭 경로를 타지 않았다"
    assert "plan_limit_unknown" in out
    assert out["plan_limit_unknown"] is None


@pytest.mark.parametrize("districts", [None, [], "지구단위계획구역"])
def test_absent_or_scalar_districts_are_safe(districts):
    """designation 이 없거나 문자열 통짜면 신호를 내지 않는다(글자 단위 순회 금지)."""
    assert _calc("자연녹지지역", districts)["plan_limit_unknown"] is None
    # ★양성 짝 — 같은 zone 에 리스트로 주면 발화한다(닫힌 이유가 designation 형태임을 증명).
    assert _calc("자연녹지지역", [DU])["plan_limit_unknown"] is not None
