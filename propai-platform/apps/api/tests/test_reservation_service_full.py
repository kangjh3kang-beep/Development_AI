"""예약 서비스 전체 단위 테스트.

ReservationService의 모든 메서드를 검증한다:
- 예약 기간 유효성 검증
- Serializable 트랜잭션 락
- 충돌 감지
- 가용성 확인
- 예약 생성 (충돌 포함)
- 예약 취소
- 예약 목록 조회
- 시설 이용률 계산
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# 고정 테스트 ID
TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000003")
TEST_RESERVATION_ID = UUID("00000000-0000-0000-0000-000000000020")

KST = timezone(timedelta(hours=9))


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
    with patch("apps.api.services.reservation_service.get_settings") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def svc(mock_db, mock_settings):
    """ReservationService 인스턴스."""
    from apps.api.services.reservation_service import ReservationService

    return ReservationService(mock_db)


# ── 예약 기간 유효성 검증 테스트 ──


class TestValidateReservationPeriod:
    """예약 기간 유효성 검증 테스트."""

    def test_정상_예약_기간(self, svc):
        """유효한 예약 기간은 예외 없이 통과한다."""
        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 12, 0, tzinfo=KST)
        # 예외 없이 통과해야 함
        svc.validate_reservation_period(start, end)

    def test_종료가_시작_이전_에러(self, svc):
        """종료 시간이 시작 시간보다 이전이면 ValueError."""
        start = datetime(2025, 6, 1, 12, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        with pytest.raises(ValueError, match="종료 시간은 시작 시간보다 이후여야 합니다"):
            svc.validate_reservation_period(start, end)

    def test_동일_시작_종료_에러(self, svc):
        """시작과 종료가 동일하면 ValueError."""
        t = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        with pytest.raises(ValueError, match="종료 시간은 시작 시간보다 이후여야 합니다"):
            svc.validate_reservation_period(t, t)

    def test_최소_예약_시간_미만_에러(self, svc):
        """30분 미만 예약은 ValueError."""
        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 10, 15, tzinfo=KST)
        with pytest.raises(ValueError, match="최소 예약 단위는 30분입니다"):
            svc.validate_reservation_period(start, end)

    def test_최대_예약_기간_초과_에러(self, svc):
        """30일 초과 예약은 ValueError."""
        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 7, 5, 10, 0, tzinfo=KST)  # 34일
        with pytest.raises(ValueError, match="최대 예약 기간은 30일입니다"):
            svc.validate_reservation_period(start, end)

    def test_정확히_30분_허용(self, svc):
        """정확히 30분은 허용된다."""
        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 10, 30, tzinfo=KST)
        svc.validate_reservation_period(start, end)


# ── Serializable 트랜잭션 락 테스트 ──


class TestAcquireLock:
    """Serializable 격리 수준 설정 테스트."""

    @pytest.mark.asyncio
    async def test_락_SQL_실행(self, svc, mock_db):
        """acquire_lock 호출 시 SET TRANSACTION ISOLATION LEVEL SERIALIZABLE이 실행된다."""
        await svc.acquire_lock()
        mock_db.execute.assert_awaited_once()
        call_args = mock_db.execute.call_args[0][0]
        assert "SERIALIZABLE" in str(call_args)


# ── 충돌 감지 테스트 ──


class TestDetectConflict:
    """시간대 충돌 감지 테스트."""

    @pytest.mark.asyncio
    async def test_충돌_없음(self, svc, mock_db):
        """충돌이 없으면 빈 리스트를 반환한다."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 12, 0, tzinfo=KST)
        conflicts = await svc.detect_conflict(TEST_PROJECT_ID, "회의실 A", start, end)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_충돌_있음(self, svc, mock_db):
        """시간이 겹치는 기존 예약이 있으면 해당 예약을 반환한다."""
        mock_reservation = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_reservation]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 12, 0, tzinfo=KST)
        conflicts = await svc.detect_conflict(TEST_PROJECT_ID, "회의실 A", start, end)
        assert len(conflicts) == 1


# ── 가용성 확인 테스트 ──


