"""입지점수 — **커버리지가 낮으면 등급을 발행하지 않는다**.

★화면 감사 실측(계획서 `PLAN_analysis_premise_audit_layer_2026-08-24.md` D6):
  `covered=1 / total_features=6` 인데 `grade="D"` 가 **단정**돼 나갔다.
  6개 지표 중 1개만 확보했으면 그건 "입지가 나쁘다"가 아니라 **"아직 모른다"** 다.
  그런데 D 는 사용자에게 **최하 등급**으로 읽힌다 — 모름이 나쁨으로 둔갑한다.

★이 캠페인이 반복해서 세운 원칙: **정답이 '값'이 아니라 '보류'일 수 있다.**
  (같은 형태를 탁상감정 신뢰도에서도 고쳤다 — `test_desk_appraisal_determinism.py`)

★가중 재정규화가 이 결함을 **키운다**: 누락 지표를 빼고 남은 것에 가중을 몰아주므로,
  1개만 있어도 점수는 그 1개의 정규화값이 되고 등급표가 그대로 적용된다.
"""

from __future__ import annotations

from app.services.site_score import site_score_service as mod


def _score(context: dict) -> dict:
    return mod.compute_site_score(context)


# 지표 1개(지가)만 확보 — 실측 결함이 난 그 형상
_ONE = {"official_price_per_sqm": 3_000_000}
# 지표 4개(지가·교통·상권·용도지역) — 하한 위
_FOUR = {
    "official_price_per_sqm": 3_000_000,
    "zone_type": "제2종일반주거지역",
    "store_count": 120,
    "infrastructure": {"nearest_subway": {"distance_m": 400}},
}


def test_grade_is_withheld_below_coverage_floor() -> None:
    """지표 1개만 확보 → 등급 **보류**(null) + 사유. 점수는 참고로 남는다."""
    r = _score(_ONE)
    assert r["covered"] < mod.GRADE_COVERAGE_FLOOR, (
        f"픽스처가 하한 위다 — 이 테스트가 공허해진다: covered={r['covered']}"
    )
    assert r["grade"] is None, (
        f"지표 {r['covered']}/{r['total_features']} 뿐인데 등급을 단정한다 — "
        f"'모른다'가 '나쁘다'로 읽힌다. grade={r['grade']}"
    )
    assert r.get("grade_basis"), "등급을 보류했으면 **사유**를 말해야 한다"
    assert "보류" in r["grade_basis"], f"보류인데 근거가 보류라고 말하지 않는다: {r['grade_basis']}"
    assert str(r["covered"]) in r["grade_basis"], (
        "사유가 몇 개 확보했는지 말하지 않는다 — 사용자가 무엇을 채워야 할지 모른다"
    )


def test_grade_is_issued_at_or_above_floor() -> None:
    """★특이도 — 하한을 넘으면 **정상 발행**된다(가드가 정상을 막으면 그것도 결함이다)."""
    r = _score(_FOUR)
    assert r["covered"] >= mod.GRADE_COVERAGE_FLOOR, f"픽스처가 하한 미만: {r['covered']}"
    assert r["grade"] is not None, f"하한을 넘었는데 등급이 없다: covered={r['covered']}"
    # ★2026-08-25 계약 강화 — `_basis` 는 **항상** 채운다(관용: legal_basis·far_basis…).
    #   종전 `_withheld_reason` 은 보류일 때만 채워져, **발행된 등급의 근거는 아무도
    #   말하지 않았다**. 이제 발행 시에도 무엇을 근거로 그 등급인지 말한다.
    assert r.get("grade_basis"), "등급을 발행했는데 근거가 없다 — 값만 있고 출처가 없다"
    assert "보류" not in r["grade_basis"], (
        f"발행했는데 근거가 보류라고 말한다: {r['grade_basis']}"
    )
    assert str(r["covered"]) in r["grade_basis"], "근거가 커버리지를 말하지 않는다"
    # ★변이 실증(2026-08-25) — 근거 문자열의 **꼬리만 지워도** 위 단언들은 통과했다
    #   (앞 절반에 커버리지가 있어서). 근거는 **자기가 설명하는 값**을 말해야 한다.
    assert r["grade"] in r["grade_basis"], (
        f"근거가 **어떤 등급인지**를 말하지 않는다 — 설명 대상이 빠졌다: {r['grade_basis']}"
    )
    assert str(r["score"]) in r["grade_basis"], (
        f"근거가 **점수**를 말하지 않는다 — 등급이 어디서 왔는지 알 수 없다: {r['grade_basis']}"
    )


