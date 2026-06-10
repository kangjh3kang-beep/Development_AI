"""팀(공유 워크스페이스) 관리 v2 — 개인 로그인 + 팀 배정, 다중 팀.

보안 설계(비밀번호 공유 금지):
- 각 사용자는 자기 계정으로 로그인. 팀 배정 시 그 팀의 전용 테넌트(tenant_id)에 소속돼
  팀의 프로젝트·구독 사용량(quota)을 공유한다(감사·책임은 개인 단위).
- 팀 생성=유료 구독자. 한 팀장이 여러 팀 소유 가능(각 팀=전용 테넌트=격리).
- 팀원 추가 2경로: ①팀장 초대(ID검색→invited)→멤버 동의(accept) ②멤버 신청→팀장 승인.
  → 강제 추가 불가(초대는 반드시 멤버 동의 필요).
- 팀장만 자기 팀 관리(초대·승인·제거·한도·삭제). 멤버는 사용만.
- 팀 삭제·멤버 제거 시 origin(개인) 테넌트로 복원.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_PROTECTED_ROLES = {"owner"}

_DDL = [
    """CREATE TABLE IF NOT EXISTS teams (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        name text NOT NULL,
        owner_user_id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS team_members (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        user_id uuid NOT NULL,
        status text NOT NULL DEFAULT 'pending',   -- pending(신청)|invited(초대됨)|approved|rejected
        role text NOT NULL DEFAULT 'team_member',
        usage_limit_krw numeric(14,2) DEFAULT 0,  -- 0=무제한
        origin_tenant_id uuid,                    -- 가입 전 개인 테넌트(탈퇴 시 복원용)
        requested_at timestamptz NOT NULL DEFAULT now(),
        approved_at timestamptz,
        approved_by uuid,
        UNIQUE(team_id, user_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_team_members_team_status ON team_members(team_id, status)",
]


async def ensure_schema(db: AsyncSession) -> None:
    for ddl in _DDL:
        await db.execute(text(ddl))
    await db.commit()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "team").lower()).strip("-") or "team"
    return f"{s[:40]}-{uuid.uuid4().hex[:8]}"


async def _user_tenant(db: AsyncSession, user_id: Any) -> str | None:
    r = (await db.execute(text("SELECT tenant_id FROM users WHERE id::text=:u"), {"u": str(user_id)})).first()
    return str(r[0]) if r and r[0] else None


# ── 팀 생성/삭제 ──────────────────────────────────────────────
async def create_team(db: AsyncSession, owner_user_id: Any, owner_tenant_id: Any, name: str) -> dict[str, Any]:
    """팀 생성 — 전용 테넌트를 새로 만든다(팀별 격리). 다중 팀 허용."""
    await ensure_schema(db)
    nm = (name or "새 팀").strip()[:100]
    new_tid = str(uuid.uuid4())
    # 팀 전용 테넌트 생성.
    await db.execute(
        text("INSERT INTO tenants(id, name, slug, is_active, plan, created_at, updated_at) "
             "VALUES (:i,:n,:s,true,'team', now(), now())"),
        {"i": new_tid, "n": f"[팀] {nm}", "s": _slug(nm)},
    )
    tid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO teams(id, name, owner_user_id, tenant_id) VALUES (:i,:n,:o,:t)"),
        {"i": tid, "n": nm, "o": str(owner_user_id), "t": new_tid},
    )
    # 팀장 본인을 owner 멤버로 등록(origin=현재 개인 테넌트, 복원용).
    await db.execute(
        text("INSERT INTO team_members(team_id, user_id, status, role, origin_tenant_id, approved_at) "
             "VALUES (:tm,:u,'approved','owner',:t, now())"),
        {"tm": tid, "u": str(owner_user_id), "t": str(owner_tenant_id)},
    )
    await db.commit()
    return {"id": tid, "name": nm, "owner_user_id": str(owner_user_id), "tenant_id": new_tid}


