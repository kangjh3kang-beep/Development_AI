"""프로젝트 라우터 단위 테스트.

상태 전환 맵(_VALID_TRANSITIONS) 및 응답 변환 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.routers.projects import _VALID_TRANSITIONS


class TestValidTransitions:
    """프로젝트 상태 전환 맵 테스트."""

    def test_7개_상태_정의(self):
        assert len(_VALID_TRANSITIONS) == 7

    def test_draft_상태_전환(self):
        assert "planning" in _VALID_TRANSITIONS["draft"]
        assert "archived" in _VALID_TRANSITIONS["draft"]

    def test_planning_상태_전환(self):
        assert "design" in _VALID_TRANSITIONS["planning"]
        assert "archived" in _VALID_TRANSITIONS["planning"]

    def test_design_상태_전환(self):
        assert "permit" in _VALID_TRANSITIONS["design"]
        assert "archived" in _VALID_TRANSITIONS["design"]

    def test_permit_상태_전환(self):
        assert "construction" in _VALID_TRANSITIONS["permit"]

    def test_construction_상태_전환(self):
        assert "completed" in _VALID_TRANSITIONS["construction"]

    def test_completed_상태_전환(self):
        assert "archived" in _VALID_TRANSITIONS["completed"]

    def test_archived_전환_없음(self):
        """archived는 최종 상태이므로 전환 없음."""
        assert _VALID_TRANSITIONS["archived"] == []

    def test_역방향_전환_불가(self):
        """completed → draft 같은 역방향 전환 없음."""
        assert "draft" not in _VALID_TRANSITIONS["completed"]
        assert "planning" not in _VALID_TRANSITIONS["construction"]
        assert "design" not in _VALID_TRANSITIONS["permit"]

    def test_모든_상태에서_archived_가능(self):
        """archived를 제외한 모든 상태에서 archived 전환 가능."""
        for state, transitions in _VALID_TRANSITIONS.items():
            if state != "archived":
                assert "archived" in transitions, f"{state}에서 archived 전환 불가"

    def test_직접_스킵_불가(self):
        """draft → construction 같은 단계 건너뛰기 불가."""
        assert "construction" not in _VALID_TRANSITIONS["draft"]
        assert "completed" not in _VALID_TRANSITIONS["draft"]

    def test_순차적_흐름(self):
        """draft → planning → design → permit → construction → completed."""
        flow = ["draft", "planning", "design", "permit", "construction", "completed"]
        for i in range(len(flow) - 1):
            current = flow[i]
            next_state = flow[i + 1]
            assert next_state in _VALID_TRANSITIONS[current], \
                f"{current} → {next_state} 전환이 허용되어야 함"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
