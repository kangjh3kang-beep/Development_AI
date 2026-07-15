"""public_price_ingest — 응답 정규화(방어적 파싱) + material_unit_prices upsert 계약 테스트.

DB 비의존(FakeSession) — 실제 DB 연결 없이 execute() 호출을 기록해 SQL/파라미터를 검증한다
(test_bim_quantities_wiring.py의 가짜 세션 패턴).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.cost import public_price_ingest as ingest_mod
from app.services.cost.public_price_ingest import (
    PUBLIC_PRICE_SOURCE_LABEL,
    ingest_public_prices,
    normalize_item,
)
from app.services.cost.unit_price_repository import _public_code

# ── normalize_item: 방어적 파싱 ──


def test_normalize_item_matches_keyword_and_candidate_fields():
    row = normalize_item({"krnPrdctNm": "이형철근 SD400 D13", "unprc": "900,000", "unit": "ton"})
    assert row is not None
    assert row["material_code"] == _public_code("rebar")
    assert row["material_price"] == 900000.0
    assert row["unit"] == "ton"
    assert row["labor_price"] == 0
    assert row["expense_price"] == 0


def test_normalize_item_breakdown_fields_populated_when_present():
    """분해 단가(mtrlcst/lbrcst/gnrlexpns — 라이브 확정 필드)가 채워진 항목은 분리 적재.

    labor>0이 되어 unit_price_repository의 T1 안전가드를 통과한다(死계층 자동 재활성 채널).
    """
    row = normalize_item({
        "krnPrdctNm": "이형철근 SD400 D13", "prce": "900000", "unit": "ton",
        "mtrlcst": "700,000", "lbrcst": "150000", "gnrlexpns": "50000",
    })
    assert row is not None
    assert row["material_price"] == 700000.0
    assert row["labor_price"] == 150000.0
    assert row["expense_price"] == 50000.0


def test_normalize_item_empty_breakdown_falls_back_to_total_price():
    """2026-07-16 라이브 현행(전건 분해 빈 문자열) — 총단가 폴백·labor 0(T1 가드 스킵 유지)."""
    row = normalize_item({
        "krnPrdctNm": "레미콘 25-24-150", "prce": "85000", "unit": "㎥",
        "mtrlcst": "", "lbrcst": "", "gnrlexpns": "",
    })
    assert row is not None
    assert row["material_price"] == 85000.0
    assert row["labor_price"] == 0
    assert row["expense_price"] == 0


def test_normalize_item_labor_without_material_not_treated_as_breakdown():
    """노무만 있고 재료 분해가 없으면 불완전 분해 — 총단가 폴백(부분 분해 오적재 방지)."""
    row = normalize_item({"krnPrdctNm": "철근 D13", "prce": "900000", "lbrcst": "150000"})
    assert row is not None
    assert row["material_price"] == 900000.0
    assert row["labor_price"] == 0


def test_normalize_item_breakdown_sum_mismatch_falls_back():
    """★정합 가드(R1): 분해 합≠총단가 1% 초과 괴리 → 폴백(T1 최우선 단가 침묵 왜곡 방지).

    경비 누락 부분분해(700k+150k=850k vs prce 900k, -5.6%)가 대표 시나리오.
    """
    row = normalize_item({
        "krnPrdctNm": "이형철근 SD400 D13", "prce": "900000",
        "mtrlcst": "700000", "lbrcst": "150000", "gnrlexpns": "",
    })
    assert row is not None
    assert row["material_price"] == 900000.0  # 검증된 총단가 유지
    assert row["labor_price"] == 0  # T1 가드 스킵 유지(왜곡 대신 정직 폴백)


def test_normalize_item_negative_expense_falls_back():
    """음수 경비 등 비정상 분해 → 합 괴리로 폴백(무검증 적재 방지)."""
    row = normalize_item({
        "krnPrdctNm": "철근 D13", "prce": "900000",
        "mtrlcst": "800000", "lbrcst": "150000", "gnrlexpns": "-50000",
    })
    assert row is not None
    assert row["material_price"] == 900000.0
    assert row["labor_price"] == 0


def test_normalize_item_prefers_first_present_name_candidate():
    row = normalize_item({"prdctClsfcNoNm": "레미콘 25-24-15", "krnPrdctNm": "무시됨", "prce": "85000"})
    assert row is not None
    assert row["material_code"] == _public_code("concrete")
    assert row["material_name"] == "레미콘 25-24-15"


def test_normalize_item_no_price_field_skipped():
    assert normalize_item({"krnPrdctNm": "철근 D13"}) is None


def test_normalize_item_no_name_field_skipped():
    assert normalize_item({"prce": "85000"}) is None


def test_normalize_item_zero_or_negative_price_skipped():
    assert normalize_item({"krnPrdctNm": "철근", "prce": "0"}) is None
    assert normalize_item({"krnPrdctNm": "철근", "prce": "-100"}) is None


def test_normalize_item_unmatched_keyword_skipped():
    # "타일"은 _PRICE_KEYWORD_RULES(콘크리트/철근/거푸집/조적/방수/창호) 어디에도 매칭 안 됨.
    assert normalize_item({"krnPrdctNm": "바닥 타일 600x600", "prce": "25000"}) is None


def test_normalize_item_non_dict_skipped():
    assert normalize_item("not-a-dict") is None  # type: ignore[arg-type]


# ── ingest_public_prices: 키 미보유 → graceful 0건 ──


class _FakeSession:
    def __init__(self) -> None:
        self.executed: list[tuple] = []
        self.committed = False

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        return None

    async def commit(self):
        self.committed = True


async def test_ingest_no_key_returns_zero_graceful(monkeypatch):
    monkeypatch.setattr(ingest_mod, "_service_key", lambda: "")
    db = _FakeSession()
    result = await ingest_public_prices(db)
    assert result["ok"] is True
    assert result["fetched"] == 0 and result["ingested"] == 0
    assert "미설정" in result["reason"]
    assert db.executed == []  # DB 호출 전혀 없음(정직 조기반환)


# ── ingest_public_prices: 키 보유 → fetch→normalize→upsert ──


class _FakeClient:
    """PublicPriceClient 대역 — page=1에서 3건(2건 매핑성공+1건 미매칭), page=2 이후 빈 응답."""

    last_kwargs: dict | None = None

    def __init__(self, service_key: str, timeout: float = 30.0) -> None:
        self.service_key = service_key
        self.closed = False

    async def fetch_facility_material_prices(self, *, prdct_clsfc_no=None, krn_prdct_nm=None, page=1, num_rows=100):
        _FakeClient.last_kwargs = {
            "prdct_clsfc_no": prdct_clsfc_no, "krn_prdct_nm": krn_prdct_nm,
            "page": page, "num_rows": num_rows,
        }
        if page == 1:
            return [
                {"krnPrdctNm": "이형철근 SD400 D13", "unprc": "900000", "unit": "ton"},
                {"krnPrdctNm": "레미콘 25-24-15", "prce": "85000", "unit": "m3"},
                {"krnPrdctNm": "바닥 타일 600x600", "prce": "25000"},  # 미매칭 → unmapped
            ]
        return []  # 2페이지부터 빈 응답 → 조기 종료

    async def close(self):
        self.closed = True


async def test_ingest_with_key_upserts_and_counts_unmapped(monkeypatch):
    monkeypatch.setattr(ingest_mod, "_service_key", lambda: "TESTKEY")
    monkeypatch.setattr(
        "app.services.cost.cost_tables_bootstrap._ensure_cost_tables", AsyncMock()
    )
    monkeypatch.setattr(
        "app.integrations.public_price_client.PublicPriceClient", _FakeClient
    )

    db = _FakeSession()
    result = await ingest_public_prices(db, keyword="레미콘", max_pages=3, num_rows=100)

    assert result["ok"] is True
    assert result["fetched"] == 3
    assert result["ingested"] == 2  # rebar + concrete
    assert result["unmapped"] == 1  # 타일

    # 2건 upsert(INSERT ... ON CONFLICT)가 실행됐고 커밋됐다.
    assert len(db.executed) == 2
    assert db.committed is True
    for stmt, params in db.executed:
        # ★독립리뷰 MEDIUM 반영: 멱등 계약을 SQL 자체로 잠근다 — ON CONFLICT가 빠진
        #   순수 INSERT로 회귀하면(재실행 시 행 증식) 이 단언이 즉시 잡는다.
        assert "ON CONFLICT" in str(stmt).upper()
        assert params["price_source"] == PUBLIC_PRICE_SOURCE_LABEL
        assert params["material_code"].startswith("PUB-")

    # ★재실행 멱등: 같은 응답으로 한 번 더 인제스트해도 같은 material_code 2건에 대한
    #   upsert만 반복된다(신규 코드 증식 없음 — ON CONFLICT DO UPDATE 대상 동일).
    codes_first = sorted(params["material_code"] for _s, params in db.executed)
    db2 = _FakeSession()
    result2 = await ingest_public_prices(db2, keyword="레미콘", max_pages=3, num_rows=100)
    assert result2["ingested"] == 2
    codes_second = sorted(params["material_code"] for _s, params in db2.executed)
    assert codes_first == codes_second

    # 1페이지 응답이 num_rows(100)보다 적었으므로(3건) 조기 종료 — 2페이지 호출 안 됨.
    assert _FakeClient.last_kwargs["page"] == 1
    assert _FakeClient.last_kwargs["krn_prdct_nm"] == "레미콘"


async def test_ingest_no_mapped_items_returns_zero(monkeypatch):
    class _EmptyMapClient(_FakeClient):
        async def fetch_facility_material_prices(self, **kwargs):
            if kwargs.get("page", 1) == 1:
                return [{"krnPrdctNm": "바닥 타일", "prce": "25000"}]
            return []

    monkeypatch.setattr(ingest_mod, "_service_key", lambda: "TESTKEY")
    monkeypatch.setattr(
        "app.services.cost.cost_tables_bootstrap._ensure_cost_tables", AsyncMock()
    )
    monkeypatch.setattr(
        "app.integrations.public_price_client.PublicPriceClient", _EmptyMapClient
    )
    db = _FakeSession()
    result = await ingest_public_prices(db)
    assert result["ok"] is True
    assert result["fetched"] == 1 and result["ingested"] == 0 and result["unmapped"] == 1
    assert db.executed == []  # upsert 없음
    assert db.committed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
