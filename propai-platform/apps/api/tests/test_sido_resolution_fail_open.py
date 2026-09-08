"""정식 행정구역명 5개가 「존재하지 않는 지역」과 **똑같이 처리**되던 것을 잠근다(2026-09-08).

■ 무엇이 있었나
`land_price_index._sido_of` 가 축약키(`"전남"`)를 주소에 **부분문자열**로 찾았는데 정식 명칭
`"전라남도"` 에는 그 축약형이 **연속으로 없다**(한글 음절 단위). 정식 시도 **17개 중 5개 실패**:
충청북도 · 충청남도 · 전라남도 · 경상북도 · 경상남도.
(전북·강원·제주는 **특별자치도 개칭** 덕에 우연히 통과했다.)

그 `""` 를 받은 `reb_client.rate_series_from_rows` 가 **fail-open** 으로 전국+전 지역 혼합
시계열을 돌려주고, 그것이 「R-ONE 지가변동률 **실데이터**」로 라벨링돼 감정평가 단가에 곱해졌다.

★라이브 확증(2026-09-08): `경상남도`→**1.047** · `zzz없는지역`→**1.047**(같은 값) ·
  `경남`(축약)→**None**(판정 거부 정상). ⇒ **정식 명칭이 「존재하지 않는 지역」과 동일 처리**됐다.

■ 처방 — 새로 만들지 않고 **정본에 위임**했다(§29)
`tax/regional_tax_data.sido_short_or_empty` 는 같은 입력 전수에서 **0/17 실패**이고 이미 단련돼
있다(후보 순회를 정렬 튜플로 고정 — `frozenset` 순회가 `PYTHONHASHSEED` 마다 다른 답을 내던
CRITICAL 봉합 · `"광주시"` 모호성은 판정하지 않음). 그 모듈이 이미 *"해석기는 한 자리에 둔다"* 고
선언했는데 `land_intelligence` 계열이 **미이관**이었다.

■ 축
  A 해석 : 정식 시도 **전수**(정본 표에서 **파생** — 손 목록 금지)가 전부 해석된다
  B 두 모집단: 해석 성공 ↔ 해석 불가가 **다른 결과**를 낸다(같으면 배선을 끊어도 결과가 같다)
  C fail-open: 지역 미해석 시 **전 지역 혼합**을 그 지역 값인 척 주지 않는다(행위로 태운다)
  D 정확일치: 계층경로(`CLS_FULLNM`)를 통한 **과매칭**을 하지 않는다
"""

from __future__ import annotations

import pytest

from app.services.external_api import reb_client as rc
from app.services.land_intelligence.land_price_index import (
    _ANNUAL_RATE,
    _DEFAULT_RATE,
    _lookup_rate,
    _sido_of,
)
from app.services.tax.regional_tax_data import _SIDO_FULL_TO_SHORT, sido_short_or_empty


def _official_sido_names() -> list[str]:
    """★정식 시도명을 **정본 표에서 파생**한다 — 손 목록을 두면 그 목록이 곧 상한이 된다."""
    return sorted({k for k in _SIDO_FULL_TO_SHORT if len(k) > 2})


# ─────────────────────────────────────────────────────────────
# 축 A — 해석 (파생형 전수)
# ─────────────────────────────────────────────────────────────

def test_official_name_population_is_not_empty() -> None:
    """★공허 진리 가드 — 단언 **앞**에. 모집단이 비면 「실패 0」이 무의미하다."""
    names = _official_sido_names()
    assert len(names) >= 15, names
    # 종전에 실패하던 다섯이 실제로 모집단에 있는가(이 락이 결함을 겨냥하는지).
    for n in ("충청북도", "충청남도", "전라남도", "경상북도", "경상남도"):
        assert n in names, f"{n} 이 모집단에 없다 — 정본 표가 바뀌었다"


@pytest.mark.parametrize("official", _official_sido_names())
def test_every_official_sido_name_resolves(official: str) -> None:
    """정식 행정구역명 **전수**가 해석된다(종전 5개 실패)."""
    got = _sido_of(f"{official} 어딘가시 어딘가동 1-1")
    assert got, f"{official} → 해석 실패(빈 문자열)"
    assert got in _ANNUAL_RATE, f"{official} → {got!r} 은 근사표 키가 아니다"


def test_sido_of_delegates_to_the_canonical_resolver_by_behavior() -> None:
    """★위임을 **행위로** 태운다 — 임포트 존재가 아니라 동일 입력에 동일 출력."""
    for official in _official_sido_names():
        addr = f"{official} 어딘가시 1-1"
        assert _sido_of(addr) == sido_short_or_empty(addr), addr


# ─────────────────────────────────────────────────────────────
# 축 B — 두 모집단 (해석 성공 ↔ 불가가 갈려야 한다)
# ─────────────────────────────────────────────────────────────

def test_resolved_and_unresolved_addresses_differ() -> None:
    """★해석 성공과 실패가 **서로 다른 결과**를 내야 한다.

    종전에는 둘이 같은 곳(전국 폴백)으로 수렴해, 배선을 끊어도 결과가 같았다.
    """
    ok_rate, ok_why = _lookup_rate("경상남도 창원시 의창구 1")
    ng_rate, ng_why = _lookup_rate("zzz없는지역 1-1")
    assert _sido_of("경상남도 창원시 의창구 1") == "경남"
    assert _sido_of("zzz없는지역 1-1") == ""
    assert ok_rate == _ANNUAL_RATE["경남"], ok_rate
    assert ng_rate == _DEFAULT_RATE, ng_rate
    assert ok_rate != ng_rate, "두 모집단이 같은 값을 낸다 — 락이 무의미하다"
    # ★사유도 갈려야 한다 — 「전국 평균」과 「지역을 못 읽었다」는 다른 말이다.
    assert ok_why != ng_why
    assert "해석하지 못해" in ng_why, ng_why
    assert "해석하지 못해" not in ok_why, ok_why


