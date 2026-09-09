"""정식 행정구역명 5개가 「존재하지 않는 지역」과 **똑같이 처리**되던 것을 잠근다(2026-09-08).

■ 무엇이 있었나
`land_price_index._sido_of` 가 축약키(`"전남"`)를 주소에 **부분문자열**로 찾았는데 정식 명칭
`"전라남도"` 에는 그 축약형이 **연속으로 없다**(한글 음절 단위). 정본 표에서 파생한 정식 명칭 **20개 중 6개 실패**(★독립 리뷰 R3 LOW-2 정정 — 종전 산문은
«17개 중 5개» 라 적었으나 파생 모집단은 20개이고 `"전라북도"` 도 실패한다. **락은 파생형이라
20개를 다 태운다 — 테스트가 옳고 산문이 틀렸다**):
충청북도 · 충청남도 · 전라남도 · **전라북도** · 경상북도 · 경상남도.
(전북**특별자치도**·강원특별자치도·제주특별자치도는 **개칭** 덕에 우연히 통과한다.)

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
        # ★독립 리뷰 R3 MEDIUM-5 가 놓친 표기로 지목한 4형태(실측으로 보강했다).
        ("우)13561 경기도 성남시", "경기"),      # 한국에서 더 흔한 표기
        ("[13561] 경기도 성남시", "경기"),
        ("463-400 경기도 성남시", "경기"),        # 구 6자리 하이픈
        ("13561, 경기도 성남시", "경기"),
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
    # ★★분기를 가르는 단언(독립 리뷰 R3 HIGH-1): 종전 단언 셋이 **양 분기에서 모두 참**이었다 —
    #   `scope` 는 분기 **밖**에서 계산되고, 대체 라벨도 `{scope}`·`{sido}` 를 보간해 «경남» 을
    #   담는다. 그래서 `if sido and scope == sido:` 를 `if False:` 로 바꿔도 전부 초록이었다
    #   (내 산문이 내 단언을 공허하게 만든 형태 — 이 저장소가 이미 기록한 결함이다).
    #   ⇒ **정직 분기에서만 참인 것**을 단언한다: 대체 문구가 **없어야** 한다.
    assert "해당 지역 실데이터가 아닙니다" not in out["rationale"], out["rationale"]
    assert "시계열이 없어" not in out["rationale"], out["rationale"]


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
    # ★`basis` 까지 본다 — 종전엔 `source`·`scope` 만 봐서 분기를 무력화해도 초록이었다(R3 HIGH-1).
    assert "해당 지역 실데이터가 아닙니다" not in ok["basis"], ok["basis"]
    assert "시계열이 없어" not in ok["basis"], ok["basis"]
    # ★★양성 단언(전수 기계 변이 2026-09-08 이 이 자리를 짚었다): 위 둘은 **음성 단언**이라
    #   `basis` 에서 지역 식별자 `({sido})` 를 **통째로 빼도 전부 참**이다(실측 SURVIVED).
    #   그러면 일치 분기와 대체 분기가 `basis` 만으로는 **구별 불가**가 되고, 화면은 어느 지역의
    #   데이터인지 말하지 못한 채 «R-ONE 실측» 으로 보인다.
    #   ⇒ 일치 분기는 **그 지역을 이름으로 말해야 한다**(대체 분기가 `전국` 을 말하는 것과 대칭).
    assert "경남" in ok["basis"], ok["basis"]


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
# ★기계 변이 전수(**86건 · 생존 11 → 봉합 후 10**) 트리아지 — **클래스로** 적는다
#   `scripts/mutate_changed.py --only apps/api --tests <이 파일> --max 400`
#   base `6f43d1c6010c`(공통 조상) · **절단 없음**(86/86) · venv Python 3.12.3
#
#   ★★이 줄이 낡아 있었다(독립 리뷰 R4 지적 · 2026-09-08). 종전 값 `75건 · 생존 10` 은
#     **R3 이전 판**의 것인데 그대로 남아, 이 파일을 읽는 사람이 «전수는 이미 돌았다»고 읽었다.
#     ★그리고 나는 R3 라운드에서 **손으로 고른 6건**만 돌리고 «전건 반영» 이라 보고했다 —
#       리뷰어 전수는 `82건 · 생존 15` 였다. **「N/N CAUGHT」의 분모를 내가 정하면 측정이 아니다.**
#     ⇒ 이 주석을 고칠 때는 **명령·base·절단 여부·인터프리터**를 함께 적는다(재현 가능해야 한다).
#
#   (C1) **이중 가드** 1건 — `reb_client.py:171 if not region_sido:` 조기 반환.
#        아래 루프의 집합 판정이 빈 문자열을 어떤 집합에서도 못 찾아 **같은 결과**를 낸다
#        (후보 집합은 빈 값을 담지 않는다). 등가 변이이지 구멍이 아니다 — 사유를 코드에 적었다.
#   (C2) **산문** 8건 — `rationale`·`basis`·`limitation`·`assumption` 문구.
#        §30 대로 표현은 단언하지 않는다. 대신 **의미를 담은 토큰**(대체 범위 이름 ·
#        «해당 지역 실데이터가 아닙니다» · «아닙니다»)만 잠근다. 의미를 뒤집는 변이는 CAUGHT 다.
#   (C3) **약한 단언** → **봉합했다**(2회): ①housing 의 `source` 를 `!= "R-ONE"` 로만 봤는데
#        임의 문자열도 그 조건을 만족했다 → **대체 범위 이름을 담는지**까지 단언한다.
#        ②`reb_statistics_service.py:77` 일치 분기의 `basis` 를 **음성 단언만** 하고 있어
#        («…아닙니다»·«시계열이 없어» 가 **없다**), 지역 식별자 `({sido})` 를 통째로 빼도
#        전부 참이었다(실측 SURVIVED) → **양성 단언**을 더했다(«경남» 이 basis 에 있어야 한다).
#        ★음성 단언은 아무것도 잠그지 않는다 — 두 분기가 구별 불가가 된다.
#   (C4) **도달 불가 방어** 1건 — `reb_client.py:222 tied: set[float] = set()` 초기화 삭제.
#        `tied` 는 `best` 와 **항상 같은 분기에서 함께** 대입되고, `best is None` 이면 그전에
#        반환하므로 이 초기화는 읽히지 않는다. 등가 변이다(사유를 그 자리에 적었다).
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


# ─────────────────────────────────────────────────────────────
# ★H4 — 배선을 **파생형 소스 락**으로 잠근다(호출부를 손으로 나열하지 않는다)
#
#   R2 가 «락이 `land_price_index` 안만 태워 한 층 짧다» 고 지적해 `desk_appraisal()` 층을
#   잠갔더니, R3 가 **그 바깥 3곳**(다필지 PDF 라우터 · rough_feasibility · avm_vision)에서
#   같은 변이가 생존함을 실증했다. **한 층씩 따라가면 다음 리뷰가 다음 층을 찾는다.**
#   ⇒ 축을 «호출부 목록» 이 아니라 **«AST 로 파생한 전 호출부»** 로 올린다:
#     주소를 받는 진입점들이 **주소를 실제로 넘기는가**(빈 리터럴이 아닌가)를 전수 단언한다.
#   ★이것은 «불린다» 가 아니라 «무엇을 넘기는가» 를 본다 — 값이 죽으면 잡힌다.
# ─────────────────────────────────────────────────────────────

# ★★독립 리뷰 R4 HIGH-2 + R3 재측정(2026-09-08) — **한 락 안에 축이 셋인데 둘만 파생이었다**:
#     · 스캔할 **파일**  = `rglob` 파생        ◎
#     · **호출부** 탐지  = `ast.walk` 전수     ◎
#     · **소비처 이름**  = 손 목록 3개         ✘ ← 여기가 상한이었다
#   실측: 손 목록 3 → 임포트 그래프 파생 **11** · 감시 호출부 10 → **17**.
#   빠져 있던 `get_market_stats` 는 **나머지 다섯 지표로 갈라지는 단일 팬아웃**이고 호출부가
#   **단 1곳**이라, 그 한 줄을 `get_market_stats("")` 로 바꾸면 자본환원율·전월세전환율·
#   주택지수·지가추이의 지역 해석이 **동시에** 죽는데 `68 passed` ::VERDICT=SURVIVED 였다.
#   ★공허 방지 가드가 그것을 **가리고 있었다** — `seen >= 5` 가 **10 으로 넉넉히 만족**했다.
#     하한을 여유 있게 넘는 것은 **모집단이 옳다는 증거가 아니다**.
#
# ★그리고 리뷰어가 **판정 축**도 뚫었다: 같은 자리에서
#     `address=""`        → CAUGHT   (구문이 빈 리터럴)
#     `address=address[:0]` → SURVIVED (런타임 효과는 **동일**)
#   ⇒ 구문 검사는 **넓이**만 담당하고, **깊이**는 「도착한 값」을 보는 행위 락이 맡는다(아래 둘째).

_ADDRESS_SSOT_MODULE = "app.services.external_api.reb_client"   # 지역해석의 단일 원천
_ADDRESS_CONSUMER_DEPTH = 2
# 공허 방지 하한 — 실측 소비처 11 · 호출부 17(2026-09-08). 손 목록 시절의 3·10 으로
# 되돌아가면 반드시 걸리도록 그 위에 둔다.
_ADDRESS_CONSUMER_FLOOR = 9
_ADDRESS_CALLSITE_FLOOR = 14
# ★팬아웃 앵커 — **모집단이 아니라 파생기의 생존 증명**이다(집합을 이것으로 제한하지 않는다).
_ADDRESS_FANOUT_ANCHOR = "get_market_stats"


def _parse_app_modules():
    """app/ 전 모듈을 한 번만 파싱해 (점표기, tree, 임포트, public address 함수)를 낸다."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    out = []
    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 파싱 불가 파일은 건너뛴다
            continue
        dotted = "app." + str(py.relative_to(root)).removesuffix(".py").replace("/", ".")
        imports, addr_fns = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                names = [x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)]
                if "address" in names and not node.name.startswith("_"):
                    addr_fns.add(node.name)
        out.append((dotted, tree, imports, addr_fns))
    return out


