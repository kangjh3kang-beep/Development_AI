"""team_service.approve_member — SoD(직무분리, 백로그③) 통합 테스트.

approve_member()가 실제로 실행하는 SQL 표면(team_members 단건 조회·_assign_to_team의 UPDATE 2건)만
충실히 모사하는 인메모리 fake DB로 구동한다(site_basis_service/design_run_store 테스트 선례 동형).
create_team/request_join 전체 흐름을 재현하지 않고, "가입 신청(pending)" 사전 상태를 직접 seed한다.

이 도메인의 author는 "신청자(user_id)"다 — request_join()이 항상 str(user_id)를 필수로 채우므로
(선택적 컬럼이 아니라 team_members.user_id 자체가 PK 구성요소) author가 None이 되는 경로가
구조적으로 없다. 그래서 "③author 미기록 → skip 표식" 케이스는 이 도메인에서 재현 불가능하며,
그 표식 자체의 정확성은 apps/api/tests/approval/test_sod.py(enforce_sod 제네릭 게이트)가 이미
포괄한다 — 여기서는 ①②④만 도메인 고유 통합 시나리오로 검증한다.
"""
from __future__ import annotations

import pytest

from app.services.team import team_service


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeTeamDb:
    """approve_member/_assign_to_team이 작성하는 SQL만 충실히 모사하는 인메모리 fake."""

    def __init__(self):
        self.members: dict[tuple[str, str], dict] = {}
        self.users: dict[str, dict] = {}
        self.commits = 0

    def seed_member(self, team_id: str, user_id: str, *, status: str = "pending") -> None:
        self.members[(team_id, str(user_id))] = {
            "status": status, "approved_by": None, "sod_check": None,
        }

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        p = params or {}
        if sql.strip().startswith(
            "SELECT status FROM team_members WHERE team_id=:t AND user_id=:u"
        ):
            row = self.members.get((p["t"], str(p["u"])))
            return _Res((row["status"],)) if row is not None else _Res(None)
        if sql.strip().startswith("UPDATE team_members SET status='approved'"):
            row = self.members.get((p["t"], str(p["u"])))
            if row is not None:
                row["status"] = "approved"
                row["approved_by"] = p["a"]
                row["sod_check"] = p.get("sod")
            return _Res(None)
        if sql.strip().startswith("UPDATE users SET tenant_id=:tt, role='team_member'"):
            self.users[str(p["u"])] = {"tenant_id": p["tt"], "role": "team_member"}
            return _Res(None)
        return _Res(None)

    async def commit(self):
        self.commits += 1


_TEAM = {"id": "team-1", "tenant_id": "tenant-team-1"}


# ══════════════════════════════════════════════════════════════════════════
# ① 자기승인 차단 — 신청자 본인이 자기 신청을 스스로 승인
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_self_approval_of_own_pending_request_is_blocked():
    """신청자(user_id)와 승인자(approver_id)가 동일하면 SoD 위반으로 거부된다."""
    db = _FakeTeamDb()
    db.seed_member("team-1", "user-1", status="pending")

    out = await team_service.approve_member(db, _TEAM, "user-1", "user-1")

    assert out["ok"] is False
    assert "SoD" in out["error"]
    # 원본은 여전히 pending(무단 승격 0).
    assert db.members[("team-1", "user-1")]["status"] == "pending"


# ══════════════════════════════════════════════════════════════════════════
# ② 타인(팀장) 승인 정상 통과
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_owner_approving_different_applicant_passes_and_marks_sod_check():
    """팀장(승인자)이 다른 신청자를 승인하면 정상 승인되고 sod_check="passed"가 기록된다."""
    db = _FakeTeamDb()
    db.seed_member("team-1", "user-2", status="pending")

    out = await team_service.approve_member(db, _TEAM, "user-2", "owner-1")

    assert out["ok"] is True
    assert out["sod_check"] == "passed"
    row = db.members[("team-1", "user-2")]
    assert row["status"] == "approved"
    assert row["approved_by"] == "owner-1"
    assert row["sod_check"] == "passed"
    assert db.users["user-2"]["tenant_id"] == "tenant-team-1"


# ══════════════════════════════════════════════════════════════════════════
# ④ 기존 흐름 무회귀 — pending이 아니면(초대·부재) SoD 판정 이전에 그대로 거부
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_pending_request_still_rejected_same_as_before():
    """가입 신청(pending) 자체가 없으면 SoD 배선 이전과 동일하게 거부된다(무회귀)."""
    db = _FakeTeamDb()
    out = await team_service.approve_member(db, _TEAM, "user-3", "owner-1")
    assert out["ok"] is False
    assert "승인할 가입 신청이 없습니다" in out["error"]


@pytest.mark.asyncio
async def test_invited_status_still_rejected_same_as_before():
    """invited(팀장 초대) 상태는 SoD 배선 이후에도 approve_member로 승인할 수 없다(무회귀 —
    강제 합류 방지는 accept_invite 전용 경로를 그대로 유지)."""
    db = _FakeTeamDb()
    db.seed_member("team-1", "user-4", status="invited")

    out = await team_service.approve_member(db, _TEAM, "user-4", "owner-1")

    assert out["ok"] is False
    assert db.members[("team-1", "user-4")]["status"] == "invited"