async def list_owned_teams(db: AsyncSession, owner_user_id: Any) -> list[dict[str, Any]]:
    rows = (await db.execute(
        text("SELECT id, name, tenant_id FROM teams WHERE owner_user_id=:u ORDER BY created_at"),
        {"u": str(owner_user_id)},
    )).all()
    return [{"id": str(r[0]), "name": r[1], "tenant_id": str(r[2])} for r in rows]


async def get_team(db: AsyncSession, team_id: str) -> dict[str, Any] | None:
    r = (await db.execute(
        text("SELECT id, name, owner_user_id, tenant_id FROM teams WHERE id=:i"), {"i": team_id},
    )).first()
    if not r:
        return None
    return {"id": str(r[0]), "name": r[1], "owner_user_id": str(r[2]), "tenant_id": str(r[3])}


async def is_team_owner(db: AsyncSession, team_id: str, user_id: Any) -> dict[str, Any] | None:
    t = await get_team(db, team_id)
    return t if t and t["owner_user_id"] == str(user_id) else None


async def delete_team(db: AsyncSession, team: dict, requester_id: Any) -> dict[str, Any]:
    """팀 삭제(팀장만). 모든 멤버를 origin 개인 테넌트로 복원 후 팀·멤버십 제거."""
    if team["owner_user_id"] != str(requester_id):
        return {"ok": False, "error": "팀장만 삭제할 수 있습니다."}
    members = (await db.execute(
        text("SELECT user_id, origin_tenant_id, role FROM team_members WHERE team_id=:t"),
        {"t": team["id"]},
    )).all()
    for uid, origin, role in members:
        if role == "owner":
            continue
        if origin:
            await db.execute(text("UPDATE users SET tenant_id=:tt, role='admin' WHERE id=:u"),
                             {"tt": str(origin), "u": str(uid)})
    await db.execute(text("DELETE FROM teams WHERE id=:t"), {"t": team["id"]})  # team_members는 CASCADE
    await db.commit()
    return {"ok": True}


# ── 팀원 추가: ①팀장 초대(동의) ②멤버 신청(승인) ──────────────
async def invite_member(db: AsyncSession, team: dict, email: str) -> dict[str, Any]:
    """팀장이 ID(이메일)로 초대 → status='invited'. 멤버가 accept해야 실제 합류(동의 필수)."""
    u = (await db.execute(text("SELECT id, tenant_id FROM users WHERE lower(email)=lower(:e)"),
                          {"e": email.strip()})).first()
    if not u:
        return {"ok": False, "error": "해당 ID(이메일)의 사용자를 찾을 수 없습니다."}
    if str(u[0]) == team["owner_user_id"]:
        return {"ok": False, "error": "본인은 초대할 수 없습니다."}
    await db.execute(
        text("INSERT INTO team_members(team_id, user_id, status, origin_tenant_id) "
             "VALUES (:tm,:u,'invited',:t) "
             "ON CONFLICT (team_id, user_id) DO UPDATE SET status='invited'"),
        {"tm": team["id"], "u": str(u[0]), "t": str(u[1]) if u[1] else None},
    )
    await db.commit()
    return {"ok": True}


async def request_join(db: AsyncSession, user_id: Any, user_tenant_id: Any, owner_email: str) -> dict[str, Any]:
    """멤버가 팀장 이메일로 가입 신청 → status='pending'(팀장 승인 대기)."""
    await ensure_schema(db)
    owner = (await db.execute(text("SELECT id FROM users WHERE lower(email)=lower(:e)"),
                              {"e": owner_email.strip()})).first()
    if not owner:
        return {"ok": False, "error": "해당 ID(이메일)의 팀장을 찾을 수 없습니다."}
    teams = await list_owned_teams(db, owner[0])
    if not teams:
        return {"ok": False, "error": "해당 사용자가 만든 팀이 없습니다."}
    team = teams[0]  # 단일 신청은 첫 팀으로(다중팀 선택은 초대 경로 사용)
    if str(owner[0]) == str(user_id):
        return {"ok": False, "error": "본인 팀에는 신청할 수 없습니다."}
    await db.execute(
        text("INSERT INTO team_members(team_id, user_id, status, origin_tenant_id) "
             "VALUES (:tm,:u,'pending',:t) ON CONFLICT (team_id, user_id) DO UPDATE SET status='pending'"),
        {"tm": team["id"], "u": str(user_id), "t": str(user_tenant_id)},
    )
    await db.commit()
    return {"ok": True, "team_name": team["name"]}