def test_unresolved_rate_is_not_silently_regional() -> None:
    """해석 실패 시 사유가 **그 사실을 말한다**(모름을 유효값으로 표현하지 않는다)."""
    for addr in ("", "zzz없는지역", "어딘가 123-4"):
        rate, why = _lookup_rate(addr)
        assert rate == _DEFAULT_RATE
        assert "해석하지 못해" in why, f"{addr!r} → {why}"


# ─────────────────────────────────────────────────────────────
# 축 C — fail-open 금지 (행위로 태운다)
# ─────────────────────────────────────────────────────────────

def _rows() -> list[dict]:
    """R-ONE 원시 행의 **실측 모양**을 그대로 쓴다(2026-09-08 라이브 관측).

    · `CLS_NM` 은 **축약형 시도명** · `CLS_FULLNM` 은 **계층 경로**
    · 한 표에 시도·시군구·동이 섞인다
    """
    return [
        # 시도 행(2개월) — 정상적으로 잡혀야 한다
        {"CLS_NM": "전남", "CLS_FULLNM": "전남광주>전남", "ITM_NM": "변동률",
         "DTA_VAL": 0.02, "WRTTIME_IDTFR_ID": "202606"},
        {"CLS_NM": "전남", "CLS_FULLNM": "전남광주>전남", "ITM_NM": "변동률",
         "DTA_VAL": 0.03, "WRTTIME_IDTFR_ID": "202607"},
        # 전국 행(2개월)
        {"CLS_NM": "전국", "CLS_FULLNM": "전국", "ITM_NM": "변동률",
         "DTA_VAL": 0.10, "WRTTIME_IDTFR_ID": "202606"},
        {"CLS_NM": "전국", "CLS_FULLNM": "전국", "ITM_NM": "변동률",
         "DTA_VAL": 0.11, "WRTTIME_IDTFR_ID": "202607"},
        # ★같은 달의 하위지역 — 계층 경로에 "경기" 가 들어 있다(과매칭 유발원)
        {"CLS_NM": "수원시", "CLS_FULLNM": "경기>수원시", "ITM_NM": "변동률",
         "DTA_VAL": 0.20, "WRTTIME_IDTFR_ID": "202607"},
        {"CLS_NM": "성남시", "CLS_FULLNM": "경기>성남시", "ITM_NM": "변동률",
         "DTA_VAL": 0.30, "WRTTIME_IDTFR_ID": "202607"},
    ]


def test_fixture_separates_two_populations() -> None:
    """★픽스처가 두 모집단을 실제로 가르는가(차가 0이면 잠금이 아니다)."""
    rows = _rows()
    assert any(r["CLS_NM"] == "전남" for r in rows)
    assert any("경기>" in r["CLS_FULLNM"] for r in rows), "과매칭 유발 행이 없다 — 축 D 가 공허해진다"
    assert not any(r["CLS_NM"] == "경기" for r in rows), "경기 시도 행이 있으면 축 D 가 공허해진다"


def test_unresolved_region_does_not_get_all_regions_mixed() -> None:
    """★fail-open 금지 — 빈 지역이 **전 지역 혼합**을 받지 않는다.

    종전 `_collect("전국") or _collect(None)` 의 `_collect(None)` 이 그것이었다.
    지금은 실제 「전국」 행만 폴백이고, 그 값들은 하위지역 값(0.20·0.30)을 **포함하지 않는다**.
    """
    series = rc.rate_series_from_rows(_rows(), "")
    values = sorted(r for _t, r in series)
    assert values == [0.10, 0.11], f"전국 행만 와야 한다: {values}"
    assert 0.20 not in values and 0.30 not in values, "하위지역이 섞였다(fail-open 재발)"


def _rows_without_nationwide() -> list[dict]:
    """★「전국」 행이 **없는** 모집단 — fail-open 분기를 실제로 도달시킨다.

    ★왜 이 픽스처가 따로 필요한가(2026-09-08 · 내 변이가 생존해서 알았다):
      `_rows()` 에는 전국 행이 **항상** 있어서 `_collect("전국") or _collect(None)` 의 `or` 가
      **단락**된다 — 즉 fail-open 을 되돌리는 변이가 **도달조차 못 해** 생존했다.
      «A 가 산다» 만으로는 «올바른 구현» 과 «아무것도 안 하는 구현» 을 가를 수 없다.
      ⇒ 두 모집단을 **같은 실행에서** 태운다: 전국 있음(폴백 성립) ↔ 전국 없음(거부해야 함).
    """
    return [r for r in _rows() if r["CLS_NM"] != "전국"]


def test_fixture_without_nationwide_actually_reaches_the_fallback_branch() -> None:
    """★공허 방지 — 이 픽스처가 정말 전국 행 0개이고 하위지역은 남아 있는가."""
    rows = _rows_without_nationwide()
    assert not any(r["CLS_NM"] == "전국" for r in rows), "전국 행이 남아 있으면 분기가 단락된다"
    assert any("경기>" in r["CLS_FULLNM"] for r in rows), "혼합될 재료가 없으면 이 락이 공허해진다"
    assert len(rows) >= 3, rows


def test_no_nationwide_rows_means_refusal_not_all_regions_mixed() -> None:
    """★★fail-open 금지의 **핵심 락** — 전국 행조차 없으면 **빈 시계열**(거부)이어야 한다.

    종전 코드(`_collect("전국") or _collect(None)`)는 여기서 **전 지역 혼합**을 돌려줬고,
    소비처가 그것을 「그 지역 시계열」로 읽었다. 지금은 아무것도 주지 않는다 —
    소비처의 판정 거부가 발화하게(모름을 유효값으로 표현하지 않는다).
    """
    rows = _rows_without_nationwide()
    for region in ("", "zzz없는지역", "경기"):
        series = rc.rate_series_from_rows(rows, region)
        assert series == [], (
            f"{region!r} → 전국 행이 없는데 값을 돌려줬다(fail-open 재발): "
            f"{sorted(r for _t, r in series)}"
        )
    # ★특이도 — 같은 픽스처에서 **진짜 시도 행은 여전히 찾는다**(항상 거부도 결함이다).
    assert sorted(r for _t, r in rc.rate_series_from_rows(rows, "전남")) == [0.02, 0.03]


