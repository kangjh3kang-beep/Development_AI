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

from apps.api.app.services.land_intelligence.nearby_map_service import (
    sigungu_hint_from_address as _sigungu_hint_from_address,
)


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
        # 세종은 시군구 계층이 없다 — 단일 토큰이 시로 끝나므로 그대로 통과
        ("세종특별자치시 조치원읍 1", "세종특별자치시"),
        # ★판정 불가 — 틀린 시군구를 주는 것보다 **빈 값**이 낫다
        ("역삼동 736", ""),
        ("", ""),
        # ★리뷰 C-1 — **시·도만 뽑히는** 입력. 종전 구현은 여기서 값을 냈고, 이 PR 이
        #   힌트를 행보다 우선시키므로 그 반쪽 값이 전 행에 전파돼 "다른 시군구의 동명
        #   지번"으로 매칭될 수 있었다(무해한 실패 → 유해한 성공). 하필 이 PR 이 고치겠다고
        #   한 특례시가 정확히 이 케이스다.
        ("경남 창원 의창구 팔용동 100", ""),
        ("충남 천안 서북구 두정동 500", ""),
        ("전북 전주 완산구 효자동 1", ""),
        ("경기 성남 분당구 정자동 178", ""),
        ("서울 역삼동 736", ""),
        ("경상북도 호미곶면 대보리 산1-1", ""),
        # ★리뷰 R-1 — **시·도 없는 자치구 단독**. 전국 중복(남구 6·중구 6·동구 5·서구 5·북구 4)
        #   이라 그대로 쓰면 다른 광역시의 동명 지번으로 매칭될 수 있다(C-1 과 같은 기전).
        ("남구 대보리 산1-1", ""),
        ("중구 태평로1가 31", ""),
        ("동구 신암동 1", ""),
        ("서구 둔산동 1", ""),
        ("북구 연산동 1", ""),
        ("강남구 대치동 316", ""),
        # ★F-1 — 광역시 축약형은 **시군구가 아니다**. endswith("시") 만으로는 시도와 시군구를
        #   구분 못 해 통과했다. 특히 "광주시" 는 광주광역시 축약형과 경기도 광주시가
        #   문자열로 충돌한다.
        ("서울시 역삼동 736", ""),
        ("부산시 우동 1", ""),
        ("광주시 충장로1가 1", ""),
        ("대전시 둔산동 1", ""),
        # 진짜 시군구인 단일 토큰은 유지되어야 한다(과잉 차단 방지)
        ("세종특별자치시 조치원읍 1", "세종특별자치시"),
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

    ★리뷰 H-1 봉합: 종전 구현은 파일 전체에서 문자열을 찾았는데, 헬퍼가 **같은 파일에
    정의**돼 있어 `def sigungu_hint_from_address(` 정의 줄이 그 단언을 충족했다. 즉
    호출부를 지워도 통과하는 **공허 단언**이었고, 내가 "배선을 닫았다"고 한 보고는 과장이었다
    (내 변이가 잡힌 건 두 번째 단언의 리터럴이 우연히 걸렸기 때문).
    이제 **호출 함수의 소스만** 떼어내 검사한다 — 정의부가 구조적으로 배제된다.
    """
    import inspect

    from apps.api.routers import auto_zoning

    body = inspect.getsource(auto_zoning.nearby_transactions_map)
    # 주석/독스트링의 언급으로 충족되지 않게 코드만 남긴다(이 저장소에서 세 번 뚫린 구멍).
    code = "\n".join(ln.split("#")[0] for ln in body.splitlines())
    assert "sigungu_hint_from_address(" in code, (
        "라우터 핸들러가 시군구 힌트 헬퍼를 호출하지 않는다 — 3레벨 시군구 절단이 되살아난다"
    )
    assert 'sigungu_hint = " ".join(' not in code, "2토큰 절단 규칙이 되살아났다"


def test_build_derives_hint_itself_for_other_callers() -> None:
    """★리뷰 H-3 — 라우터 밖 호출부(desk_appraisal·assistant_agent)도 힌트를 얻는가.

    라우터 한 곳만 고치면 근본 봉합이 아니다. 하필 이 진단의 발단인 호미곶 사례가
    `desk_appraisal` 경로다 — 거기서 안 고쳐지면 헤드라인 증상이 그대로 남는다.
    """
    import inspect

    from apps.api.app.services.land_intelligence import nearby_map_service as nm

    body = inspect.getsource(nm.NearbyMapService.build)
    code = "\n".join(ln.split("#")[0] for ln in body.splitlines())
    assert "sigungu_hint_from_address(" in code, (
        "build() 가 힌트를 스스로 도출하지 않는다 — 힌트를 안 넘기는 호출부가 "
        "중개사무소 소재지로 폴백한다(이 PR 이 근원이라 규정한 상태 그대로)"
    )