def _derive_address_consumers(mods) -> set[str]:
    """SSOT(`reb_client`)에서 깊이 ≤2 로 닿는 모듈의 public `address` 함수를 파생한다.

    ★깊이 2 는 단정이 아니라 **실측으로 고른 경계**다(2026-09-08):
        1촌 = 8개(지역해석 **생산자** 전부) · 2촌 = +3개(`desk_appraisal` ·
        `resolve_time_adjustment` · 라우터 `price_trend`) · **3촌부터 지역해석과 무관한 함수**가
        섞인다. `app/` 전체로 넓히면 `address` 를 받는 함수가 **190개**라 명백히 과대다.
    """
    layer = {_ADDRESS_SSOT_MODULE}
    seen_mods = {_ADDRESS_SSOT_MODULE}
    consumers: set[str] = set()
    for _ in range(_ADDRESS_CONSUMER_DEPTH):
        nxt = {d for d, _t, imps, _f in mods if d not in seen_mods and any(t in layer for t in imps)}
        if not nxt:
            break
        for d, _t, _i, fns in mods:
            if d in nxt:
                consumers |= fns
        seen_mods |= nxt
        layer = nxt
    return consumers


def test_address_consumer_set_is_derived_not_enumerated() -> None:
    """★파생기 자체가 살아 있는가 — 붕괴하면 아래 배선 락이 **조용히 공허**해진다.

    (SSOT 이름이 바뀌어 집합이 비어도 `not offenders` 는 참이다 — 그래서 따로 단언한다.)
    """
    consumers = _derive_address_consumers(_parse_app_modules())
    assert len(consumers) >= _ADDRESS_CONSUMER_FLOOR, (
        f"주소 소비처를 {len(consumers)}개만 파생했다(하한 {_ADDRESS_CONSUMER_FLOOR}) — "
        f"SSOT 이름이 바뀌었거나 임포트 경로가 끊겼다: {sorted(consumers)}"
    )
    assert _ADDRESS_FANOUT_ANCHOR in consumers, (
        f"단일 팬아웃 `{_ADDRESS_FANOUT_ANCHOR}` 가 파생 집합에서 사라졌다: {sorted(consumers)}"
    )


def test_every_call_site_passes_a_real_address_not_a_literal() -> None:
    """★전 호출부(AST 파생)가 `address=` 에 **빈 리터럴을 넘기지 않는다**(넓이 축).

    ★이 락이 잡는 것은 «구문이 빈 리터럴인가» 뿐이다 — `address[:0]` 처럼 **런타임에만 비는**
      형태는 원리적으로 못 잡는다(리뷰어 실증). 그 축은 아래 행위 락이 맡는다.
    """
    import ast

    mods = _parse_app_modules()
    consumers = _derive_address_consumers(mods)
    offenders: list[str] = []
    per_consumer: dict[str, int] = {}
    for dotted, tree, _imports, _fns in mods:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name not in consumers:
                continue
            per_consumer[name] = per_consumer.get(name, 0) + 1
            arg = next((k.value for k in node.keywords if k.arg == "address"), None)
            if arg is None and node.args:
                arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and not arg.value.strip():
                offenders.append(f"{dotted}:{node.lineno} {name}(address='')")
    seen = sum(per_consumer.values())
    assert seen >= _ADDRESS_CALLSITE_FLOOR, (
        f"호출부를 {seen}건만 찾았다(하한 {_ADDRESS_CALLSITE_FLOOR}) — "
        f"수집기가 죽었거나 소비처 파생이 좁아졌다: {per_consumer}"
    )
    # ★팬아웃 자리는 호출부가 **단 1곳**이라, 그 1건이 스캔에서 빠지면 집계 하한만으로는 묻힌다.
    assert per_consumer.get(_ADDRESS_FANOUT_ANCHOR, 0) >= 1, (
        f"`{_ADDRESS_FANOUT_ANCHOR}` 호출부를 한 건도 못 찾았다 — 팬아웃이 무감시다: {per_consumer}"
    )
    assert not offenders, (
        "주소를 받는 진입점이 **빈 리터럴**을 넘긴다 — 모든 필지가 같은 값을 받게 된다:\n  "
        + "\n  ".join(offenders)
    )