def test_unknown_region_falls_back_to_nationwide_only() -> None:
    """존재하지 않는 지역도 **전 지역 혼합**이 아니라 전국 행만 받는다."""
    series = rc.rate_series_from_rows(_rows(), "zzz없는지역")
    assert sorted(r for _t, r in series) == [0.10, 0.11]


# ─────────────────────────────────────────────────────────────
# 축 D — 정확일치 (계층경로 과매칭 금지)
# ─────────────────────────────────────────────────────────────

def test_region_filter_does_not_match_via_hierarchy_path() -> None:
    """★`"경기"` 가 `CLS_FULLNM="경기>수원시"` 에 매칭되면 안 된다.

    라이브에서 이 과매칭이 «같은 달의 수십 개 하위지역»을 한 시계열로 모았고,
    소비처가 그것을 「그 지역 24개월」로 읽어 `yearly 2024 = +80.68%` 를 출판했다
    (월 최대 0.267% 로는 **물리적으로 불가능**한 값).
    """
    series = rc.rate_series_from_rows(_rows(), "경기")
    values = sorted(r for _t, r in series)
    # 경기 시도 행이 없으므로 전국 폴백이어야 한다 — 하위지역 값이 오면 과매칭이다.
    assert 0.20 not in values and 0.30 not in values, f"계층경로 과매칭: {values}"
    assert values == [0.10, 0.11], values


def test_exact_match_still_finds_the_real_sido_row() -> None:
    """★특이도 — 정확일치가 **진짜 시도 행은 찾는다**(항상 거부하면 그것도 결함이다)."""
    series = rc.rate_series_from_rows(_rows(), "전남")
    assert sorted(r for _t, r in series) == [0.02, 0.03], series
    # 두 모집단 대조: 전남은 자기 값을, 미해석은 전국 값을 받는다.
    assert sorted(r for _t, r in rc.rate_series_from_rows(_rows(), "")) == [0.10, 0.11]


def test_scope_tells_the_truth_about_the_fallback() -> None:
    """라벨 정직 — 전국으로 떨어졌으면 **그 지역이라고 말하지 않는다**."""
    assert rc.rate_series_scope(_rows(), "전남") == "전남"
    assert rc.rate_series_scope(_rows(), "경기") == "전국"
    assert rc.rate_series_scope(_rows(), "zzz없는지역") == "전국"


# ─────────────────────────────────────────────────────────────
# ★부채 — 미이관 재구현 2곳(반환 계약이 다르다 · 이 PR 범위 밖)
# ─────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="★부채: hyphen_client.extract_sido 가 **완전명**을 반환해 정본과 계약이 갈린다(정식 시도명 20개 전수 불일치 20/20)")
def test_hyphen_resolver_delegates_to_the_canonical_one() -> None:
    """★사유를 **실측으로** 정정했다(독립 리뷰 MEDIUM-3).

    종전 `reason` 은 *"onbid/hyphen **2곳**이 미이관(축약 vs 완전명)"* 이라고 썼는데 **틀렸다** —
    정식 시도명 20개 전수 3자 비교 실측: `onbid._sido_from_address` **불일치 0건**(이미 축약형을
    돌려준다) · `hyphen.extract_sido` **불일치 20건**. 즉 이 xfail 은 **hyphen 하나가 떠받치고**
    있었고, 첫 단언(onbid)은 통과하고 있었다.
    ★그리고 onbid 의 **진짜 결함은 이 테스트가 태우지 않았다**(아래 별도 부채로 분리).
    """
    from app.services.registry.hyphen_client import extract_sido

    addr = "전라남도 순천시 조례동 1"
    assert extract_sido(addr) == sido_short_or_empty(addr)


@pytest.mark.xfail(strict=True, reason="★부채: onbid_client._sido_from_address 의 `first[:2]` 폴백이 **존재하지 않는 시도를 지어낸다**")
def test_onbid_resolver_does_not_fabricate_a_sido() -> None:
    """★onbid 의 결함은 «계약이 다름» 이 아니라 **날조**다(독립 리뷰 MEDIUM-3 실측).

        '성남시 분당구 1'    정본='' → onbid='성남'
        'zzz없는지역 1-1'    정본='' → onbid='zz'
        '해운대구 우동 1394'  정본='' → onbid='해운'

    이 PR 이 고치겠다고 선언한 «모름을 유효값으로 표현하지 않는다» **그 자체**다.
    ★hyphen 만 이관하면 위 xfail 이 XPASS 로 뒤집혀 마커가 제거되고, **onbid 의 날조가
      부채 목록에서 사라진 채 남는다**(§C-12) — 그래서 **두 부채를 분리**한다.
    """
    from app.services.auction.onbid_client import _sido_from_address

    for addr in ("성남시 분당구 1", "zzz없는지역 1-1", "해운대구 우동 1394"):
        assert _sido_from_address(addr) == sido_short_or_empty(addr), addr


# ─────────────────────────────────────────────────────────────
# ★독립 리뷰 R1 반영 — 축을 넓히고 배선을 잠근다
# ─────────────────────────────────────────────────────────────

def _rows_with_region_nm_only() -> list[dict]:
    """★`CLS_NM` 이 **없고** `REGION_NM` 만 있는 행 — 폴백 분기를 실제로 태운다(MEDIUM-5).

    ★기계 변이가 `row_region_name` 의 `REGION_NM`/`REGION` 분기에서 **3건 나란히 생존**했다.
      원인: 모든 픽스처 행에 `CLS_NM` 이 있어 그 분기가 **도달 불가**였다.
      ★fail-open 픽스처에서 방금 고친 것과 **같은 형태**를 옆 함수에서 다시 만들었다.
      ⇒ 분기를 만들었으면 **그 분기를 태우는 행**을 픽스처에 같이 넣는다.
    """
    return [
        {"REGION_NM": "전남", "ITM_NM": "변동률", "DTA_VAL": 0.05, "WRTTIME_IDTFR_ID": "202605"},
        {"REGION": "전국", "ITM_NM": "변동률", "DTA_VAL": 0.06, "WRTTIME_IDTFR_ID": "202605"},
    ]


