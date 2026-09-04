"""unit_price_repository — P1 단가 4계층 리졸버(T1 공공고시→T2 표준품셈→T3 fallback) 해석순서 테스트.

DB 비의존 — UnitPriceRepository._db_cache를 직접 주입해 _load_db() 호출을 우회한다
(리포지토리가 "1회 로드 후 캐시" 구조이므로 캐시를 미리 채우면 실 DB 접속 없이 tier 분기 검증 가능).
"""

from __future__ import annotations

import pytest

from app.services.cost.unit_price_repository import (
    UnitPriceRepository,
    _public_code,
)


def _repo_with_cache(cache: dict) -> UnitPriceRepository:
    repo = UnitPriceRepository()
    repo._db_cache = cache
    return repo


# ── T1 최우선: PUB-<KEY> 행이 있고 price_source가 '표준시장단가'로 시작하면 T1 ──


async def test_t1_public_price_wins_when_present():
    # ★T1 안전가드 통과 조건: 노무/경비 분해 보유(labor·exp>0) + 단위가 표준(m3)과 일치.
    #   (예전 픽스처는 labor=0/exp=0이라 하류 원가계산서에서 법정 제비율이 소실되는 버그를
    #    '정상'으로 고정했었다 — 분해 있는 실공공단가로 정정.)
    repo = _repo_with_cache({
        _public_code("concrete"): {
            "spec": "레미콘(공공)", "unit": "m3", "mat_unit": 90000.0,
            "labor_unit": 30000.0, "exp_unit": 8000.0,
            "price_basis_year": 2026, "price_source": "표준시장단가 2026상",
            "region": "전국", "source_url": "https://www.data.go.kr/data/15129415/openapi.do",
        },
        "RC-001": {  # T2 표준품셈도 동시에 있지만 T1이 우선해야 함
            "spec": "레미콘(품셈)", "unit": "m3", "mat_unit": 82000.0,
            "labor_unit": 35000.0, "exp_unit": 8000.0,
            "price_basis_year": 2025, "price_source": "표준품셈2025", "region": "경기도",
            "source_url": None,
        },
    })
    p = await repo.get_price("concrete")
    assert p["tier"] == "T1_public"
    assert p["mat_unit"] == 90000.0
    assert p["price_source"] == "표준시장단가 2026상"
    assert p["source_url"] == "https://www.data.go.kr/data/15129415/openapi.do"
    assert p["basis_date"] == "2026-01-01"


# ── ★T1 안전가드: 노무·경비 분해 없이 총단가만 실은 공공단가(labor=exp=0)는 스킵→T2/T3 폴백 ──
#   (하류 OriginCostCalculator가 간접노무비·4대보험을 노무=0에 곱해 법정 제비율을 소실시키는 것 차단)


async def test_t1_skipped_when_no_labor_breakdown_falls_back_to_t2():
    repo = _repo_with_cache({
        _public_code("concrete"): {  # 총단가를 재료비 슬롯에만 실음(노무·경비 0) → 안전가드 스킵
            "spec": "레미콘(공공)", "unit": "m3", "mat_unit": 130000.0,
            "labor_unit": 0.0, "exp_unit": 0.0,
            "price_basis_year": 2026, "price_source": "표준시장단가 2026상", "region": "전국",
        },
        "RC-001": {  # 분해 있는 T2가 폴백 대상
            "spec": "레미콘(품셈)", "unit": "m3", "mat_unit": 82000.0,
            "labor_unit": 35000.0, "exp_unit": 8000.0,
            "price_basis_year": 2025, "price_source": "표준품셈2025", "region": "경기도",
            "source_url": None,
        },
    })
    p = await repo.get_price("concrete")
    assert p["tier"] != "T1_public"          # 노무0 공공단가는 채택 안 함
    assert p["labor_unit"] == 35000.0        # T2의 정상 노무비(제비율 계산 정합)


# ── ★T1 안전가드: 단위가 표준 기대단위와 불일치하는 공공단가는 스킵→폴백(물량×엉뚱단가 차단) ──


async def test_t1_skipped_when_unit_mismatch_falls_back():
    repo = _repo_with_cache({
        _public_code("concrete"): {  # 콘크리트 기대단위는 m3인데 ton으로 옴 → 안전가드 스킵
            "spec": "레미콘(공공)", "unit": "ton", "mat_unit": 90000.0,
            "labor_unit": 30000.0, "exp_unit": 8000.0,
            "price_basis_year": 2026, "price_source": "표준시장단가 2026상", "region": "전국",
        },
    })
    p = await repo.get_price("concrete")
    assert p["tier"] != "T1_public"          # 단위 불일치 공공단가는 채택 안 함
    assert p["unit"] == "m3"                  # T3 fallback의 정상 단위