# ─────────────────────────────────────────────────────────────
# ★R4 HIGH-1 — 카디널리티 블록에 **락이 하나도 없었다**
#
#   R3 라운드에서 행동을 가장 많이 바꾼 자리인데, 나는 **손으로 고른 변이 6건**만 돌리고
#   «전건 반영» 이라고 보고했다. 독립 리뷰가 전수로 돌리자 `75건·생존 10` 이
#   **`82건·생존 15`** 가 됐고, 늘어난 5건이 **전부 이 블록**이었다. 재현(2026-09-08):
#       `if len(tied) > 1:` → `if False:`      → 68 passed  ::VERDICT=SURVIVED
#       `tied = {round(val, 6)}` → `pass`      → 68 passed  ::VERDICT=SURVIVED
#       (대조군 `region_sido not in …` → `if False:` → 5 failed ::VERDICT=CAUGHT — 조회기 생존)
#   ★이 파일의 모든 픽스처가 (지역,시점)당 **1행**이라 이 분기는 **도달조차 하지 않았다**.
#     ⇒ 분기를 만들었으면 **그 분기를 태우는 행**을 같은 커밋에(§B-9).
# ─────────────────────────────────────────────────────────────

# 규모 구분 표의 실제 모양(라이브 실측 `A_2024_00615` — 지역은 GRP_NM, 규모는 CLS_NM).
_SIZE_CLASSES = ("전체", "40㎡이하", "40㎡초과 60㎡이하", "60㎡초과 85㎡이하", "85㎡초과")


def _size_rows(region: str, wrttime: str, values: tuple[float, ...]) -> list[dict]:
    """한 (지역,시점)에 규모 구분 5행 — 라이브가 실제로 내는 모양."""
    assert len(values) == len(_SIZE_CLASSES)
    return [
        {"GRP_NM": region, "CLS_NM": cls, "ITM_NM": "지수",
         "DTA_VAL": val, "WRTTIME_IDTFR_ID": wrttime}
        for cls, val in zip(_SIZE_CLASSES, values, strict=True)
    ]


def test_latest_value_picks_the_aggregate_row_when_present() -> None:
    """★집계 행(`전체`)이 있으면 **그것을 고른다** — 거부가 아니라 해석한다.

    라이브 실측값 그대로: `(서울, 202607)` 5행 · `전체`=100.656133…
    ★(지역,시점) 조합 **442개 전부**에 `전체` 가 정확히 1행씩 있었다(예외 0) — 그래서 좁힌다.
    """
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = _size_rows("서울", "202607",
                      (100.656133, 100.338932, 101.111603, 102.249849, 105.224865))
    got = latest_value_from_rows(rows, "서울")
    assert got is not None, "집계 행이 있는데 거부했다 — 좁히기가 안 걸렸다"
    assert got == (100.6561, "202607"), got
    # ★대조 모집단 — 규모 행 하나를 고르면 **다른 값**이 나온다(픽스처가 차를 만든다).
    assert got[0] != 105.2249, "집계 행과 최대 규모 행이 같은 값이면 이 락은 아무것도 안 가른다"


def test_latest_value_rejects_ambiguity_when_there_is_no_aggregate_row() -> None:
    """★집계 표기가 없는 표에서 값이 갈리면 **여전히 거부**한다(최후 방어).

    상업용수익률 표 모양(라이브 실측: `CLS_NM` 이 **상권명** — `강남`·`광복동`·`금호지구`).
    """
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = [
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 5.4, "WRTTIME_IDTFR_ID": "202607"},
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 7.9, "WRTTIME_IDTFR_ID": "202607"},
    ]
    assert latest_value_from_rows(rows, "서울") is None, (
        "값이 갈리는데 하나를 골랐다 — 행 순서가 사용자 금액을 정하게 된다"
    )


def test_latest_value_accepts_when_same_period_rows_agree() -> None:
    """★거부가 **담요가 아님**을 가른다 — 같은 시점 여러 행이 **같은 값**이면 채택한다."""
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = [
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 5.4, "WRTTIME_IDTFR_ID": "202607"},
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 5.4, "WRTTIME_IDTFR_ID": "202607"},
    ]
    assert latest_value_from_rows(rows, "서울") == (5.4, "202607")


def test_latest_value_resets_the_tie_set_when_a_newer_period_wins() -> None:
    """★더 늦은 시점이 이기면 **동률 집합도 갱신**돼야 한다.

    안 그러면 옛 시점의 갈린 값들이 남아 **최신 시점이 단일 행인데도 거부**된다
    (과다 거부 = 조용한 기본값 폴백). 변이 `tied = {round(val, 6)}` → `pass` 가 이것을 만든다.
    """
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = [
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 5.4, "WRTTIME_IDTFR_ID": "202605"},
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 7.9, "WRTTIME_IDTFR_ID": "202605"},
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 6.1, "WRTTIME_IDTFR_ID": "202607"},
    ]
    assert latest_value_from_rows(rows, "서울") == (6.1, "202607"), (
        "옛 시점의 동률이 최신 시점 판정에 남아 있다"
    )


def test_aggregate_narrowing_is_inert_without_the_marker() -> None:
    """★특이도 — 집계 표기가 없는 표에서 좁히기는 **아무 행도 버리지 않는다**.

    (좁히기가 무조건 걸리면 상업용수익률 표는 전 지역 0건이 된다.)
    """
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = [
        {"CLS_NM": "서울", "ITM_NM": "투자수익률", "DTA_VAL": 6.96, "WRTTIME_IDTFR_ID": "2005"},
    ]
    assert latest_value_from_rows(rows, "서울") == (6.96, "2005")


# ─────────────────────────────────────────────────────────────
# ★R4 HIGH-2(깊이 축) — 판정을 **구문 모양**에서 **「도착한 값」**으로 올린다
#
#   위 넓이 축은 «호출부에 빈 리터럴이 적혀 있는가» 만 본다. 리뷰어가 같은 자리에서
#       `address=""`          → CAUGHT
#       `address=address[:0]` → **SURVIVED**   ← 런타임 효과는 동일
#   을 실증했다. 구문으로는 원리적으로 못 가른다 ⇒ **소비처에 실제로 무엇이 도착했는지**를 본다.
#   ★소비처 목록은 여기서도 **파생**이다(손으로 적으면 위 결함이 이 락에서 재발한다).
# ─────────────────────────────────────────────────────────────

_WIRED_ADDRESS = "서울특별시 강남구 역삼동 1"
# 공허 방지 — desk_appraisal 한 번 호출로 실제 발화하는 소비처 수의 하한(실측 기반).
_WIRED_CONSUMER_FLOOR = 2


