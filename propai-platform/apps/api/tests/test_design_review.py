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
