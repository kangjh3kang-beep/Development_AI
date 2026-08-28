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
    # ★**키를 못 박는다.** 처음엔 `any("제2종" in n …)` 로 썼는데 그것은 표준명이든 공백형이든
    #   통과하는 단언이라, 앵커가 **매칭 텍스트를 그대로 키로 쓰는 회귀**(유령 키)를
    #   그대로 통과시켰다(독립 리뷰가 변이로 적발 — 정정을 넣어도 초록이었다).
    #   조각 키는 **반드시 표준명**이어야 한다: 그래야 `value_basis=="base_item"` 게이트가
    #   같은 딕셔너리를 보고 완화값이 기본항을 덮어쓰는 것을 막는다.
    assert names == ["제2종일반주거지역", "제3종일반주거지역"], (
        f"조각 키가 표준명이 아니다 — 유령 키가 생겼다: {names}"
    )


def test_anchor_path_unchanged_for_unspaced(svc: OrdinanceService) -> None:
    """★특이도 — 무공백 표기 앵커는 **종전과 같이** 잡힌다(상위집합 = 무회귀)."""
    seg = "4. 제2종일반주거지역: 230퍼센트 이하 16. 자연녹지지역: 20퍼센트 이하"
    names = [f[0] for f in svc._iter_zone_fragments(seg)]
    assert names == ["제2종일반주거지역", "자연녹지지역"], f"무공백 표기가 회귀했다: {names}"


def test_pattern_does_not_cross_line_breaks() -> None:
    """줄바꿈은 넘지 않는다 — **방어적 경화**(도달 가능 경로에서는 미실증).

    ★정직 표기(독립 리뷰 지적): 소비처가 받는 `section` 은 `_locate_section` 이
    `_normalize_ws`(`\\s+`→단일 공백)로 접은 문자열이라 **개행이 도달하지 않는다**
    (실측: 오산 섹션 4,207자에 개행 0건). 내가 잰 *"매칭 수 21개 전부 동일"* 이 이미
    그 사실을 말하고 있었는데 인과 주장으로 잘못 적었다.
    즉 이 락은 *"지금 나는 결함"* 이 아니라 그 성질이 우연히 넓어지는 것을 막는다 —
    조이는 비용이 0 이므로 유지한다.
    """
    import re

    pat = _flex_zone_pattern("농림지역")
    assert re.search(pat, "농림지역"), "무공백 표기를 놓쳤다"
    assert re.search(pat, "농 림지역"), "같은 줄 공백을 놓쳤다"
    assert re.search(pat, "농　림지역"), "전각공백을 놓쳤다(다른 지자체 대비)"
    # ★핵심 — 줄을 넘으면 **매칭되면 안 된다**.
    assert not re.search(pat, "농\n림지역"), "줄바꿈을 넘어 매칭했다 — 가짜 용도지역을 만든다"
    assert not re.search(pat, "…농\n   림지역…"), "들여쓰기된 다음 줄과 이어 붙었다"


def test_real_document_unaffected_by_the_tightening(svc: OrdinanceService, text: str) -> None:
    """★특이도 — 조이고 나서도 **실제 원문 결과가 그대로**여야 한다(회귀 0의 근거)."""
    for zone, (want_bcr, want_far) in ORDINANCE_TRUTH.items():
        got = svc._parse_bcr_far_from_text(text, zone, "오산시")
        assert got is not None and (got.get("bcr"), got.get("far")) == (want_bcr, want_far), (
            f"{zone}: 줄바꿈 배제 후 값이 달라졌다 → {got}"
        )


def test_fragment_only_path_resolves_to_canonical(svc: OrdinanceService) -> None:
    """★번호(`NN.`) 없는 **조각 전용** 문서에서도 표준명으로 해소된다.

    기본항 추출이 비면 유일한 키가 조각 키다. 그것이 공백형이면 표준명 요청과
    매칭되지 않아 **값 230 을 읽어 놓고 버리고** 국가상한 폴백이 나간다
    (독립 리뷰가 이 경로를 별건으로 지적했다 — 오산 픽스처는 번호형이라 안 걸린다).
    """
    sec = "용도지역에서의 용적률 제2종 일반주거지역 230퍼센트 이하 자연녹지지역 100퍼센트 이하"
    assert svc._extract_base_items(sec) == {}, "이 픽스처는 기본항이 비어야 조각 경로를 태운다"
    keys = {f[0] for f in svc._iter_zone_fragments(sec)}
    assert keys == {"제2종일반주거지역", "자연녹지지역"}, keys
    assert svc._match_requested_zone("제2종일반주거지역", keys) == "제2종일반주거지역"
