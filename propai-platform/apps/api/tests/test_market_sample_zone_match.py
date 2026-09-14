"""참고 실거래 표본의 **용도지역 일치**를 잰다 — 잴 수 있는 것을 조건문으로 말하지 않는다.

★왜(라이브 실측 2026-09-14 · 경기도 남양주시 화도읍 마석우리 265-1):
  `subject.zone_type` = **일반상업지역** 이고
  `land_market_stats.land_use_mix` = 제1종일반주거 83.3% · 계획관리 16.7% 였다.
  ⇒ **대상 용도지역이 표본에 0.0%.** 그런데 참고단가 **3,855,297원/㎡** 가 「참고」 라벨로 나갔다.

  응답 전수(리프 168개)에서 그 「0%」를 담은 **기계 필드는 0건**이었고, 산문만 이렇게 말했다:
      *"대상지와 다른 용도지역·지목이 **섞여 있으면** 단가가 크게 다를 수 있습니다."*
  ⇒ **가정법**이라 「확인 못 했다」와 「확인했고 0% 다」가 **같은 문장으로 덮인다.**
  원인은 한 줄이다 — `stats_note(stats, window_months)` 에 **대상 용도지역 인자가 없었다.**

★이 모듈의 주석이 자기 언어로 **이미 경고**하고 있었다(`land_dong_stats.py`):
  *"혼입도 왜곡도 아니고 **모집단이 다른** 것이었는데 `scope_label` 이 '논현동' 뿐이라
    사용자는 구분할 수 없다"*(논현동 1-1 공시지가 0.54배 사고).
  설계 의도는 *"막지 않고 **밝힌다**"* 였는데, ***밝힘이 조건문이면 밝힌 것이 아니다.***
"""
from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="app 패키지가 3.11+ 문법을 쓴다 — 개발 기본 python3(3.10)에서는 임포트 불가. "
           "★로컬에서 돌리려면 3.12 venv 를 쓴다: "
           "/home/kangjh3kang/.venvs/propai312/bin/python -m pytest <이 파일> (propai312 · GDAL 불필요).",
)

_MIX_COMMERCIAL_ABSENT = [
    {"land_use": "제1종일반주거지역", "count": 5, "share_pct": 83.3},
    {"land_use": "계획관리지역", "count": 1, "share_pct": 16.7},
]
_MIX_ALL_COMMERCIAL = [{"land_use": "일반상업지역", "count": 6, "share_pct": 100.0}]


def _stats(mix):
    return {
        "scope_label": "마석우리 · 답", "sample_count": 6,
        "unit_price_per_sqm": 3_855_297,
        "land_use_mix": mix,
        "jimok_mix": [{"jimok": "답", "count": 6, "share_pct": 100.0}],
    }


def test_zone_match_separates_three_states():
    """★**3상태** — `None`(못 쟀다) / `0.0`(쟀고 0%) / `>0`. 뭉치면 「모름」이 「없음」으로 샌다."""
    from app.services.market.land_dong_stats import zone_match

    s = _stats(_MIX_COMMERCIAL_ABSENT)

    # ① 못 쟀다 — 대상 미상
    assert zone_match(s, None) is None
    # ② 못 쟀다 — 표본 구성 없음(대상은 있는데)
    assert zone_match({"land_use_mix": []}, "일반상업지역") is None
    # ③ 쟀고 0% — ★`None` 과 **다른 값**이어야 한다(이 구분이 이 PR 의 요지다)
    z = zone_match(s, "일반상업지역")
    assert z is not None and z["share_pct"] == 0.0 and z["verdict"] == "none"
    # ④ 일부
    z2 = zone_match(s, "제1종일반주거지역")
    assert z2["share_pct"] == 83.3 and z2["verdict"] == "partial"
    # ⑤ 전부
    z3 = zone_match(_stats(_MIX_ALL_COMMERCIAL), "일반상업지역")
    assert z3["share_pct"] == 100.0 and z3["verdict"] == "match"


def test_zone_match_uses_the_same_normalisation_as_the_producer():
    """★생산자(`_mix_of`)가 `_norm` 으로 키를 만든다 — **같은 정규화로 비교**해야 한다.

    ★2026-09-14 실측 교훈: 내 축이 프로덕션 축과 한 단계 다르면 **40배**까지 어긋난다
      (보존잡 재고를 `(type, key)` 로 세어 243건 → 프로덕션 축 `(type, 윈도우폭, key)` 로 **6건**).
    """
    from app.services.market.land_dong_stats import zone_match

    s = _stats([{"land_use": "  일반상업지역  ", "count": 6, "share_pct": 100.0}])
    z = zone_match(s, "일반상업지역")
    assert z is not None and z["share_pct"] == 100.0, "공백만 다른데 못 맞추면 정규화가 갈린 것이다"


