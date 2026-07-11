"""프로젝트 소유권 검증 표준계약 회귀가드 (IDOR 방지 공용 헬퍼).

assert_project_owned가 (1)비UUID는 검사생략 (2)소유 일치는 통과 (3)tenant 불일치는 403 거부
(4)프로젝트 부재는 graceful None 을 지키는지 고정한다. boq_auto `/draft/from-project` 등
project_id로 데이터를 조회하는 엔드포인트의 무인증/타테넌트 접근을 이 계약으로 봉합.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.auth.project_ownership import assert_project_owned

_UUID = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDB:
    """db.execute(...).first() 만 흉내내는 최소 비동기 스텁(진짜 DB 불필요)."""

    def __init__(self, row):
        self._row = row

    async def execute(self, *args, **kwargs):
        return _Result(self._row)


class _User:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


def _run(coro):
    return asyncio.run(coro)


def test_non_uuid_skips_ownership_check():
    """비UUID(데모/임시 ID) → None. 소유권 검사 생략(graceful echo 경로)."""
    assert _run(assert_project_owned("demo-project", _FakeDB(("t1",)), _User("t9"))) is None


def test_owner_match_returns_tenant():
    """UUID + 소유 tenant 일치 → owner_tenant 반환(통과)."""
    assert _run(assert_project_owned(_UUID, _FakeDB(("t1",)), _User("t1"))) == "t1"


def test_owner_mismatch_raises_403():
    """★핵심: 소유 tenant 불일치 → 403 거부(타테넌트 IDOR 차단)."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        _run(assert_project_owned(_UUID, _FakeDB(("t1",)), _User("t2")))
    assert ei.value.status_code == 403


def test_missing_project_returns_none():
    """UUID이나 프로젝트 행 부재 → None(호출부가 '프로젝트없음' 정직 처리)."""
    assert _run(assert_project_owned(_UUID, _FakeDB(None), _User("t2"))) is None


def test_null_owner_tenant_passes():
    """프로젝트의 tenant_id가 NULL(주인없음/레거시) → 검사 통과(None 소유 = 거부 근거 없음)."""
    assert _run(assert_project_owned(_UUID, _FakeDB((None,)), _User("t2"))) is None
