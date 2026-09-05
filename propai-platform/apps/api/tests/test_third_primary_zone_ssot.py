"""**세 번째 「주용도지역」 구현**을 면적가중 SSOT 로 정렬한다.

## 무엇이 잘못돼 있었나 (2026-09-05 · 두 함수 직접 실행)

`integrated_recommender._primary_zone` 은 **최대 필지 argmax** 였고, 형제는
**용도지역별 면적 합산 + 330㎡ 이하 흡수**(`mixed_zone_limits` · 국토계획법 §84·시행령 §94)다.
**5케이스 중 2케이스에서 갈렸다**:

    [제2종 400, 제2종 400, 상업 500]  →  SSOT=제2종일반주거지역 / 구판=일반상업지역
    [제2종 300, 제2종 300, 상업 400]  →  SSOT=제2종일반주거지역 / 구판=일반상업지역

★**주거 면적이 합계로 더 큰 부지를 「상업」이라 말했다.** 그 값은 `get_permitted_types`
(**허용 용도**)·`_baseline_far`(**용적률**)·★**LLM 프롬프트**로 간다.

★**법적 근거는 SSOT 쪽에만 있다.** argmax 는 근거 문구가 없다.
★`premise_audit` 의 `path_invariance_zone` 이 잡으려던 결함인데, 그 감사기는
**이 경로에 배선돼 있지 않다**(호출부는 시뮬레이터·auto_zoning 둘뿐).
"""
from __future__ import annotations

import pathlib

import pytest

from app.services.development.integrated_recommender.orchestrator import IntegratedRecommender
from app.services.development.scenario_simulator import dominant_zone_by_area

_P = IntegratedRecommender._primary_zone


def _parcels(rows):
    return [{"zone_type": z, "land_area_sqm": a} for z, a in rows]


def _legacy_argmax(parcels):
    """★**구판 알고리즘을 재현**한다 — 그래야 「고쳤다」가 의미를 갖는다.

    이것이 없으면 *"SSOT 와 같다"* 는 단언이 **처음부터 같았을 수도 있는** 공허한 참이 된다.
    """
    with_zone = [p for p in parcels if p.get("zone_type")]
    if not with_zone:
        return ""
    return max(with_zone, key=lambda p: (p.get("land_area_sqm") or 0)).get("zone_type") or ""


#: ★**갈리던 케이스** — 이 픽스처가 비면 아래 단언이 전부 공허해진다.
DIVERGED = [
    [("제2종일반주거지역", 400), ("제2종일반주거지역", 400), ("일반상업지역", 500)],
    [("제2종일반주거지역", 300), ("제2종일반주거지역", 300), ("일반상업지역", 400)],
]
#: 우연히 같던 케이스 — **회귀가 아니라는 근거**.
UNCHANGED = [
    [("제2종일반주거지역", 1000)],
    [("제2종일반주거지역", 500), ("일반상업지역", 500)],
    [("제2종일반주거지역", 5000), ("자연녹지지역", 300)],
]


@pytest.mark.parametrize("rows", DIVERGED)
def test_갈리던_케이스가_SSOT_답으로_뒤집혔다(rows):
    """★**두 모집단을 같은 실행에서** — 구판과 다르고, SSOT 와 같다."""
    parcels = _parcels(rows)
    zone, basis = _P(parcels)
    legacy = _legacy_argmax(parcels)
    ssot, ssot_basis = dominant_zone_by_area([{"zone": z, "area": a} for z, a in rows])

    # ★이 픽스처가 **실제로 갈리는 입력**임을 먼저 증명한다(공허 진리 방지).
    assert legacy != ssot, f"픽스처가 두 알고리즘을 안 가른다: legacy={legacy!r} ssot={ssot!r}"
    assert zone == ssot, f"SSOT 와 다른 답을 냈다: {zone!r} != {ssot!r}"
    assert zone != legacy, "구판 답이 그대로다 — 대체가 안 됐다"
    assert basis == ssot_basis


@pytest.mark.parametrize("rows", UNCHANGED)
def test_우연히_같던_케이스는_그대로다_회귀_아님의_근거(rows):
    parcels = _parcels(rows)
    zone, _ = _P(parcels)
    assert zone == _legacy_argmax(parcels), "종전과 같아야 하는 케이스가 바뀌었다"


