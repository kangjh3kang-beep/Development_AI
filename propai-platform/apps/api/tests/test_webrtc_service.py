"""WebRTC 영상 감리 세션 서비스 단위 테스트.

WebRTCService의 모든 메서드를 검증한다:
- SDP 정규화 / Answer 생성
- 세션 생성 / 조회 / 종료
- SDP Offer 처리
- ICE candidate 재시도 로직
- 세션 지속 시간 계산
"""

import os
import sys
from datetime import UTC, datetime

UTC = UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# 고정 테스트 ID
TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000003")
TEST_SESSION_ID = UUID("00000000-0000-0000-0000-000000000010")


@pytest.fixture
def mock_db():
    """Mock DB 세션."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_settings():
    """get_settings 모킹을 위한 패치."""
    with patch("apps.api.services.webrtc_service.get_settings") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def svc(mock_db, mock_settings):
    """WebRTCService 인스턴스."""
    from apps.api.services.webrtc_service import WebRTCService

    return WebRTCService(mock_db)


# ── SDP 처리 테스트 ──


class TestSanitizeSDP:
    """SDP 정규화 테스트."""

    def test_줄바꿈_LF를_CRLF로_변환(self, svc):
        """LF(\\n)만 포함된 SDP를 CR+LF(\\r\\n)로 변환한다."""
        result = svc.sanitize_sdp("v=0\no=- 123\ns=-")
        assert "\r\n" in result
        assert result == "v=0\r\no=- 123\r\ns=-"

    def test_기존_CRLF_유지(self, svc):
        """이미 CR+LF인 SDP는 변환 후에도 동일해야 한다."""
        original = "v=0\r\no=- 123\r\ns=-"
        result = svc.sanitize_sdp(original)
        assert result == original

    def test_빈문자열(self, svc):
        """빈 문자열 입력 시 빈 문자열 반환."""
        assert svc.sanitize_sdp("") == ""

    def test_혼합_줄바꿈_정규화(self, svc):
        """CR+LF와 LF가 혼합된 경우에도 정상 정규화."""
        mixed = "line1\r\nline2\nline3"
        result = svc.sanitize_sdp(mixed)
        # \r\n → \n → \r\n 이므로 모두 \r\n 으로 통일
        assert result.count("\r\n") == 2


class TestGenerateSDPAnswer:
    """SDP Answer 생성 테스트."""

    def test_기본_SDP_Answer_포맷(self, svc):
        """세션 ID가 포함된 유효한 SDP Answer를 반환한다."""
        answer = svc.generate_sdp_answer(TEST_SESSION_ID)
        assert "v=0" in answer
        assert str(TEST_SESSION_ID) in answer
        assert "propai-webrtc" in answer

    def test_SDP_Answer_CRLF_포맷(self, svc):
        """SDP Answer는 CR+LF 줄바꿈을 사용한다."""
        answer = svc.generate_sdp_answer(TEST_SESSION_ID)
        assert "\r\n" in answer


# ── 세션 관리 테스트 ──


class TestCreateSession:
    """세션 생성 테스트."""

    @pytest.mark.asyncio
    async def test_세션_생성_성공(self, svc, mock_db):
        """세션 생성 시 DB에 추가되고 커밋된다."""
        session = await svc.create_session(
            tenant_id=TEST_TENANT_ID,
            project_id=TEST_PROJECT_ID,
            user_id=TEST_USER_ID,
        )
        # DB에 add 호출 확인
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_세션_생성_필드_검증(self, svc, mock_db):
        """생성된 세션의 필드 값이 올바른지 확인한다."""
        session = await svc.create_session(
            tenant_id=TEST_TENANT_ID,
            project_id=TEST_PROJECT_ID,
            user_id=TEST_USER_ID,
        )
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.tenant_id == TEST_TENANT_ID
        assert added_obj.project_id == TEST_PROJECT_ID
        assert added_obj.initiator_user_id == TEST_USER_ID
        assert added_obj.status == "waiting"


class TestGetSession:
    """세션 조회 테스트."""

    @pytest.mark.asyncio
    async def test_세션_조회_성공(self, svc, mock_db):
        """존재하는 세션을 조회하면 결과를 반환한다."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await svc.get_session(TEST_SESSION_ID, TEST_TENANT_ID)
        assert result == mock_session

    @pytest.mark.asyncio
    async def test_세션_조회_미존재(self, svc, mock_db):
        """존재하지 않는 세션을 조회하면 None을 반환한다."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await svc.get_session(TEST_SESSION_ID, TEST_TENANT_ID)
        assert result is None


class TestListActiveSessions:
    """활성 세션 목록 조회 테스트."""

    @pytest.mark.asyncio
    async def test_활성_세션_목록_조회(self, svc, mock_db):
        """활성 세션 목록을 올바르게 반환한다."""
        mock_sessions = [MagicMock(), MagicMock()]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_sessions
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await svc.list_active_sessions(TEST_TENANT_ID)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_프로젝트별_활성_세션_조회(self, svc, mock_db):
        """프로젝트 ID를 지정하면 해당 프로젝트의 활성 세션만 반환한다."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await svc.list_active_sessions(
            TEST_TENANT_ID, project_id=TEST_PROJECT_ID
        )
        assert result == []


