"""legal-check 및 regulation_service 'fail-open 제거' 회귀잠금 테스트.

★배경(라이브 그라운드 트루스): /building-compliance/legal-check 가 미등록 용도지역에 대해
overall_pass=True('적합')를 반환하는 fail-open 버그가 있었다. 실제로 검증되지 않은
용도지역이 사용자에게 '적합'으로 보이는 위험. 올바른 표준계약(fail-closed)은
resolve_zone_limits(zone_limit_contract)에 이미 존재한다.

이 테스트는 fail-closed 동작을 '잠근다'(다시 fail-open으로 회귀하면 실패한다):
  - 미등록 용도지역 → overall_pass는 True가 아님(False) + overall_status=="needs_verification".
  - 등록 용도지역(한도 이내) → overall_pass is True + overall_status=="pass".
  - 등록 용도지역(한도 초과) → overall_pass is False + overall_status=="fail".
  - regulation_service: _analyze_compliance 실패 폴백이 is_compliant=True를 반환하지 않음.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# propai-platform 루트를 Python path에 추가(다른 테스트와 동일 패턴)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.routers.building_compliance import (
    CheckRequest,
    LegalCheckRequest,
    RuleCheckRequest,
    _pre_design_review,
    legal_check,
    rule_check,
)


# ══════════════════════════════════════════════════════════════════
# 1. legal-check — 미등록 용도지역은 절대 '적합'이 아님(fail-closed)
# ══════════════════════════════════════════════════════════════════

class TestLegalCheckFailClosed:
    """미등록/미인식 용도지역은 overall_pass=True로 반환하면 안 된다."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("zone_code", ["자연취락지구", "미상", "", None])
    async def test_미등록_용도지역은_적합_아님_미확인(self, zone_code):
        req = LegalCheckRequest(
            zone_code=zone_code, planned_bcr=50, planned_far=200,
        )
        resp = await legal_check(req)
        # ★fail-open 잠금: 미등록 용도지역은 절대 True(적합)가 아님.
        assert resp.overall_pass is not True
        assert resp.overall_pass is False
        # 적합/부적합이 아닌 '미확인'으로 정직 표기.
        assert resp.overall_status == "needs_verification"
        assert "미확인" in (resp.remarks or "")

    @pytest.mark.asyncio
    async def test_등록_용도지역_한도이내_적합(self):
        # 제2종일반주거지역: 건폐율 60% / 용적률 250%(SSOT). 계획값이 한도 이내 → 적합.
        req = LegalCheckRequest(
            zone_code="제2종일반주거지역", planned_bcr=55, planned_far=240,
        )
        resp = await legal_check(req)
        assert resp.overall_pass is True
        assert resp.overall_status == "pass"
        assert resp.bcr_pass is True
        assert resp.far_pass is True
        # SSOT 한도값이 응답에 반영됨(로컬표 드리프트 없음).
        assert resp.bcr_limit == 60
        assert resp.far_limit == 250

    @pytest.mark.asyncio
    async def test_등록_용도지역_한도초과_부적합(self):
        # 제2종일반주거지역 용적률 상한 250% 초과(300%) → 부적합.
        req = LegalCheckRequest(
            zone_code="제2종일반주거지역", planned_bcr=55, planned_far=300,
        )
        resp = await legal_check(req)
        assert resp.overall_pass is False
        assert resp.overall_status == "fail"
        assert resp.far_pass is False


# ══════════════════════════════════════════════════════════════════
# 2. regulation_service — 분석 실패 폴백은 '적합'을 단정하지 않음
# ══════════════════════════════════════════════════════════════════

