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

import pathlib
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
    import re

    # ★**수치와 판정어의 인접**을 본다 — 수치만 보면 같은 노트의 **구성 나열**이 단언을
    #   «다른 이유로» 만족시키고, 판정어만 보면 수치를 지워도 통과한다.
    #   (실측 2026-09-14: 이 파일에서 같은 클래스를 **세 번** 만났다 — 0%·partial·match)
    assert re.search(r"0\.0%\*{0,2}\(0건\)", absent), f"0% 판정 문장에 수치가 없다: {absent[-160:]}"
    assert "쓸 수 없습니다" in absent
    assert re.search(r"100%\*{0,2}\s*입니다 — 같은 용도지역 표본", allmatch), (
        f"전부 일치 **판정 문장**이 수치를 안 싣는다: {allmatch[-160:]}")
    assert "쓸 수 없습니다" not in allmatch


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


def _kwarg_value_src(func_name: str, call_name: str, kwarg: str) -> list[str]:
    """그 호출이 `kwarg=` 로 넘기는 **값 표현식의 소스**를 뽑는다.

    ★왜 키워드 존재만으로 부족한가(기계 변이 실측 2026-09-14):
      `target_land_use=str((subject or {}).get("zone_type") or "")` 의 **문자열 `"zone_type"` 만**
      바꾸는 변이가 **SURVIVED** 했다. 키워드는 그대로라 「넘긴다」는 참이지만, 넘어가는 값이
      **항상 빈 값**이 되어 기능이 통째로 꺼진다.
      ⇒ 저장소 기록 그대로다: ***「불린다」가 아니라 「무엇을 넘기는가」를 보라.***
    """
    import ast
    import inspect
    import textwrap

    from app.services.land_intelligence import desk_appraisal_service as mod

    src = textwrap.dedent(inspect.getsource(getattr(mod, func_name)))
    tree = ast.parse(src)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != call_name:
            continue
        for kw in node.keywords:
            if kw.arg == kwarg:
                out.append(ast.get_source_segment(src, kw.value) or "")
    return out


