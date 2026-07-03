"""LiveKit Phase 3 — T1: 룸명·권한 순수 규칙(결정론, 인프라/키 불요).

역할→VideoGrant 매핑·프로젝트 스코프 룸명·녹화 권한을 단위로 검증한다(LiveKit Cloud 미연결).
멤버십 자체(접근 가능 여부)는 라우터 require_project_member가 1차 강제 — 본 규칙은 역할별 권한만.
"""

from app.services.livekit.livekit_rules import can_record, room_name, video_grant


class TestRoomName:
    def test_project_scoped_deterministic(self):
        assert room_name("p1", "main") == "proj-p1-main"
        assert room_name("p1") == "proj-p1-main"  # 기본 room_key=main
        assert room_name("p1", "main") == room_name("p1", "main")  # 결정론

    def test_sanitizes_unsafe_chars(self):
        assert room_name("p1", "a/b c!") == "proj-p1-abc"  # 비안전 문자 제거
        assert room_name("p1", "") == "proj-p1-main"  # 빈값→main
        assert room_name("p1", "헬로") == "proj-p1-main"  # 비ASCII 전부 제거→main 폴백


class TestVideoGrant:
    def test_host_roomadmin_and_publish(self):
        g = video_grant("owner", "r1")
        assert g["room"] == "r1"
        assert g["room_join"] is True
        assert g["room_admin"] is True
        assert g["can_publish"] is True
        assert g["can_subscribe"] is True
        assert video_grant("manager", "r1")["room_admin"] is True

    def test_participant_publish_no_admin(self):
        for role in ("contributor", "reviewer_internal", "external_reviewer"):
            g = video_grant(role, "r1")
            assert g["can_publish"] is True
            assert g["can_subscribe"] is True
            assert g["room_admin"] is False

    def test_viewer_subscribe_only(self):
        g = video_grant("viewer", "r1")
        assert g["can_publish"] is False
        assert g["can_subscribe"] is True
        assert g["room_admin"] is False

    def test_unknown_role_least_privilege(self):
        # 미지 역할은 최소권한(구독만, admin·publish 없음)
        g = video_grant("bogus", "r1")
        assert g["can_publish"] is False
        assert g["room_admin"] is False
        assert g["can_subscribe"] is True


class TestCanRecord:
    def test_host_only(self):
        assert can_record("owner") is True
        assert can_record("manager") is True
        for role in ("contributor", "reviewer_internal", "external_reviewer", "viewer", "bogus"):
            assert can_record(role) is False


class TestRecordingModel:
    def test_table_and_columns(self):
        from app.models.livekit import Recording

        assert Recording.__tablename__ == "livekit_recordings"
        cols = set(Recording.__table__.columns.keys())
        for c in ("id", "project_id", "organization_id", "room", "egress_id",
                  "s3_key", "status", "started_by", "started_at", "ended_at"):
            assert c in cols, f"Recording 컬럼 누락: {c}"
        assert Recording.__table__.columns["room"].nullable is False
        assert Recording.__table__.columns["status"].default.arg == "recording"
