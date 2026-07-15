"""설계 자동 검토 피드백 테스트 (건축법)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.design_review.design_review_service import DesignReviewService


class TestDesignReview:
    """설계 검토."""

    def setup_method(self):
        self.svc = DesignReviewService()

    def test_all_pass(self):
        """규제 이내 → pass."""
        result = self.svc.review_design_parameters(
            {"far_applied": 200, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        assert result["review_status"] == "pass"
        assert result["error_count"] == 0
        assert result["pass_rate_pct"] == 100.0

    def test_far_exceeded(self):
        """용적률 초과 → correction_required."""
        result = self.svc.review_design_parameters(
            {"far_applied": 350, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        assert result["review_status"] == "correction_required"
        assert result["error_count"] >= 1
        errors = [e["item"] for e in result["errors_detected"]]
        assert "용적률_초과" in errors

    def test_bcr_exceeded(self):
        """건폐율 초과."""
        result = self.svc.review_design_parameters(
            {"far_applied": 200, "bcr_applied": 70},
            {"max_far": 300, "max_bcr": 60},
        )
        errors = [e["item"] for e in result["errors_detected"]]
        assert "건폐율_초과" in errors

    def test_correction_items_provided(self):
        """위반 시 보정 항목 제시."""
        result = self.svc.review_design_parameters(
            {"far_applied": 350, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        assert len(result["correction_items"]) > 0

    def test_checklist_count(self):
        """검토 체크리스트 10개 항목."""
        assert len(DesignReviewService.REVIEW_CHECKLIST) == 10

    def test_legal_basis(self):
        """법적 근거: 건축법 제25조."""
        result = self.svc.review_design_parameters(
            {"far_applied": 200, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        assert result["legal_basis"] == "건축법 제25조"

    def test_not_checked_items_separated(self):
        """★정직성: 이 파라미터 검토는 건폐율·용적률만 판정한다.

        나머지 8개 체크리스트(일조·주차·피난·방화·장애인·에너지 등)를 passed로 합산해
        pass_rate를 부풀리던 오도를 제거 — not_checked로 분리하고 pass_rate는 검사 항목 기준.
        """
        result = self.svc.review_design_parameters(
            {"far_applied": 200, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        # 검사 대상은 2개(건폐율·용적률)뿐 — passed 2개, not_checked 8개(정직 분리).
        assert result["checked_items"] == ["건폐율_준수", "용적률_준수"]
        assert set(result["passed_items"]) == {"건폐율_준수", "용적률_준수"}
        assert len(result["not_checked_items"]) == 8
        assert "주차장_설치기준" in result["not_checked_items"]
        assert "피난시설_적합" in result["not_checked_items"]
        # pass_rate는 '검사한 항목(2개)' 기준 — 미검사 8개를 통과로 계산하지 않는다.
        assert result["pass_rate_pct"] == 100.0

    def test_pass_rate_reflects_only_checked(self):
        """용적률 초과 시 pass_rate = 1/2(50%) — 검사 항목만 반영(미검사 항목 제외)."""
        result = self.svc.review_design_parameters(
            {"far_applied": 350, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        assert result["passed_items"] == ["건폐율_준수"]
        assert result["pass_rate_pct"] == 50.0
