"""`그 밖에 용도지구·구역 등` 은 **조건 하나가 아니라 나열**이다 — 항목마다 값이 다르다.

【라이브 실측 2026-08-21 · 오산시 도시계획 조례 제46조 본문】

    1. 취락지구: 40퍼센트 이하
    2. 개발진흥지구: 자연녹지지역에 지정된 경우 30퍼센트 이하
    3. 수산자원보호구역: 30퍼센트 이하
    4. 「자연공원법」에 따른 자연공원: 60퍼센트 이하
    5. 공업지역에 있는 「산업입지…」…준산업단지: 80퍼센트 이하

종전에는 조각 스캐너가 집은 **하나(30)** 가 조 전체를 대표했다. 그래서
**취락지구 부지에 30%(실제 40%)** 가 나갈 수 있었다 — None 보다 위험한 형태다.

【★왜 조각(`context`)으로는 원리적으로 불가능했나】
`context` 는 용도지역명 **뒤**에서 잘려 시작하는 **120자 고정 창**이라 앞뒤가 다 잘린다
(실측: 1·2·5호가 창 밖). 그 창으로 매칭을 넓히면 **보이지 않는 항목을 말없이 빠뜨리고**
"이 부지는 해당 없음" 이라는 **거짓 음성**을 낸다 — 보수적 기각보다 나쁘다.
그래서 창이 아니라 **조문 본문 전체**를 읽는다.

【이 파일이 잠그는 것】
1. 나열을 항목별로 뜯는다(번호·이름·값·용도지역 한정)
2. 매칭되면 **그 항목의 값**을 낸다(조각 값이 아니라)
3. 나열을 못 읽으면 **판정 보류**(종전의 보수적 기각 유지)
4. 부분일치 규율(#703) — 제도가 다른 이름을 집지 않는다
"""

import pytest

from app.services.zoning.ordinance_conditional import (
    extract_article_body,
    match_site_conditions,
    parse_district_options,
)

# ── 라이브 원문 최소 재현(꼬리 XML·개정 주기 포함 — 실제로 이렇게 들어온다) ──────────
_REAL_BODY = (
    "제46조(그 밖에 용도지구·구역 등의 건폐율) 영 제84조제4항에 따라 다음 각 호의 어느 "
    "하나에 해당하는 용도지구ㆍ용도구역 등의 건폐율은 다음 각 호와 같다."
    "〈개정 2025. 2. 28〉 1. 취락지구: 40퍼센트 이하 2. 개발진흥지구: 자연녹지지역에 "
    "지정된 경우 30퍼센트 이하 3. 수산자원보호구역: 30퍼센트 이하 "
    "4. 「자연공원법」에 따른 자연공원: 60퍼센트 이하 5. 공업지역에 있는 "
    "「산업입지 및 개발에 관한 법률」 제2조제8호가목부터 다목까지에 따른 "
    "국가산업단지ㆍ일반산업단지ㆍ도시첨단산업단지 및 같은 조 제12호에 따른 준산업단지: "
    "80퍼센트 이하 ]]></조내용><조 조문번호='004700'><조제목>건폐율의 강화</조제목>"
)


@pytest.fixture
def options():
    return parse_district_options(extract_article_body(_REAL_BODY, 0))


def test_premise_values_actually_differ(options):
    """전제 — 항목 값이 **서로 달라야** 이 수정이 의미가 있다(공허 방지).

    전부 같은 값이면 조각 값 하나로 대표해도 결과가 같아, 배선을 끊어도 티가 안 난다.
    """
    vals = {o["value"] for o in options}
    assert len(vals) >= 3, f"값이 갈리지 않는다: {vals}"
    assert 40 in vals and 60 in vals, "취락 40·자연공원 60 이 서로 달라야 한다"


def test_parses_every_enumerated_item(options):
    """전수 — 5개 항목을 **하나도 빠뜨리지 않는다**."""
    got = {o["no"]: (o["name"], o["value"]) for o in options}
    assert got[1][0] == "취락지구" and got[1][1] == 40
    assert got[2][0] == "개발진흥지구" and got[2][1] == 30
    assert got[3][0] == "수산자원보호구역" and got[3][1] == 30
    assert got[4][0] == "자연공원" and got[4][1] == 60, "근거법 인용(「」)이 이름에 남았다"
    # ★5호는 이름이 100자를 넘는다 — 길이 상한이 좁으면 **통째로 사라진다**(실측 적발).
    assert 5 in got and got[5][1] == 80, f"5호(80%)가 사라졌다: {sorted(got)}"


