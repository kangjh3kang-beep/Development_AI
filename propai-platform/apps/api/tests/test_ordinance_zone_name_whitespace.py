"""조례 파서 — **용도지역명 공백 표기**를 읽는다(주거지역 전면 미독 봉합).

【무엇이 잘못돼 있었나 — 2026-08-28 라이브 실측】
조례 원문은 `제2종 일반주거지역`(띄어쓰기)을 쓰는데 표준 키는 `제2종일반주거지역`(무공백)이라,
`re.escape(zone)` 로 만든 패턴이 **주거지역을 통째로 못 읽었다**.
오산시 조례 원문 전수 — 공백형 **3건** / 무공백형 **0건**.

결과: 제2종·제3종이 `None` → 국가상한 폴백(250%)이 조례값(230%) 대신 나가 **20%p 과대계상**.
★그 250% 는 조례가 *"지구단위계획을 수립하는 경우"* 에만 주는 값인데, 같은 화면이
`지구단위계획 = 불가` 라고 말하고 있었다(두 결함이 서로를 가렸다).

【★픽스처가 실제 원문인 이유】
2026-08-19 세션이 같은 파서를 고치다 **커밋을 보류**했다 — *"값이 나왔지만 틀렸다"*
(자연녹지 bcr 30 ← 원문 20). 교훈: **값이 나온 것은 고쳐진 것이 아니다.**
그래서 합성 문자열이 아니라 **law.go.kr DRF 원문**(자치법규ID 2097518 · 시행 20260506)에서
제45조·제51조를 발췌해 픽스처로 쓰고, **조례 원문 값을 리터럴로 못 박는다**.
"""

from pathlib import Path

import pytest

from app.services.land_intelligence.ordinance_service import (
    OrdinanceService,
    _flex_zone_pattern,
)

# ★**전문**을 쓴다. 처음엔 제45·51조만 발췌했더니 정답 문자열이 있는데도 파서가 `None` 을
#   냈다 — 파서가 섹션 경계·상호참조 앵커 등 **문서 구조**에 의존하기 때문이다.
#   발췌를 손보는 것은 파서가 아니라 **내 픽스처를 맞추는 일**이라 원문을 그대로 둔다.
FIXTURE = Path(__file__).parent / "fixtures" / "osan_ordinance_full.xml"

# ★조례 원문 값 — 코드에서 파생시키지 않고 리터럴로 못 박는다(자기참조 단언 금지).
#   오산시 도시계획 조례 제45조①(건폐율)·제51조①(용적률).
ORDINANCE_TRUTH = {
    "제2종일반주거지역": (60, 230),   # §45①4호 · §51①4호(단, 지구단위계획 수립 시 250)
    "제3종일반주거지역": (50, 280),   # §45①5호 · §51①5호
    "자연녹지지역": (20, 100),        # §45①16호 · §51①
}


@pytest.fixture(scope="module")
def text() -> str:
    assert FIXTURE.exists(), f"픽스처 없음: {FIXTURE}"
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def svc() -> OrdinanceService:
    return OrdinanceService()


def test_fixture_uses_spaced_notation_not_synthetic(text: str) -> None:
    """★공허 방지 — 픽스처가 **문제의 표기**를 실제로 담고 있어야 이 테스트가 의미를 갖는다."""
    assert text.count("제2종 일반주거지역") >= 1, "공백 표기가 픽스처에 없다 — 결함을 재현 못 한다"
    assert text.count("제2종일반주거지역") == 0, "무공백 표기가 섞였다 — 원문이 아니다"


@pytest.mark.parametrize("zone", sorted(ORDINANCE_TRUTH))
def test_parses_ordinance_truth_for_every_zone(svc: OrdinanceService, text: str, zone: str) -> None:
    """탐지 + 특이도 — 공백형(주거)은 **새로** 읽히고, 무공백형(녹지)은 **종전과 같다**."""
    got = svc._parse_bcr_far_from_text(text, zone, "오산시")
    assert got is not None, f"{zone} 파싱 실패 — 공백 표기를 못 읽는다"
    want_bcr, want_far = ORDINANCE_TRUTH[zone]
    assert (got.get("bcr"), got.get("far")) == (want_bcr, want_far), (
        f"{zone}: 조례 원문은 bcr={want_bcr} far={want_far} 인데 "
        f"파서가 bcr={got.get('bcr')} far={got.get('far')} 를 냈다"
    )


def test_unknown_zone_stays_none(svc: OrdinanceService, text: str) -> None:
    """★두 번째 모집단 — 공백 허용이 **과잉 매칭**으로 번지지 않는다(없는 용도지역은 None)."""
    assert svc._parse_bcr_far_from_text(text, "제9종상상지역", "오산시") is None


def test_flex_pattern_is_superset_of_exact(svc: OrdinanceService) -> None:
    """★무회귀의 근거 — `\\s*` 는 공백만 매칭하므로 **무공백 표기도 그대로** 잡힌다."""
    import re

    pat = _flex_zone_pattern("제2종일반주거지역")
    assert re.search(pat, "4. 제2종일반주거지역: 230퍼센트 이하"), "무공백 표기를 놓쳤다(회귀)"
    assert re.search(pat, "4. 제2종 일반주거지역: 230퍼센트 이하"), "공백 표기를 놓쳤다"
    # 공백만 허용한다 — 사이에 **다른 문자**가 끼면 매칭되면 안 된다(과잉 일반화 방지).
    assert not re.search(pat, "제2종XX일반주거지역"), "공백 아닌 문자를 넘어 매칭했다"


def test_anchor_path_also_reads_spaced_names(svc: OrdinanceService) -> None:
    """★두 번째 소비처 — `_iter_zone_fragments`(앵커)도 공백 표기를 읽는다.

    ★왜 별도 락인가(변이 실측): 공백 허용 헬퍼를 **두 곳**(기본항 `head` · 앵커 `alt`)에
    적용했는데, 처음엔 기본항만 태우는 락뿐이라 **앵커를 `re.escape` 로 되돌리는 변이가
    SURVIVED** 했다. 한 헬퍼를 여러 곳이 쓰면 **소비처마다** 잠가야 한다.
    """
    seg = "4. 제2종 일반주거지역: 230퍼센트 이하 5. 제3종 일반주거지역: 280퍼센트 이하"
    names = [f[0] for f in svc._iter_zone_fragments(seg)]
    assert len(names) == 2, f"공백 표기 조각을 놓쳤다: {names}"
    assert any("제2종" in n and "일반주거지역" in n for n in names), names
    assert any("제3종" in n and "일반주거지역" in n for n in names), names


def test_anchor_path_unchanged_for_unspaced(svc: OrdinanceService) -> None:
    """★특이도 — 무공백 표기 앵커는 **종전과 같이** 잡힌다(상위집합 = 무회귀)."""
    seg = "4. 제2종일반주거지역: 230퍼센트 이하 16. 자연녹지지역: 20퍼센트 이하"
    names = [f[0] for f in svc._iter_zone_fragments(seg)]
    assert len(names) == 2, f"무공백 표기가 회귀했다: {names}"