def test_region_nm_fallback_branch_is_actually_exercised() -> None:
    """★공허 방지 — 이 픽스처가 정말 `CLS_NM` 없는 행인가."""
    rows = _rows_with_region_nm_only()
    assert all("CLS_NM" not in r for r in rows), "CLS_NM 이 있으면 폴백 분기가 안 돈다"
    assert rc.row_region_name(rows[0]) == "전남"
    assert rc.row_region_name(rows[1]) == "전국"


def test_region_nm_fallback_is_used_by_both_consumers() -> None:
    """폴백 분기가 `_collect` 와 `_has_region` **양쪽**에서 동작한다."""
    rows = _rows_with_region_nm_only()
    assert sorted(r for _t, r in rc.rate_series_from_rows(rows, "전남")) == [0.05]
    assert rc._has_region(rows, "전남") is True
    assert rc._has_region(rows, "경기") is False


def test_cls_nm_wins_over_the_fallback_keys() -> None:
    """★두 축 대조 — `CLS_NM` 이 있으면 **그쪽이 우선**한다(폴백이 덮어쓰지 않는다)."""
    row = {"CLS_NM": "전남", "REGION_NM": "경기", "ITM_NM": "변동률", "DTA_VAL": 1.0}
    assert rc.row_region_name(row) == "전남"


# ── HIGH-1: latest_value_from_rows 도 같은 축으로 (형제 미스윕이었다) ──

def test_latest_value_does_not_match_via_hierarchy_path() -> None:
    """★`"경기"` 가 `CLS_FULLNM="경기>성남시"` 를 통해 **성남시 값을 채택**하면 안 된다.

    독립 리뷰 실측: 같은 `rows` 로 `rate_series_from_rows` 는 전국으로 떨어지는데
    `latest_value_from_rows` 는 **0.30(성남시)을 「경기」로** 돌려줬다 — 두 축이 갈렸다.
    """
    got = rc.latest_value_from_rows(_rows(), "경기")
    assert got is None or got[0] not in (0.20, 0.30), f"계층경로 과매칭: {got}"


def test_latest_value_does_not_judge_region_by_item_name() -> None:
    """★`ITM_NM`(항목명)은 지역이 아니다 — 그것으로 지역을 판정하면 안 된다."""
    rows = [{"CLS_NM": "서울", "ITM_NM": "경기지수", "DTA_VAL": 7.7, "WRTTIME_IDTFR_ID": "202607"}]
    assert rc.latest_value_from_rows(rows, "경기") is None, "ITM_NM 으로 지역을 판정했다"
    # 특이도 — 진짜 서울 행은 찾는다.
    assert rc.latest_value_from_rows(rows, "서울") == (7.7, "202607")


def test_latest_value_has_no_per_row_fail_open() -> None:
    """★지역 필드가 **빈 행**이 필터를 통과하면 안 된다(per-row fail-open)."""
    rows = [
        {"DTA_VAL": 9.99, "WRTTIME_IDTFR_ID": "209912"},          # 지역 없음 — 통과하면 안 된다
        {"CLS_NM": "전남", "DTA_VAL": 0.02, "WRTTIME_IDTFR_ID": "202607"},
    ]
    got = rc.latest_value_from_rows(rows, "전남")
    assert got == (0.02, "202607"), f"지역 없는 행이 채택됐다: {got}"


# ── HIGH-3: 배선 락 — 함수가 아니라 «주소가 실제로 전달되는가» ──

def test_time_adjust_actually_uses_the_address() -> None:
    """★배선 — 주소를 상수로 바꾸면 빨개져야 한다.

    ★독립 리뷰 실측: `_lookup_rate(address)` → `_lookup_rate("")` 변이가 **전 저장소
      12,280건을 통과**했다. 즉 모든 필지가 주소와 무관하게 1.8% 를 받게 만들어도 무잠금이었다.
      락이 함수를 태우면서 **그 함수가 불리는지**는 아무것도 안 봤다.
    """
    from app.services.land_intelligence.land_price_index import time_adjust_factor

    seoul = time_adjust_factor("서울특별시 강남구 역삼동 1", base_year=2025)
    gyeongbuk = time_adjust_factor("경상북도 안동시 1", base_year=2025)
    unknown = time_adjust_factor("zzz없는곳 1", base_year=2025)
    # 세 모집단이 **서로 다른** 연변동률을 받아야 한다(주소가 실제로 쓰인다는 증거).
    rates = {seoul["annual_rate"], gyeongbuk["annual_rate"], unknown["annual_rate"]}
    assert len(rates) == 3, f"주소가 결과를 바꾸지 않는다(배선 끊김): {rates}"
    assert seoul["annual_rate"] != unknown["annual_rate"]
    assert gyeongbuk["annual_rate"] != unknown["annual_rate"]
    # 사유에도 해석된 지역이 실려야 한다(어느 지역 요율인지 사용자가 알 권리).
    assert "서울" in seoul["rationale"], seoul["rationale"]
    assert "경북" in gyeongbuk["rationale"], gyeongbuk["rationale"]


# ── MEDIUM-1: 접두 잡음 회귀 방지(내가 만든 회귀였다) ──

@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("경기도 성남시 분당구 1", "경기"),
        ("(우)13561 경기도 성남시 분당구", "경기"),
        ("13561 경기도 성남시 분당구", "경기"),
        ("  경기도 성남시", "경기"),
        ("충청남도 천안시 서북구", "충남"),
    ],
)
def test_postal_prefix_does_not_break_resolution(addr: str, expected: str) -> None:
    """★정본은 `startswith` 라 접두 잡음에 약하다 — **우편번호만** 벗겨 그 계열을 살린다."""
    assert _sido_of(addr) == expected


