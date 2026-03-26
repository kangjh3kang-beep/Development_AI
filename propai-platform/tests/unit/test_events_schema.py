"""SSE 이벤트 스키마 단위 테스트.

AgentStepEvent, StreamingReportEvent, DroneAlertEvent 필드 검증.
datetime.now(UTC) 사용 확인.
"""

from datetime import UTC, datetime
from pathlib import Path

from packages.schemas.events import AgentStepEvent, DroneAlertEvent, StreamingReportEvent

_EVENTS_SOURCE = (
    Path(__file__).resolve().parents[2] / "packages" / "schemas" / "events.py"
).read_text(encoding="utf-8")


class TestDatetimeUTC:
    """datetime.utcnow() 대신 datetime.now(UTC)를 사용하는지 검증."""

    def test_no_utcnow_in_source(self) -> None:
        """datetime.utcnow가 소스에 없다."""
        assert "datetime.utcnow" not in _EVENTS_SOURCE

    def test_uses_datetime_now_utc(self) -> None:
        """datetime.now(UTC)를 사용한다."""
        assert "datetime.now(UTC)" in _EVENTS_SOURCE

    def test_imports_utc(self) -> None:
        """UTC가 import되어 있다."""
        assert "from datetime import UTC" in _EVENTS_SOURCE


class TestAgentStepEvent:
    """AgentStepEvent 필드 검증."""

    def test_default_event_type(self) -> None:
        """기본 event_type이 agent_step이다."""
        event = AgentStepEvent(
            step_index=0,
            step_name="parcel_analysis",
            status="running",
            progress_pct=0.0,
        )
        assert event.event_type == "agent_step"

    def test_timestamp_is_utc(self) -> None:
        """timestamp가 UTC 타임존을 사용한다."""
        event = AgentStepEvent(
            step_index=0,
            step_name="parcel_analysis",
            status="running",
            progress_pct=0.0,
        )
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == UTC

    def test_data_optional(self) -> None:
        """data 필드는 기본 None이다."""
        event = AgentStepEvent(
            step_index=0,
            step_name="regulation",
            status="completed",
            progress_pct=1.0,
        )
        assert event.data is None

    def test_error_message_optional(self) -> None:
        """error_message 필드는 기본 None이다."""
        event = AgentStepEvent(
            step_index=0,
            step_name="avm",
            status="error",
            progress_pct=0.5,
        )
        assert event.error_message is None

    def test_progress_pct_range(self) -> None:
        """progress_pct가 0.0~1.0 범위이다."""
        event = AgentStepEvent(
            step_index=3,
            step_name="avm",
            status="completed",
            progress_pct=0.5,
        )
        assert 0.0 <= event.progress_pct <= 1.0

    def test_timestamp_recent(self) -> None:
        """timestamp가 현재 시각 근처이다."""
        before = datetime.now(UTC)
        event = AgentStepEvent(
            step_index=0,
            step_name="parcel_analysis",
            status="running",
            progress_pct=0.0,
        )
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after


class TestStreamingReportEvent:
    """StreamingReportEvent 필드 검증."""

    def test_default_event_type(self) -> None:
        """기본 event_type이 report_chunk이다."""
        event = StreamingReportEvent(chunk_index=0, content="테스트")
        assert event.event_type == "report_chunk"

    def test_is_final_default_false(self) -> None:
        """is_final 기본값이 False이다."""
        event = StreamingReportEvent(chunk_index=0, content="내용")
        assert event.is_final is False

    def test_timestamp_is_utc(self) -> None:
        """timestamp가 UTC 타임존을 사용한다."""
        event = StreamingReportEvent(chunk_index=0, content="내용")
        assert event.timestamp.tzinfo is not None


class TestDroneAlertEvent:
    """DroneAlertEvent 필드 검증."""

    def test_default_event_type(self) -> None:
        """기본 event_type이 drone_alert이다."""
        event = DroneAlertEvent(
            inspection_id="insp-001",
            severity="HIGH",
            defect_type="crack",
            location={"x": 1.0, "y": 2.0, "z": 3.0},
        )
        assert event.event_type == "drone_alert"

    def test_image_url_optional(self) -> None:
        """image_url 필드는 기본 None이다."""
        event = DroneAlertEvent(
            inspection_id="insp-002",
            severity="LOW",
            defect_type="rust",
            location={"x": 0, "y": 0, "z": 0},
        )
        assert event.image_url is None

    def test_timestamp_is_utc(self) -> None:
        """timestamp가 UTC 타임존을 사용한다."""
        event = DroneAlertEvent(
            inspection_id="insp-003",
            severity="EMERGENCY",
            defect_type="collapse",
            location={"x": 0, "y": 0, "z": 0},
        )
        assert event.timestamp.tzinfo is not None