def test_note_says_the_measured_share_instead_of_a_conditional():
    """★대상을 주면 **가정법이 사라지고 실측**이 나온다."""
    from app.services.market.land_dong_stats import stats_note

    n = stats_note(_stats(_MIX_COMMERCIAL_ABSENT), 6, target_land_use="일반상업지역")
    assert n, "조회기 사망 — 노트가 비었다"
    assert "섞여 있으면" not in n, (
        "★쟀는데도 가정법으로 말한다 — 「확인 못 했다」와 「확인했고 0%」가 같은 문장으로 덮인다")
    assert "0.0%" in n, f"실측 수치가 없다: {n[-160:]}"
    assert "모집단이 다릅니다" in n


def test_note_is_unchanged_when_target_is_unknown():
    """★대상을 모르면 **가정법이 정직한 자리**다 — 현행 문구 그대로(무회귀)."""
    from app.services.market.land_dong_stats import stats_note

    n = stats_note(_stats(_MIX_COMMERCIAL_ABSENT), 6)
    assert n and "섞여 있으면" in n, "대상 미상일 때는 조건문이 맞다"
    assert "0.0%" not in n, "재지 않았는데 수치를 말하면 날조다"


def test_two_populations_produce_different_notes():
    """★**두 모집단** — 일치 0% 와 일치 100% 가 **다른 문구**를 내야 한다.

    차가 0인 픽스처는 잠금이 아니다.
    """
    from app.services.market.land_dong_stats import stats_note

    absent = stats_note(_stats(_MIX_COMMERCIAL_ABSENT), 6, target_land_use="일반상업지역")
    allmatch = stats_note(_stats(_MIX_ALL_COMMERCIAL), 6, target_land_use="일반상업지역")
    assert absent != allmatch, "두 모집단이 같은 문구를 낸다 — 이 락은 공허하다"
    assert "0.0%" in absent and "쓸 수 없습니다" in absent
    assert "같은 용도지역 표본입니다" in allmatch and "쓸 수 없습니다" not in allmatch


def test_reference_note_and_machine_field_carry_the_mismatch():
    """★**소비처까지** — `methods[1]` 이 참고값과 함께 일치 실측을 싣는가.

    ★기계 필드(`reference_zone_match`)도 함께 본다 — 산문만 고치면 소비처는 **파싱**해야 한다.
    """
    from app.services.land_intelligence.desk_appraisal_service import (
        _assemble_methods,
        _zone_match_clause,
    )

    stats = _stats(_MIX_COMMERCIAL_ABSENT)

    # ★대조군 먼저 — 대상 미상이면 절이 **비어야** 한다(가정법도 안 붙인다)
    assert _zone_match_clause(stats, None) == ""
    clause = _zone_match_clause(stats, "일반상업지역")
    assert "0.0%" in clause and "모집단이 다르므로" in clause

    ms = _assemble_methods(
        method_pub={"method": "공시지가 기준 추정", "unit_price": 3_153_689},
        method_cmp=None, building=None, income=None,
        land_stats=stats, comparable_skip_note="위치 확인 거래 없음",
        target_land_use="일반상업지역",
    )
    cmp_m = next(m for m in ms if m["method"] == "거래사례비교법")
    assert cmp_m["reference_unit_price"] == 3_855_297
    assert "0.0%" in (cmp_m["reference_note"] or ""), "참고단가 옆에 일치 실측이 없다"
    zm = cmp_m["reference_zone_match"]
    assert zm and zm["share_pct"] == 0.0 and zm["verdict"] == "none", (
        "기계 필드가 없으면 소비처는 산문을 파싱해야 한다 — 그건 소비가 아니다")


