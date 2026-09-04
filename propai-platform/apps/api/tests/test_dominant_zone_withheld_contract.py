"""우세 용도지역 **보류**를 계약대로 낸다 — 센티널이 아니라 `None + _absent`.

## 왜 (실측 2026-09-04)

`#963` 에서 「형제와 일치」를 `xfail(strict)` 부채로 뺐다. 그냥 맞추면 회귀 2건이 났다:
  · `mixed_review_required` 가 `DevelopmentScenarioCard.tsx:211` **볼드 배지에 맨몸으로** 나감
  · `_is_residential()` 이 False 가 되어 주거계 **4종이 「불가·요건 미해당」**, 1종은 **사라짐**

★조회에서 **답이 이미 저장소에 있었다** — `app/utils/withheld.py` 의 보류값 계약:

    X : 값 | None  ·  X_basis : 문구  ·  X_absent : **닫힌 7종** 코드
    ★센티널 금지 — 값 자리에 "mixed_review_required" 를 넣지 않는다

★★그리고 **형제가 그 계약을 위반**한다(`special_parcel.py:1869` 이 그 문자열을 **값으로** 냄).
검증기 `validate_withheld_pair` 는 있는데 **`special_parcel`·`scenario_simulator` 가 그 검사를
안 탄다** — 「검사기는 있는데 대상이 안 탄다」. 그래서 «형제와 일치» 는 **위반을 따라가는 것**이었다.
→ 형제 **판정은 따르되 계약 형태로 번역**한다(형제 수정은 소비처 6곳 파급이라 별건).
"""
import pytest

from app.services.development import scenario_simulator as SS
from app.services.development.scenario_simulator import (
    DevelopmentScenarioSimulator,
    dominant_zone_by_area,
)
from app.utils.withheld import ABSENT_REASONS, SENTINEL_VALUES, validate_withheld_pair


def _rows(pairs):
    return [{"zone": z, "area": a} for z, a in pairs]


# ── ① 계약 준수 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("label,pairs", [
    ("규제성격 상이(상업+주거)", [("일반상업지역", 1200.0), ("제2종일반주거지역", 800.0)]),
    ("동률(±5% 이내)", [("제2종일반주거지역", 1000.0), ("제3종일반주거지역", 1020.0)]),
    ("녹지+주거", [("자연녹지지역", 900.0), ("제2종일반주거지역", 1100.0)]),
])
def test_withheld_is_none_plus_code_not_a_sentinel(label, pairs):
    """★단일화를 거부할 때 **값은 None**, 사유는 **닫힌 어휘 코드**."""
    zone, basis = dominant_zone_by_area(_rows(pairs))
    assert zone is None, f"{label}: 값 자리에 {zone!r} — 계약은 None 을 요구한다"
    assert basis == SS.ZONE_BASIS_AMBIGUOUS
    assert basis in ABSENT_REASONS, f"닫힌 어휘 밖 코드 — {basis!r}"
    # ★센티널이 되살아나면 여기서 죽는다
    assert str(zone) not in SENTINEL_VALUES


def test_sentinel_never_leaves_this_module():
    """★금지어가 **어떤 경로로도** 값으로 나가지 않는다 — 전 모집단 파생."""
    pops = [
        [("일반상업지역", 1200.0), ("제2종일반주거지역", 800.0)],
        [("제2종일반주거지역", 1000.0), ("제3종일반주거지역", 1020.0)],
        [("자연녹지지역", 900.0), ("제2종일반주거지역", 1100.0)],
        [("제2종일반주거지역", 1500.0), ("준공업지역", 300.0)],
        [("제1종일반주거지역", 410.0), ("제2종일반주거지역", 1300.0)],
        [("제2종일반주거지역", 800.0)],
    ]
    seen = {dominant_zone_by_area(_rows(p))[0] for p in pops}
    assert seen, "모집단이 비었다"
    bad = {z for z in seen if isinstance(z, str) and z.strip() in SENTINEL_VALUES}
    assert not bad, f"센티널이 값으로 나갔다 — {bad}"
    # ★음성 대조군 — 단일화 가능한 부지는 **이름**이 나와야 한다(과잉 보류 방지)
    single, sb = dominant_zone_by_area(_rows([("제1종일반주거지역", 410.0),
                                              ("제2종일반주거지역", 1300.0)]))
    assert single == "제2종일반주거지역" and sb == SS.ZONE_BASIS_AREA_WEIGHTED, (single, sb)