@pytest.mark.asyncio
async def test_wired_consumers_receive_the_real_address_not_an_emptied_one(monkeypatch) -> None:
    """★파생한 소비처 전부에 감시자를 달고 `desk_appraisal` 을 한 번 태운다.

    발화한 소비처가 받은 `address` 는 **입력과 글자 그대로 같아야** 한다.
    `""` · `address[:0]` · `address.strip()[:0]` 처럼 **무엇으로 비우든** 이 락이 잡는다.
    """
    import importlib
    import inspect

    mods = _parse_app_modules()
    consumers = _derive_address_consumers(mods)
    received: dict[str, list[object]] = {}

    def _address_of(fn_obj, args, kwargs):
        try:
            bound = inspect.signature(fn_obj).bind_partial(*args, **kwargs)
            return bound.arguments.get("address", "<미전달>")
        except TypeError:  # pragma: no cover - 시그니처 불일치는 원본이 알아서 터진다
            return "<바인딩실패>"

    for dotted, _tree, _imports, fns in mods:
        for fn in sorted(fns & consumers):
            try:
                mod = importlib.import_module(dotted)
            except Exception:  # pragma: no cover - 임포트 불가 모듈은 이 락의 대상이 아니다
                continue
            orig = getattr(mod, fn, None)
            if not callable(orig):
                continue

            def _make(fn=fn, orig=orig):
                if inspect.iscoroutinefunction(orig):
                    async def spy(*a, **kw):
                        received.setdefault(fn, []).append(_address_of(orig, a, kw))
                        return await orig(*a, **kw)
                else:
                    def spy(*a, **kw):
                        received.setdefault(fn, []).append(_address_of(orig, a, kw))
                        return orig(*a, **kw)
                return spy

            monkeypatch.setattr(mod, fn, _make())

    _patch_rone(monkeypatch, _many_months("서울", rate=0.90))
    from app.services.land_intelligence.desk_appraisal_service import desk_appraisal

    await desk_appraisal(address=_WIRED_ADDRESS, area_sqm=500.0,
                         official_price_per_sqm=1_000_000.0)

    # ★공허 방지 — 감시자가 실제로 발화했는가(0이면 이 락은 아무것도 안 본다).
    assert len(received) >= _WIRED_CONSUMER_FLOOR, (
        f"소비처가 {len(received)}개만 발화했다(하한 {_WIRED_CONSUMER_FLOOR}) — "
        f"감시자가 안 걸렸거나 배선이 끊겼다: {sorted(received)}"
    )
    # ★팬아웃이 실제로 태워졌는가 — 이 자리가 R4 가 실증한 SURVIVED 지점이다.
    assert _ADDRESS_FANOUT_ANCHOR in received, (
        f"`{_ADDRESS_FANOUT_ANCHOR}` 가 발화하지 않았다 — 팬아웃이 이 락 밖이다: {sorted(received)}"
    )
    mangled = {
        fn: vals for fn, vals in received.items()
        if any(v != _WIRED_ADDRESS for v in vals)
    }
    assert not mangled, (
        "소비처에 **입력과 다른 주소**가 도착했다 — 그 지표는 모든 필지에서 같은 값이 된다:\n  "
        + "\n  ".join(f"{fn}: {vals!r}" for fn, vals in sorted(mangled.items()))
    )


# ─────────────────────────────────────────────────────────────
# ★부채(초록 안에 보이게) — 지수형 표는 시점수정을 **원리적으로 못 낸다**
#   라이브 실측 2026-09-08: 주택매매가격지수 `A_2024_00615` 의 `distinct_ITM_NM` = `['지수']`.
#   `rate_series_from_rows` 는 `"변동" not in itm` 인 행을 버리므로 시계열이 `[]` 가 되고,
#   `housing_time_adjust` → `resolve_time_adjustment` 가 **base·branch 모두** UNKNOWN 이다
#   (이 PR 이 만든 회귀가 아니다 — 양쪽에서 같이 죽어 있다).
#   지수형은 ∏(1+r) 이 아니라 `index[t1]/index[t0]` 로 계산해야 한다 — **별건**이라 여기서는
#   고치지 않고, 고치면 이 xfail 이 **strict 라 빨개져** 마커를 지우게 만든다.
# ─────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason="★부채: 지수형(ITM_NM='지수') 표에서 시점수정 계수 미산출 — index[t1]/index[t0] 미구현",
)
def test_index_typed_table_should_yield_a_time_adjust_factor() -> None:
    """지수형 표만 있는 상태에서도 시점수정 계수가 나와야 한다(미구현 — strict xfail)."""
    from app.services.external_api.reb_client import cumulative_factor_from_rows

    # ★★픽스처는 **라이브 모양**이어야 한다(독립 리뷰 R5 MEDIUM-4).
    #   종전 픽스처는 (지역,시점)당 **1행**이었다. 그것을 보고 구현하는 사람은 «집계행만 오는 표»
    #   를 가정하게 되고, 실제 표에서는 **규모 5행**을 받아 5배 팽창한 시계열로 계산한다
    #   — 이 PR 이 방금 고친 결함(R5 HIGH-3)과 **같은 뿌리**다. 부채 픽스처가 다음 결함의 씨앗이 된다.
    rows = [
        {"GRP_NM": "서울", "CLS_NM": cls, "ITM_NM": "지수",
         "DTA_VAL": base + i * 0.1 + offset, "WRTTIME_IDTFR_ID": f"{yr}{i:02d}"}
        for yr, base in (("2024", 100.0), ("2025", 101.2))
        for i in range(1, 13)
        for offset, cls in enumerate(_SIZE_CLASSES)
    ]
    # ★공허 방지 — 픽스처가 실제로 다행인가(1행이면 이 부채의 취지가 사라진다).
    assert len(rows) == 24 * len(_SIZE_CLASSES), len(rows)
    assert cumulative_factor_from_rows(rows, "서울") is not None


# ─────────────────────────────────────────────────────────────
# ★R5 HIGH-3 / MEDIUM-2 — 좁히기를 **공용 헬퍼**로 빼고 **시점 단위**로 판정한다
#
#   HIGH-3: 좁히기를 `latest_value_from_rows` **한 함수에만** 넣었더니, 같은 표 모양을 받는
#           형제 `rate_series_from_rows` 가 그대로였다. 리뷰어 실측 —
#             규모 5행 × 24개월 → series **120** · cumulative **None** · yearly **30.0%**
#           정답은 series 24 · cumulative 1.1272 · yearly **6.0%**. 이 PR 의 표제 결함
#           («경기 yearly 2024 = +80.68%»)과 **같은 산수**다. `trend_from_rows` 는 저장소
#           **참조 0건**이라 아무도 안 보고 있었다.
#   MEDIUM-2: 표 전체에 걸쳐 한 번에 걸렀더니, 최신 시점에만 집계행이 없을 때 그 시점이
#           **통째로 사라져** 한 달 묵은 값이 «최신» 인 척 반환됐다(base 는 거부했다).
#           ⇒ **시점 단위**로 판정한다.
# ─────────────────────────────────────────────────────────────


def _size_series_rows(region: str, periods: list[str], rate: float = 0.5) -> list[dict]:
    """규모 구분 5행 × N개월 — 라이브 표 모양(지역=GRP_NM · 규모=CLS_NM)."""
    return [
        {"GRP_NM": region, "CLS_NM": cls, "ITM_NM": "변동률",
         "DTA_VAL": rate, "WRTTIME_IDTFR_ID": t}
        for t in periods for cls in _SIZE_CLASSES
    ]


_TWO_YEARS = [f"2024{m:02d}" for m in range(1, 13)] + [f"2025{m:02d}" for m in range(1, 13)]


def test_size_split_rows_do_not_inflate_the_series() -> None:
    """★규모 5행이 시계열을 **5배로 부풀리지 않는다**(형제 추출기도 좁히기를 받는다)."""
    from app.services.external_api.reb_client import rate_series_from_rows

    series = rate_series_from_rows(_size_series_rows("서울", _TWO_YEARS), "서울")
    assert len(series) == len(_TWO_YEARS), (
        f"시계열이 {len(series)}건 — 규모 구분 행이 그대로 들어왔다(기대 {len(_TWO_YEARS)})"
    )


