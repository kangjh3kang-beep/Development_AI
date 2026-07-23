"""시장·분양 정밀화 계약(market_precision, W3-8) 단위테스트.

검증 축:
  A. 계약 불변식 — PriceSuggestion 점추정 단독 금지, AbsorptionEstimate UNKNOWN+수치공존 금지.
  B. ComparableSet — MOLIT 사례를 선정/제외 사유와 함께 itemize(무자료 시 가짜 사례 금지).
  C. TimeAdjustment — R-ONE 실계수 가용/미가용 양쪽 경로(외삽 금지·정직 UNKNOWN·OBSERVED에도
     "표시가격 미보정" 명시 — R1 M-3).
  D. AbsorptionEstimate — 항상 UNKNOWN(데이터 소스 부재 확정, 모델 날조 금지).
  E. PriceSuggestion 조립 — suggest_base_price() 결과 재포장(range 필드 정합·unavailable 정직).
  F. suggest._trade_per_pyeong collect_cases 옵션 — 기본(False) 무회귀 + True 시 itemized cases,
     파싱실패 행도 명시 제외(exclude_reason)되어 수집 N=선정+제외 항등이 성립(R1 M-2).
  G. precision 경로 MOLIT 수집 중복 제거 — suggest_base_price(collect_cases=True) 1회 호출 +
     assemble_market_precision() 이후에도 총 수집 호출은 8회(재수집 없음, R1 M-1).

외부 실호출 없음(MOLIT·R-ONE 모두 스텁/모킹).
"""
from __future__ import annotations

import uuid

import pytest

from app.services.market_precision.absorption import estimate_absorption
from app.services.market_precision.comparables import (
    build_comparable_set,
    build_comparable_set_from_cases,
)
from app.services.market_precision.contracts import (
    AbsorptionEstimate,
    ComparableCase,
    ComparableSet,
    PriceSuggestion,
)
from app.services.market_precision.price_suggestion import (
    assemble_market_precision,
    price_suggestion_from_result,
)
from app.services.market_precision.time_adjustment import resolve_time_adjustment
from app.services.provenance.fact_status import FactStatus
from app.services.sales.pricing import suggest as suggest_mod
from app.services.sales.pricing.suggest import _trade_per_pyeong
from apps.api.integrations.molit_client import MolitClient

# ── A. 계약 불변식 ──────────────────────────────────────────────────────

class TestContractInvariants:
    def test_price_suggestion_point_없이_range만_허용(self):
        # point_10k만 있고 range가 없으면 거부(점추정 단독 금지)
        with pytest.raises(ValueError, match="점추정 단독 금지"):
            PriceSuggestion(
                point_10k=5000.0, range_low_10k=None, range_high_10k=None,
                unit_label="만원/평", data_source="live", basis="",
            )

    def test_price_suggestion_point_none이면_range_none도_허용(self):
        ps = PriceSuggestion(
            point_10k=None, range_low_10k=None, range_high_10k=None,
            unit_label="만원/평", data_source="unavailable", basis="데이터 없음",
        )
        assert ps.point_10k is None

    def test_price_suggestion_range_모두_있으면_통과(self):
        ps = PriceSuggestion(
            point_10k=5000.0, range_low_10k=4500.0, range_high_10k=5500.0,
            unit_label="만원/평", data_source="live", basis="",
        )
        assert ps.range_low_10k == 4500.0

    def test_absorption_unknown인데_수치있으면_거부(self):
        with pytest.raises(ValueError, match="UNKNOWN"):
            AbsorptionEstimate(status=FactStatus.UNKNOWN, absorption_rate_pct=55.0, basis="x")

    def test_absorption_unknown_수치none은_허용(self):
        est = AbsorptionEstimate(status=FactStatus.UNKNOWN, absorption_rate_pct=None, basis="x")
        assert est.absorption_rate_pct is None

    def test_comparable_set_to_dict_카운트_정합(self):
        case = ComparableCase(
            case_id="abc", source="MOLIT_실거래", building_name="테스트빌딩",
            dong="역삼동", jibun="1-1", deal_ym="202501", deal_date="2025-01-15",
            price_10k_won=50000.0, area_m2=84.0, per_pyeong_10k=1970.0,
            proximity_scope="동일법정동", included=True, selection_basis="sanity",
        )
        cs = ComparableSet(
            cases=(case,), included_count=1, excluded_count=0,
            anchor_scope="동", data_source="molit_live", note="1건 선정",
        )
        d = cs.to_dict()
        assert d["total_count"] == 1
        assert d["cases"][0]["case_id"] == "abc"


