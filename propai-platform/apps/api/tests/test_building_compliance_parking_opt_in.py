"""/building-compliance/rule-check 주차 기하검증 opt-in 배선(스펙 P — W3-5) 회귀 테스트.

기본 경로(주차 관련 신규 필드 미입력)는 parking_geometry 속성 자체가 응답 객체에
설정되지 않아야 한다(무회귀 — 기존 소비자 응답 스키마 무변화). 값을 입력하면
verify_parking_plan(app.services.parking) 결과가 additive 필드로 부착되어야 한다.
"""

from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

# 다른 building_compliance 테스트(test_legal_check_failclosed.py)와 동일 패턴.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.routers.building_compliance import RuleCheckRequest, rule_check


class TestRuleCheckParkingGeometryOptIn:
    @pytest.mark.asyncio
    async def test_default_path_has_no_parking_geometry_attribute(self):
        """주차 신규 필드를 전혀 보내지 않으면 parking_geometry가 아예 설정되지 않는다."""
        req = RuleCheckRequest(
            zone_code="제2종일반주거지역",
            land_area_sqm=1000,
            building_type="아파트",
            building_area_sqm=500,
            total_gfa_sqm=2000,
            floor_count_above=5,
            unit_count=20,
            parking_count=20,
        )
        resp = await rule_check(req)
        assert not hasattr(resp, "parking_geometry")

    @pytest.mark.asyncio
    async def test_opt_in_attaches_parking_geometry(self):
        """parking_layout_area_sqm을 보내면 parking_geometry가 additive로 부착된다."""
        req = RuleCheckRequest(
            zone_code="제2종일반주거지역",
            land_area_sqm=1000,
            building_type="아파트",
            building_area_sqm=500,
            total_gfa_sqm=2000,
            floor_count_above=5,
            unit_count=20,
            parking_count=20,
            parking_layout_area_sqm=3000.0,
            parking_aisle_width_m=6.5,
            parking_turn_radius_m=6.5,
        )
        resp = await rule_check(req)
        assert hasattr(resp, "parking_geometry")
        geom = resp.parking_geometry
        assert geom["required_count"] == 20  # 20세대 × 1.0대/세대
        assert geom["verdict"] in ("pass", "warn", "fail")
        assert geom["layout"] is not None
        assert geom["swept_path"] is not None

    @pytest.mark.asyncio
    async def test_zero_area_does_not_trigger_opt_in(self):
        """0 이하 면적은 opt-in 조건 미충족 — 기존과 동일하게 생략."""
        req = RuleCheckRequest(
            zone_code="제2종일반주거지역",
            land_area_sqm=1000,
            building_type="아파트",
            total_gfa_sqm=2000,
            unit_count=20,
            parking_count=20,
            parking_layout_area_sqm=0.0,
        )
        resp = await rule_check(req)
        assert not hasattr(resp, "parking_geometry")

    @pytest.mark.asyncio
    async def test_invalid_stall_type_falls_back_gracefully(self):
        """알 수 없는 stall_type 문자열이 와도 500 없이 general로 폴백해 계속 동작한다."""
        req = RuleCheckRequest(
            zone_code="제2종일반주거지역",
            land_area_sqm=1000,
            building_type="아파트",
            total_gfa_sqm=2000,
            unit_count=20,
            parking_count=20,
            parking_layout_area_sqm=3000.0,
            parking_stall_type="존재하지않는유형",
        )
        resp = await rule_check(req)
        assert hasattr(resp, "parking_geometry")
        assert resp.parking_geometry["layout"]["stall_type"] == "general"


class TestRuleCheckParkingFieldBoundaries:
    """★R1 LOW: opt-in 수치 필드 경계값 가드(Field(gt=0)/Field(ge=0))."""

    def test_negative_layout_area_rejected(self):
        with pytest.raises(ValidationError):
            RuleCheckRequest(land_area_sqm=1000, parking_layout_area_sqm=-1.0)

    def test_zero_layout_area_still_allowed_as_skip_sentinel(self):
        """0은 '미제공'과 동일하게 취급되는 sentinel이므로 ge=0으로 허용해야 한다."""
        req = RuleCheckRequest(land_area_sqm=1000, parking_layout_area_sqm=0.0)
        assert req.parking_layout_area_sqm == 0.0

    def test_zero_or_negative_aisle_width_rejected(self):
        with pytest.raises(ValidationError):
            RuleCheckRequest(land_area_sqm=1000, parking_aisle_width_m=0.0)
        with pytest.raises(ValidationError):
            RuleCheckRequest(land_area_sqm=1000, parking_aisle_width_m=-2.0)

    def test_zero_or_negative_turn_radius_rejected(self):
        with pytest.raises(ValidationError):
            RuleCheckRequest(land_area_sqm=1000, parking_turn_radius_m=0.0)

    def test_negative_angle_rejected(self):
        with pytest.raises(ValidationError):
            RuleCheckRequest(land_area_sqm=1000, parking_angle_deg=-10)