class TestCheckAvailability:
    """시간대 가용성 확인 테스트."""

    @pytest.mark.asyncio
    async def test_가용_시간대(self, svc, mock_db):
        """충돌 없는 시간대는 available=True를 반환한다."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 12, 0, tzinfo=KST)
        result = await svc.check_availability(TEST_PROJECT_ID, "회의실 A", start, end)
        assert result["available"] is True
        assert result["conflicts"] == 0


# ── 예약 생성 테스트 ──


class TestCreateReservation:
    """예약 생성 테스트."""

    @pytest.mark.asyncio
    async def test_예약_생성_성공(self, svc, mock_db):
        """충돌이 없으면 예약이 성공적으로 생성된다."""
        # detect_conflict가 빈 리스트를 반환하도록 설정
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 12, 0, tzinfo=KST)

        reservation = await svc.create_reservation(
            tenant_id=TEST_TENANT_ID,
            project_id=TEST_PROJECT_ID,
            facility_name="회의실 A",
            reserved_by=TEST_USER_ID,
            start_time=start,
            end_time=end,
            notes="정기 회의",
        )
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_예약_생성_충돌_에러(self, svc, mock_db):
        """충돌이 있으면 ValueError가 발생한다."""
        # acquire_lock은 첫 번째 execute 호출
        # detect_conflict는 두 번째 execute 호출
        existing_reservation = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [existing_reservation]
        mock_result_conflict = MagicMock()
        mock_result_conflict.scalars.return_value = mock_scalars

        # 첫 번째 호출: acquire_lock (결과 무관)
        # 두 번째 호출: detect_conflict (충돌 반환)
        mock_db.execute.side_effect = [MagicMock(), mock_result_conflict]

        start = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        end = datetime(2025, 6, 1, 12, 0, tzinfo=KST)

        with pytest.raises(ValueError, match="기존 예약이 있습니다"):
            await svc.create_reservation(
                tenant_id=TEST_TENANT_ID,
                project_id=TEST_PROJECT_ID,
                facility_name="회의실 A",
                reserved_by=TEST_USER_ID,
                start_time=start,
                end_time=end,
            )


# ── 예약 취소 테스트 ──


class TestCancelReservation:
    """예약 취소 테스트."""

    @pytest.mark.asyncio
    async def test_예약_취소_성공(self, svc, mock_db):
        """존재하는 예약을 취소하면 상태가 cancelled로 변경된다."""
        mock_reservation = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_db.execute.return_value = mock_result

        result = await svc.cancel_reservation(TEST_RESERVATION_ID, TEST_TENANT_ID)
        assert result is not None
        assert result.status == "cancelled"
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_예약_취소_미존재(self, svc, mock_db):
        """존재하지 않는 예약을 취소하면 None을 반환한다."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await svc.cancel_reservation(TEST_RESERVATION_ID, TEST_TENANT_ID)
        assert result is None


# ── 예약 목록 조회 테스트 ──


class TestListReservations:
    """예약 목록 조회 테스트."""

    @pytest.mark.asyncio
    async def test_예약_목록_조회(self, svc, mock_db):
        """시설의 예약 목록을 올바르게 반환한다."""
        mock_reservations = [MagicMock(), MagicMock()]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_reservations
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await svc.list_reservations(TEST_PROJECT_ID, "회의실 A")
        assert len(result) == 2


# ── 시설 이용률 계산 테스트 ──


class TestCalculateUtilizationRate:
    """시설 이용률 계산 테스트."""

    def test_이용률_정상(self, svc):
        """예약 시간 대비 이용률을 정확히 계산한다."""
        r1 = MagicMock()
        r1.status = "confirmed"
        r1.start_time = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        r1.end_time = datetime(2025, 6, 1, 12, 0, tzinfo=KST)  # 2시간

        r2 = MagicMock()
        r2.status = "confirmed"
        r2.start_time = datetime(2025, 6, 1, 14, 0, tzinfo=KST)
        r2.end_time = datetime(2025, 6, 1, 15, 0, tzinfo=KST)  # 1시간

        # 총 3시간 / 10시간 = 30%
        rate = svc.calculate_utilization_rate([r1, r2], total_hours=10.0)
        assert rate == 30.0

    def test_이용률_취소_예약_제외(self, svc):
        """취소된 예약은 이용률 계산에서 제외한다."""
        r1 = MagicMock()
        r1.status = "cancelled"
        r1.start_time = datetime(2025, 6, 1, 10, 0, tzinfo=KST)
        r1.end_time = datetime(2025, 6, 1, 12, 0, tzinfo=KST)

        rate = svc.calculate_utilization_rate([r1], total_hours=10.0)
        assert rate == 0.0

    def test_이용률_총시간_0(self, svc):
        """총 시간이 0이면 0%를 반환한다."""
        rate = svc.calculate_utilization_rate([], total_hours=0)
        assert rate == 0.0

    def test_이용률_100_초과_방지(self, svc):
        """이용률이 100%를 초과하지 않도록 캡핑한다."""
        r1 = MagicMock()
        r1.status = "confirmed"
        r1.start_time = datetime(2025, 6, 1, 0, 0, tzinfo=KST)
        r1.end_time = datetime(2025, 6, 2, 0, 0, tzinfo=KST)  # 24시간

        # 24시간 / 10시간 → 240% → 100%로 캡핑
        rate = svc.calculate_utilization_rate([r1], total_hours=10.0)
        assert rate == 100.0
