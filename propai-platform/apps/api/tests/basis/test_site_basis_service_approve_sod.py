"""site_basis_service.approve_site_basis — SoD(직무분리, 백로그③) 통합 테스트.

approve_site_basis()가 실제로 실행하는 SQL 표면만 충실히 모사하는 인메모리 fake DB로 구동한다
(design_run_store 테스트 선례 동형). assess_site_basis 전체 흐름을 재현하지 않고, 두 테이블
(site_basis_state·site_basis_transition_event)의 사전 상태를 직접 seed한다 — approve_site_basis는
이 두 테이블만 읽고 쓰므로, 이 편이 assess 전체를 재현하는 것보다 결정적이고 테스트 대상 함수의
SQL 표면만 좁게 검증한다.

게이트:
 ①자기승인(author == approved_by, 최초 assess 이벤트 actor로 author 도출) 차단.
 ②타인 승인(author != approved_by) 정상 통과("passed").
 ③author 미기록(assess 이벤트 actor가 "system"이거나 이벤트 자체가 없음) → skip 표식, 승인은
   그대로 진행(무회귀 — author 배선 미완료를 하드 차단하지 않는다).
 ④기존 흐름(run_id 미존재·P0 미충족)은 SoD 배선 이후에도 그대로 거부된다(무회귀).
"""
from __future__ import annotations

import pytest

from app.services.basis.site_basis_service import approve_site_basis

_CLEAR_GATES = [
    {"name": "access", "clear": True, "status": "PASS", "reason": "", "source": "caller_declared"},
    {"name": "dev_act_permit", "clear": True, "status": "PASS", "reason": "", "source": "caller_declared"},
    {"name": "rights", "clear": True, "status": "CONFIRMED", "reason": "", "source": "caller_declared"},
]

_BLOCKED_GATES = [
    {"name": "access", "clear": False, "status": "BLOCKED", "reason": "", "source": "caller_declared"},
    {"name": "dev_act_permit", "clear": True, "status": "PASS", "reason": "", "source": "caller_declared"},
    {"name": "rights", "clear": True, "status": "CONFIRMED", "reason": "", "source": "caller_declared"},
]


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


def _tenant_match(row_tenant, query_tenant) -> bool:
    """IS NOT DISTINCT FROM 의미론 — 둘 다 None도 일치."""
    return row_tenant == query_tenant