# ── ★T1 안전가드: 경비만 분해되고 노무=0인 공공단가도 스킵(제비율은 오직 labor_unit서 파생) ──
#   (or _exp>0 논리홀 회귀가드 — 리뷰 P1)


async def test_t1_skipped_when_expense_only_no_labor():
    repo = _repo_with_cache({
        _public_code("concrete"): {  # 경비만 분해·노무=0 → 제비율 소실이므로 스킵해야 함
            "spec": "레미콘(공공)", "unit": "m3", "mat_unit": 125000.0,
            "labor_unit": 0.0, "exp_unit": 5000.0,
            "price_basis_year": 2026, "price_source": "표준시장단가 2026상", "region": "전국",
        },
        "RC-001": {
            "spec": "레미콘(품셈)", "unit": "m3", "mat_unit": 82000.0,
            "labor_unit": 35000.0, "exp_unit": 8000.0,
            "price_basis_year": 2025, "price_source": "표준품셈2025", "region": "경기도",
            "source_url": None,
        },
    })
    p = await repo.get_price("concrete")
    assert p["tier"] != "T1_public"          # 노무 미분해(경비만)면 채택 안 함
    assert p["labor_unit"] == 35000.0        # T2의 정상 노무비


# ── T1 부재, T2 존재 → T2 ──


async def test_t2_standard_when_t1_absent():
    repo = _repo_with_cache({
        "RC-001": {
            "spec": "레미콘(품셈)", "unit": "m3", "mat_unit": 82000.0,
            "labor_unit": 35000.0, "exp_unit": 8000.0,
            "price_basis_year": 2025, "price_source": "표준품셈2025", "region": "경기도",
            "source_url": None,
        },
    })
    p = await repo.get_price("concrete")
    assert p["tier"] == "T2_standard"
    assert p["price_source"] == "표준품셈2025"


# ── T1·T2 모두 부재(예: masonry — T2 매핑 자체가 없음) → T3 fallback ──


async def test_t3_fallback_when_neither_present():
    repo = _repo_with_cache({})
    p = await repo.get_price("masonry")
    assert p["tier"] == "T3_fallback"
    assert p["price_source"] == "fallback"
    assert p["source_url"] is None


async def test_t1_public_code_that_lacks_public_prefix_ignored():
    # PUB-CONCRETE 행이 있어도 price_source가 표준시장단가 접두가 아니면 T1로 채택하지 않는다.
    repo = _repo_with_cache({
        _public_code("concrete"): {
            "spec": "레미콘", "unit": "m3", "mat_unit": 90000.0,
            "labor_unit": 0.0, "exp_unit": 0.0,
            "price_basis_year": 2026, "price_source": "기타출처", "region": "전국",
            "source_url": None,
        },
    })
    p = await repo.get_price("concrete")
    assert p["tier"] == "T3_fallback"


async def test_unknown_key_returns_none():
    repo = _repo_with_cache({})
    assert await repo.get_price("no_such_key") is None


# ── escalate_to_current: opt-in, 기본 미적용 ──


async def test_escalation_default_off_no_escalated_key():
    repo = _repo_with_cache({})
    p = await repo.get_price("concrete")
    assert "escalated" not in p


async def test_escalation_opt_in_adds_field_when_live(monkeypatch):
    async def _fake_factor(base_ym, target_ym=None):
        return {"factor": 1.05, "base_index": 140.0, "target_index": 147.0,
                "base_ym": base_ym, "target_ym": "202607",
                "source": "KOSIS", "confidence": "live"}

    monkeypatch.setattr(
        "app.services.cost.cost_index_service.escalation_factor", _fake_factor
    )
    repo = _repo_with_cache({})
    p = await repo.get_price("concrete", escalate_to_current=True)
    assert p["escalated"]["factor"] == 1.05


async def test_escalation_opt_in_graceful_when_unavailable(monkeypatch):
    async def _fake_factor(base_ym, target_ym=None):
        return {"factor": 1.0, "confidence": "unavailable"}

    monkeypatch.setattr(
        "app.services.cost.cost_index_service.escalation_factor", _fake_factor
    )
    repo = _repo_with_cache({})
    p = await repo.get_price("concrete", escalate_to_current=True)
    assert "escalated" not in p  # unavailable이면 원본 그대로(무날조)


# ── get_prices: 전체 키 순회, 기존 키 불변(회귀 0) ──


async def test_get_prices_returns_all_fallback_keys_when_db_empty():
    repo = _repo_with_cache({})
    prices = await repo.get_prices()
    assert set(prices.keys()) == {"concrete", "rebar", "formwork", "masonry", "waterproof", "window"}
    for key, p in prices.items():
        assert p["tier"] == "T3_fallback"
        assert p["price_source"] == "fallback"  # 기존 계약 불변


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