def test_site_payload_satisfies_the_withheld_contract():
    """★저장소 **검증기**로 짝을 검사한다 — 내가 만든 규칙이 아니라 확립된 계약이다.

    `special_parcel`·`scenario_simulator` 가 이 검사를 **안 타고 있었다**(소비처 실측).
    """
    for zone, code in ((None, SS.ZONE_BASIS_AMBIGUOUS), ("제2종일반주거지역", None)):
        site = {"primary_zone": zone, "primary_zone_absent": code,
                "primary_zone_basis": "면적가중" if zone else "규제성격 상이 — 단일화 보류"}
        assert validate_withheld_pair(site, "primary_zone") == [], (
            f"계약 위반 — {validate_withheld_pair(site, 'primary_zone')}"
        )
    # ★음성 대조군 — 센티널을 넣으면 검증기가 **잡아야** 한다(검사기 생존 증명)
    broken = {"primary_zone": "mixed_review_required", "primary_zone_basis": "x"}
    assert validate_withheld_pair(broken, "primary_zone"), "검증기가 센티널을 못 잡는다"


# ── ② 보류가 「불가」로 번역되지 않는다 ────────────────────────────────────

def _ctx(zone, zones):
    return {"total_area_sqm": 12000.0, "primary_zone": zone, "zones": zones,
            "far_effective_blended": 200, "far_legal_blended": 250, "multi": True,
            "near_station": {"name": "t", "distance_m": 200}, "near_station_m": 200,
            "region": "서울특별시", "integration_feasible": True,
            "adjacency": {"contiguous": True, "components": 1, "note": "단일 필지",
                          "max_pair_distance_m_min": 10.0},
            "buildings": {"old_ratio": 0.8, "total_units": 200},
            "block_aging": {"old_ratio": 0.75, "meets_2_3": True, "total_units": 300,
                            "radius_m": 100, "buildings_found": 50},
            "apartment_restricted_zones": []}


@pytest.mark.parametrize("label,zones", [
    ("★주거+공업(83:17)", ["제2종일반주거지역", "준공업지역"]),
    ("★동률 주거", ["제2종일반주거지역", "제3종일반주거지역"]),
    ("상업+주거", ["일반상업지역", "제2종일반주거지역"]),
    ("녹지+주거", ["자연녹지지역", "제2종일반주거지역"]),
])
def test_withheld_does_not_become_impossible(label, zones):
    """★보류는 «모른다» 이지 «아니다» 가 아니다 — 판정이 바뀌면 안 된다.

    실측(봉합 전): 주거+공업·동률에서 **4종이 조건부→불가, 1종은 목록에서 사라짐**(21→20).
    55% 가 주거인 부지에 «요건 미해당» 은 **거짓 사유**였다.
    """
    sim = DevelopmentScenarioSimulator()
    single = {x["scheme"]: x["applicable"] for x in sim._scenarios(_ctx(zones[0], zones))}
    held = {x["scheme"]: x["applicable"] for x in sim._scenarios(_ctx(None, zones))}
    assert len(single) >= 20, f"대조군이 비정상 — {len(single)}종"
    assert set(single) == set(held), (
        f"{label}: 시나리오가 사라졌다 — 없어진 것 {sorted(set(single) - set(held))}"
    )
    diff = {k: (single[k], held[k]) for k in single if single[k] != held[k]}
    assert not diff, f"{label}: 보류가 판정을 바꿨다 — {diff}"


def test_single_zone_sites_are_untouched():
    """★음성 대조군 — 단일 용도지역은 **아무것도 바뀌면 안 된다**(회귀 방지)."""
    sim = DevelopmentScenarioSimulator()
    for z, want in (("제2종일반주거지역", 21), ("일반상업지역", 20), ("자연녹지지역", 20)):
        got = sim._scenarios(_ctx(z, [z]))
        assert len(got) == want, f"{z}: {len(got)}종 (기대 {want}) — 단일 용도지역이 바뀌었다"


def test_zone_pool_actually_widens_the_check():
    """★배선 — `res`/`com` 이 **`zones` 전체**를 보는가(`zone` 하나만 보면 보류에서 False)."""
    sim = DevelopmentScenarioSimulator()
    # 보류 + zones 에 주거 있음 → 주거계 방식이 목록에 있어야 한다
    held = {x["scheme"] for x in sim._scenarios(_ctx(None, ["준공업지역", "제2종일반주거지역"]))}
    assert "역세권 장기전세주택(시프트)" in held, f"주거계가 사라졌다 — {len(held)}종"
    # ★음성 대조군 — zones 에 주거가 **없으면** 그 방식은 없어야 한다(과잉 포함 방지)
    nores = {x["scheme"] for x in sim._scenarios(_ctx(None, ["준공업지역", "일반상업지역"]))}
    assert "역세권 장기전세주택(시프트)" not in nores, "주거가 없는데 주거계가 들어왔다"


# ── ③ 변이가 드러낸 사각 봉합 ──────────────────────────────────────────────

