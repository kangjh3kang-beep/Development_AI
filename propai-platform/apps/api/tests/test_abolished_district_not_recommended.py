"""**폐지된 제도를 「추진 가능」으로 권하지 않는다** — 입지규제최소구역 → 도시혁신구역.

## 무엇이 잘못돼 있었나

`#940` 이 이 시나리오를 「불가 → 조건부」로 **승격**시켰다(당시 게이트 축이 틀렸으므로 승격
자체는 옳았다). **그런데 제도 자체가 그 사이 폐지됐다** — 승격만 하고 라벨을 안 고친 조합이다.

★**법제처 DRF 원문 직접 조회**(2026-09-05 · `lawService.do?OC=test&target=law&ID=009294`
· 699,281B · 법령명 「국토의 계획 및 이용에 관한 법률」 일치 확인):

    제40조의2 → **삭제**
    제40조의3 → **도시혁신구역**        (시행 20260701)

★볼트 기록을 **승계하지 않고 원문으로 다시 확인**했다 — 법령은 기록이 가장 빨리 낡는 축이다.

## 왜 「불가」보다 나쁜가

존재하지 않는 제도를 **추진 가능한 사업방식으로 제안**하고, 다른 시나리오의 **대체안으로도
권했다**. 사용자가 그것을 근거로 인허가를 준비하면 **헛걸음이고 그 비용은 되돌릴 수 없다.**

★**시나리오를 지우지 않는다** — 제도는 **승계**됐지 없어진 것이 아니다.
"""
from __future__ import annotations

import pytest

from app.services.development.scenario_simulator import (
    SPECIAL_ZONE_SCHEME,
    DevelopmentScenarioSimulator,
)

_SIM = DevelopmentScenarioSimulator()

#: ★**독립 리터럴** — 소스 상수에서 파생시키지 않는다. 상수를 옛 이름으로 되돌려도
#:   자기 상수를 단언하는 락은 초록이다(이 세션이 실측한 형태).
ABOLISHED = "입지규제최소구역"
SUCCESSOR = "도시혁신구역"


def _ctx(zone="일반상업지역", area=12000, station=True, region="서울특별시"):
    return {
        "primary_zone": zone, "zones": [zone] if zone else [],
        "total_area_sqm": area, "area": area, "parcel_count": 3,
        "region": region, "multi": True, "integration_feasible": True,
        # ★**프로덕션이 쓰는 키**를 쓴다. 직전 PR 의 적대 리뷰가 *"픽스처의 `far` 키는
        #   `_scenarios()` 가 안 읽으므로 그 축이 통째로 죽어 있다"* 를 지적했는데(L-1),
        #   내가 이 파일에서 **그대로 재현**했고 `est_far` 단언이 **첫 실행에서 잡았다**.
        #   ★*"픽스처는 생산자가 실제로 만드는 모양인가"* — 이 세션의 반복 자문이다.
        "far_effective_blended": 250, "far_legal_blended": 250,
        "bcr": 60, "near_station": station, "near_station_m": 300,
        "buildings": {}, "block_aging": {"oldest_age": 30},
    }


def _all_text(rows) -> str:
    """★시나리오의 **모든 사람이 읽는 필드**를 잇는다 — 한 필드만 보면 다른 필드로 샌다."""
    out = []
    for r in rows:
        out.append(str(r.get("scheme") or ""))
        out.append(str(r.get("notes") or ""))
        for key in ("requirements", "pros", "cons", "buildable_types"):
            out.extend(str(x) for x in (r.get(key) or []))
    return "\n".join(out)


