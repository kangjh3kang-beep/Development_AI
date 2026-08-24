"""효과기 도달범위 표가 **코드와 어긋나지 않게** 잠근다.

## 이 표가 왜 위험한가

이런 표는 **쓰는 순간부터 낡는다.** 누군가 효과기를 새로 만들거나 소비처를 연결해도
표는 가만히 있고, 다음 사람은 그 표를 **사실로 읽는다**. 그러면 정직하려고 만든 문서가
거짓말을 하는 장치가 된다 — 이 저장소가 반복해서 데인 형태다.

그래서 여기서 잠그는 것은 표의 **내용**이 아니라 표와 코드의 **일치**다:

· 코드에 있는 액션 상수가 표에 **전부** 있는가(새 효과기가 조용히 안 들어오게)
· 표에 있는 키가 코드에 **실재**하는가(죽은 항목 방지)
· `PRODUCT` 로 적힌 것이 정말 성장엔진 **밖에서** 읽히는가(낙관적 표기 방지)
· `NONE`/`SELF` 로 적힌 것에 **무엇이 빠졌는지**가 적혀 있는가
"""

import re
from pathlib import Path

import pytest

from apps.api.app.services.growth.effector_reach import (
    EFFECTORS,
    Reach,
    by_reach,
    product_reaching_count,
)

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
GROWTH = API_ROOT / "app" / "services" / "growth"


def _action_constants() -> set[str]:
    """코드가 선언한 액션 상수 값을 **파생**시킨다(사람이 센 목록이 상한이 되지 않게)."""
    found: set[str] = set()
    for name in ("heal_actions.py", "feature_flags.py"):
        src = (GROWTH / name).read_text(encoding="utf-8")
        # ACTION_XXX = "value" 형태만 — 주석·문자열 본문은 잡지 않는다.
        for m in re.finditer(r'^ACTION_[A-Z_]+\s*=\s*"([a-z_]+)"', src, re.M):
            found.add(m.group(1))
    return found


def test_table_is_not_empty():
    """공허 진리 가드 — 표가 비면 아래 검사가 전부 통과한다."""
    assert len(EFFECTORS) >= 7, "효과기 표가 줄었다 — 아래 검사들이 공허해진다"


def test_every_action_constant_is_in_the_table():
    """★새 효과기가 표를 거치지 않고 들어오면 잡는다."""
    declared = _action_constants()
    assert declared, "액션 상수를 하나도 못 찾았다 — 정규식·경로가 깨졌다(0건은 부재가 아니다)"
    listed = {e.key for e in EFFECTORS}
    missing = declared - listed
    assert not missing, (
        f"코드에 있는 효과기가 표에 없다: {sorted(missing)} — "
        "도달범위를 적지 않으면 다음 사람이 '배선 완결'로 오독한다"
    )


def test_no_dead_rows():
    """★표에만 있고 코드에 없는 항목을 남기지 않는다."""
    declared = _action_constants()
    listed = {e.key for e in EFFECTORS}
    stale = listed - declared
    assert not stale, f"표에만 있는 죽은 항목: {sorted(stale)} — 지워라"


@pytest.mark.parametrize("eff", EFFECTORS, ids=lambda e: e.key)
def test_every_row_carries_evidence(eff):
    """근거 없는 판정을 막는다 — 다음 사람이 **재볼 수 있어야** 한다."""
    assert len(eff.evidence) > 40, f"{eff.key} 의 근거가 너무 짧다"


@pytest.mark.parametrize(
    "eff", [e for e in EFFECTORS if e.reach is not Reach.PRODUCT], ids=lambda e: e.key
)
def test_non_product_rows_say_what_is_missing(eff):
    """★'안 닿는다'만 적고 끝내지 않는다 — 무엇이 있어야 닿는지까지 적는다."""
    assert len(eff.missing) > 10, f"{eff.key} 에 '무엇이 빠졌는지'가 없다"


def test_product_rows_are_actually_read_outside_growth():
    """★낙관적 표기 방지 — `PRODUCT` 는 성장엔진 **밖**에 독자가 있어야 한다.

    이 검사가 없으면 누군가 `reach` 를 PRODUCT 로 바꿔 적기만 해도 표가 좋아 보인다.
    """
    product = by_reach(Reach.PRODUCT)
    assert product, "PRODUCT 가 하나도 없다 — 이 검사가 공허해진다(전제)"

    outside = list(API_ROOT.rglob("*.py"))
    assert len(outside) > 50, "소스 수집이 비었다 — 경로가 깨졌다"

    for key in product:
        readers = [
            p
            for p in outside
            if ".venv" not in p.parts
            and "services/growth" not in p.as_posix()
            and "tests" not in p.parts
            and key in p.read_text(encoding="utf-8", errors="ignore")
        ]
        assert readers, (
            f"{key} 는 PRODUCT 로 적혀 있는데 성장엔진 밖에서 아무도 안 읽는다 — "
            "표가 낙관적이다"
        )


def test_current_reach_is_recorded_honestly():
    """★지금 상태를 **숫자로** 못박는다.

    이 숫자가 **늘어나면** 표를 고쳐야 하고(좋은 방향), **줄어들면** 회귀다.
    어느 쪽이든 이 테스트가 먼저 말한다 — 조용히 바뀌지 않게.
    """
    assert product_reaching_count() == 1, (
        "제품에 닿는 효과기 수가 바뀌었다 — effector_reach 표를 실측으로 갱신하라"
    )
    assert set(by_reach(Reach.PRODUCT)) == {"threshold_relax"}
    # ★음성 짝 — 안 닿는 것들도 같은 실행에서 확인한다(부재 단언 혼자 두지 않는다).
    assert set(by_reach(Reach.SELF)) == {"threshold_autotune", "feature_toggle"}
    assert set(by_reach(Reach.NONE)) == {
        "cache_warm",
        "stale_reanalysis",
        "circuit_observe",
        "prompt_ab_adopt",
    }
