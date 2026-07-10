"""P4 T2 — 설계변경 예측공사비 서비스(change_forecast.py) 단위 테스트.

MC 밴드 상시 산출·리스크→WB 변환 매핑·수치 미보유 항목의 정직 스킵(data_gaps)을 검증한다.
"""

from __future__ import annotations

import pytest

from app.services.cost.change_forecast import forecast_change_cost

BASE_SPEC = {
    "building_type": "apartment", "total_gfa_sqm": 30000.0,
    "floor_count_above": 20, "floor_count_below": 2, "structure_type": "RC",
}


class TestForecastChangeCost:

    @pytest.mark.asyncio
    async def test_mc_band_present_without_risks(self):
        """risks가 없어도(또는 None이어도) MC 밴드는 항상 산출된다(요구사항)."""
        result = await forecast_change_cost(BASE_SPEC, None)
        band = result["mc_band"]
        assert band["p10"] <= band["p50"] <= band["p90"]
        assert band["base_total"] == result["base_total"]
        assert result["scenarios"] == []
        assert result["data_gaps"] == []

    @pytest.mark.asyncio
    async def test_high_severity_mapped_risk_produces_scenario(self):
        risks = [{"category": "법규초과", "item": "건폐율 초과", "severity": "high", "est_impact": "약 +5%"}]
        result = await forecast_change_cost(BASE_SPEC, risks)
        assert len(result["scenarios"]) == 1
        scen = result["scenarios"][0]
        assert scen["wb_targets"] == ["WB04"]
        assert scen["wb_names"] == ["골조공사(RC·철골)"]
        assert scen["wb_base_amount"] > 0
        assert scen["delta_low"] == scen["delta_high"]
        # 델타는 실제 base WB 금액 × 5%(design_change_predictor의 TYPICAL 상수) — 수치 재계산 검증.
        assert scen["delta_low"] == round(scen["wb_base_amount"] * 5 / 100)

    @pytest.mark.asyncio
    async def test_range_scenario_low_high_differ(self):
        """용적률 초과는 MAX(15%) 단일값이므로 low==high, 건폐율은 TYPICAL(5%) 단일값 —
        두 항목의 pct가 서로 달라 delta 크기도 달라야 한다(수치 하드코딩 아님을 교차검증)."""
        risks = [
            {"category": "법규초과", "item": "건폐율 초과", "severity": "high"},
            {"category": "법규초과", "item": "용적률 초과", "severity": "high"},
        ]
        result = await forecast_change_cost(BASE_SPEC, risks)
        by_item = {s["risk_item"]: s for s in result["scenarios"]}
        assert by_item["건폐율 초과"]["delta_pct_low"] == 5
        assert by_item["용적률 초과"]["delta_pct_low"] == 15
        assert by_item["용적률 초과"]["delta_low"] > by_item["건폐율 초과"]["delta_low"]

    @pytest.mark.asyncio
    async def test_unmapped_or_no_number_risk_skipped_honestly(self):
        """수치(±%) 없는 정성 경고(info/warn류)·매핑 없는 항목은 시나리오화하지 않고
        data_gaps에 사유를 남긴다(무음 스킵 금지 — 정직 표면화)."""
        risks = [
            {"category": "누락", "item": "승강기 설치 확인 필요", "severity": "info"},
            {"category": "간섭정합", "item": "높이-층수 불일치", "severity": "warn"},
            {"category": "누락", "item": "법정주차 부족", "severity": "high", "est_impact": "+5~15%"},
        ]
        result = await forecast_change_cost(BASE_SPEC, risks)
        assert result["scenarios"] == []
        assert len(result["data_gaps"]) == 3
        gap_text = " ".join(result["data_gaps"])
        assert "승강기 설치 확인 필요" in gap_text
        assert "높이-층수 불일치" in gap_text
        assert "법정주차 부족" in gap_text

    @pytest.mark.asyncio
    async def test_mixed_mapped_and_unmapped(self):
        risks = [
            {"category": "법규초과", "item": "높이제한 초과", "severity": "high"},
            {"category": "누락", "item": "부대복리시설 확인 필요", "severity": "info"},
        ]
        result = await forecast_change_cost(BASE_SPEC, risks)
        assert len(result["scenarios"]) == 1
        assert len(result["data_gaps"]) == 1
        assert result["scenarios"][0]["risk_item"] == "높이제한 초과"