# ── B/F. ComparableSet + _trade_per_pyeong collect_cases ──────────────────

class _StubMolitRows:
    """MolitClient.get_transactions 스텁 — _trade_per_pyeong이 최근 8개월을 순회 조회하므로,
    첫 호출(가장 최근 월) 1회에만 고정 rows를 반환하고 나머지 7개월은 빈 값으로 응답해
    테스트 기대값을 8배 중복 없이 결정론적으로 유지한다."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._served = False

    async def __call__(self, sigungu5, ym, prop_type="apt", num_rows=1000):
        if self._served:
            return []
        self._served = True
        return list(self._rows)


def _row(dong="역삼동", price=50000, area=84.0, name="테스트빌딩", jibun="1-1", deal_date="2025-01-15"):
    return {
        "building_name": name, "jibun": jibun, "dong": dong,
        "price_10k_won": price, "area_m2": area, "deal_date": deal_date,
    }


@pytest.mark.asyncio
async def test_trade_per_pyeong_기본은_기존_shape_불변(monkeypatch):
    rows = [_row(dong="역삼동", price=50000, area=84.0)]
    monkeypatch.setattr(MolitClient, "get_transactions", _StubMolitRows(rows))
    result = await _trade_per_pyeong("11680", "역삼동", "apt")
    assert set(result.keys()) == {"dong", "sigungu"}  # collect_cases=False → cases 키 없음
    assert result["dong"]["n"] == 1


@pytest.mark.asyncio
async def test_trade_per_pyeong_collect_cases_포함_및_제외_사유(monkeypatch):
    rows = [
        _row(dong="역삼동", price=50000, area=84.0, name="포함사례"),          # 정상 → 포함
        _row(dong="삼성동", price=50000, area=84.0, name="타동사례"),          # 타동 → sigungu만
        {"building_name": "결측사례", "jibun": "9-9", "dong": "역삼동",
         "price_10k_won": 0, "area_m2": 84.0, "deal_date": "2025-01-01"},       # 금액 0 → 제외
    ]
    monkeypatch.setattr(MolitClient, "get_transactions", _StubMolitRows(rows))
    result = await _trade_per_pyeong("11680", "역삼동", "apt", collect_cases=True)
    cases = result["cases"]
    by_name = {c["building_name"]: c for c in cases}
    assert by_name["포함사례"]["included"] is True
    assert by_name["포함사례"]["matched_dong"] is True
    assert by_name["타동사례"]["matched_dong"] is False
    assert by_name["결측사례"]["included"] is False
    assert by_name["결측사례"]["exclude_reason"]


@pytest.mark.asyncio
async def test_trade_per_pyeong_파싱실패_행도_명시제외_수집N_항등(monkeypatch):
    """R1 M-2 회귀가드: 비수치(파싱불가) 행을 무음 폐기(continue만)하지 않고 exclude_reason과
    함께 cases에 남긴다 — 결과적으로 수집 N(rows 총건수) == included+excluded 항등이 성립한다."""
    rows = [
        _row(dong="역삼동", price=50000, area=84.0, name="정상행"),
        {"building_name": "파싱실패행", "jibun": "2-2", "dong": "역삼동",
         "price_10k_won": "이상한값", "area_m2": 84.0, "deal_date": "2025-01-01"},
        {"building_name": "파싱실패행2", "jibun": "3-3", "dong": "역삼동",
         "price_10k_won": 50000, "area_m2": "형식오류", "deal_date": "2025-01-01"},
    ]
    monkeypatch.setattr(MolitClient, "get_transactions", _StubMolitRows(rows))
    result = await _trade_per_pyeong("11680", "역삼동", "apt", collect_cases=True)
    cases = result["cases"]
    assert len(cases) == len(rows)  # 무음 절단 없음(수집 N=선정+제외 항등)
    included = sum(1 for c in cases if c["included"])
    excluded = sum(1 for c in cases if not c["included"])
    assert included + excluded == len(rows)
    by_name = {c["building_name"]: c for c in cases}
    assert by_name["파싱실패행"]["included"] is False
    assert "파싱" in by_name["파싱실패행"]["exclude_reason"]
    assert by_name["파싱실패행2"]["included"] is False
    assert "파싱" in by_name["파싱실패행2"]["exclude_reason"]


def test_build_comparable_set_from_cases_순수조립_no_io():
    """build_comparable_set_from_cases는 I/O 없이 이미 수집된 원시 행만으로 조립한다(R1 M-1)."""
    raw = [
        {"ym": "202501", "dong": "역삼동", "jibun": "1-1", "building_name": "A",
         "deal_date": "2025-01-01", "price_10k_won": 50000.0, "area_m2": 84.0,
         "per_pyeong_10k": 1967.7, "matched_dong": True, "included": True, "exclude_reason": None},
    ]
    cs = build_comparable_set_from_cases(raw)
    assert cs.included_count == 1
    assert cs.data_source == "molit_live"

    empty_cs = build_comparable_set_from_cases(None)
    assert empty_cs.data_source == "unavailable"
    empty_cs2 = build_comparable_set_from_cases([])
    assert empty_cs2.data_source == "unavailable"


@pytest.mark.asyncio
async def test_build_comparable_set_무자료시_가짜사례_금지(monkeypatch):
    monkeypatch.setattr(MolitClient, "get_transactions", _StubMolitRows([]))
    cs = await build_comparable_set("11680", "역삼동", "apt")
    assert cs.cases == ()
    assert cs.data_source == "unavailable"
    assert cs.anchor_scope == "unavailable"


@pytest.mark.asyncio
async def test_build_comparable_set_선정_제외_카운트(monkeypatch):
    rows = [
        _row(dong="역삼동", price=50000, area=84.0, name="A"),
        _row(dong="역삼동", price=50000, area=84.0, name="B"),
        {"building_name": "C", "jibun": "1", "dong": "역삼동",
         "price_10k_won": 999999999, "area_m2": 1.0, "deal_date": "2025-01-01"},  # 평당가 sanity 초과
    ]
    monkeypatch.setattr(MolitClient, "get_transactions", _StubMolitRows(rows))
    cs = await build_comparable_set("11680", "역삼동", "apt")
    assert cs.included_count == 2
    assert cs.excluded_count == 1
    assert cs.anchor_scope == "동"
    assert cs.data_source == "molit_live"


# ── C. TimeAdjustment ──────────────────────────────────────────────────

class TestTimeAdjustment:
    @pytest.mark.asyncio
    async def test_rone_미설정시_unknown_미보정_정직표기(self, monkeypatch):
        async def _none(*_a, **_k):
            return None
        monkeypatch.setattr(
            "app.services.market_precision.time_adjustment.housing_time_adjust", _none,
        )
        ta = await resolve_time_adjustment("서울 강남구 역삼동")
        assert ta.status == FactStatus.UNKNOWN
        assert ta.factor is None
        assert ta.source == "미보정"
        assert "미설정" in ta.limitation or "실패" in ta.limitation

    @pytest.mark.asyncio
    async def test_rone_가용시_observed_실계수(self, monkeypatch):
        async def _factor(*_a, **_k):
            return {"factor": 1.05, "source": "R-ONE", "basis": "주택매매가격지수 누적 변동"}
        monkeypatch.setattr(
            "app.services.market_precision.time_adjustment.housing_time_adjust", _factor,
        )
        ta = await resolve_time_adjustment("서울 강남구 역삼동")
        assert ta.status == FactStatus.OBSERVED
        assert ta.factor == 1.05
        assert ta.source == "R-ONE"

    @pytest.mark.asyncio
    async def test_rone_가용해도_observed_경로에_미보정_명시(self, monkeypatch):
        """R1 M-3 회귀가드: 실계수(OBSERVED)가 있어도 "표시 가격은 미보정 원본"임을
        assumption에 명시한다(계수=근거 표기용, 자동 반영 아님 — UNKNOWN 경로와 대칭)."""
        async def _factor(*_a, **_k):
            return {"factor": 1.05, "source": "R-ONE", "basis": "x"}
        monkeypatch.setattr(
            "app.services.market_precision.time_adjustment.housing_time_adjust", _factor,
        )
        ta = await resolve_time_adjustment("서울 강남구 역삼동")
        assert ta.assumption is not None
        assert "미보정" in ta.assumption
        assert "표시 가격" in ta.assumption


# ── D. AbsorptionEstimate ──────────────────────────────────────────────

class TestAbsorptionEstimate:
    def test_항상_unknown(self):
        est = estimate_absorption()
        assert est.status == FactStatus.UNKNOWN
        assert est.absorption_rate_pct is None
        assert est.limitations

    def test_demand_proxy_note는_참고로만_부착(self):
        est = estimate_absorption(demand_proxy_note="주변 실거래 표본 42건")
        assert est.status == FactStatus.UNKNOWN
        assert any("참고(흡수율 아님)" in a for a in est.assumptions)


# ── E. PriceSuggestion 조립(suggest_base_price 결과 재포장) ─────────────

class TestPriceSuggestionFromResult:
    def test_unavailable시_range_전부_none(self):
        res = {"data_source": "unavailable", "note": "주변 실거래 없음"}
        ps = price_suggestion_from_result(res)
        assert ps.point_10k is None
        assert ps.range_low_10k is None
        assert ps.range_high_10k is None
        assert ps.data_source == "unavailable"

    def test_live_tiers에서_range_추출(self):
        res = {
            "data_source": "live",
            "note": "적정분양가 산정 완료",
            "market_reference": {"market_pp_supply_10k": 3000},
            "trust": {"confidence": 0.8, "warnings": []},
            "cost_validation": None,
            "tiers": [
                {"tier": "conservative", "per_pyeong_10k": 3150, "premium_pct": 5},
                {"tier": "base", "per_pyeong_10k": 3450, "premium_pct": 15},
                {"tier": "aggressive", "per_pyeong_10k": 3750, "premium_pct": 25},
            ],
        }
        ps = price_suggestion_from_result(res)
        assert ps.range_low_10k == 3150
        assert ps.range_high_10k == 3750
        assert ps.point_10k == 3450
        assert ps.data_source == "live"

    def test_trust_warning은_limitations로_전파(self):
        res = {
            "data_source": "live",
            "note": "x",
            "market_reference": {},
            "trust": {"confidence": 0.3, "warnings": ["신뢰도 낮음"]},
            "cost_validation": {"warning": "원가 미회수 경고"},
            "tiers": [
                {"tier": "conservative", "per_pyeong_10k": 100, "premium_pct": 5},
                {"tier": "aggressive", "per_pyeong_10k": 130, "premium_pct": 25},
            ],
        }
        ps = price_suggestion_from_result(res)
        assert "신뢰도 낮음" in ps.limitations
        assert "원가 미회수 경고" in ps.limitations


# ── G. precision 경로 MOLIT 수집 중복 제거(R1 M-1 회귀가드) ─────────────

class _CountingMolit:
    """MolitClient.get_transactions 스텁 — 호출 횟수를 센다. 첫 호출(가장 최근 월)에만
    고정 rows를 반환하고 나머지는 빈 값(결정론적 median, 8회 순회 자체는 그대로 유지)."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.call_count = 0

    async def __call__(self, sigungu5, ym, prop_type="apt", num_rows=1000):
        self.call_count += 1
        return list(self._rows) if self.call_count == 1 else []


