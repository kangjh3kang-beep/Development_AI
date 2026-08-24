"""조건부 법정 상한(법 제75조의3) — **열되 적용하지 않는다** 배선 락.

【무엇을 푸는가】
`far_tier_service` 는 실효 한도를 `min(법정상한, 조례값)` 으로 낸다. 조례가 정한 완화값
(자연녹지 건폐율 30%)을 정확히 파싱해도 법정상한 20% 에 되깎여 **화면에 도달하지 못한다**.
국토계획법 제75조의3제2항은 그 상한 자체를 성장관리계획구역에서 열어 둔다.

【★그런데 자동 적용하면 안 된다】
완화 성립 요건은 셋인데(①구역 지정 ②성장관리계획 본문이 건폐율을 정할 것 ③조례 비율)
**②의 원천이 우리에게 없다**. 그래서 이 계층은 **가능 상한만** 내고 실효값은 그대로 둔다.
이 파일이 잠그는 것의 절반은 "무엇을 하지 **않는가**"다.

【그라운드 트루스 — 법제처 DRF 원문(2026-08-19)】
· 제75조의3제2항 1호 계획관리지역 50% / 2호 생산관리·농림 및 대통령령 녹지지역 30%
· 시행령: "대통령령으로 정하는 녹지지역" = 자연녹지지역·생산녹지지역
· 제75조의3제3항: 구역 내 **계획관리지역**만 용적률 125%
【designation 그라운드 트루스 — VWorld NED 실조회】
· 화성시 정남면 문학리 1(생산관리지역) → 성장관리권역×3 + **성장관리계획구역**
· 아산시 음봉면 산동리 1(계획관리지역) → **성장관리계획구역**
"""

import pytest

from app.services.zoning.conditional_legal_ceiling import (
    GROWTH_MGMT_BCR_CEILING,
    GROWTH_MGMT_FAR_CEILING,
    resolve_conditional_ceiling,
)

PLAN_ZONE = "성장관리계획구역"        # 국토계획법 — 완화 근거
METRO_REGIME = "성장관리권역"         # 수도권정비계획법 — 완화 근거 **아님**

# 라이브 실측 designation(화성시) — 두 제도가 한 필지에 공존한다.
HWASEONG_REAL = ["성장관리권역", "성장관리권역", "성장관리계획구역", "성장관리권역"]


def test_premise_the_two_names_are_both_present_in_real_data():
    """전제 — 실측 목록에 두 이름이 **모두** 있어야 아래 분리 단언이 공허하지 않다."""
    assert PLAN_ZONE in HWASEONG_REAL
    assert METRO_REGIME in HWASEONG_REAL


@pytest.mark.parametrize(
    ("zone", "bcr", "far"),
    [
        ("계획관리지역", 50, 125),   # 제2항1호 + 제3항
        ("생산관리지역", 30, None),  # 제2항2호
        ("농림지역", 30, None),      # 제2항2호
        ("자연녹지지역", 30, None),  # 제2항2호(시행령)
        ("생산녹지지역", 30, None),  # 제2항2호(시행령)
    ],
)
def test_ceilings_match_the_statute(zone, bcr, far):
    """★법정 수치를 조문과 결속한다 — 대역만 보면 상수가 장식이 된다(회귀망 규율 A.5)."""
    got = resolve_conditional_ceiling(zone, [PLAN_ZONE])
    assert got is not None
    assert got["bcr_ceiling_pct"] == bcr
    assert got["far_ceiling_pct"] == far
    # 상수 테이블과도 결속(코드 안에서 두 곳이 갈리면 즉시 실패).
    # ★2026-08-24 — 표가 `LegalLimit` 로 바뀌었다. **공개 출력은 숫자 그대로**이고,
    #   표 쪽은 `.value` 로 본다(값 무변경을 이 두 줄이 함께 증명한다).
    _b = GROWTH_MGMT_BCR_CEILING.get(zone)
    _f = GROWTH_MGMT_FAR_CEILING.get(zone)
    assert (_b.value if _b is not None else None) == bcr
    assert (_f.value if _f is not None else None) == far
    # ★근거가 값과 함께 다니는지 — 감싸기가 형식만이 아님을 본다.
    if _b is not None:
        assert "제75조의3제2항" in _b.law, f"건폐율 상한의 조문이 사라졌다: {_b.law}"
    if _f is not None:
        assert "제75조의3제3항" in _f.law, f"용적률 상한의 조문이 사라졌다: {_f.law}"


def test_far_relaxation_is_planning_management_only():
    """★용적률 완화는 **계획관리지역 한정**이다(제3항) — 녹지에 붙이면 과대허용."""
    assert resolve_conditional_ceiling("자연녹지지역", [PLAN_ZONE])["far_ceiling_pct"] is None
    assert resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE])["far_ceiling_pct"] == 125


