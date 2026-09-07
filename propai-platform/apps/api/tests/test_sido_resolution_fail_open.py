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

@pytest.mark.xfail(strict=True, reason="★부채: onbid_client/hyphen_client 의 자체 시도 해석기 2곳이 미이관(반환 계약이 축약 vs 완전명으로 갈린다)")
def test_all_sido_resolvers_delegate_to_the_canonical_one() -> None:
    """언젠가 주소→시도 해석기가 **한 자리**여야 한다(정본 독스트링이 이미 선언한 것)."""
    from app.services.auction.onbid_client import _sido_from_address
    from app.services.registry.hyphen_client import extract_sido

    addr = "전라남도 순천시 조례동 1"
    canonical = sido_short_or_empty(addr)
    assert _sido_from_address(addr) == canonical
    assert extract_sido(addr) == canonical