@pytest.mark.asyncio
async def test_precision_경로_molit_수집_8회_재수집없음(monkeypatch):
    """R1 M-1 핵심 회귀가드: suggest_base_price(collect_cases=True) 1회 호출 +
    assemble_market_precision() 이후에도 MolitClient.get_transactions 총 호출 수는
    8회(8개월×1회 수집)여야 한다 — 16회(2배, comparables.py 재수집)면 회귀."""
    rows = [
        _row(dong="역삼동", price=50000, area=84.0, name="A"),
        _row(dong="역삼동", price=51000, area=84.0, name="B"),
    ]
    stub = _CountingMolit(rows)
    monkeypatch.setattr(MolitClient, "get_transactions", stub)

    async def _loc(*_a, **_k):
        return "서울 강남구 역삼동 1", "1168010100100010000", "APT"

    monkeypatch.setattr(suggest_mod, "_site_location", _loc)

    res = await suggest_mod.suggest_base_price(
        None, uuid.uuid4(), bcode="1168010100", collect_cases=True,
    )
    assert res["data_source"] == "live"
    assert "trade_cases" in res
    assert stub.call_count == 8  # suggest_base_price 내부 1회 수집분(8개월)

    bundle = await assemble_market_precision(res)

    assert stub.call_count == 8  # ★핵심: assemble_market_precision 이후에도 그대로 8(재수집 없음)
    assert bundle["comparable_set"]["included_count"] >= 1