def test_metro_regime_alone_opens_nothing():
    """★★수도권 `성장관리권역` 만으로는 **아무것도 열리지 않는다**.

    이 한 줄이 이 캠페인의 원래 오진을 막는다 — 그대로 갔으면 경기 성장관리권역 전역에
    근거 없는 건폐율 +10%p 가 붙었다.
    """
    assert resolve_conditional_ceiling("자연녹지지역", [METRO_REGIME]) is None
    assert resolve_conditional_ceiling("계획관리지역", [METRO_REGIME, "도시지역"]) is None
    # ★양성 짝 — 같은 실행에서 이 함수가 **열 수 있다**는 것을 증명한다. 없으면 함수가
    #   항상 None 을 내도 이 테스트가 통과한다(부재 단언은 그 자체로 잠금이 아니다).
    assert resolve_conditional_ceiling("자연녹지지역", [PLAN_ZONE]) is not None


def test_real_parcel_with_both_regimes_opens_via_the_plan_zone_only():
    """실측 화성시 필지 — 두 이름이 섞여 있어도 **계획구역 때문에만** 열린다."""
    got = resolve_conditional_ceiling("생산관리지역", HWASEONG_REAL)
    assert got is not None and got["bcr_ceiling_pct"] == 30
    assert got["condition"] == PLAN_ZONE

    # 대조군: 같은 목록에서 계획구역만 빼면 **닫힌다**(열린 이유가 계획구역임을 증명).
    without = [d for d in HWASEONG_REAL if d != PLAN_ZONE]
    assert without, "대조군이 비면 이 단언이 공허하다"
    assert resolve_conditional_ceiling("생산관리지역", without) is None


@pytest.mark.parametrize("zone", ["제2종일반주거지역", "일반상업지역", "보전녹지지역", "보전관리지역"])
def test_ineligible_zones_stay_closed_even_inside_the_plan_zone(zone):
    """구역 안이어도 **완화 대상 용도지역이 아니면** 열리지 않는다(제2항 각 호 한정).

    ★보전녹지·보전관리는 시행령이 지목한 녹지지역이 **아니다** — 넣으면 과대허용이다.
    """
    assert resolve_conditional_ceiling(zone, [PLAN_ZONE]) is None
    # ★양성 짝 — 같은 구역·같은 호출로 **열리는 용도지역**이 있어야 "이 zone 이라서 닫혔다"가 참이다.
    assert resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE]) is not None


@pytest.mark.parametrize("districts", [None, [], ["도시지역"], "성장관리계획구역"])
def test_no_districts_no_ceiling(districts):
    """designation 이 없거나 문자열 통짜면 열지 않는다(str 을 순회해 글자 단위로 읽지 않는다)."""
    assert resolve_conditional_ceiling("계획관리지역", districts) is None
    # ★양성 짝 — 같은 zone 에 **리스트로** 주면 열린다(닫힌 이유가 designation 형태임을 증명).
    assert resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE]) is not None


def test_dict_designations_are_accepted():
    """VWorld designation 은 dict 로도 흐른다 — 판별자 공용 정규화를 그대로 탄다."""
    got = resolve_conditional_ceiling("계획관리지역", [{"district_name": PLAN_ZONE}])
    assert got is not None and got["bcr_ceiling_pct"] == 50


def test_result_declares_itself_not_applied():
    """★계약 — 이 값은 **가능 상한**이지 적용값이 아니다. 소비처가 오독하면 날조가 된다."""
    got = resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE])
    assert got["applied"] is False
    # 우리가 확인할 수 없는 요건을 **명시**한다(모르는 것을 모른다고 적는다).
    assert any("성장관리계획 본문" in r for r in got["requires"])
    assert any("조례" in r for r in got["requires"])
    assert any("제75조의3" in b for b in got["legal_basis"])


def test_missing_zone_type_is_closed():
    assert resolve_conditional_ceiling(None, [PLAN_ZONE]) is None
    assert resolve_conditional_ceiling("  ", [PLAN_ZONE]) is None
    # ★양성 짝 — 같은 designation 으로 유효 zone 은 열린다(닫힌 이유가 zone 부재임을 증명).
    assert resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE]) is not None


# ── 소비처 락 — `calc_effective_far` 가 실제로 이 값을 내고, **실효값은 그대로**인가 ────
#   ★순수함수만 테스트하면 "정의만 하고 소비처 0"이 된다(이 저장소의 반복 결함).


def _calc(zone: str, districts):
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    return calc_effective_far(
        {"zone_limits": {}, "special_districts": districts, "local_ordinance": {}},
        zone,
        1000.0,
    )


def test_far_tier_emits_the_conditional_ceiling():
    """소비처가 값을 낸다 — 순수함수만 맞고 배선이 없으면 화면엔 아무것도 안 간다."""
    out = _calc("자연녹지지역", [PLAN_ZONE])
    cc = out.get("conditional_ceiling")
    assert cc is not None, "far_tier_service 가 conditional_ceiling 을 싣지 않는다(배선 끊김)"
    assert cc["bcr_ceiling_pct"] == 30
    assert cc["applied"] is False


def test_far_tier_key_exists_even_when_closed():
    """★해당 없을 때도 **키는 있다**(None) — 소비처가 `in` 으로 분기하지 않게."""
    out = _calc("자연녹지지역", [METRO_REGIME])
    assert "conditional_ceiling" in out
    assert out["conditional_ceiling"] is None