class TestRegulationAnalyzeFailClosed:
    """_analyze_compliance 실패 폴백이 is_compliant=True를 반환하면 안 된다."""

    @pytest.mark.asyncio
    async def test_LLM_실패시_적합_단정_안함(self):
        from apps.api.services.regulation_service import RegulationService

        mock_db = AsyncMock()
        with patch("apps.api.services.regulation_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="test")
            svc = RegulationService(mock_db)

            # LLM 호출 실패를 시뮬레이션(langchain_anthropic 미설치/임포트 실패 → except 폴백).
            # 기존 test_regulation_service.py와 동일하게 자연 실패 경로를 태운다.
            result = await svc._analyze_compliance(
                regulation_type="zoning",
                project_info={"address": "서울시"},
                retrieved_docs=[],
            )
            # ★fail-open 잠금: 실패 폴백은 절대 '적합(True)'이 아님(fail-closed=False).
            assert result["is_compliant"] is not True
            assert result["is_compliant"] is False
            assert "미확인" in result["summary"]


# ══════════════════════════════════════════════════════════════════
# 3. _pre_design_review(/check) — 서브스트링 오매칭이 '자신있는 적합'을 만들면 안 됨
# ══════════════════════════════════════════════════════════════════

class TestPreDesignReviewFailClosed:
    """설계 전 검토가 로컬표 서브스트링 오매칭('농림축산…'→'농림', '…준주거 검토용지'→'준주거')으로
    거짓 확정 한도를 확신 통과시키면 안 된다. 공용 SSOT resolve_zone_limits로 fail-closed."""

    @pytest.mark.asyncio
    async def test_미등록_스퍼리어스_존은_경고_확정한도_안붙음(self):
        # '농림축산식품부 소유부지'는 SSOT에서 미매칭(과거 로컬표는 '농림'으로 거짓확정 20/80%).
        req = CheckRequest(
            project_id="p1", zone_code="농림축산식품부 소유부지", area_sqm=1000,
            planned_bcr=25, planned_far=90,
        )
        out = await _pre_design_review(req)
        # ★fail-open 잠금: 미확정 용도지역은 '경고'(자신있는 pass 아님).
        assert out["overall_status"] == "warning"
        # 거짓 매칭(농림 한도)로 buildable_scale/건폐율 상한 확정 체크가 붙지 않는다.
        codes = [c.get("rule_code") for c in out["checks"]]
        assert "zone_unknown" in codes
        assert "buildable_scale" not in codes
        # 위반 목록에 근거없는 fail 없음(미확정=경고이지 부적합 단정도 아님).
        assert out["violations"] == []

    @pytest.mark.asyncio
    async def test_혼합표기_존은_보수적_존으로_매칭_거짓준주거_아님(self):
        # '자연녹지지역 인근 준주거 검토용지' → 과거 로컬표는 '준주거'(70/500%)로 거짓확정했다.
        # SSOT는 보수적으로 실제 등장 용도지역(자연녹지 20/100%)으로 매칭 — 거짓 500% 금지.
        req = CheckRequest(
            project_id="p2", zone_code="자연녹지지역 인근 준주거 검토용지", area_sqm=1000,
            planned_bcr=15, planned_far=90,
        )
        out = await _pre_design_review(req)
        # 최대 연면적 산정에 거짓 준주거 용적률(500%)이 새면 안 된다.
        scale = next((c for c in out["checks"] if c.get("rule_code") == "buildable_scale"), None)
        if scale is not None:
            # 자연녹지 100% 기준(최대 연면적 ≈ 1000㎡)이어야 하며 500%(≈5000㎡)면 안 됨.
            assert "5,000" not in scale["detail"]
            assert "1,000㎡" in scale["detail"]
        # 계획값(15%/90%)이 자연녹지 상한(20%/100%) 이내라 fail 없음(거짓 매칭 아님).
        assert out["violations"] == []


# ══════════════════════════════════════════════════════════════════
# 4. rule_check(/rule-check) — 한도보완이 서브스트링 오매칭으로 거짓 확정하면 안 됨
# ══════════════════════════════════════════════════════════════════

class TestRuleCheckFailClosed:
    """rule_check의 미입력 한도 보완이 로컬표 서브스트링('농림축산…'→'농림')이 아니라
    공용 SSOT resolve_zone_limits(fail-closed)로만 확정 한도를 채운다."""

    @pytest.mark.asyncio
    async def test_스퍼리어스_존은_거짓한도_안채우고_엔진기본값_폴백(self):
        # '농림축산식품부 소유부지'는 SSOT 미매칭 → max_far가 거짓 80%로 채워지면 안 됨.
        # 미입력이면 엔진 기본값(far 200)으로 graceful 폴백(거짓 확정 없음).
        req = RuleCheckRequest(
            zone_code="농림축산식품부 소유부지",
            land_area_sqm=1000, building_area_sqm=300, total_gfa_sqm=1500,
            floor_count_above=5, building_type="근린생활시설",
        )
        resp = await rule_check(req)
        # 응답이 정상 생성되고(엔진 폴백), 거짓 '농림' 매칭으로 zone_name이 확정되지 않는다.
        # (ZONE_DEFAULTS 매칭도 없으면 zone_name은 원문/미상 — 거짓 확정 아님)
        assert resp is not None
        # 연면적 1500㎡/1000㎡=150% 는 엔진 기본 far 200% 이내 → 용적률 위반(fail) 없어야 정상.
        far_items = [r for r in resp.results if "용적률" in (r.rule_name or "")]
        for it in far_items:
            # 거짓 '농림' far 80%가 채워졌다면 150%>80%로 fail이 떴을 것 — fail이면 안 됨.
            assert it.status != "fail"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