def test_amendment_note_is_not_read_as_an_item(options):
    """★개정 주기의 날짜가 나열 번호로 읽히지 않는다.

    `〈개정 2025. 2. 28〉` 의 `2. 28` 이 항목으로 잡혀 1호가 `'28〉 1. 취락지구'` 가 됐다(실측 적발).
    """
    assert all("〉" not in o["name"] for o in options), [o["name"] for o in options]
    assert all("개정" not in o["name"] for o in options)
    # 공허 진리 가드 — 원문에 정말 개정 주기가 있었는가.
    assert "〈개정" in _REAL_BODY


def test_xml_tail_is_cut_before_parsing():
    """★조문 본문은 다음 조 헤더/CDATA 꼬리에서 끊는다 — 안 끊으면 태그 속 숫자가 섞인다."""
    body = extract_article_body(_REAL_BODY, 0)
    assert "]]>" not in body and "조문번호" not in body
    # 공허 진리 가드 — 원문에 정말 꼬리가 있었는가.
    assert "]]>" in _REAL_BODY


def _item(zone: str, options) -> dict:
    return {
        "kind": "bcr", "value": 30,          # ← 조각 스캐너가 집었던 값(대표값 아님)
        "article": "제46조", "article_title": "그 밖에 용도지구·구역 등의 건폐율",
        "condition_key": "designated_district", "condition_kind": "site",
        "direction": "relax", "zone_type": zone, "district_options": options,
    }


def _run(zone, districts, options):
    r = match_site_conditions([_item(zone, options)], districts)
    for bucket in ("matched", "unmatched_site", "undecidable"):
        if r[bucket]:
            return bucket, r[bucket][0]
    raise AssertionError("어느 버킷에도 담기지 않았다")


def test_matched_carries_the_items_own_value(options):
    """★★핵심 — 매칭되면 **그 항목의 값**을 낸다(조각 값 30 이 아니라)."""
    bucket, row = _run("자연녹지지역", ["자연취락지구"], options)
    assert bucket == "matched"
    assert row["value"] == 40, "조각 값(30)이 그대로 나왔다 — 취락지구 부지에 틀린 수치"
    assert row["matched_option"] == "취락지구"
    assert "자연취락지구" in row["why"]


def test_different_district_gets_a_different_value(options):
    """★두 모집단 — 같은 조문인데 **다른 부지는 다른 값**을 받아야 한다."""
    _, chwirak = _run("자연녹지지역", ["자연취락지구"], options)
    _, park = _run("자연녹지지역", ["자연공원"], options)
    assert chwirak["value"] == 40 and park["value"] == 60
    assert chwirak["value"] != park["value"], "값이 갈리지 않으면 배선을 끊어도 같다"


def test_subtype_designation_matches_parent_category(options):
    """하위유형 지정명이 조례의 상위 범주명을 포함하면 매칭된다(`취락지구` ⊂ `자연취락지구`)."""
    assert _run("자연녹지지역", ["자연취락지구"], options)[0] == "matched"
    assert _run("자연녹지지역", ["집단취락지구"], options)[0] == "matched"


def test_zone_scope_limit_is_enforced(options):
    """★항목이 용도지역을 한정하면 그 지역일 때만 성립(`개발진흥지구: 자연녹지지역에 …`)."""
    ok_bucket, ok_row = _run("자연녹지지역", ["개발진흥지구"], options)
    assert ok_bucket == "matched" and ok_row["value"] == 30
    # ★양성 짝과 쌍 — 한정 밖 용도지역에서는 성립하지 않는다.
    assert _run("계획관리지역", ["개발진흥지구"], options)[0] == "unmatched_site"


def test_metro_regime_name_is_not_matched(options):
    """★#703 규율 — 수도권정비계획법 권역은 국계법 용도지구·구역이 아니다(실데이터 경로)."""
    bucket, _ = _run("자연녹지지역", ["성장관리권역"], options)
    assert bucket == "unmatched_site"
    # ★양성 짝 — 같은 실행에서 진짜 지구는 매칭된다(매칭이 통째로 죽은 게 아님).
    assert _run("자연녹지지역", ["자연취락지구"], options)[0] == "matched"