async def _assign_to_team(db: AsyncSession, team: dict, user_id: Any, approver_id: Any) -> None:
    await db.execute(
        text("UPDATE team_members SET status='approved', approved_at=now(), approved_by=:a "
             "WHERE team_id=:t AND user_id=:u"),
        {"a": str(approver_id), "t": team["id"], "u": str(user_id)},
    )
    await db.execute(text("UPDATE users SET tenant_id=:tt, role='team_member' WHERE id=:u"),
                     {"tt": team["tenant_id"], "u": str(user_id)})
    await db.commit()


async def approve_member(db: AsyncSession, team: dict, user_id: Any, approver_id: Any) -> dict[str, Any]:
    """팀장이 멤버의 자발 신청(pending)만 승인 → 팀 테넌트 배정.
    ★invited(팀장 초대)는 승인 불가 — 반드시 멤버 본인의 동의(accept_invite)를 거쳐야 한다(강제 합류 방지)."""
    m = (await db.execute(text("SELECT status FROM team_members WHERE team_id=:t AND user_id=:u"),
                          {"t": team["id"], "u": str(user_id)})).first()
    if not m or m[0] != "pending":
        return {"ok": False, "error": "승인할 가입 신청이 없습니다(초대는 상대의 동의가 필요)."}
    await _assign_to_team(db, team, user_id, approver_id)
    return {"ok": True}


async def accept_invite(db: AsyncSession, user_id: Any, team_id: str) -> dict[str, Any]:
    """멤버가 초대(invited)에 동의 → 팀 합류(테넌트 배정)."""
    team = await get_team(db, team_id)
    if not team:
        return {"ok": False, "error": "팀을 찾을 수 없습니다."}
    m = (await db.execute(text("SELECT status FROM team_members WHERE team_id=:t AND user_id=:u"),
                          {"t": team_id, "u": str(user_id)})).first()
    if not m or m[0] != "invited":
        return {"ok": False, "error": "수락할 초대가 없습니다."}
    await _assign_to_team(db, team, user_id, user_id)
    return {"ok": True}


async def decline_invite(db: AsyncSession, user_id: Any, team_id: str) -> dict[str, Any]:
    await db.execute(text("DELETE FROM team_members WHERE team_id=:t AND user_id=:u AND status='invited'"),
                     {"t": team_id, "u": str(user_id)})
    await db.commit()
    return {"ok": True}


async def remove_member(db: AsyncSession, team: dict, user_id: Any) -> dict[str, Any]:
    """팀원 제거(팀장만). 개인 테넌트로 복원."""
    row = (await db.execute(
        text("SELECT origin_tenant_id, role FROM team_members WHERE team_id=:t AND user_id=:u"),
        {"t": team["id"], "u": str(user_id)},
    )).first()
    if row and row[1] == "owner":
        return {"ok": False, "error": "팀장은 제거할 수 없습니다."}
    if row and row[0]:
        await db.execute(text("UPDATE users SET tenant_id=:tt, role='admin' WHERE id=:u"),
                         {"tt": str(row[0]), "u": str(user_id)})
    await db.execute(text("DELETE FROM team_members WHERE team_id=:t AND user_id=:u"),
                     {"t": team["id"], "u": str(user_id)})
    await db.commit()
    return {"ok": True}