def test_commercial_axis_also_widens():
    """★`com` 축 — `res` 만 넓히고 `com` 을 두면 상업계 방식이 보류에서 사라진다.

    변이 실측: `com = _is_commercial(zone)` 로 되돌려도 **SURVIVED** 였다 —
    상업계 방식을 태우는 모집단이 없었기 때문이다.
    """
    sim = DevelopmentScenarioSimulator()
    zones = ["제2종일반주거지역", "일반상업지역"]
    single = {x["scheme"]: x["applicable"] for x in sim._scenarios(_ctx("일반상업지역", zones))}
    held = {x["scheme"]: x["applicable"] for x in sim._scenarios(_ctx(None, zones))}
    # 상업 우세로 단일화했을 때 추진 가능하던 것이 보류에서 사라지면 안 된다
    com_ok = [k for k, v in single.items() if v in ("가능", "조건부")]
    assert com_ok, "대조군이 비었다"
    lost = [k for k in com_ok if held.get(k) not in ("가능", "조건부")]
    assert not lost, f"보류에서 상업계 추진 경로가 사라졌다 — {lost}"
    # ★음성 대조군 — 상업 유무가 무엇을 가르는지 **소스에서 확인하고** 그 축을 쓴다.
    #   `com` 은 `applicable` 을 안 바꾼다 — `est_far`(역세권 활성화)와 **결합건축 적격**을 가른다.
    #   ★처음엔 «이름 집합», 다음엔 «판정» 으로 비교해 **두 번 거짓 실패**를 냈다.
    #     대조군은 «다를 것 같은 축» 이 아니라 **그 변수가 실제로 지배하는 축**이어야 한다.
    def _axis(zs):
        m = {x["scheme"]: x for x in sim._scenarios(_ctx(None, zs))}
        return (m["역세권 활성화사업"]["est_far"], m["결합건축"]["est_far"])

    assert _axis(zones) != _axis(["제2종일반주거지역", "자연녹지지역"]), (
        f"상업 유무가 est_far·결합건축을 안 가른다 — com 축이 죽었다 "
        f"({_axis(zones)} vs {_axis(['제2종일반주거지역', '자연녹지지역'])})"
    )


def test_single_zone_site_without_zones_list_is_safe():
    """★`zone` 을 pool 에서 빼면 **`zones` 가 비어 있는 부지**가 무너진다.

    변이 실측: `_zone_pool` 을 `zones` 만으로 바꿔도 **SURVIVED** — `zones` 없는 ctx 를
    태우는 모집단이 없었다. 실제 호출부는 `zones` 를 항상 채우지만, 그 전제가 깨지면
    **단일 용도지역 부지가 통째로 「불가」** 가 된다.
    """
    sim = DevelopmentScenarioSimulator()
    got = {x["scheme"]: x["applicable"] for x in sim._scenarios(
        {**_ctx("제2종일반주거지역", []), "zones": []})}
    ok = [k for k, v in got.items() if v in ("가능", "조건부")]
    # ★느슨한 하한(`>= 20`·`>= 5`)은 변이를 못 잡았다 — pool 이 비어도 20종·12개는 남기 때문이다.
    #   실측값에 **결속**시킨다: `zone` 이 pool 에 있으면 21종·16개, 빠지면 20종·12개.
    assert (len(got), len(ok)) == (21, 16), (
        f"{len(got)}종·추진가능 {len(ok)}개 (기대 21·16) — "
        "`zones` 가 비었을 때 `zone` 이 pool 에서 빠지면 20·12 가 된다"
    )
    # ★음성 대조군 — pool 이 **정말로** 비면 갈려야 한다(단언이 공허하지 않음을 증명)
    empty = {x["scheme"]: x["applicable"] for x in sim._scenarios(
        {**_ctx(None, []), "zones": []})}
    assert (len(empty), len([1 for v in empty.values() if v in ("가능", "조건부")])) == (20, 12), (
        f"대조군이 예상과 다르다 — {len(empty)}종"
    )


def test_absent_code_is_wired_into_the_site_payload():
    """★계약 필드가 **응답에 실린다** — 만들어 놓고 안 실으면 검증기가 볼 것이 없다.

    변이 실측: `"primary_zone_absent"` 줄을 지워도 **SURVIVED** 였다.
    소스가 아니라 **AST 로 페이로드 딕트**를 본다(주석·문자열에 안 뚫리게).
    """
    import ast
    import inspect
    import pathlib

    src = pathlib.Path(inspect.getsourcefile(SS)).read_text(encoding="utf-8")
    with_zone = with_absent = 0
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.Dict):
            continue
        keys = {k.value for k in n.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "primary_zone" in keys and "zones" in keys:
            with_zone += 1
            if "primary_zone_absent" in keys:
                with_absent += 1
    assert with_zone >= 2, f"site 페이로드를 {with_zone}곳 찾았다 — 수집기 이상"
    assert with_absent == with_zone, (
        f"{with_zone}곳 중 {with_absent}곳만 `primary_zone_absent` 를 싣는다 — "
        "값이 None 인데 사유 코드가 없으면 `validate_withheld_pair` 가 계약 위반으로 잡는다"
    )
