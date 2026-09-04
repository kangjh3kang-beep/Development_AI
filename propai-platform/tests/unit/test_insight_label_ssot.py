"""인사이트 **표시명**이 백엔드 SSOT 에 있고, 사용자 산문에 **raw enum 이 새지 않게** 잠근다.

## 무엇이 있었나 (2026-08-25 라이브 실측)

「성장 분석」 화면에 이런 문장이 떠 있었다:

    "critical 인사이트(recurring_verify_error) — 사람 진단 필요."

백엔드가 **사용자에게 보이는 산문을 조립**하는데(`narrative`·`diagnosis`) 표시명을 몰라
**영문 enum 을 그대로 끼운** 것이다. 명시 분기는 2종(`error_cluster`·`heal_escalation`)뿐인데
카탈로그는 11종이라 **9종이 그 폴백으로 샜다.**

★프론트에 라벨표가 있어도 못 고친다 — 그 문장은 **백엔드가 만들어 저장**하고 프론트는
  그대로 렌더할 뿐이다. `#808` 이 세운 것은 **타입 목록** SSOT 였고 **표시명은 아니었다.**

## 여기서 잠그는 것

1. 카탈로그 타입에 **전부** 라벨이 있다(양방향 — 죽은 라벨도 막는다)
2. 모르는 타입은 **감추지 않고 원문 그대로** 나온다(새 타입 신호를 죽이지 않는다)
3. ★**사용자 산문에 raw 타입을 끼우는 자리가 새로 생기면 잡는다** — 두 곳을 고친 것으로
   끝내지 않는다. 목록이 아니라 **소스에서 파생**시킨다(사람이 센 목록은 상한이 된다).
"""

import re
from pathlib import Path

import pytest
from apps.api.app.services.growth.insight_types import (
    INSIGHT_LABELS,
    INSIGHT_TYPES,
    insight_label,
)

GROWTH = Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "services" / "growth"


def test_catalog_is_not_empty():
    """공허 진리 가드 — 카탈로그가 비면 아래 검사가 전부 통과한다."""
    assert len(INSIGHT_TYPES) >= 10, "카탈로그가 줄었다 — 아래 검사들이 공허해진다"
    assert len(INSIGHT_LABELS) >= 10, "라벨표가 줄었다"


def test_every_catalog_type_has_a_label():
    """★백엔드가 조립하는 문장에 영문 raw 가 나가지 않으려면 전 타입에 라벨이 있어야 한다."""
    missing = sorted(INSIGHT_TYPES - set(INSIGHT_LABELS))
    assert not missing, f"라벨 없는 타입(사용자 산문에 영문 raw 로 나간다): {missing}"


def test_no_ghost_labels():
    """★표에만 있고 카탈로그에 없는 라벨을 남기지 않는다(#808 이 프론트에서 겪은 그 형태)."""
    ghosts = sorted(set(INSIGHT_LABELS) - INSIGHT_TYPES)
    assert not ghosts, f"카탈로그에 없는 유령 라벨: {ghosts}"


def test_labels_are_korean_and_not_the_key_itself():
    """라벨 자리에 키를 그대로 넣어 '전부 라벨 있음'을 만들 수 있다 — 그 우회를 막는다."""
    for k, v in INSIGHT_LABELS.items():
        assert v != k, f"{k} 의 라벨이 키와 같다 — 라벨이 아니다"
        assert re.search(r"[가-힣]", v), f"{k} 의 라벨에 한글이 없다: {v!r}"


def test_unknown_type_is_not_hidden():
    """★모르는 타입을 '알 수 없음'으로 뭉개지 않는다 — 새 타입 신호가 사라진다."""
    assert insight_label("brand_new_kind") == "brand_new_kind"
    # 음성 짝 — 아는 타입은 실제로 번역된다(항상 원문을 돌려주는 구현을 배제).
    assert insight_label("recurring_verify_error") == "검증오류 재발"


def _prose_lines_interpolating_type() -> list[tuple[str, int, str]]:
    """`growth/` 안에서 **사용자 산문 f-string 에 타입 변수를 그대로 끼우는** 줄을 파생한다.

    ★목록을 손으로 적지 않는다 — 새로 생기면 자동으로 걸린다.
    ★주석은 걷어낸다(주석에 적은 예시가 위반으로 잡히지 않게 — 이 저장소가 여러 번 데인 형태).
    """
    hits: list[tuple[str, int, str]] = []
    pat = re.compile(r'return\s+f"[^"]*\{\s*(itype|t|insight_type)\s*\}')
    for f in sorted(GROWTH.glob("*.py")):
        for i, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = re.sub(r"(^|\s)#.*$", r"\1", raw)
            if pat.search(line):
                hits.append((f.name, i, raw.strip()))
    return hits


def test_sweep_finds_nothing_raw():
    """★두 곳을 고친 것으로 끝내지 않는다 — 새 누출이 생기면 여기서 잡힌다."""
    hits = _prose_lines_interpolating_type()
    assert not hits, (
        "사용자 산문에 raw 타입을 끼우는 자리가 있다 — `insight_label()` 을 경유하라:\n"
        + "\n".join(f"  {n}:{i}  {s}" for n, i, s in hits)
    )


def test_sweep_actually_detects(tmp_path, monkeypatch):
    """★대조군 — 이 스윕이 **정말 잡는지** 확인한다(전수 0건이 '검사기 사망'일 수 있다).

    실제 위반을 임시 파일로 만들어 같은 정규식에 태운다. 이 검사가 없으면
    `test_sweep_finds_nothing_raw` 는 정규식이 깨져도 초록이다.
    """
    pat = re.compile(r'return\s+f"[^"]*\{\s*(itype|t|insight_type)\s*\}')
    violating = '    return f"critical 인사이트({itype}) — 사람 진단 필요."'
    clean = '    return f"critical 인사이트({insight_label(itype)}) — 사람 진단 필요."'
    commented = '    # return f"critical 인사이트({itype}) — 예시"'
    assert pat.search(violating), "스윕 정규식이 실제 위반을 못 잡는다 — 검사기가 죽었다"
    assert not pat.search(clean), "교정된 형태를 위반으로 신고한다 — 위양성"
    stripped = re.sub(r"(^|\s)#.*$", r"\1", commented)
    assert not pat.search(stripped), "주석을 위반으로 신고한다 — 위양성"


@pytest.mark.parametrize("t", sorted(INSIGHT_TYPES))
def test_label_is_usable_in_prose(t):
    """전 타입이 문장에 끼워도 영문이 남지 않는다(파생형 — 새 타입이 자동으로 들어온다)."""
    s = f"critical 인사이트({insight_label(t)}) — 사람 진단 필요."
    assert t not in s, f"{t}: 산문에 영문 타입이 그대로 남는다"