class _FakeSiteBasisApproveDb:
    """approve_site_basis가 작성한 SQL만 충실히 모사하는 인메모리 fake(라이브 DB 불가 대체)."""

    def __init__(self):
        self.state: dict[str, dict] = {}
        self.events: list[dict] = []
        self._seq = 0
        self.commits = 0
        self.rollbacks = 0

    def seed_state(
        self, run_id, *, tenant_id=None, pnu=None, project_id=None,
        artifact_status="ANALYZED", basis_status="ADVISORY", gates=None, content_hash="hash-1",
    ) -> None:
        self.state[run_id] = {
            "artifact_status": artifact_status, "basis_status": basis_status,
            "gates": gates if gates is not None else list(_CLEAR_GATES),
            "content_hash": content_hash, "tenant_id": tenant_id, "pnu": pnu, "project_id": project_id,
            "approved_by": None, "sod_check": None,
        }

    def seed_assess_event(self, run_id, *, actor) -> None:
        self._seq += 1
        self.events.append({"run_id": run_id, "action": "assess", "actor": actor, "seq": self._seq})

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        p = params or {}
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql or sql.strip().startswith("ALTER TABLE"):
            return _Res(None)
        if sql.strip().startswith("SELECT artifact_status, gates, content_hash, tenant_id, pnu, project_id"):
            row = self.state.get(p["rid"])
            if row is None or not _tenant_match(row["tenant_id"], p.get("tid")):
                return _Res(None)
            return _Res((row["artifact_status"], row["gates"], row["content_hash"],
                        row["tenant_id"], row["pnu"], row["project_id"]))
        if "SELECT actor FROM site_basis_transition_event" in sql:
            matches = sorted(
                (e for e in self.events if e["run_id"] == p["rid"] and e["action"] == "assess"),
                key=lambda e: e["seq"],
            )
            if not matches:
                return _Res(None)
            return _Res((matches[0]["actor"],))
        if sql.strip().startswith("UPDATE site_basis_state SET artifact_status"):
            row = self.state.get(p["rid"])
            if row is not None:
                row["artifact_status"] = p["st"]
                row["basis_status"] = p["bst"]
                row["approved_by"] = p["by"]
                row["sod_check"] = p.get("sod")
            return _Res(None)
        if sql.strip().startswith("INSERT INTO site_basis_transition_event"):
            return _Res(None)
        return _Res(None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


# ══════════════════════════════════════════════════════════════════════════
# ① 자기승인 차단
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_self_approval_blocked_when_author_matches_approver():
    """작성자(최초 assess actor)와 승인자가 동일하면 SoD 위반으로 거부된다."""
    db = _FakeSiteBasisApproveDb()
    db.seed_state("basis_x1", tenant_id="t-a")
    db.seed_assess_event("basis_x1", actor="user-1")

    out = await approve_site_basis(db=db, run_id="basis_x1", approved_by="user-1", tenant_id="t-a")

    assert out["ok"] is False
    assert "SoD" in out["message"]
    # 원본은 여전히 ANALYZED(무단 승격 0).
    assert db.state["basis_x1"]["artifact_status"] == "ANALYZED"
    assert db.state["basis_x1"]["approved_by"] is None


# ══════════════════════════════════════════════════════════════════════════
# ② 타인 승인 정상 통과
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_different_approver_passes_and_marks_sod_check_passed():
    """작성자와 승인자가 다르면 정상 승인되고 sod_check="passed"가 기록된다."""
    db = _FakeSiteBasisApproveDb()
    db.seed_state("basis_x2", tenant_id="t-a")
    db.seed_assess_event("basis_x2", actor="user-1")

    out = await approve_site_basis(db=db, run_id="basis_x2", approved_by="user-2", tenant_id="t-a")

    assert out["ok"] is True
    assert out["artifact_status"] == "APPROVED"
    assert out["sod_check"] == "passed"
    assert db.state["basis_x2"]["sod_check"] == "passed"


# ══════════════════════════════════════════════════════════════════════════
# ③ author 미기록 → skip 표식(무언 통과 금지·하드 차단도 금지)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_assess_event_skips_sod_and_still_approves():
    """assess 이벤트가 아예 없으면(author 조회 불가) 승인은 그대로 통과하고 skip 표식만 남는다."""
    db = _FakeSiteBasisApproveDb()
    db.seed_state("basis_x3", tenant_id="t-a")
    # seed_assess_event 호출 없음 — author 조회 실패(row is None) 재현.

    out = await approve_site_basis(db=db, run_id="basis_x3", approved_by="user-9", tenant_id="t-a")

    assert out["ok"] is True
    assert out["sod_check"] == "skipped(author 미기록)"


@pytest.mark.asyncio
async def test_system_actor_treated_as_no_author_even_if_matches_approver_literally():
    """assess 당시 created_by 미기재로 actor="system"이면 author 미기록 취급 — approved_by가
    우연히 "system" 문자열이어도 자기승인으로 오탐 차단하지 않는다(무회귀)."""
    db = _FakeSiteBasisApproveDb()
    db.seed_state("basis_x4", tenant_id="t-a")
    db.seed_assess_event("basis_x4", actor="system")

    out = await approve_site_basis(db=db, run_id="basis_x4", approved_by="system", tenant_id="t-a")

    assert out["ok"] is True
    assert out["sod_check"] == "skipped(author 미기록)"


# ══════════════════════════════════════════════════════════════════════════
# ④ 기존 흐름 무회귀
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_missing_run_id_still_rejected_same_as_before():
    """run_id 미존재는 SoD 배선 이전과 동일하게 거부된다(무회귀)."""
    db = _FakeSiteBasisApproveDb()
    out = await approve_site_basis(db=db, run_id="basis_missing", approved_by="user-1", tenant_id="t-a")
    assert out["ok"] is False
    assert "없음" in out["message"]


@pytest.mark.asyncio
async def test_p0_not_clear_still_rejected_before_sod_check_runs():
    """P0 게이트 미충족이면 SoD 판정 이전에 can_approve() 게이트에서 그대로 거부된다(무회귀) —
    작성자와 승인자가 달라도(=SoD 자체는 통과할 조합) 게이트 미충족이면 여전히 차단된다."""
    db = _FakeSiteBasisApproveDb()
    db.seed_state("basis_x5", tenant_id="t-a", gates=list(_BLOCKED_GATES))
    db.seed_assess_event("basis_x5", actor="user-1")

    out = await approve_site_basis(db=db, run_id="basis_x5", approved_by="user-2", tenant_id="t-a")

    assert out["ok"] is False
    assert "P0" in out["message"]


@pytest.mark.asyncio
async def test_wrong_tenant_still_not_found_same_as_before():
    """★HIGH-1 테넌트 격리 — SoD 배선 이후에도 다른 테넌트의 run_id는 여전히 '없음'으로 거부(무회귀)."""
    db = _FakeSiteBasisApproveDb()
    db.seed_state("basis_x6", tenant_id="t-a")
    db.seed_assess_event("basis_x6", actor="user-1")

    out = await approve_site_basis(db=db, run_id="basis_x6", approved_by="user-2", tenant_id="t-b")

    assert out["ok"] is False
    assert db.state["basis_x6"]["artifact_status"] == "ANALYZED"