@pytest.mark.parametrize(
    ("zone", "area", "station", "region"),
    [
        ("일반상업지역", 12000, True, "서울특별시"),      # 조건부 경로
        ("일반상업지역", 800, True, "서울특별시"),        # 불가 경로(면적 미달)
        ("제2종일반주거지역", 12000, False, "서울특별시"),  # 역세권 미발화
        ("", 12000, True, "서울특별시"),                 # 용도지역 미확보
        # ★★**대체안 안내문 경로** — 이것이 빠져 있었고, 그래서 「대체안 문구만 되돌리는」
        #   변이가 **SURVIVED** 했다(내가 «형제 미스윕 방지» 라고 이름 붙인 바로 그 축인데
        #   픽스처가 그 경로를 **원리적으로 못 태웠다**).
        #   실측: 대체안은 **비서울 + 역세권** 에서만 발화한다(서울은 제도가 적용되므로).
        ("일반상업지역", 12000, True, "경기도 성남시"),
        ("제2종일반주거지역", 12000, True, "부산광역시"),
    ],
)
def test_폐지된_제도명이_응답_어디에도_없다_파생형(zone, area, station, region):
    """★**파생형 전수** — `scheme` 하나만 보면 `notes`·`cons` 로 샌다.

    실제로 `#940` 은 본 시나리오만 보고 **대체안 안내문에 남은 옛 이름을 놓쳤다**(형제 미스윕).
    """
    rows = _SIM._scenarios(_ctx(zone, area, station, region))
    assert rows, "시나리오가 0종 — 판정 거부(공허 진리 방지)"
    text = _all_text(rows)
    # ★승계 고지는 **예외**다 — 옛 이름으로 검색한 사용자를 위해 일부러 남긴다.
    without_notice = "\n".join(
        ln for ln in text.splitlines() if "승계" not in ln and "삭제되고" not in ln
    )
    assert ABOLISHED not in without_notice, (
        f"폐지된 제도명이 남아 있다(zone={zone!r} area={area} station={station} region={region!r}) — "
        "승계 고지 밖에서 그 이름이 나오면 사용자는 **추진 가능한 제도**로 읽는다."
    )


def test_대체안_안내문_경로가_실제로_발화한다_공허진리_가드():
    """★위 파생형 검사가 **그 경로를 실제로 태웠는지** 따로 증명한다.

    첫 판은 픽스처 4종이 전부 `region="서울특별시"` 라 **대체안 안내문이 한 번도 렌더되지
    않았다.** 그래서 그 문구만 되돌리는 변이가 **SURVIVED** 했다 —
    ***검사는 있는데 대상이 없어 통과하는 공허한 그린***(이 저장소가 4회 이상 겪은 형태).
    실측: 대체안은 **비서울 + 역세권** 에서만 발화한다.
    """
    rows = _SIM._scenarios(_ctx(region="경기도 성남시", station=True))
    alts = [r for r in rows if "대체:" in (r.get("notes") or "")]
    assert alts, "대체안 안내문이 렌더되지 않았다 — 위 파생형 검사가 이 경로를 못 태운다"
    # ★진짜 계약 — **어느 대체안도 폐지 제도를 권하지 않는다**(전수).
    for r in alts:
        assert ABOLISHED not in (r.get("notes") or ""), (
            f"{r['scheme']}: 대체안으로 **폐지된 제도**를 권한다 — {r.get('notes')!r}"
        )
    # ★그리고 **후속 제도가 대체안 목록에서 사라지지 않았다**(한쪽만 보면 «그냥 지웠다» 도 만점).
    #   ★단 **모든** 대체안이 그것을 담아야 하는 것은 아니다 — 시프트는 자기 대체 목록이 따로다.
    #   실측으로 확인한 대상만 단언한다(과잉 단언은 정상 코드를 막는다).
    with_successor = [r for r in alts if SUCCESSOR in (r.get("notes") or "")]
    assert with_successor, f"후속 제도를 대체안에서 통째로 뺐다: {[r['scheme'] for r in alts]}"


