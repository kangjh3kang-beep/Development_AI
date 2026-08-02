"""시군구 힌트 추출 골든 — 지오코딩 질의의 **정확성**을 좌우하는 한 줄.

## 배경 (2026-08-02 실측)

VWorld 는 시군구가 틀리면 **정확히 실패**한다:
    "강남구 대치동 316" → OK  /  "서초구 대치동 316" → FAIL  /  "송파구 …" → FAIL

그런데 힌트가 `" ".join(parts[:2])` 였다. 3레벨 시군구가 통째로 잘린다:
    "경상북도 포항시 남구 …" → "경상북도 포항시"  (남구 소실)

성남시 분당구·수원시 영통구·창원시 의창구·고양시 덕양구·천안시 서북구·전주시 완산구 …
특례시와 행정시가 **전부** 같은 방식으로 깨졌다. 호미곶 전 카테고리 `located=0` 의 유력 원인.

## 이 골든이 잠그는 것

토큰 수를 세는 방식으로 되돌아가면 즉시 실패한다. 기대값은 **문자열 리터럴**로 박는다
(입력에서 파생하면 항등식이 되어 아무것도 못 잡는다).
"""

from __future__ import annotations

import pytest

from apps.api.routers.auto_zoning import _sigungu_hint_from_address


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        # ★3레벨 — 종전 구현이 전부 틀렸던 케이스
        ("경상북도 포항시 남구 호미곶면 대보리 산1-1", "경상북도 포항시 남구"),
        ("경기도 성남시 분당구 정자동 178", "경기도 성남시 분당구"),
        ("경기도 수원시 영통구 매탄동 1", "경기도 수원시 영통구"),
        ("경상남도 창원시 의창구 팔용동 100", "경상남도 창원시 의창구"),
        ("충청남도 천안시 서북구 두정동 500", "충청남도 천안시 서북구"),
        # 2레벨 — 종전 구현도 맞았던 케이스(무회귀 확인)
        ("서울특별시 강남구 역삼동 736", "서울특별시 강남구"),
        ("경기도 의정부시 의정부동 224", "경기도 의정부시"),
        # 시/도 단축표기 — 접미사 규칙만으로는 못 잡아 별도 처리한 경로
        ("서울 강남구 대치동 316", "서울 강남구"),
        ("경기 용인시 수지구 신봉동 56-19", "경기 용인시 수지구"),
        # 군 단위
        ("경상북도 울릉군 울릉읍 도동리 1", "경상북도 울릉군"),
        # ★판정 불가 — 틀린 시군구를 주는 것보다 **빈 값**이 낫다
        ("역삼동 736", ""),
        ("", ""),
    ],
)
def test_sigungu_hint_extracts_full_sigungu_level(address: str, expected: str) -> None:
    assert _sigungu_hint_from_address(address) == expected


def test_stops_at_eup_myeon_dong_ri() -> None:
    """읍·면·동·리에서 멈춘다 — 더 가면 시군구가 아니라 하위 행정구역을 넣게 된다."""
    # 호미곶'면'이 힌트에 들어가면 질의가 "… 남구 호미곶면 호미곶면 대보리 …" 가 된다.
    assert "호미곶면" not in _sigungu_hint_from_address("경상북도 포항시 남구 호미곶면 대보리 산1-1")
    assert "대보리" not in _sigungu_hint_from_address("경상북도 포항시 남구 호미곶면 대보리 산1-1")


def test_old_two_token_rule_would_fail_these() -> None:
    """★변이 방향 고정 — 종전 규칙(`parts[:2]`)으로 되돌리면 이 단언이 깨진다.

    회귀락이 "무엇을 막고 있는지"를 테스트 안에 남긴다. 종전 규칙의 산출을 여기서
    **독립적으로 재현**해 현행과 다름을 보인다(구현을 호출하지 않는다 — 동어반복 방지).
    """
    addr = "경상북도 포항시 남구 호미곶면 대보리 산1-1"
    old_rule = " ".join(addr.split()[:2])  # 종전 구현의 독립 재현
    assert old_rule == "경상북도 포항시"
    assert _sigungu_hint_from_address(addr) != old_rule, (
        "힌트가 종전 2토큰 규칙과 같아졌다 — 3레벨 시군구 절단이 되살아났다"
    )


# ── 배선층 불변식 ───────────────────────────────────────────────────────────

def test_router_actually_calls_the_helper() -> None:
    """★배선 잠금 — 헬퍼가 옳아도 **호출부가 되돌아가면** 아무 소용이 없다.

    실제로 확인했다: 라우터를 종전 2토큰 규칙으로 되돌리는 변이(3행)를 주입했더니
    위 골든 14건이 **전건 통과**했다. 골든은 헬퍼를 직접 호출하기 때문이다.
    이 저장소는 같은 함정(배선 미변이)에 네 번 뚫린 기록이 있다
    (`feedback_mutation_wiring_and_scope`). 로직·배선을 **따로** 잠근다.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "routers" / "auto_zoning.py").read_text(encoding="utf-8")
    # 주석/독스트링의 언급으로 충족되지 않도록 **호출 형태**로 못 박는다.
    assert "_sigungu_hint_from_address(" in src, (
        "라우터가 시군구 힌트 헬퍼를 호출하지 않는다 — 3레벨 시군구 절단이 되살아난다"
    )
    # 종전 규칙이 되살아나면 실패한다(변수명이 바뀌어도 이 형태는 남는다).
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    assert 'sigungu_hint = " ".join(' not in code, (
        "라우터에 2토큰 절단 규칙이 되살아났다"
    )