def test_size_split_rows_do_not_inflate_the_yearly_trend() -> None:
    """★화면이 그리는 연간 변동률이 **부풀지 않는다** — 여기가 사용자가 보는 자리다."""
    from app.services.external_api.reb_client import trend_from_rows

    tr = trend_from_rows(_size_series_rows("서울", _TWO_YEARS, rate=0.5), "서울", 24)
    yearly = {y["year"]: y["rate"] for y in tr.get("yearly", [])}
    assert yearly, "연간 통계가 비었다(수집기 사망)"
    # 월 0.5% × 12개월 = 6.0%. 규모 5행이 새면 30.0% 가 된다(리뷰어 실측값).
    assert yearly.get("2024") == 6.0, f"연간 변동률이 부풀었다: {yearly}"
    assert yearly.get("2025") == 6.0, f"연간 변동률이 부풀었다: {yearly}"


def test_size_split_rows_still_yield_a_cumulative_factor() -> None:
    """★부풀리기를 막느라 **정당한 계수까지 죽이지 않는다**(위양성 축)."""
    from app.services.external_api.reb_client import cumulative_factor_from_rows

    got = cumulative_factor_from_rows(_size_series_rows("서울", _TWO_YEARS), "서울", 24)
    assert got == 1.1272, f"누적계수가 안 나온다(고유 기간 부족으로 거부됐나): {got}"


def test_missing_aggregate_at_the_latest_period_rejects_not_returns_stale() -> None:
    """★최신 시점에 집계행이 없으면 **거부**한다 — 구값을 최신인 척 내보내지 않는다."""
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = [
        {"GRP_NM": "서울", "CLS_NM": "전체", "DTA_VAL": 5.0, "WRTTIME_IDTFR_ID": "202607"},
        {"GRP_NM": "서울", "CLS_NM": "40㎡이하", "DTA_VAL": 4.0, "WRTTIME_IDTFR_ID": "202607"},
        {"GRP_NM": "서울", "CLS_NM": "40㎡이하", "DTA_VAL": 8.0, "WRTTIME_IDTFR_ID": "202608"},
        {"GRP_NM": "서울", "CLS_NM": "85㎡초과", "DTA_VAL": 9.0, "WRTTIME_IDTFR_ID": "202608"},
    ]
    assert latest_value_from_rows(rows, "서울") is None, (
        "최신 시점에 집계행이 없는데 한 달 묵은 값을 «최신»으로 돌려줬다"
    )
    # ★두 모집단을 가른다 — 최신 시점에도 집계행이 있으면 **그 값을 채택**한다.
    ok = [*rows, {"GRP_NM": "서울", "CLS_NM": "전체", "DTA_VAL": 7.0, "WRTTIME_IDTFR_ID": "202608"}]
    assert latest_value_from_rows(ok, "서울") == (7.0, "202608")


# ─────────────────────────────────────────────────────────────
# ★R5 MEDIUM-1 — 감시자 락은 「값이 망가지는」 축만 봤다. **「호출이 사라지는」 축**은 무잠금이었다
#
#   리뷰어 실측: `cap = await commercial_cap_rate(address)` → `cap = None`
#     → `75 passed, 7 xfailed` ::VERDICT=SURVIVED
#   자본환원율 조회를 **통째로 끊어도** 전 락이 초록이었다(desk_appraisal 이 조용히 기본값으로
#   떨어진다). 원인은 `_WIRED_CONSUMER_FLOOR = 2` 인데 실제 발화가 **7** 이라는 것 —
#   ★내가 바로 그 위 주석에 «하한을 여유 있게 넘는 것은 모집단이 옳다는 증거가 아니다» 라고
#     써 놓고 새 하한에서 같은 것을 했다.
#
#   ★★하한을 올리는 것만으로는 못 잡는다 — **호출부가 사라지면 파생 집합도 같이 줄어든다.**
#     그래서 축을 «몇 개가 불렸나» 가 아니라 **«무엇이 응답에 실렸나»**(효과)로 옮긴다.
# ─────────────────────────────────────────────────────────────

# R-ONE 이 값을 줄 때 `get_market_stats` 가 **반드시 실어야 하는** 통계들.
# ★목록이 아니라 **계약**이다 — 하나라도 조용히 빠지면 화면은 그 자리에 문서화된 기본값을
#   그리면서 아무 말도 하지 않는다(사용자는 R-ONE 을 봤다고 믿는다).
_RONE_BACKED_STATS = ("housing_time_adjust", "cap_rate", "jeonse_conversion_rate", "land_price_trend")


@pytest.mark.asyncio
async def test_market_stats_carries_every_rone_backed_statistic(monkeypatch) -> None:
    """★R-ONE 이 값을 주면 **네 통계가 전부 응답에 실린다** — 하나라도 끊기면 잡힌다."""
    from app.services.land_intelligence.reb_statistics_service import get_market_stats

    # 규모 구분 5행 × 24개월 — 라이브 표 모양 그대로(집계행 포함).
    # ★값 2.5 는 네 통계의 sane 범위를 **동시에** 만족하도록 고른 것이다
    #   (cap 1.0~12.0 · 전월세 2.0~12.0 · 누적계수 0.5~2.0 → 1.025**24 = 1.81).
    #   한 픽스처로 넷을 태우려면 그 교집합 안에 있어야 한다.
    rows = _size_series_rows("서울", _TWO_YEARS, rate=2.5)
    _patch_statbl(monkeypatch, rows)
    _patch_rone(monkeypatch, rows)   # land_price_trend 는 다른 통로(fetch_land_price_changes)를 탄다
    ms = await get_market_stats("서울특별시 강남구 1")

    missing = [k for k in _RONE_BACKED_STATS if not ms.get(k)]
    assert not missing, (
        f"R-ONE 이 값을 주는데 응답에서 빠진 통계가 있다 — 그 자리는 화면에서 조용히 "
        f"기본값이 된다: {missing} / 실린 키={sorted(k for k, v in ms.items() if v)}"
    )
    assert ms.get("rone_available") is True, ms.get("rone_available")

    # ★두 모집단을 가른다 — R-ONE 이 아무것도 못 주면 그 사실이 응답에 드러나야 한다.
    _patch_statbl(monkeypatch, [])
    _patch_rone(monkeypatch, [])
    empty = await get_market_stats("서울특별시 강남구 1")
    assert not any(empty.get(k) for k in _RONE_BACKED_STATS), empty
    assert empty.get("rone_available") is False, empty.get("rone_available")


@pytest.mark.asyncio
async def test_region_resolved_tells_the_truth_about_address_parsing(monkeypatch) -> None:
    """★`region_resolved` 가 **실제 해석 여부**를 말한다(R5 LOW-1 봉합의 잠금).

    ★이 락은 **처방을 넣고 잠그지 않아** 변이가 생존한 것을 보고 뒤늦게 붙였다
      (`"region_resolved": True` 고정 → 80 passed ::VERDICT=SURVIVED).
      필드를 만든 커밋에서 같이 잠갔어야 했다(§A-1 — 나중은 오지 않는다).
    """
    from app.services.land_intelligence.reb_statistics_service import get_market_stats

    _patch_statbl(monkeypatch, [])
    _patch_rone(monkeypatch, [])

    resolved = await get_market_stats("서울특별시 강남구 역삼동 1")
    assert resolved["region_resolved"] is True, resolved
    assert resolved["region"] == "서울", resolved

    # ★반대 모집단 — 시·도를 해석할 수 없는 주소는 그 사실을 말해야 한다.
    #   `region` 은 여전히 "전국" 이다(기존 소비처 계약) — 그래서 **별도 필드**가 필요했다.
    unresolved = await get_market_stats("zzz없는지역 123")
    assert unresolved["region_resolved"] is False, unresolved
    assert unresolved["region"] == "전국", unresolved