def test_법령참조_레지스트리가_시나리오명과_결속된다():
    """★레지스트리 키만 되돌리는 변이가 **SURVIVED** 했다 — 소비처를 안 태웠다.

    `SCHEME_*` 매핑의 키가 시나리오명과 어긋나면 **법령 근거가 조용히 안 붙는다**
    (조회 실패가 아니라 **키 미스**라 예외도 안 난다). ★**파생형**으로 잠근다 —
    레지스트리에 등록된 이름은 **실제로 생성되는 시나리오명 집합 안**에 있어야 한다.
    """
    from app.services.development import scenario_simulator as _ss

    registry = next(
        v for k, v in vars(_ss).items()
        if isinstance(v, dict) and "단순 건축" in v and isinstance(v.get("단순 건축"), list)
    )
    assert ABOLISHED not in registry, "레지스트리에 폐지된 제도명이 남아 있다"
    assert SUCCESSOR in registry, "레지스트리에 후속 제도명이 없다"

    # ★**결속** — 등록된 이름이 실제 시나리오명과 맞는지(오타·개명 드리프트 차단).
    produced = {r["scheme"] for r in _SIM._scenarios(_ctx())}
    assert SUCCESSOR in produced, "레지스트리 이름이 실제 시나리오명과 다르다"


def test_후속_제도명이_실제로_나온다_두_모집단():
    """★한쪽만 단언하면 «그냥 지웠다» 도 만점을 받는다 — **제도는 승계됐지 없어지지 않았다.**"""
    rows = _SIM._scenarios(_ctx())
    schemes = [r["scheme"] for r in rows]
    assert SUCCESSOR in schemes, f"후속 제도가 목록에서 사라졌다: {schemes}"
    assert ABOLISHED not in schemes
    # ★소스 상수가 **독립 리터럴과 같은가** — 자기 상수 단언을 피한다.
    assert SPECIAL_ZONE_SCHEME == SUCCESSOR, "상수가 조용히 바뀌었다"


def test_승계_사실을_고지한다_옛_이름_검색자를_위해():
    """★그냥 이름만 바꾸면 *"전에 되던 것이 왜 없어졌나"* 가 된다 — **승계**를 말한다."""
    rows = _SIM._scenarios(_ctx())
    target = next(r for r in rows if r["scheme"] == SUCCESSOR)
    note = target.get("notes") or ""
    assert ABOLISHED in note, "옛 이름이 승계 고지에 없다 — 검색한 사용자가 길을 잃는다"
    assert "40의2" in note or "§40의2" in note, "삭제된 조문 근거가 없다"
    assert "40의3" in note or "§40의3" in note, "승계 조문 근거가 없다"


def test_판정_로직은_안_바뀌었다_회귀_아님의_근거():
    """★**제도명만 바꿨다**는 근거 — 개수·판정값·용적률이 그대로다."""
    rows = _SIM._scenarios(_ctx())
    target = next(r for r in rows if r["scheme"] == SUCCESSOR)
    assert target["applicable"] == "조건부"
    assert target["est_far"] == 250 * 1.5
    assert target["contribution_pct"] == 30
    # 면적 미달이면 여전히 불가(조건 불변)
    small = _SIM._scenarios(_ctx(area=800))
    t2 = next(r for r in small if r["scheme"] == SUCCESSOR)
    assert t2["applicable"] == "불가"


def test_시나리오_개수가_불변이다():
    """★제도를 **지운 것이 아니라 승계**했다 — 개수가 줄면 그건 다른 변경이다."""
    rows = _SIM._scenarios(_ctx())
    assert len([r for r in rows if r["scheme"] == SUCCESSOR]) == 1, "중복 또는 소실"


# ★부채를 초록 안에 드러낸다.
#   **도시혁신구역의 지정 요건**(면적·입지)이 입지규제최소구역과 같은지 **미확인**이다 —
#   §40의3 전문과 시행령을 안 읽었다. 그래서 판정 조건(`area>=5000 and (station or com)`)을
#   **그대로 뒀다**. ★조건을 지어내는 것이 이름을 안 고치는 것보다 나쁘다.
def test_todo_도시혁신구역_지정요건_원문_확인():
    pytest.skip("★부채: §40의3 전문·시행령 미독 — 판정 조건이 승계 제도에 맞는지 미확인(지어내지 않음)")