class TestHandleOffer:
    """SDP Offer 처리 테스트."""

    @pytest.mark.asyncio
    async def test_Offer_처리_성공(self, svc, mock_db):
        """SDP Offer를 수신하면 세션 상태가 active로 변경되고 Answer를 반환한다."""
        mock_session = MagicMock()
        mock_session.id = TEST_SESSION_ID
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        session, answer = await svc.handle_offer(
            session_id=TEST_SESSION_ID,
            tenant_id=TEST_TENANT_ID,
            sdp="v=0\no=- 123",
        )
        assert session.status == "active"
        assert "v=0" in answer
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_Offer_세션_미존재_에러(self, svc, mock_db):
        """존재하지 않는 세션에 Offer를 보내면 ValueError가 발생한다."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="세션을 찾을 수 없습니다"):
            await svc.handle_offer(
                session_id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                sdp="v=0",
            )


class TestHandleICECandidate:
    """ICE candidate 처리 테스트."""

    @pytest.mark.asyncio
    async def test_ICE_candidate_첫번째_시도_성공(self, svc, mock_db):
        """ICE candidate가 첫 번째 시도에서 성공한다."""
        mock_session = MagicMock()
        mock_session.ice_candidates_json = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        success, attempts = await svc.handle_ice_candidate(
            session_id=TEST_SESSION_ID,
            tenant_id=TEST_TENANT_ID,
            candidate={"candidate": "test", "sdpMid": "0"},
        )
        assert success is True
        assert attempts == 1

    @pytest.mark.asyncio
    async def test_ICE_세션_미존재_에러(self, svc, mock_db):
        """존재하지 않는 세션에 ICE candidate를 보내면 ValueError가 발생한다."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="세션을 찾을 수 없습니다"):
            await svc.handle_ice_candidate(
                session_id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                candidate={"candidate": "test"},
            )

    @pytest.mark.asyncio
    async def test_ICE_재시도_후_최종_실패(self, svc, mock_db):
        """모든 재시도가 실패하면 (False, 3)을 반환한다."""
        mock_session = MagicMock()
        mock_session.ice_candidates_json = {"candidates": []}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # flush에서 예외를 발생시켜 재시도 유도
        mock_db.flush.side_effect = Exception("DB 오류")

        with patch("apps.api.services.webrtc_service.asyncio.sleep", new_callable=AsyncMock):
            success, attempts = await svc.handle_ice_candidate(
                session_id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                candidate={"candidate": "retry-test"},
            )
        assert success is False
        assert attempts == 3


class TestEndSession:
    """세션 종료 테스트."""

    @pytest.mark.asyncio
    async def test_세션_종료_성공(self, svc, mock_db):
        """세션을 종료하면 상태가 ended로 변경된다."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await svc.end_session(TEST_SESSION_ID, TEST_TENANT_ID)
        assert result is not None
        assert result.status == "ended"
        assert result.ended_at is not None
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_세션_종료_미존재(self, svc, mock_db):
        """존재하지 않는 세션 종료 시 None을 반환한다."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await svc.end_session(TEST_SESSION_ID, TEST_TENANT_ID)
        assert result is None


class TestCalculateSessionDuration:
    """세션 지속 시간 계산 테스트."""

    def test_지속_시간_계산(self, svc):
        """시작/종료 시간이 모두 있으면 초 단위로 지속 시간을 반환한다."""
        mock_session = MagicMock()
        mock_session.started_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        mock_session.ended_at = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)

        duration = svc.calculate_session_duration(mock_session)
        assert duration == 1800.0  # 30분 = 1800초

    def test_종료_시간_없으면_None(self, svc):
        """종료 시간이 없으면 None을 반환한다."""
        mock_session = MagicMock()
        mock_session.started_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        mock_session.ended_at = None

        duration = svc.calculate_session_duration(mock_session)
        assert duration is None

    def test_시작_시간_없으면_None(self, svc):
        """시작 시간이 없으면 None을 반환한다."""
        mock_session = MagicMock()
        mock_session.started_at = None
        mock_session.ended_at = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)

        duration = svc.calculate_session_duration(mock_session)
        assert duration is None