# ─────────────────────────────────────────────────────────────
# ★R6 HIGH-1 — 「공용 헬퍼로 뺐다」가 「축을 공유했다」를 뜻하지 않았다
#
#   R5 대응에서 좁히기를 `narrow_to_period_aggregate()` 로 빼서 두 추출기가 함께 쓰게 했다.
#   그런데 **적용 지점**이 달랐다 — `latest_value_from_rows` 는 **지역 필터 뒤**, `_collect` 는
#   **전 행**. 그래서 한 시점에 **다른 지역**이 집계행을 가지면 집계행 없는 지역의 행이
#   그 시점에서 통째로 사라졌다(리뷰어 실증, 내가 재현):
#       latest_value_from_rows(rows,"경기") = (0.3, '202607')   ← 유일행
#       rate_series_from_rows(rows,"경기")  = []                ← 같은 행이 사라졌다
#
#   ★★락이 못 본 이유: `_size_series_rows` 가 **한 지역만** 만든다. 단일 지역에서는
#     두 적용 지점이 **원리적으로 같은 답**을 낸다 — 저장소 §「픽스처는 두 모집단을 갈라야 한다」.
#     그래서 여기서는 **집계행을 가진 지역 + 갖지 않은 지역**을 같은 표에 넣는다.
# ─────────────────────────────────────────────────────────────


def _mixed_region_rows(periods: list[str]) -> list[dict]:
    """한 표에 두 지역 — 서울은 규모 구분(집계행 있음) · 경기는 단일 행(집계행 없음)."""
    out: list[dict] = []
    for t in periods:
        out += [
            {"GRP_NM": "서울", "CLS_NM": cls, "ITM_NM": "변동률",
             "DTA_VAL": 0.5, "WRTTIME_IDTFR_ID": t}
            for cls in _SIZE_CLASSES
        ]
        out.append({"GRP_NM": "경기", "CLS_NM": "시군구계", "ITM_NM": "변동률",
                    "DTA_VAL": 0.3, "WRTTIME_IDTFR_ID": t})
    return out


def test_another_regions_aggregate_row_does_not_delete_mine() -> None:
    """★남의 지역 집계행이 **내 지역 행을 지우지 않는다**(좁히기는 (지역,시점) 축이다)."""
    from app.services.external_api.reb_client import (
        latest_value_from_rows,
        rate_series_from_rows,
        rate_series_scope,
    )

    rows = _mixed_region_rows(_TWO_YEARS)
    series = rate_series_from_rows(rows, "경기")
    assert len(series) == len(_TWO_YEARS), (
        f"경기 시계열이 {len(series)}건 — 서울이 집계행을 가졌다는 이유로 지워졌다"
    )
    assert rate_series_scope(rows, "경기") == "경기", rate_series_scope(rows, "경기")
    # ★두 추출기가 **같은 답**을 내야 한다 — 이것이 「공용 헬퍼」가 실제로 뜻하는 것이다.
    assert latest_value_from_rows(rows, "경기") == (0.3, _TWO_YEARS[-1])


def test_mixed_table_still_narrows_the_region_that_has_an_aggregate_row() -> None:
    """★위양성 축 — 축을 고치느라 **집계행이 있는 지역의 좁히기까지 죽이지 않는다**."""
    from app.services.external_api.reb_client import rate_series_from_rows

    rows = _mixed_region_rows(_TWO_YEARS)
    seoul = rate_series_from_rows(rows, "서울")
    assert len(seoul) == len(_TWO_YEARS), (
        f"서울 시계열이 {len(seoul)}건 — 규모 5행이 그대로 새고 있다(좁히기 사망)"
    )


# ─────────────────────────────────────────────────────────────
# ★R6 LOW-2 — 제출 PDF 가 화면보다 **적게** 말하고 있었다
#   화면(`desk-appraisal-basis.ts`)은 4종을 그리는데 PDF 어댑터는 3종이었다.
#   제출본은 화면보다 오래 남고 **다른 사람이 읽는다** — 갈림 자체가 결함이다.
# ─────────────────────────────────────────────────────────────


def _pdf_basis_lines(market_stats: dict, time_adjust_basis: str = "시점수정 근거") -> list[str]:
    """PDF 어댑터가 §5 에 실제로 싣는 줄들을 뽑는다(렌더 산출물을 본다)."""
    from app.services.report.render.appraisal_adapter import build_report_model_from_appraisal

    doc = build_report_model_from_appraisal({
        "ok": True, "address": "서울특별시 강남구 1",
        "appraised_price_per_sqm": 2_000_000, "appraised_total_won": 1_000_000_000,
        "area_sqm": 500, "confidence": 0.7, "range_per_sqm": {"low": 1, "high": 2},
        "methods": [], "weight_note": "단독 채택",
        "time_adjust_basis": time_adjust_basis, "market_stats": market_stats,
    })
    for sec in doc.sections:
        if sec.title.startswith("5."):
            return [p for b in sec.blocks for p in getattr(b, "paragraphs", [])]
    return []


def test_pdf_carries_the_same_honesty_signals_as_the_screen() -> None:
    """★제출 PDF 가 주택지수 대체 범위와 시·도 미해석을 **함께 싣는다**."""
    lines = _pdf_basis_lines({
        "region": "서울", "region_resolved": True, "rone_available": True,
        "housing_time_adjust": {"source": "R-ONE", "factor": 1.0243,
                                "basis": "주택매매가격지수 누적 변동", "scope": "전국"},
    })
    joined = "\n".join(lines)
    assert lines, "PDF §5 가 비었다(수집기 사망)"
    assert "주택가격지수 누적변동" in joined, joined
    assert "범위 전국" in joined and "실데이터가 아닙니다" in joined, joined


def test_pdf_reports_unresolved_sido() -> None:
    """★시·도 미해석 고지가 제출본에도 실린다(화면만 고치고 끝내지 않는다)."""
    lines = _pdf_basis_lines({"region": "전국", "region_resolved": False, "rone_available": True})
    assert any("시·도를 해석하지 못해" in ln for ln in lines), lines


def test_pdf_does_not_cry_wolf_when_scope_matches() -> None:
    """★위양성 축 — 요청 지역 값이면 그 경고가 **뜨지 않는다**."""
    lines = _pdf_basis_lines({
        "region": "서울", "region_resolved": True, "rone_available": True,
        "housing_time_adjust": {"source": "R-ONE", "factor": 1.0243,
                                "basis": "주택매매가격지수 누적 변동(서울)", "scope": "서울"},
    })
    joined = "\n".join(lines)
    assert "주택가격지수 누적변동" in joined, joined
    assert "실데이터가 아닙니다" not in joined, joined
    assert "시·도를 해석하지 못해" not in joined, joined


