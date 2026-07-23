"""용적률 rule-check/legal-check 구조상한(건폐율×층수) 흡수 — 회귀잠금(레인H, 2026-07-24).

★배경(라이브 그라운드 트루스): POST /building-compliance/rule-check
(BuildingCodeRuleEngine._check_far)와 POST /building-compliance/legal-check가 자연녹지 등
층수제한 zone에서 법정 용적률 '범위' 상한(예: 자연녹지 100%)만 비교해, 실효 물리적 상한
(건폐 20%×법정4층=80%)을 넘는 far=100% 설계를 '적합'으로 과대낙관 통과시켰다.

근본원인: 두 경로가 공유하는 zone_limit_contract.resolve_zone_limits가 legal_limits_for만
참조하고, 구조상한을 흡수한 applicable_limits_for(레인A, 2026-07-23)를 거치지 않는다.

근원수정: 공용 헬퍼 far_cap_with_structural_overlay(legal_zone_limits.py, structural_cap_for·
should_apply_structural_cap을 감싸 재사용 — 산식 복제 0)를 신설해 BuildingCodeRuleEngine.
_check_far와 /legal-check 라우터 둘 다 이 헬퍼 하나만 임포트한다(한 곳 수정이 두 경로에 전파).

이 테스트는 구조상한 흡수 동작을 '잠근다'(다시 법정 상한만 비교하는 과대낙관 회귀가
재발하면 실패한다). _check_bcr은 건폐율 자체가 구조상한과 무관해(건폐율은 이미 법정
실효 상한) 미변경 — 이 파일은 BL-002(용적률)만 다룬다.
"""

from __future__ import annotations

import pytest

from app.services.permit.building_code_rules import BuildingCodeRuleEngine, ComplianceStatus
from app.services.zoning.legal_zone_limits import far_cap_with_structural_overlay

_ENGINE = BuildingCodeRuleEngine()


# ══════════════════════════════════════════════════════════════════
# 1. far_cap_with_structural_overlay — 공용 헬퍼 단위테스트
# ══════════════════════════════════════════════════════════════════

class TestFarCapWithStructuralOverlay:
    def test_binds_when_structural_cap_lower_than_legal_max(self):
        # 자연녹지 건폐 20% × 법정 4층 = 80% < 법정 100% → 구조상한 바인딩.
        far, floor_cap, basis, note = far_cap_with_structural_overlay("자연녹지지역", 100.0, 20.0)
        assert far == 80.0
        assert floor_cap == 4
        assert basis is not None and "별표17" in basis
        assert note is None

    def test_unlimited_floor_zone_is_fully_unaffected(self):
        # 일반상업지역은 층수 제한이 없어 구조상한 대상이 아니다(완전 무영향 — 무회귀).
        far, floor_cap, basis, note = far_cap_with_structural_overlay("일반상업지역", 1300.0, 70.0)
        assert far == 1300.0
        assert floor_cap is None
        assert basis is None
        assert note is None

    def test_missing_applied_bcr_is_silent_passthrough(self):
        # 건폐율 미입력(None) — 산정 근거 없음. 경고 없이 원래 한도 유지(무음 — 정상 케이스).
        far, floor_cap, basis, note = far_cap_with_structural_overlay("자연녹지지역", 100.0, None)
        assert far == 100.0
        assert floor_cap is None
        assert basis is None
        assert note is None

    def test_ratio_unit_contamination_keeps_legal_max_but_notes_reason(self):
        # 건폐율이 비율(0.2)로 오입력되면 structural_cap_for의 R1 타당성 게이트가
        # (None,None,None)을 반환한다 — 무음 폴백 금지, 법정 한도는 유지하되 사유를 정직 표기.
        far, floor_cap, basis, note = far_cap_with_structural_overlay("자연녹지지역", 100.0, 0.2)
        assert far == 100.0
        assert floor_cap is None
        assert basis is None
        assert note is not None and "확인 필요" in note

    def test_bcr_exceeding_legal_max_keeps_legal_far_but_notes_reason(self):
        # 자연녹지 법정 건폐 상한(20%)을 넘는 45% 입력(오염/오입력 의심) — 동일 게이트.
        far, floor_cap, basis, note = far_cap_with_structural_overlay("자연녹지지역", 100.0, 45.0)
        assert far == 100.0
        assert note is not None

    def test_cap_equal_to_max_far_does_not_bind(self):
        # 보전녹지(법정 건폐 20%·용적 80%): 구조상한 = 20%×4층 = 80% == 법정 80% — 엄격히
        # '더 낮을' 때만 바인딩(should_apply_structural_cap 시맨틱)하므로 미적용(그대로 유지).
        far, floor_cap, basis, note = far_cap_with_structural_overlay("보전녹지지역", 80.0, 20.0)
        assert far == 80.0
        assert basis is None
        assert note is None

    def test_missing_max_far_returns_none(self):
        far, floor_cap, basis, note = far_cap_with_structural_overlay("자연녹지지역", None, 20.0)
        assert far is None
        assert floor_cap is None and basis is None and note is None