def test_two_populations_actually_differ() -> None:
    """★픽스처가 두 모집단을 갈라야 한다 — 둘이 같으면 배선을 끊어도 결과가 같다."""
    low = _score(_ONE)
    high = _score(_FOUR)
    assert low["covered"] != high["covered"], "두 픽스처의 커버리지가 같다 — 대조가 성립 안 한다"
    assert (low["grade"] is None) and (high["grade"] is not None), (
        f"저커버리지와 고커버리지가 **같은 등급 계약**을 낸다: {low['grade']} / {high['grade']}"
    )


def test_floor_is_a_named_constant_not_a_magic_number() -> None:
    """계약 상수에 결속한다 — 대역(`> 2`)만 보면 상수가 장식이 된다(§A-5)."""
    assert isinstance(mod.GRADE_COVERAGE_FLOOR, int)
    assert 1 < mod.GRADE_COVERAGE_FLOOR <= len(mod.WEIGHTS)


def test_both_gradeless_paths_have_the_same_key_shape() -> None:
    """지표 0개와 하한 미달은 **같은 키 모양**이어야 한다 — 갈리면 한쪽만 처리된다."""
    empty = _score({})
    low = _score(_ONE)
    for k in ("grade", "grade_basis", "covered", "total_features"):
        assert k in empty, f"지표 0개 경로에 `{k}` 가 없다 — 소비처가 두 갈래를 따로 다뤄야 한다"
        assert k in low, f"하한 미달 경로에 `{k}` 가 없다"
    assert empty["grade"] is None and low["grade"] is None
    assert empty["grade_basis"] and low["grade_basis"]


def test_근거_키가_저장소_관용을_따른다() -> None:
    """★`X_basis` 가 이 저장소의 확립된 관용이다 — 새 이름을 만들지 않는다(§29).

    실측(origin/main): `legal_basis` **293** · `far_basis` **135** · `floor_cap_basis` 31 ·
    `qty_basis` 25 · `sample_basis` 18 · `gfa_basis` 16 · `price_basis` 12 · `area_basis` 11.
    종전 `grade_withheld_reason` 은 **이 저장소에서 단 하나뿐인** 이름이었다 —
    즉 **없는 걸 만든 게 아니라 있는 걸 안 쓴 것**이었다.

    ★이 락이 없으면 다음 사람이 또 새 이름을 만든다(`_reason`·`_note`·`_why`…).
      이름이 갈리면 **파생형 검사가 불가능**해지고, 규칙은 다시 산문이 된다.
    """
    r_low, r_ok = _score(_ONE), _score(_FOUR)
    for label, r in (("보류", r_low), ("발행", r_ok)):
        assert "grade_basis" in r, f"[{label}] 관용 키 `grade_basis` 가 없다"
        assert not any(k.endswith("_withheld_reason") for k in r), (
            f"[{label}] `_withheld_reason` 계열이 되살아났다 — 관용은 `_basis` 다: "
            f"{[k for k in r if k.endswith('_withheld_reason')]}"
        )
    # ★두 모집단이 **다른 근거 문구**를 내야 한다(같으면 이 락은 아무것도 안 잠근다)
    assert r_low["grade_basis"] != r_ok["grade_basis"], "보류와 발행이 같은 근거를 낸다"