# ★★이 PR 이 **좁힌 범위**를 숨기지 않는다(독립 리뷰 R2 MEDIUM-1).
#   base 는 부분문자열이라 아래 형태를 해석했는데 지금은 못 한다. 임의 괄호 라벨을 벗기는
#   1차 시도는 **시도를 품은 라벨까지 벗겨** 더 큰 회귀를 냈으므로(11형태 중 9회귀) 되돌렸다.
#   ⇒ 정직한 상태: «우편번호 외의 접두는 지원하지 않는다». 부채로 초록 안에 드러낸다.
@pytest.mark.xfail(strict=True, reason="★부채(R2 MEDIUM-1): 회사명·괄호 라벨·국가명 접두는 미지원 — base 대비 좁아진 범위")
@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("(주)오케이 서울특별시 강남구 1", "서울"),
        ("[경기도] 성남시 분당구 1", "경기"),
        ("한국은행 서울특별시 중구 1", "서울"),
        ("대한민국 경기도 성남시", "경기"),
    ],
)
def test_other_prefix_noise_is_not_supported_yet(addr: str, expected: str) -> None:
    """언젠가 지원해야 한다 — 다만 **시도를 품은 라벨을 벗기지 않는** 방식이어야 한다."""
    assert _sido_of(addr) == expected


@pytest.mark.parametrize(
    "addr",
    ["zzz없는곳 1", "(우)00000 zzz없는곳", "13561 zzz없는곳", "광주시 오포읍", "", "   "],
)
def test_prefix_stripping_does_not_fabricate_a_sido(addr: str) -> None:
    """★특이도 — 잡음을 벗겨도 **없는 시도를 지어내지 않는다**(모호한 `광주시` 포함)."""
    assert _sido_of(addr) == ""


# ─────────────────────────────────────────────────────────────
# ★HIGH-2 + HIGH-3(async 경로) — 계획서가 선언한 「라벨 정직화」를 **실제로** 태운다
#
#   독립 리뷰 실측: 수정 후에도 경남이 «R-ONE 지가변동률 **실데이터**» 라벨로 1.0491 을 받아
#   채택 단가에 곱해졌다 — 혼합이 전국으로 좁아졌을 뿐 «확신 있는 답» 은 그대로였다.
#   그리고 그 async 경로는 **어떤 락도 태우지 않았다**(배선 변이가 생존).
#   ⇒ `reb_ready`/`fetch_land_price_changes` 를 스텁해 **그 경로를 직접 실행**한다.
#     ★스텁이 검증 대상 층을 우회하지 않는다 — 스텁하는 것은 «네트워크» 뿐이고,
#       지역 해석·범위 판정·라벨 조립은 **진짜 코드가 돈다**.
# ─────────────────────────────────────────────────────────────

def _patch_rone(monkeypatch, rows: list[dict]) -> None:
    """네트워크만 스텁한다 — 판정 로직은 진짜를 태운다."""
    import app.services.external_api.reb_client as _rc

    monkeypatch.setattr(_rc, "reb_ready", lambda: True)

    async def _fetch(months: int = 24):
        return rows

    monkeypatch.setattr(_rc, "fetch_land_price_changes", _fetch)


def _many_months(region: str, n: int = 24, rate: float = 0.05) -> list[dict]:
    """한 지역의 **n개월** 시계열.

    ★`cumulative_factor_from_rows` 는 **고유 기간이 요청 개월(기본 24) 미만이면 판정을 거부**한다
      (#1014 이 넣은 가드). 12개월짜리 픽스처를 주면 그 거부가 발화해 근사표로 떨어지고,
      **async 경로를 태우려던 락이 조용히 다른 길을 잰다** — 처음 이 픽스처를 12개월로 만들었다가
      그 함정을 밟았다. 기본을 24로 둔다.
    ★변동률은 누적이 sane-range(0.7~1.3)에 들도록 작게 유지한다.
    """
    return [
        {"CLS_NM": region, "ITM_NM": "변동률", "DTA_VAL": rate,
         "WRTTIME_IDTFR_ID": f"2024{m:02d}" if m <= 12 else f"2025{m - 12:02d}"}
        for m in range(1, n + 1)
    ]


@pytest.mark.asyncio
async def test_regional_series_is_labeled_as_that_region(monkeypatch) -> None:
    """요청 지역의 시계열이 **실제로 있으면** 그 지역 실데이터라고 말해도 된다(특이도)."""
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async

    _patch_rone(monkeypatch, _many_months("경남") + _many_months("전국"))
    out = await time_adjust_factor_async("경상남도 창원시 의창구 1")
    assert out["source"] == "R-ONE", out
    assert out.get("scope") == "경남", out
    assert "경남" in out["rationale"], out["rationale"]


@pytest.mark.asyncio
async def test_nationwide_fallback_must_not_claim_regional_real_data(monkeypatch) -> None:
    """★★핵심 — 요청 지역 시계열이 **없어** 전국으로 떨어지면 **그렇다고 말해야** 한다.

    종전에는 이 경우에도 `source="R-ONE"` · *"R-ONE 지가변동률 **실데이터** 최근 24개월 누적"*
    이었다. 그 문자열은 `DeskAppraisalReportClient.tsx:570` 등에 **그대로 찍히고**,
    그 계수는 `desk_appraisal_service` 에서 **채택 단가에 곱해진다**.
    """
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async

    # 경남 행은 **없고** 전국만 있는 모집단(정확일치가 거부하는 바로 그 상황).
    _patch_rone(monkeypatch, _many_months("전국"))
    out = await time_adjust_factor_async("경상남도 창원시 의창구 1")

    # ★계약이 `source` 가 아니라 **`scope`** 다(R2 MEDIUM-3 재설계):
    #   프론트가 `source === "R-ONE"` 정확일치로 렌더하므로 그 문자열은 **그대로 둔다** —
    #   동적으로 바꾸면 «고쳤는데 화면에서 사라지는» 형태가 된다.
    #   ⇒ 기계 판독 정직성은 `scope`, 사람이 읽는 정직성은 `rationale` 이 나른다.
    assert out.get("scope") == "전국", out
    assert out["source"] == "R-ONE", out["source"]   # 렌더 계약 보존
    # ★사용자가 읽는 줄이 **거짓 단정**을 하지 않는가.
    assert "해당 지역 실데이터가 아닙니다" in out["rationale"], out["rationale"]
    # 두 모집단 대조 — 지역 시계열이 있는 경우(위 테스트)와 **다른** 라벨이어야 한다.
    assert out["rationale"] != f"R-ONE 지가변동률 실데이터(경남) 최근 24개월 누적 시점수정 {out['factor']}"