# ══════════════════════════════════════════════════════════════════
# 2. BuildingCodeRuleEngine._check_far(BL-002) — 자연녹지 구조상한 흡수
# ══════════════════════════════════════════════════════════════════

class TestCheckFarStructuralCapAbsorption:
    def test_natural_green_bcr20_far100_now_fails_at_structural_cap(self):
        """★확정버그 회귀잠금: 자연녹지 bcr=20%·far=100%는 과거 '적합'(법정100% 비교)이었으나
        구조상한(20%×4층=80%) 흡수 후 '부적합'(80% 이하)이어야 한다(라이브 재현 대조)."""
        design = {"building_area_sqm": 200.0, "total_gfa_sqm": 1000.0}
        site = {"land_area_sqm": 1000.0, "max_far": 100.0, "zone_type": "자연녹지지역"}

        result = _ENGINE._check_far(design, site)  # noqa: SLF001 — 회귀잠금 직접 호출

        assert result.status == ComplianceStatus.FAIL
        assert result.required_value == "80% 이하 (구조상한: 건폐율×4층)"
        assert result.actual_value == "100.0%"

    def test_natural_green_within_structural_cap_passes(self):
        # bcr=15%×4층=60%(구조상한) ≥ far 60% → 적합(경계값). 구조상한이 여전히 표시됨.
        design = {"building_area_sqm": 150.0, "total_gfa_sqm": 600.0}
        site = {"land_area_sqm": 1000.0, "max_far": 100.0, "zone_type": "자연녹지지역"}

        result = _ENGINE._check_far(design, site)  # noqa: SLF001

        assert result.status == ComplianceStatus.PASS
        assert "구조상한" in result.required_value

    def test_unlimited_floor_zone_unaffected_by_structural_cap(self):
        """층수 무제한 용도지역(일반상업지역)은 구조상한 대상이 아니다(완전 무영향)."""
        design = {"building_area_sqm": 700.0, "total_gfa_sqm": 12000.0}
        site = {"land_area_sqm": 1000.0, "max_far": 1300.0, "zone_type": "일반상업지역"}

        result = _ENGINE._check_far(design, site)  # noqa: SLF001

        assert result.status == ComplianceStatus.PASS
        assert result.required_value == "1300% 이하"  # 구조상한 문구 없음(무영향)

    def test_bcr_ratio_contamination_does_not_silently_pass_without_note(self):
        """건폐율 입력 이상(bcr=0.2%, 비율↔퍼센트 오입력 의심)이어도 법정 한도로 정직
        폴백하되(무음 아님) 사유를 required_value에 남긴다."""
        design = {"building_area_sqm": 2.0, "total_gfa_sqm": 1000.0}  # bcr=0.2%
        site = {"land_area_sqm": 1000.0, "max_far": 100.0, "zone_type": "자연녹지지역"}

        result = _ENGINE._check_far(design, site)  # noqa: SLF001

        assert result.status == ComplianceStatus.PASS  # 법정 100% 유지(비물리 bcr로 미산정)
        assert "구조상한 미산정" in result.required_value

    def test_missing_building_area_is_silent_no_cap_note(self):
        """건축면적 미입력(0)은 '이상 입력'이 아니라 '미제공' — 무음으로 법정 한도 유지."""
        design = {"total_gfa_sqm": 900.0}  # building_area_sqm 결손
        site = {"land_area_sqm": 1000.0, "max_far": 100.0, "zone_type": "자연녹지지역"}

        result = _ENGINE._check_far(design, site)  # noqa: SLF001

        assert result.required_value == "100% 이하"  # 구조상한/미산정 문구 없음(무음)


# ══════════════════════════════════════════════════════════════════
# 3. /legal-check 형제 스윕 — 동일 결함·동일 공용헬퍼(로직 복제 없음)
# ══════════════════════════════════════════════════════════════════

class TestLegalCheckStructuralCapAbsorption:
    @pytest.mark.asyncio
    async def test_natural_green_bcr20_far100_now_fails(self):
        from apps.api.routers.building_compliance import LegalCheckRequest, legal_check

        req = LegalCheckRequest(
            zone_code="자연녹지지역", planned_bcr=20, planned_far=100, planned_height_m=12,
        )
        resp = await legal_check(req)

        assert resp.overall_status == "fail"
        assert resp.far_pass is False
        assert resp.far_limit == 80.0
        assert "구조상한" in (resp.remarks or "")

    @pytest.mark.asyncio
    async def test_unlimited_floor_zone_unaffected(self):
        from apps.api.routers.building_compliance import LegalCheckRequest, legal_check

        req = LegalCheckRequest(
            zone_code="일반상업지역", planned_bcr=70, planned_far=1200, planned_height_m=0,
        )
        resp = await legal_check(req)

        assert resp.overall_status == "pass"
        assert resp.far_limit == 1300


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