def test_전_구현이_SSOT_와_항상_일치한다_파생형():
    """★**조합 전수** — 손으로 고른 케이스가 상한이 되지 않게 한다."""
    import itertools
    zones = ["제2종일반주거지역", "일반상업지역", "자연녹지지역"]
    areas = [200, 330, 400, 1000]
    checked = 0
    for n in (1, 2, 3):
        for combo in itertools.product(itertools.product(zones, areas), repeat=n):
            rows = list(combo)
            zone, basis = _P(_parcels(rows))
            ssot, ssot_basis = dominant_zone_by_area([{"zone": z, "area": a} for z, a in rows])
            assert (zone, basis) == (ssot, ssot_basis), f"{rows}: {zone!r} != {ssot!r}"
            checked += 1
    # ★공허 진리 방지 — 조합이 0이면 위 루프가 0회 돈다.
    assert checked >= 100, f"조합 {checked}건뿐 — 판정 거부"


def test_basis_를_버리지_않는다():
    """★이 세션이 **세 번 고친** 결함이 *"생산자가 사유를 내는데 소비처가 안 읽는다"* 였다."""
    zone, basis = _P(_parcels([("제2종일반주거지역", 400), ("일반상업지역", 500)]))
    assert basis, "근거를 안 낸다"
    # ★닫힌 토큰 — 어휘 밖 값이면 소비처가 해석할 수 없다.
    assert basis in {"area_weighted", "single_zone", "first_parcel_no_area", "none"}


def test_응답이_basis_를_실제로_싣는다_배선층():
    """★**함수 반환만 잠그면 응답 배선은 무잠금**이다 — 내 변이가 그것을 잡았다.

    *"basis 를 버리지 않는다"* 라고 써 놓고 **응답 조립을 안 잠갔다.**
    `"primary_zone_basis"` 줄을 지우는 변이가 **SURVIVED** 했다
    — 이 세션이 반복해서 만난 **배선 무잠금**이다.

    ★`ast` 로 판정한다 — 주석·문자열에 원리적으로 안 뚫린다.
    ★그리고 **키가 있다**가 아니라 **그 키에 `primary_zone_basis` 값이 실린다**를 본다
      («이름이 있다» 와 «값이 실린다» 는 다른 단언이다).
    """
    import ast

    src = pathlib.Path(
        "app/services/development/integrated_recommender/orchestrator.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        if "primary_zone" not in keys:
            continue
        found.append(keys)
        # ★그 dict 안에서 basis 키의 **값**이 무엇인지 본다.
        pair = {
            k.value: v for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant)
        }
        assert "primary_zone_basis" in pair, (
            "응답에 primary_zone 은 싣는데 **근거(basis)를 버린다** — "
            "생산자가 사유를 내는데 소비처가 안 읽는 그 결함이다."
        )
        val = pair["primary_zone_basis"]
        assert isinstance(val, ast.Name) and val.id == "primary_zone_basis", (
            f"basis 키에 엉뚱한 값이 실린다: {ast.dump(val)[:80]} — "
            "«키가 있다» 와 «값이 실린다» 는 다른 단언이다."
        )
    # ★공허 진리 방지 — dict 를 하나도 못 찾으면 위 루프가 0회 돈다.
    assert found, "primary_zone 을 싣는 응답 dict 를 못 찾았다 — 판정 거부"


def test_빈_입력은_빈_문자열과_none_을_낸다_경계():
    assert _P([]) == ("", "none")
    assert _P([{"zone_type": None, "land_area_sqm": 100}]) == ("", "none")


# ★부채를 초록 안에 드러낸다.
#   ① `premise_audit` 의 `path_invariance_zone` 이 **이 경로에 배선돼 있지 않다**
#      (호출부는 `scenario_simulator`·`routers/auto_zoning` 둘뿐) — 두 경로가 갈려도 아무도 안 잡는다.
#   ② **보류(mixed_review)** 는 `#972`(다른 세션)가 형제 쪽에 넣는 중이라 여기서 같이 하지 않았다.
def test_todo_감사기를_이_경로에도_배선한다():
    pytest.skip("★부채: path_invariance_zone 이 integrated_recommender 경로에 미배선(별건)")