# ─────────────────────────────────────────────────────────────
# ★R6 MEDIUM-2 — 같은 «대체 scope» 신호에 두 모듈이 **반대로** 반응한다
#   리뷰어: «어느 쪽이 계약인지 코드가 말하지 않는다». 맞다 — 그래서 **실행 가능한 형태**로 적는다.
#     · market_precision = Zero-Trust 사실 파이프라인 → **적용하지 않는다**(UNKNOWN)
#     · desk_appraisal   = 참고용 추정 → **적용하되 고지한다**(+ 이제 `scope` 를 기계 필드로 싣는다)
#   두 명제를 같은 테스트에서 나란히 단언해, 한쪽이 조용히 바뀌면 잡히게 한다.
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_two_pipelines_answer_substitute_scope_differently_on_purpose(monkeypatch) -> None:
    """★대체 scope 에 대한 두 계약을 **함께** 잠근다(비대칭이 의도임을 실행으로 적는다)."""
    from app.services.land_intelligence.desk_appraisal_service import desk_appraisal
    from app.services.provenance.fact_status import FactStatus

    # 경남 시계열은 없고 전국만 있다 → scope="전국" 대체가 발생하는 상황.
    _patch_rone(monkeypatch, _many_months("전국", rate=0.5))

    out = await desk_appraisal(address="경상남도 창원시 의창구 1", area_sqm=500.0,
                               official_price_per_sqm=1_000_000.0)
    # ① desk_appraisal — **적용하고 고지한다**(값이 살아 있고 범위가 기계 필드로 실린다).
    assert out.get("time_adjust"), out.get("time_adjust")
    assert out.get("time_adjust_scope") == "전국", out.get("time_adjust_scope")
    # ★두 모집단으로 가른다(독립 리뷰 R7 M-1) — 종전엔 이 한 줄뿐이라 필드를 `"전국"` 리터럴로
    #   **고정해도 초록**이었다(상수를 자기 자신과 비교하는 락).
    _patch_rone(monkeypatch, _many_months("경남", rate=0.5) + _many_months("전국", rate=0.9))
    own = await desk_appraisal(address="경상남도 창원시 의창구 1", area_sqm=500.0,
                               official_price_per_sqm=1_000_000.0)
    assert own.get("time_adjust_scope") == "경남", own.get("time_adjust_scope")
    assert "실데이터가 아닙니다" not in str(own.get("time_adjust_basis") or ""), own.get("time_adjust_basis")
    assert "실데이터가 아닙니다" in str(out.get("time_adjust_basis") or ""), out.get("time_adjust_basis")

    # ② market_precision — **적용하지 않는다**(같은 신호에 반대로 답한다).
    import app.services.market_precision.time_adjustment as _ta

    async def _substituted(_address: str = "") -> dict:
        return {"factor": 1.0121, "source": "R-ONE", "scope": "전국", "basis": "대체"}

    monkeypatch.setattr(_ta, "housing_time_adjust", _substituted)
    demoted = await _ta.resolve_time_adjustment("경상남도 창원시 의창구 1")
    assert demoted.status == FactStatus.UNKNOWN, demoted.status
    # ★계수는 **남아 있다** — 그 모듈은 그것을 «근거 표기용» 이라 부르고 표시 가격에 곱하지 않는다.
    #   내가 처음 쓴 단언(`factor is None`)은 **코드를 안 읽고 쓴 것**이라 틀렸다.
    #   계약은 «값을 지운다» 가 아니라 «관측이 아니라고 말하고, 인용하지 말라고 적는다» 이다.
    assert demoted.factor is not None, demoted.factor
    assert "적용하지 않은 미보정 원본" in demoted.assumption, demoted.assumption
    assert "아닙니다" in demoted.limitation and "인용하지 마십시오" in demoted.limitation, demoted.limitation

    # ★두 계약의 차이를 한 줄로 못 박는다 — 한쪽이 조용히 상대 쪽으로 바뀌면 여기서 걸린다.
    assert out.get("time_adjust") and demoted.status is FactStatus.UNKNOWN, (
        "desk_appraisal 은 적용하고 고지하며, market_precision 은 관측으로 승격하지 않는다"
    )


# ─────────────────────────────────────────────────────────────
# ★R6 MEDIUM-1 → **R7 M-2 로 정정** — 내가 남긴 부채가 **거짓 전제** 위에 있었다
#
#   R6 지적을 받고 «상업용수익률 표는 시도가 CLS_FULLNM 에만 있어 시도 선택이 원리적으로 불가»
#   라며 strict xfail 을 걸었다. R7 이 «같은 파일이 같은 표에 모순되는 실측을 적고 있다» 고
#   짚어 **라이브로 다시 쟀더니 내 전제가 틀렸다**(2026-09-08 · `/land-price/rone-test`):
#       A_2024_00683 (YY) 300행 중 `CLS_NM` 이 **시도명인 행 24건**
#       (서울4·부산4·대구4·인천3·광주3·대전3·울산3 — `CLS_FULLNM` 도 같은 시도명)
#       ⇒ `latest_value_from_rows(rows, "서울")` = **(6.96, '2005')** — 선택은 **된다**
#   모순의 출처는 같은 파일 독스트링의 **전사 오류**였다(`CLS_NM="서울"` 에 엉뚱한 경로를 짝지음).
#   ★거짓 부채는 부채가 없는 것보다 나쁘다 — 다음 사람이 있지도 않은 결함을 고치러 간다.
#     그래서 xfail 을 **지우고**, 실제로 남은 한계를 **관측으로** 적는다:
#       · 그 표의 최신 시점은 **2005년**이고 레지스트리 `cycle="QQ"` 는 **행 0건**이다(범위 밖·기록만)
#       · 상권 행이 시도 선택에 섞이지 않는 것은 `row_region_names` 의 정확일치가 보장한다 — 아래로 잠근다


def test_commercial_yield_selects_the_sido_row_not_a_submarket_row() -> None:
    """★시도 행은 고르고 **상권 행은 섞이지 않는다**(라이브 모양 그대로).

    라이브 실측: 같은 표에 `CLS_NM="서울"`(시도, `CLS_FULLNM="서울"`)과
    `CLS_NM="금호지구"`(상권, `CLS_FULLNM="광주>금호지구"`)가 **함께** 있다.
    """
    from app.services.external_api.reb_client import latest_value_from_rows

    rows = [
        {"CLS_NM": "서울", "CLS_FULLNM": "서울", "ITM_NM": "투자수익률",
         "DTA_VAL": 6.96, "WRTTIME_IDTFR_ID": "2005"},
        {"CLS_NM": "금호지구", "CLS_FULLNM": "광주>금호지구", "ITM_NM": "투자수익률",
         "DTA_VAL": 7.13, "WRTTIME_IDTFR_ID": "2005"},
    ]
    assert latest_value_from_rows(rows, "서울") == (6.96, "2005"), "시도 행을 못 골랐다"
    # ★계층 경로는 지역 후보가 아니다 — «광주» 로 조회해도 그 상권 행이 잡히면 안 된다.
    assert latest_value_from_rows(rows, "광주") is None, "계층 경로가 지역으로 새어 들어왔다"