@pytest.mark.asyncio
async def test_async_path_actually_uses_the_resolved_address(monkeypatch) -> None:
    """★배선(async) — 주소를 상수로 바꾸면 빨개져야 한다.

    독립 리뷰 실측: `cumulative_factor_from_rows(rows, sido)` → `(rows, "")` 변이가
    **전 저장소를 통과**했다(이 경로를 태우는 락이 0건이었다).
    """
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async

    # 지역별로 **다른** 변동률 → 주소가 쓰이면 결과가 갈린다.
    rows = _many_months("경남", rate=0.05) + _many_months("서울", rate=0.90)
    # ★공허 방지 — 픽스처가 **판정 거부를 넘는가**(안 넘으면 근사표로 떨어져 다른 길을 잰다).
    assert rc.distinct_period_count(rc.rate_series_from_rows(rows, "경남")) >= 24
    _patch_rone(monkeypatch, rows)
    gyeongnam = await time_adjust_factor_async("경상남도 창원시 1")
    seoul = await time_adjust_factor_async("서울특별시 강남구 1")
    assert gyeongnam.get("scope") == "경남" and seoul.get("scope") == "서울", (gyeongnam, seoul)
    assert gyeongnam["factor"] != seoul["factor"], (
        f"주소가 결과를 바꾸지 않는다(배선 끊김): {gyeongnam['factor']} == {seoul['factor']}"
    )


# ─────────────────────────────────────────────────────────────
# ★독립 리뷰 R2 반영 — 판정과 산출이 **같은 필터**를 쓰는가
# ─────────────────────────────────────────────────────────────

def _rows_region_present_but_values_missing() -> list[dict]:
    """★그 지역 **행은 있는데 값이 결측**(`'-'`)인 모집단 — R-ONE 이 실제로 주는 형태.

    ★R2 HIGH-A 가 재현한 자리다: `_has_region` 은 지역**만** 보므로 True 인데,
      시계열을 만드는 `_collect` 는 `DTA_VAL` 이 **숫자로 파싱될 것**까지 보므로 빈다.
      판정과 산출을 갈라 두면 «전국 값을 경남이라고 말하는» 상태가 된다.
    """
    return [
        {"CLS_NM": "경남", "ITM_NM": "변동률", "DTA_VAL": "-", "WRTTIME_IDTFR_ID": f"2024{m:02d}"}
        for m in range(1, 13)
    ] + _many_months("전국")


def test_scope_is_derived_from_the_same_filter_that_built_the_series() -> None:
    """★★행은 있는데 시계열이 없으면 **그 지역이라고 말하면 안 된다**(R2 HIGH-A)."""
    rows = _rows_region_present_but_values_missing()
    # 전제 — 두 축이 실제로 갈리는 모집단인가(공허 방지).
    assert rc._has_region(rows, "경남") is True, "경남 행이 없으면 이 락이 공허하다"
    assert rc.rate_series_from_rows(rows, "경남", _no_fallback=True) == [], "값이 파싱되면 축이 안 갈린다"
    # ★판정은 산출을 따라야 한다.
    assert rc.rate_series_scope(rows, "경남") == "전국", rc.rate_series_scope(rows, "경남")
    # 시계열은 전국 값이어야 한다(경남 값이 섞이면 안 된다).
    assert sorted({r for _t, r in rc.rate_series_from_rows(rows, "경남")}) == [0.05]


@pytest.mark.asyncio
async def test_missing_values_do_not_produce_a_regional_real_data_label(monkeypatch) -> None:
    """그 상태에서 라벨이 «경남 실데이터» 라고 말하면 안 된다(감정평가 문서에 찍힌다)."""
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async

    _patch_rone(monkeypatch, _rows_region_present_but_values_missing())
    out = await time_adjust_factor_async("경상남도 창원시 1")
    assert out.get("scope") == "전국", out
    assert out["source"] == "R-ONE", out["source"]   # 렌더 계약 보존
    assert "해당 지역 실데이터가 아닙니다" in out["rationale"], out["rationale"]


# ── R2 HIGH-E: 표마다 **지역 필드가 다르다** ──

def _jeonse_shaped_rows() -> list[dict]:
    """★전월세전환율 표의 **실측 모양**(2026-09-08 라이브): 지역이 `GRP_NM` 이고
    `CLS_NM` 은 **규모 구분**이다. `CLS_NM` 만 보면 이 표에서 지역이 **0건**이 된다.
    """
    return [
        {"GRP_NM": "서울", "GRP_FULLNM": "서울", "CLS_NM": "전체",
         "ITM_NM": "전월세전환율", "DTA_VAL": 6.6, "WRTTIME_IDTFR_ID": "202607"},
        {"GRP_NM": "도심권", "GRP_FULLNM": "서울>도심권", "CLS_NM": "전체",
         "ITM_NM": "전월세전환율", "DTA_VAL": 5.8, "WRTTIME_IDTFR_ID": "202607"},
        {"GRP_NM": "전국", "GRP_FULLNM": "전국", "CLS_NM": "40㎡이하",
         "ITM_NM": "전월세전환율", "DTA_VAL": 7.1, "WRTTIME_IDTFR_ID": "202607"},
    ]