def test_metro_regime_guard_actually_fires_when_reachable():
    """★★위 테스트는 **공허했다** — 변이감사가 잡았다.

    실조례의 항목명(`취락지구`·`자연공원`…) 중 어느 것도 `성장관리권역` 의 부분문자열이
    아니라서, 위 테스트에서는 이름 매칭(`hit`)이 **이미 None** 이었다. 즉 권역 배제 가드는
    **한 번도 실행되지 않고** 테스트가 통과했다(`METRO_REGIME_NAMES` 분기를 무력화해도 생존).

    그래서 **가드가 도달 가능한 입력**을 합성해 가드 자체를 태운다. 실데이터로는 이 가드가
    도달 불가일 수 있으나(관측 범위 내에서 그렇다), 도달하면 **반드시 배제해야** 한다 —
    그것이 #703(경기 전역 건폐율 +10%p 직전 차단)이 남긴 규율이다.
    """
    # 조례가 `성장관리` 로 시작하는 항목을 적었다고 가정 → 이름 매칭이 **성립한다**.
    synthetic = [{"no": 1, "name": "성장관리", "value": 99, "zone_scope": None}]

    # ① 전제 — 가드가 없다면 이 입력은 매칭된다(부분문자열이 실제로 성립함을 확인).
    assert "성장관리" in "성장관리권역"

    # ② 수도권 권역은 **배제**된다.
    assert _run("자연녹지지역", ["성장관리권역"], synthetic)[0] == "unmatched_site"

    # ③ ★양성 짝 — 같은 항목명이라도 권역이 아닌 지정이면 **매칭된다**.
    #    이게 없으면 매칭이 통째로 죽어도 ②가 통과한다.
    bucket, row = _run("자연녹지지역", ["성장관리계획구역"], synthetic)
    assert bucket == "matched" and row["value"] == 99


def test_article_body_picks_the_article_containing_pos():
    """★여러 조문이 있을 때 **`pos` 가 속한 조문**을 고른다(가장 가까운 앞선 조).

    변이감사: 조문이 하나뿐인 픽스처만 쓰면 `begin` 초기화·`st <= pos` 비교를 지워도
    결과가 같아 **생존**한다. 조문 두 개를 두고 각각을 짚어야 그 줄이 잠긴다.
    """
    two = (
        "제46조(그 밖에 용도지구·구역 등의 건폐율) 1. 취락지구: 40퍼센트 이하 "
        "제48조(방화지구에서의 건폐율의 완화) 1. 방화지구: 90퍼센트 이하 "
    )
    first = extract_article_body(two, two.index("취락지구"))
    second = extract_article_body(two, two.index("방화지구: 90"))
    assert "제46조" in first and "제48조" not in first
    assert "제48조" in second and "제46조" not in second
    # 그리고 각 조문에서 뽑히는 값이 실제로 다르다(전제 — 같으면 구분이 무의미).
    assert parse_district_options(first)[0]["value"] == 40
    assert parse_district_options(second)[0]["value"] == 90


def test_article_body_before_any_header_is_empty_not_crash():
    """★조문 헤더가 없는 텍스트에서도 죽지 않는다 — 빈 문자열/헤더 없음 방어."""
    assert extract_article_body("", 0) == ""
    # 헤더가 전혀 없으면 본문을 통째로 돌려주되 예외를 내지 않는다.
    assert extract_article_body("헤더 없는 본문 1. 취락지구: 40퍼센트", 5) != ""


def test_zone_scope_inside_the_item_name_is_stripped():
    """★용도지역 한정이 **항목명 안**에 붙어도 이름에서 걷어낸다.

    실측 원문은 한정구가 값 앞(`: 자연녹지지역에 지정된 경우 30퍼센트`)에 오지만,
    조례마다 표기가 달라 이름 쪽에 붙는 형태도 있다. 걷어내지 않으면 지정명과 매칭되지 않는다.
    """
    body = "제46조(그 밖에 용도지구·구역 등) 1. 개발진흥지구 자연녹지지역에 지정된 경우: 30퍼센트 이하"
    opt = parse_district_options(body)[0]
    assert opt["name"] == "개발진흥지구", f"한정구가 이름에 남았다: {opt['name']!r}"
    assert opt["zone_scope"] == "자연녹지지역"


def test_unmatched_clears_the_stale_fragment_value(options):
    """★해당 없음으로 판정했으면 조각 값을 달고 다니지 않는다(소비처 오독 방지)."""
    bucket, row = _run("자연녹지지역", ["제1종지구단위계획구역"], options)
    assert bucket == "unmatched_site"
    assert row["value"] is None, "해당 없는데 30% 가 붙어 있다"
    # 그리고 **왜** 해당 없는지 — 전체 목록을 봤다는 사실이 근거다.
    assert "5개 항목" in row["why"]


def test_unreadable_enumeration_stays_conservative():
    """★나열을 못 읽으면 **판정 보류** — 종전의 보수적 태도를 유지한다(거짓 음성 금지).

    ★양성 짝 동봉: 같은 실행에서 나열이 있으면 판정이 **실제로 일어난다**.
    없으면 매칭 로직이 통째로 죽어 항상 보류를 내도 이 테스트가 통과한다.
    """
    opts = parse_district_options(extract_article_body(_REAL_BODY, 0))
    assert _run("자연녹지지역", ["자연취락지구"], opts)[0] == "matched"

    bucket, row = _run("자연녹지지역", ["자연취락지구"], [])
    assert bucket == "undecidable"
    assert "읽지 못함" in row["why"]