def test_zone_match_clause_covers_all_three_branches():
    """★`_zone_match_clause` **세 갈래 전수** — 기계 변이가 `match` 분기를 무력화해도 살아남았다.

    ★생존 실측(2026-09-14 · `mutate_changed.py`): `desk_appraisal_service.py:211`
      `if zm["verdict"] == "match":` **조건무력화 SURVIVED** — 내 락이 `None` 과 0% 만 봤다.
      ***한 함수의 분기를 일부만 태우면 나머지는 무잠금이다.***
    """
    from app.services.land_intelligence.desk_appraisal_service import _zone_match_clause

    none_c = _zone_match_clause(_stats(_MIX_COMMERCIAL_ABSENT), None)
    zero_c = _zone_match_clause(_stats(_MIX_COMMERCIAL_ABSENT), "일반상업지역")
    part_c = _zone_match_clause(_stats(_MIX_COMMERCIAL_ABSENT), "제1종일반주거지역")
    full_c = _zone_match_clause(_stats(_MIX_ALL_COMMERCIAL), "일반상업지역")

    # ★공허 방지 — 네 갈래가 **서로 다른 값**이어야 한다(차가 0이면 이 락은 장식이다)
    assert len({none_c, zero_c, part_c, full_c}) == 4, (
        f"갈래가 안 갈린다: {[none_c, zero_c, part_c, full_c]}")

    assert none_c == "", "못 쟀으면 아무 말도 하지 않는다(가정법도 안 붙인다)"
    assert "0.0%" in zero_c
    # ★**수치가 계약이고 문구는 표현이다** — 수치만 단언한다(문구를 잠그면 다듬을 때마다 깨진다)
    assert "83.3%" in part_c, f"일부 일치 갈래가 **실측 수치**를 안 싣는다: {part_c}"
    assert "100%" in full_c, f"전부 일치 갈래가 **실측 수치**를 안 싣는다: {full_c}"

    # ★★**문구가 아니라 「거짓」을 잠근다**(기계 변이 실측 2026-09-14):
    #   `if zm["verdict"] == "match":` 한 줄을 지우면 match 의 `return` 이 0% 블록 안의
    #   **죽은 코드**가 되고, 100% 일치가 **partial 문구**로 떨어진다 —
    #   *"…100% **뿐입니다 — 나머지는 다른 용도지역입니다**"*.
    #   ***100% 일치인데 「나머지는 다른 용도지역」은 거짓이다.*** 수치만 단언하면 통과한다
    #   (실제로 그 변이가 SURVIVED 했다). 표현이 아니라 **참·거짓**을 단언한다.
    assert "뿐입니다" not in full_c, (
        f"전부 일치인데 «뿐입니다» 라고 말한다 — 거짓이다: {full_c}")
    assert "나머지는" not in full_c, (
        f"전부 일치인데 «나머지는 다른 용도지역» 이라고 말한다 — 남은 것이 없다: {full_c}")
    # 거울상 — 일부 일치인데 «전부» 로 말하면 그것도 거짓이다(양방향)
    assert "뿐입니다" in part_c, f"일부 일치인데 한정어가 없다: {part_c}"


def _calls_and_kwargs(func_name: str, call_name: str) -> tuple[int, set[str]]:
    """`desk_appraisal` 본문에서 `call_name(...)` 호출이 넘기는 **키워드 이름**을 AST 로 뽑는다.

    ★**문자열 포함 검사를 쓰지 않는다** — 주석에 그 낱말을 쓰면 위음성이 된다
      (2026-09-14 실측: 같은 세션에서 그 형태로 변이 하나를 놓쳤다).
    """
    import ast
    import inspect
    import textwrap

    from app.services.land_intelligence import desk_appraisal_service as mod

    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(mod, func_name))))
    out: set[str] = set()
    seen = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = getattr(f, "id", None) or getattr(f, "attr", None)
        if name != call_name:
            continue
        seen += 1
        out |= {kw.arg for kw in node.keywords if kw.arg}
    return seen, out


def test_call_sites_actually_pass_the_target_zone():
    """★★**호출부를 잠근다** — 배선을 지워도 내 락이 초록이었다(기계 변이 실측).

    ★생존 실측(2026-09-14): `desk_appraisal_service.py:814`·`:835` 의
      `target_land_use=...` **줄삭제가 SURVIVED**. 앞선 락이 `_assemble_methods` 를 **직접**
      호출해서 **호출부를 한 번도 안 태웠기 때문**이다.
      ⇒ 저장소 기록 그대로다: ***「존재를 잠그면 행위는 안 잠긴다」*** ·
        ***「배선 락의 축은 AST 로 파생한 호출부」***.
    """
    for call in ("_assemble_methods", "land_stats_note", "land_zone_match"):
        seen, kws = _calls_and_kwargs("desk_appraisal", call)
        # ★대조군 먼저 — **세 상태를 가른다**: 호출 없음(조회기 사망) / 호출은 있는데 키워드 0 /
        #   키워드는 있는데 target 이 없음. 뭉치면 "조회기 사망" 이 **위치인자 호출**을 덮는다
        #   (2026-09-14 실측: 내가 실제로 그렇게 뭉쳐 놓고 한 번 오진했다).
        assert seen, f"★조회기 사망 — desk_appraisal 안에서 {call}(...) 호출 자체를 못 찾았다"
        assert kws, (
            f"{call}(...) 을 **위치인자로만** 부른다 — 시그니처가 바뀌면 조용히 밀린다(저장소 §33)")
        assert "target_land_use" in kws, (
            f"{call}(...) 이 대상 용도지역을 **안 넘긴다** — 그러면 그 함수는 원리적으로 "
            f"가정법밖에 말할 수 없다. 넘기는 키워드: {sorted(kws)}")