def test_effective_values_are_untouched_by_the_ceiling():
    """★★무회귀의 핵심 — 상한을 열어도 **실효값은 바뀌지 않는다**.

    적용 요건(성장관리계획 본문)을 확인할 수 없으므로 올리면 날조다. 이 단언이 깨지면
    누군가 '가능 상한'을 실효값으로 승격시킨 것이다.
    """
    opened = _calc("자연녹지지역", [PLAN_ZONE])
    closed = _calc("자연녹지지역", [METRO_REGIME])

    # 공허 진리 가드 — 한쪽은 실제로 열려 있어야 비교가 의미를 갖는다.
    assert opened["conditional_ceiling"] is not None
    assert closed["conditional_ceiling"] is None

    assert opened["effective_bcr_pct"] == closed["effective_bcr_pct"]
    assert opened["effective_far_pct"] == closed["effective_far_pct"]
    # 그리고 그 값은 여전히 **법정 자연녹지 상한**(20%)이다 — 30 으로 새지 않았다.
    assert opened["effective_bcr_pct"] == 20


# ── 변이감사(49 변이) 생존 13건 트리아지 — 진짜 구멍 4종을 닫는다 ────────────────────


def test_legal_basis_names_the_right_paragraph_per_kind():
    """★조문 인용을 **종류별로** 결속한다.

    종전 단언은 `any("제75조의3" in b)` 라, 두 문자열 중 하나가 망가져도 나머지가 통과시켰다
    (변이 생존으로 적발). 사용자는 이 문자열을 근거로 조문을 찾아간다 — 틀리면 못 찾는다.
    """
    both = resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE])["legal_basis"]
    assert any("제75조의3제2항" in b and "건폐율" in b for b in both)
    assert any("제75조의3제3항" in b and "용적률" in b for b in both)

    # 녹지는 용적률 완화가 없으므로 **제3항이 실려서는 안 된다**(음성 단언).
    green = resolve_conditional_ceiling("자연녹지지역", [PLAN_ZONE])["legal_basis"]
    assert any("제75조의3제2항" in b for b in green)
    assert not any("제75조의3제3항" in b for b in green)


def test_result_carries_the_zone_it_was_resolved_for():
    """어떤 용도지역 기준으로 열렸는지 산출물이 말한다 — 다필지에서 섞이면 추적 불가."""
    assert resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE])["zone_type"] == "계획관리지역"
    assert resolve_conditional_ceiling("자연녹지지역", [PLAN_ZONE])["zone_type"] == "자연녹지지역"


def test_note_states_the_number_and_refuses_to_claim_application():
    """★설명문이 **수치를 담되 적용을 주장하지 않는다**.

    이 문장은 화면에 그대로 나간다. "30%까지 열릴 수 있다"가 "30%다"로 바뀌면 그 순간
    근거 없는 단정이 된다 — 문구도 검증 대상이다(CLAUDE.md 규율 C.10).
    """
    note = resolve_conditional_ceiling("자연녹지지역", [PLAN_ZONE])["note"]
    assert "건폐율 상한이 30%" in note and "자연녹지지역" in note
    # ★"무엇을 더 확인해야 하는가"를 통째로 잠근다 — 종전엔 `"성장관리계획" in note` 였는데
    #   앞 문장의 '성장관리계획구역'이 그 부분문자열을 이미 갖고 있어 **공허했다**(변이 생존).
    assert "성장관리계획 본문과 조례가 정하므로" in note
    assert "적용값으로 쓰지 않습니다" in note
    # 이 완화가 **무엇을 제치는지**도 문구가 말한다 — 사용자가 근거를 찾아갈 수 있어야 한다.
    assert "제77조제1항" in note and "제78조제1항" in note
    # 녹지는 용적률이 안 열리므로 그 문구가 **없어야** 한다(음성 단언).
    assert "용적률 상한" not in note

    # 계획관리는 둘 다 열리므로 두 수치가 모두 실린다(조립식이 죽은 분기 없이 처리).
    both = resolve_conditional_ceiling("계획관리지역", [PLAN_ZONE])["note"]
    assert "건폐율 상한이 50%" in both and "용적률 상한이 125%" in both


def test_zone_unmatched_early_return_still_carries_the_key():
    """★형제 미러 — 용도지역 매칭 실패 조기반환에도 키가 있어야 한다.

    이 경로는 별도 return 문이라, 본 경로에만 키를 넣으면 소비처가 여기서 KeyError 를 만난다.
    """
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    out = calc_effective_far(
        {"zone_limits": {}, "special_districts": [PLAN_ZONE], "local_ordinance": {}},
        "존재하지않는용도지역",
        1000.0,
    )
    # 공허 진리 가드 — 실제로 미매칭 경로를 탔는가.
    assert out.get("far_basis") == "zone_unmatched", "미매칭 경로를 타지 않았다"
    assert "conditional_ceiling" in out
    assert out["conditional_ceiling"] is None