def test_region_field_differs_per_statistical_table() -> None:
    """★후보 필드 **집합**으로 판정해야 표마다 다른 모양을 견딘다(R2 HIGH-E).

    ★한 표의 모양을 보편이라 가정하면 다른 표에서 **조용히 0건**이 된다 — 그러면
      R-ONE 실측값이 사라지고 하드코딩 기본값으로 떨어지는데, 그 상실이 **고지되지 않는다**.
    """
    rows = _jeonse_shaped_rows()
    assert rc.row_region_names(rows[0]) == {"서울", "전체"}
    # 지역은 GRP_NM 에서 잡힌다.
    assert rc.latest_value_from_rows(rows, "서울") == (6.6, "202607")
    assert rc.latest_value_from_rows(rows, "전국") == (7.1, "202607")
    # ★규모 구분은 시도명과 절대 같아지지 않으므로 오염되지 않는다(판별력).
    assert rc.latest_value_from_rows(rows, "40㎡이하") == (7.1, "202607")  # 명시 조회는 가능
    # ★계층 경로 경유 과매칭은 여전히 금지 — "서울>도심권" 이 «서울» 로 잡히면 안 된다.
    assert rc.latest_value_from_rows([rows[1]], "서울") is None, "GRP_FULLNM 과매칭"


# ── R2 HIGH-F: per-call fail-open(무필터) 제거 ──

def test_latest_value_refuses_when_region_is_unknown() -> None:
    """★지역을 모르면 **거부**한다 — 종전에는 필터가 통째로 꺼져 «가장 늦은 행» 이 이겼다.

    실측(리뷰어): `zzz없는지역` 이 **제주 9.9%** 를 «R-ONE 실측» 으로 받아 자본환원율로 채택됐다.
    """
    rows = [
        {"CLS_NM": "서울", "DTA_VAL": 4.2, "WRTTIME_IDTFR_ID": "202506"},
        {"CLS_NM": "제주", "DTA_VAL": 9.9, "WRTTIME_IDTFR_ID": "202606"},
    ]
    assert rc.latest_value_from_rows(rows, "") is None, "무필터 fail-open 재발"
    # 특이도 — 지역을 알면 그 값을 준다(항상 거부도 결함이다).
    assert rc.latest_value_from_rows(rows, "서울") == (4.2, "202506")
    assert rc.latest_value_from_rows(rows, "제주") == (9.9, "202606")


# ─────────────────────────────────────────────────────────────
# ★R2 HIGH-B / HIGH-C / HIGH-D — 형제 표면과 **사용자 금액에 닿는 배선**
# ─────────────────────────────────────────────────────────────

def _patch_statbl(monkeypatch, rows: list[dict]) -> None:
    """통계표 조회만 스텁 — 해석·범위판정·라벨조립은 진짜 코드가 돈다."""
    import app.services.external_api.reb_client as _rc
    import app.services.land_intelligence.reb_statistics_service as _rs

    async def _fetch(statbl, cycle="MM", size=240, wrttime=None):
        return rows

    monkeypatch.setattr(_rc, "fetch_statbl_rows", _fetch)
    monkeypatch.setattr(_rs, "_statbl", lambda key: "DUMMY_ID")


@pytest.mark.asyncio
async def test_housing_sibling_does_not_claim_regional_real_data(monkeypatch) -> None:
    """★HIGH-B — 형제(`housing_time_adjust`)도 전국 대체를 그 지역인 척 말하면 안 된다.

    실측(리뷰어): `zzz없는지역` 과 `경상남도` 가 **바이트 동일한 답**을 받았다.
    이 셋(`housing`·`cap_rate`·`jeonse`)은 내가 고친 줄 **바로 밑에** 나란히 렌더된다.
    """
    from app.services.land_intelligence.reb_statistics_service import housing_time_adjust

    _patch_statbl(monkeypatch, _many_months("전국"))   # 경남 행 없음
    out = await housing_time_adjust("경상남도 창원시 1")
    assert out is not None
    assert out.get("scope") == "전국", out
    assert out["source"] == "R-ONE", out["source"]   # 렌더 계약 보존(R2 MEDIUM-3)
    # ★사람이 읽는 줄은 **대체 범위를 이름으로** 담아야 한다(기계 변이 [56] 이 약한 단언을 뚫었다).
    assert "전국" in out["basis"], out["basis"]
    assert "해당 지역 실데이터가 아닙니다" in out["basis"], out["basis"]

    # 특이도 — 그 지역 시계열이 있으면 그 지역이라고 말해도 된다.
    _patch_statbl(monkeypatch, _many_months("경남") + _many_months("전국"))
    ok = await housing_time_adjust("경상남도 창원시 1")
    assert ok["source"] == "R-ONE" and ok.get("scope") == "경남", ok


@pytest.mark.asyncio
async def test_cap_rate_refuses_for_unknown_region(monkeypatch) -> None:
    """★HIGH-B/F — 「없는 지역」이 남의 지역 수익률을 받으면 안 된다.

    실측(리뷰어): `zzz없는지역` → **제주 9.9%** 를 «R-ONE … 실측» 으로 받아 채택됐다.
    """
    from app.services.land_intelligence.reb_statistics_service import commercial_cap_rate

    rows = [
        {"CLS_NM": "서울", "DTA_VAL": 4.2, "WRTTIME_IDTFR_ID": "202506"},
        {"CLS_NM": "제주", "DTA_VAL": 9.9, "WRTTIME_IDTFR_ID": "202606"},
    ]
    _patch_statbl(monkeypatch, rows)
    assert await commercial_cap_rate("zzz없는지역 1") is None
    # 특이도 — 아는 지역은 자기 값을 받는다.
    got = await commercial_cap_rate("서울특별시 강남구 1")
    assert got and got["pct"] == 4.2, got


@pytest.mark.asyncio
async def test_market_precision_does_not_call_a_substitute_observed(monkeypatch) -> None:
    """★HIGH-C — 요청 지역 값이 아니면 **OBSERVED 가 아니다**.

    그 모듈은 *"가짜 계수 금지 … UNKNOWN + 미보정 정직 표기"* 를 독스트링에 선언해 놓고
    존재하지 않는 지역도 **관측됨**으로 승격시키고 있었다.
    """
    from app.services.market_precision.time_adjustment import resolve_time_adjustment
    from app.services.provenance.fact_status import FactStatus

    _patch_statbl(monkeypatch, _many_months("전국"))
    sub = await resolve_time_adjustment("경상남도 창원시 1")
    assert sub.status == FactStatus.UNKNOWN, sub.status
    assert "아닙니다" in sub.limitation, sub.limitation

    _patch_statbl(monkeypatch, _many_months("경남") + _many_months("전국"))
    real = await resolve_time_adjustment("경상남도 창원시 1")
    assert real.status == FactStatus.OBSERVED, real.status