def _literals_and_names(expr_src: str) -> tuple[set[str], set[str]]:
    """값 표현식의 **문자열 리터럴**과 **이름**을 각각 뽑는다.

    ★왜 부분문자열이 아니라 AST 인가(독립 리뷰 H1 · 2026-09-14 재현):
      종전 단언은 `assert "zone_type" in v` 였는데 그것은 **부분문자열**이라
      `subject.get("zone_type_2")` 도 **통과**한다. 그리고 `zone_type_2` 는 **가상이 아니다** —
      `desk_appraisal_service.py` 가 실제로 그 키를 담고(`"zone_type_2": lc.get("zone_type_2")`),
      web 타입에도 선언돼 있다(`lib/land/desk-appraisal.ts`). 즉 **옆에 실재하는 다른 필드**로
      갈아 끼워도 내 락이 초록이었다(변이 실측 `::VERDICT=SURVIVED`).
      ⇒ 저장소 기록 그대로다: ***경계를 주지 않은 포함 검사는 형제 이름에 뚫린다***
        (`매도청구 가능` 이 `매도청구 가능여부` 를 집던 그 자리).
    """
    import ast

    tree = ast.parse(expr_src, mode="eval")
    lits = {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    return lits, names


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
        # ★★값 축 — 「넘긴다」가 아니라 **「무엇을 넘기는가」**
        vals = _kwarg_value_src("desk_appraisal", call, "target_land_use")
        assert vals, f"{call}(...) 의 target_land_use 값 표현식을 못 읽었다"
        for v in vals:
            lits, names = _literals_and_names(v)
            # ★**정확 일치**다. `"zone_type" in v` 는 부분문자열이라 실재하는 형제 키
            #   `zone_type_2` 로 갈아 끼워도 통과했다(리뷰 H1 · 변이 SURVIVED 재현).
            assert "zone_type" in lits, (
                f"{call}(target_land_use=…) 이 **대상 용도지역을 안 읽는다** — 넘기기는 하지만 "
                f"값이 비면 기능이 통째로 꺼진다. 읽는 키: {sorted(lits)} · 원문 {v!r}")
            assert "subject" in names, (
                f"{call}(target_land_use=…) 이 subject 에서 오지 않는다. "
                f"이름: {sorted(names)} · 원문 {v!r}")
        assert "target_land_use" in kws, (
            f"{call}(...) 이 대상 용도지역을 **안 넘긴다** — 그러면 그 함수는 원리적으로 "
            f"가정법밖에 말할 수 없다. 넘기는 키워드: {sorted(kws)}")


def test_partial_branch_of_the_note_carries_the_measured_share():
    """★`stats_note` 의 **일부 일치** 갈래도 수치를 싣는가 — 0%/100% 만 보면 가운데가 빈다.

    ★생존 실측: `land_dong_stats.py:424` 문자열변경 SURVIVED — 그 f-string 이 유일하게
      partial 수치를 싣는데 앞선 락은 **0% 와 100% 만** 봤다.
    """
    from app.services.market.land_dong_stats import stats_note

    import re

    n = stats_note(_stats(_MIX_COMMERCIAL_ABSENT), 6, target_land_use="제1종일반주거지역")
    assert n, "조회기 사망 — 노트가 비었다"

    # ★★**「다른 이유로 만족되는 단언」을 피한다**(실측 2026-09-14):
    #   처음엔 `"83.3%" in n` 으로 짰는데 **SURVIVED** 했다 — 같은 노트의 **구성 나열**
    #   (`land_dong_stats:398` "용도지역 제1종일반주거지역 83.3% · …")이 그 문자열을 이미
    #   싣기 때문이다. ***내 단언은 판정 문장이 아니라 나열 때문에 참이었다.***
    #   ⇒ **수치와 한정어가 붙어 있는지**를 본다(그 둘의 인접이 판정 문장의 지문이다).
    assert re.search(r"83\.3%\*{0,2}\s*뿐입니다", n), (
        f"일부 일치 **판정 문장**이 수치를 안 싣는다(나열의 수치는 다른 것이다): {n[-170:]}")
    assert "0.0%" not in n, "일부 일치인데 0% 를 말하면 거짓이다"


def _returned_dict_keys(func_name: str) -> set[str]:
    """`desk_appraisal` 이 **반환하는 dict 리터럴의 최상위 키**를 AST 로 뽑는다."""
    import ast
    import inspect
    import textwrap

    from app.services.land_intelligence import desk_appraisal_service as mod

    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(mod, func_name))))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            keys |= {k.value for k in node.value.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def test_response_keys_are_a_contract():
    """★**출력 키 이름은 계약이다** — 소비처(PDF·화면)가 그 이름으로 읽는다.

    ★생존 실측: `"land_market_stats_zone_match"` · `"land_market_stats_note"` 의
      **키 문자열을 바꾸는 변이가 SURVIVED** 했다. 키가 바뀌면 소비처는 **조용히 `None`** 을
      받는다 — 이 저장소가 반복해 데인 «정의만 하고 소비처 0» 의 거울상이다.
    """
    keys = _returned_dict_keys("desk_appraisal")
    # ★대조군 먼저 — AST 가 반환 dict 를 찾았는가
    assert "land_market_stats" in keys, f"조회기 사망 — 반환 키를 못 찾았다: {sorted(keys)[:10]}"
    assert "zzz_nope_sentinel" not in keys          # 역대조군

    for k in ("land_market_stats_zone_match", "land_market_stats_note"):
        assert k in keys, f"출력 키 {k!r} 가 사라졌다 — 소비처는 조용히 None 을 받는다: {sorted(keys)}"


def _returned_dict_value_src(func_name: str, key: str) -> str | None:
    """반환 dict 에서 `key` 가 가진 **값 표현식의 소스**를 뽑는다."""
    import ast
    import inspect
    import textwrap

    from app.services.land_intelligence import desk_appraisal_service as mod

    src = textwrap.dedent(inspect.getsource(getattr(mod, func_name)))
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if isinstance(k, ast.Constant) and k.value == key:
                return ast.get_source_segment(src, v)
    return None


def _first_positional_src(expr_src: str, call_name: str) -> list[str]:
    """`call_name(...)` 의 **첫 위치인자** 소스를 뽑는다."""
    import ast

    tree = ast.parse(expr_src, mode="eval")
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name == call_name and node.args:
            out.append(ast.get_source_segment(expr_src, node.args[0]) or "")
    return out


def test_machine_field_describes_the_very_stats_it_is_shown_beside():
    """★★**키 이름이 아니라 「무엇을 재는가」를 잠근다**(독립 리뷰 H2 · 2026-09-14 재현).

    ★생존 실측: `land_zone_match(land_dong_stats_out, …)` 의 **첫 인자를 `None` 으로** 바꾼
      변이가 `::VERDICT=SURVIVED`. 앞선 락은 ①키워드 이름 ②출력 키 이름만 봤다 —
      둘 다 그대로라 **초록인데 필드는 영구 `None`** 이었다.
      ⇒ 저장소 기록 그대로다: ***「불린다」가 아니라 「무엇을 넘기는가」*** ·
        ***상수를 자기 자신과 비교하는 락은 아무것도 안 잠근다.***

    ★축은 **동일성**이다: 일치율은 `land_market_stats` **바로 그 통계**를 재야 한다.
      다른 통계를 재면 화면에는 A 를 보여 주고 «A 는 0% 다» 대신 **B 의 0%** 를 말하게 된다.
    """
    stats_src = _returned_dict_value_src("desk_appraisal", "land_market_stats")
    assert stats_src, "★조회기 사망 — 반환 dict 에서 land_market_stats 를 못 찾았다"

    for key, call in (("land_market_stats_zone_match", "land_zone_match"),
                      ("land_market_stats_note", "land_stats_note")):
        val = _returned_dict_value_src("desk_appraisal", key)
        assert val, f"★조회기 사망 — 반환 dict 에서 {key} 를 못 찾았다"
        firsts = _first_positional_src(val, call)
        assert firsts, f"{key} 가 {call}(...) 을 **위치 첫 인자 없이** 부른다: {val!r}"
        for got in firsts:
            assert got == stats_src, (
                f"{key} 가 **land_market_stats 와 다른 것을 재고 있다** — 화면엔 {stats_src!r} 을 "
                f"보여 주면서 일치율은 {got!r} 로 낸다. 소비처는 조용히 틀린 값을 받는다.")


@pytest.mark.xfail(strict=True, reason=(
    "★부채(2026-09-14 · 독립 리뷰 H2): 기계 필드 `land_market_stats_zone_match` 와 "
    "`reference_zone_match` 는 **소비처 0** 이다(실측: 정의부·본 락 제외 0파일. "
    "대조군 `reference_note` 는 5파일 — PDF `appraisal_adapter.py:277` · "
    "web `DeskAppraisalReportClient.tsx:493` 로 **실제 사용자에게 닿는다**). "
    "즉 사용자가 보는 경로는 산문 쪽이고, 기계 필드는 아직 「정의만 하고 소비처 0」 클래스다. "
    "★배선하면 이 xfail 이 **XPASS 로 실패**한다 — 그때 부채표를 지우라는 신호다."))
def test_debt_machine_zone_match_field_has_no_consumer_yet():
    """소비처를 **AST/파생이 아니라 저장소 전수 grep** 으로 센다(축: 파일)."""
    import subprocess

    root = pathlib.Path(__file__).resolve().parents[3]
    out = subprocess.run(
        ["git", "grep", "-l", "-e", "land_market_stats_zone_match", "-e", "reference_zone_match",
         "--", "apps/"], cwd=root, capture_output=True, text=True)
    # rc 1 == 0건. rc >1 은 **조회기 사망**이라 부채 판정에 쓰면 안 된다.
    assert out.returncode in (0, 1), f"★조회기 사망(rc={out.returncode}): {out.stderr[:200]}"
    files = {f for f in out.stdout.split() if f}
    consumers = {f for f in files
                 if "desk_appraisal_service.py" not in f
                 and "test_market_sample_zone_match.py" not in f}
    assert consumers, f"기계 필드를 읽는 소비처가 생겼다 — 부채 해소: {sorted(consumers)}"