async def set_member_limit(db: AsyncSession, team_id: str, user_id: Any, limit_krw: float) -> dict[str, Any]:
    await db.execute(
        text("UPDATE team_members SET usage_limit_krw=:l WHERE team_id=:t AND user_id=:u AND role<>'owner'"),
        {"l": max(0.0, float(limit_krw or 0)), "t": team_id, "u": str(user_id)},
    )
    await db.commit()
    return {"ok": True}


async def list_members(db: AsyncSession, team_id: str) -> list[dict[str, Any]]:
    rows = (await db.execute(
        text("SELECT m.user_id, u.email, u.name, m.status, m.role, COALESCE(m.usage_limit_krw,0), m.requested_at "
             "FROM team_members m LEFT JOIN users u ON u.id=m.user_id "
             "WHERE m.team_id=:t ORDER BY m.requested_at"),
        {"t": team_id},
    )).all()
    return [
        {"user_id": str(r[0]), "email": r[1], "name": r[2], "status": r[3], "role": r[4],
         "usage_limit_krw": float(r[5] or 0), "requested_at": r[6].isoformat() if r[6] else None}
        for r in rows
    ]


async def my_memberships(db: AsyncSession, user_id: Any) -> list[dict[str, Any]]:
    """내가 소속/초대/신청한 팀(멤버 관점)."""
    rows = (await db.execute(
        text("SELECT t.id, t.name, m.status FROM team_members m JOIN teams t ON t.id=m.team_id "
             "WHERE m.user_id=:u AND m.role<>'owner' ORDER BY m.requested_at DESC"),
        {"u": str(user_id)},
    )).all()
    return [{"team_id": str(r[0]), "team_name": r[1], "status": r[2]} for r in rows]


async def member_usage(db: AsyncSession, team_id: str, days: int = 30) -> list[dict[str, Any]]:
    rows = (await db.execute(
        text("SELECT m.user_id, u.email, m.role, COALESCE(m.usage_limit_krw,0), "
             "COALESCE(SUM(l.input_tokens+l.output_tokens),0), COALESCE(SUM(l.cost_krw),0) "
             "FROM team_members m LEFT JOIN users u ON u.id=m.user_id "
             "LEFT JOIN llm_usage_log l ON l.user_id = m.user_id::text "
             "  AND l.created_at >= now() - (:d || ' days')::interval "
             "WHERE m.team_id=:t AND m.status='approved' "
             "GROUP BY m.user_id, u.email, m.role, m.usage_limit_krw ORDER BY 6 DESC"),
        {"t": team_id, "d": int(days)},
    )).all()
    return [
        {"user_id": str(r[0]), "email": r[1], "role": r[2], "usage_limit_krw": float(r[3] or 0),
         "tokens": int(r[4] or 0), "cost_krw": round(float(r[5] or 0))}
        for r in rows
    ]


async def member_limit_status(db: AsyncSession, user_id: Any, days: int = 30) -> dict[str, Any]:
    """이 사용자가 팀 멤버이고 한도를 초과했는지(서버측 차단용)."""
    r = (await db.execute(
        text("SELECT m.usage_limit_krw FROM team_members m "
             "WHERE m.user_id=:u AND m.status='approved' AND m.role<>'owner' "
             "AND COALESCE(m.usage_limit_krw,0) > 0 LIMIT 1"),
        {"u": str(user_id)},
    )).first()
    if not r:
        return {"limited": False}
    limit = float(r[0] or 0)
    used = (await db.execute(
        text("SELECT COALESCE(SUM(cost_krw),0) FROM llm_usage_log "
             "WHERE user_id=:u AND created_at >= now() - (:d || ' days')::interval"),
        {"u": str(user_id), "d": int(days)},
    )).first()
    used_krw = float(used[0] or 0) if used else 0.0
    return {"limited": used_krw >= limit, "limit_krw": limit, "used_krw": round(used_krw)}