@pytest.mark.asyncio
async def test_desk_appraisal_wiring_actually_passes_the_address(monkeypatch) -> None:
    """★★HIGH-D — 사용자 감정평가 금액에 닿는 **유일한 경로**의 배선을 태운다.

    ★리뷰어 실측: `desk_appraisal_service.py` 에서 `time_adjust_factor_async(address, …)` 를
      `("" , …)` 로 바꾸는 변이가 **12,269건을 통과**했다 — 모든 필지의 주소를 버려도 초록이었다.
      내가 추가한 배선 락 둘은 **`land_price_index` 안**만 태웠다(한 층 짧았다).
    """
    from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

    _patch_rone(monkeypatch, _many_months("서울", rate=0.90) + _many_months("경남", rate=0.05))
    seoul = await desk_appraisal(address="서울특별시 강남구 역삼동 1", area_sqm=500.0,
                                 official_price_per_sqm=1_000_000.0)
    gyeongnam = await desk_appraisal(address="경상남도 창원시 의창구 1", area_sqm=500.0,
                                     official_price_per_sqm=1_000_000.0)
    assert seoul.get("time_adjust") != gyeongnam.get("time_adjust"), (
        f"주소가 시점수정을 바꾸지 않는다(배선 끊김): {seoul.get('time_adjust')}"
    )
    # 사유에도 그 지역이 실려야 한다.
    assert "서울" in str(seoul.get("time_adjust_basis") or ""), seoul.get("time_adjust_basis")


# ─────────────────────────────────────────────────────────────
# ★기계 변이 전수(75건 · 생존 10) 트리아지 — **클래스로** 적는다(항목 나열 금지)
#   `scripts/mutate_changed.py --tests <이 파일> --max 300` · base `6f43d1c6010c` · 절단 없음
#
#   (C1) **이중 가드** 1건 — `reb_client.py:171 if not region_sido:` 조기 반환.
#        아래 루프의 집합 판정이 빈 문자열을 어떤 집합에서도 못 찾아 **같은 결과**를 낸다
#        (후보 집합은 빈 값을 담지 않는다). 등가 변이이지 구멍이 아니다 — 사유를 코드에 적었다.
#   (C2) **산문** 8건 — `rationale`·`basis`·`limitation`·`assumption` 문구.
#        §30 대로 표현은 단언하지 않는다. 대신 **의미를 담은 토큰**(대체 범위 이름 ·
#        «해당 지역 실데이터가 아닙니다» · «아닙니다»)만 잠근다. 의미를 뒤집는 변이는 CAUGHT 다.
#   (C3) **약한 단언** 1건 → **봉합했다**: housing 의 `source` 를 `!= "R-ONE"` 로만 봤는데
#        임의 문자열도 그 조건을 만족했다. **대체 범위 이름을 담는지**까지 단언한다.
#
#   ⇒ 새 생존이 나오면 먼저 이 세 클래스에 속하는지 보라. 속하지 않으면 진짜 구멍이다.
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# ★`market_precision` 은 «scope 부재» 를 강등하지 않는다(기존 회귀가드가 옳았다).
#   그 안전성은 **우리 생산자가 항상 scope 를 싣는다**는 데서 온다 — 그것을 여기서 강제한다.
#   이 락이 없으면 «부재는 통과» 가 조용한 fail-open 이 된다.
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_our_producers_always_report_scope(monkeypatch) -> None:
    """R-ONE 값을 돌려주는 우리 생산자는 **예외 없이** `scope` 를 싣는다."""
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async
    from app.services.land_intelligence.reb_statistics_service import housing_time_adjust

    for rows, addr in (
        (_many_months("경남") + _many_months("전국"), "경상남도 창원시 1"),   # 지역 있음
        (_many_months("전국"), "경상남도 창원시 1"),                          # 전국 대체
        (_many_months("전국"), "zzz없는지역 1"),                              # 지역 미해석
    ):
        _patch_rone(monkeypatch, rows)
        ta = await time_adjust_factor_async(addr)
        if ta.get("source") == "R-ONE":
            assert ta.get("scope"), f"time_adjust: scope 누락 {ta}"

        _patch_statbl(monkeypatch, rows)
        h = await housing_time_adjust(addr)
        if h and h.get("source") == "R-ONE":
            assert h.get("scope"), f"housing: scope 누락 {h}"


@pytest.mark.asyncio
async def test_market_precision_demotes_only_on_contradiction(monkeypatch) -> None:
    """★부재(모름)와 모순(다름)을 가른다 — 둘을 뭉치면 기존 계약이 깨진다.

    ★처음엔 «부재도 강등» 으로 짰다가 기존 회귀가드 `test_rone_가용시_observed_실계수` 가
      빨개져 알았다. **그 테스트가 옳았다** — 생산자가 안 알려준 것을 «다르다» 로 지어내면 안 된다.
    """
    from app.services.market_precision import time_adjustment as _ta
    from app.services.provenance.fact_status import FactStatus

    async def _no_scope(*_a, **_k):
        return {"factor": 1.05, "source": "R-ONE", "basis": "x"}

    async def _other_scope(*_a, **_k):
        return {"factor": 1.05, "source": "R-ONE", "basis": "x", "scope": "전국"}

    monkeypatch.setattr(_ta, "housing_time_adjust", _no_scope)
    assert (await _ta.resolve_time_adjustment("서울 강남구 1")).status == FactStatus.OBSERVED

    monkeypatch.setattr(_ta, "housing_time_adjust", _other_scope)
    demoted = await _ta.resolve_time_adjustment("서울 강남구 1")
    assert demoted.status == FactStatus.UNKNOWN, demoted.status
    assert "아닙니다" in demoted.limitation, demoted.limitation