# ─────────────────────────────────────────────────────────────
# ★R7 HIGH-1 — 처방을 **한 창(window)** 에만 걸었다
#
#   `cumulative_factor_from_rows` 는 «고유 기간 부족이면 거부» 를, `is_time_series` 는 **최근 24개월**
#   창에서 판정하는데 `yearly` 는 **시계열 전체**를 그냥 더했다. 그래서 좁히기가 무동작인 구간이
#   창 **밖**에 있으면 그 해 막대만 조용히 배수로 부풀고 **배지는 꺼져 있다**. 실측:
#       최근24 고유기간 24 → is_time_series True(배지 꺼짐) · 누적계수 1.1272(정답)
#       yearly = [2024: **12.0**, 2025: 6.0, 2026: 6.0]      ← 정답은 각 연 6.0
#   ⇒ 형제(`latest_value_from_rows`)가 이미 가진 규율을 여기에도 건다 —
#     **같은 시점에 값이 갈리면 합치지 말고 그 시점을 버린다**(같은 값이면 한 번만 센다).
#     그리고 «연간» 이라 쓰면서 몇 달을 더했는지 말하지 않으면 부분 합계가 연간 값인 척한다
#     → `months_counted` · `ambiguous_periods` 를 함께 싣는다.
# ─────────────────────────────────────────────────────────────


def _period_rows(values_by_month: dict[int, list[float]], year: str = "2024") -> list[dict]:
    """(시점)당 값 목록을 그대로 행으로 편다 — 카디널리티를 픽스처가 직접 만든다."""
    return [
        {"GRP_NM": "서울", "CLS_NM": f"규모{i}", "ITM_NM": "변동률",
         "DTA_VAL": v, "WRTTIME_IDTFR_ID": f"{year}{m:02d}"}
        for m, vals in values_by_month.items()
        for i, v in enumerate(vals)
    ]


def test_yearly_is_not_inflated_by_periods_outside_the_24_month_window() -> None:
    """★창 **밖** 구간이 부풀지 않는다 — 배지가 꺼져 있어도 막대는 정답이어야 한다."""
    from app.services.external_api.reb_client import trend_from_rows

    # 2024 는 집계행이 **없다**(좁히기 무동작 → 2행 유지) · 2025·2026 은 있다.
    rows: list[dict] = []
    for m in range(1, 13):
        for cls in ("40㎡이하", "85㎡초과"):
            rows.append({"GRP_NM": "서울", "CLS_NM": cls, "ITM_NM": "변동률",
                         "DTA_VAL": 0.5, "WRTTIME_IDTFR_ID": f"2024{m:02d}"})
    for yr in ("2025", "2026"):
        for m in range(1, 13):
            for cls in _SIZE_CLASSES:          # '전체' 포함 → 좁히기 동작
                rows.append({"GRP_NM": "서울", "CLS_NM": cls, "ITM_NM": "변동률",
                             "DTA_VAL": 0.5, "WRTTIME_IDTFR_ID": f"{yr}{m:02d}"})
    yearly = {y["year"]: y for y in trend_from_rows(rows, "서울", 24).get("yearly", [])}
    assert yearly, "연간 통계가 비었다(수집기 사망)"
    for yr in ("2024", "2025", "2026"):
        assert yearly[yr]["rate"] == 6.0, f"{yr} 이 부풀었다: {yearly}"
        assert yearly[yr]["months_counted"] == 12, yearly[yr]


def test_same_period_duplicate_values_are_counted_once() -> None:
    """★같은 값이 중복 표기된 것은 **한 번만** 센다(중복 ≠ 두 달)."""
    from app.services.external_api.reb_client import trend_from_rows

    tr = trend_from_rows(_period_rows({m: [0.5, 0.5] for m in range(1, 13)}), "서울", 24)
    y = tr["yearly"][0]
    assert (y["rate"], y["months_counted"]) == (6.0, 12), y


def test_same_period_conflicting_values_are_dropped_not_summed() -> None:
    """★값이 갈리는 시점은 **버린다** — 더하면 «연간 변동률» 이 거짓이 된다."""
    from app.services.external_api.reb_client import trend_from_rows

    # 전부 갈림 → 셀 수 있는 시점이 0 → 통계 자체를 내지 않는다.
    allbad = trend_from_rows(_period_rows({m: [0.5, 0.9] for m in range(1, 13)}), "서울", 24)
    assert not allbad.get("yearly"), allbad

    # 절반만 갈림 → 남은 6개월만 세고, **몇 달인지·몇 개를 버렸는지 말한다**.
    mixed = trend_from_rows(
        _period_rows({m: ([0.5, 0.9] if m <= 6 else [0.5]) for m in range(1, 13)}), "서울", 24)
    y = mixed["yearly"][0]
    assert (y["rate"], y["months_counted"]) == (3.0, 6), y
    assert mixed["ambiguous_periods"] == 6, mixed["ambiguous_periods"]


def test_item_filter_runs_before_narrowing_not_after() -> None:
    """★R7 H-2 — 커밋이 «ITM 필터를 좁히기 **앞**에 둔다» 고 **선언**했는데 무잠금이었다.

    선언을 썼으면 그 선언에 변이를 넣어야 한다(§C-30). 갈라 주는 모집단:
      한 시점의 **집계행이 다른 항목**(`지수`)이고 쓸 행은 `변동률` 인 경우.
      필터가 좁히기 **뒤**에 있으면 집계행(지수)이 좁히기에서 이기고 → 항목 필터가 그것을 버려
      **그 시점이 통째로 사라진다**(리뷰어 실측).
    """
    from app.services.external_api.reb_client import rate_series_from_rows

    rows = [
        # 202606 — 집계행 없음, 변동률 단일
        {"GRP_NM": "서울", "CLS_NM": "40㎡이하", "ITM_NM": "변동률",
         "DTA_VAL": 0.5, "WRTTIME_IDTFR_ID": "202606"},
        # 202607 — 집계행이 **지수**(쓸 수 없는 항목) · 쓸 행은 변동률
        {"GRP_NM": "서울", "CLS_NM": "전체", "ITM_NM": "지수",
         "DTA_VAL": 100.0, "WRTTIME_IDTFR_ID": "202607"},
        {"GRP_NM": "서울", "CLS_NM": "40㎡이하", "ITM_NM": "변동률",
         "DTA_VAL": 0.7, "WRTTIME_IDTFR_ID": "202607"},
    ]
    periods = [t for t, _ in rate_series_from_rows(rows, "서울")]
    assert "202607" in periods, (
        f"202607 이 사라졌다 — 항목 필터가 좁히기 **뒤**에 있다: {periods}"
    )
    assert periods == ["202606", "202607"], periods


def test_pdf_time_adjust_line_reports_substitute_scope() -> None:
    """★R7 M-1 — 제출 PDF 의 시점수정 줄도 대체 범위를 말한다(화면과 같은 축)."""
    from app.services.report.render.appraisal_adapter import build_report_model_from_appraisal

    def lines(scope: str, region: str) -> list[str]:
        doc = build_report_model_from_appraisal({
            "ok": True, "appraised_price_per_sqm": 2_000_000, "appraised_total_won": 1,
            "area_sqm": 500, "confidence": 0.7, "range_per_sqm": {"low": 1, "high": 2},
            "methods": [], "weight_note": "단독", "time_adjust_basis": "R-ONE 지가변동률 누적",
            "time_adjust_scope": scope,
            "market_stats": {"region": region, "region_resolved": True, "rone_available": True},
        })
        return [p for sec in doc.sections if sec.title.startswith("5.")
                for b in sec.blocks for p in getattr(b, "paragraphs", [])]

    sub = "\n".join(lines("전국", "경남"))
    assert "범위 전국" in sub and "실데이터가 아닙니다" in sub, sub
    # ★위양성 축 — 요청 지역 값이면 그 경고가 뜨지 않는다.
    own = "\n".join(lines("경남", "경남"))
    assert "시점수정" in own and "실데이터가 아닙니다" not in own, own
