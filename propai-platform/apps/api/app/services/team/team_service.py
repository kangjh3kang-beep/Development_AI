"""팀(공유 워크스페이스) 관리 — 개인 로그인 + 팀 배정 방식.

보안 설계(비밀번호 공유 금지):
- 각 사용자는 자기 계정으로 로그인하되, 승인 시 팀의 공유 테넌트(tenant_id)에 배정된다.
  → 팀의 프로젝트·구독 사용량(quota)을 공유하지만, 로그인/감사/책임은 개인 단위로 유지.
- 팀 생성은 유료 구독자(사업자/구독자)만. 가입은 신청→팀장 승인(무단 접근 차단).
- 팀장만 멤버 승인·제거·사용량 한도 설정 가능. 멤버는 사용만(과금/팀관리 불가).
- 모든 변경은 감사로그 권장. 멤버별 사용량 한도는 서버측 강제(billing 게이트).

데이터:
- teams(id, name, owner_user_id, tenant_id, created_at)
- team_members(id, team_id, user_id, status, role, usage_limit_krw, origin_tenant_id, ...)
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
        status text NOT NULL DEFAULT 'pending',   -- pending|approved|rejected
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


async def get_team_owned(db: AsyncSession, owner_user_id: Any) -> dict[str, Any] | None:
    """내가 소유(팀장)한 팀."""
    r = (await db.execute(
        text("SELECT id, name, owner_user_id, tenant_id FROM teams WHERE owner_user_id=:u LIMIT 1"),
        {"u": str(owner_user_id)},
    )).first()
    if not r:
        return None
    return {"id": str(r[0]), "name": r[1], "owner_user_id": str(r[2]), "tenant_id": str(r[3])}


async def create_team(db: AsyncSession, owner_user_id: Any, owner_tenant_id: Any, name: str) -> dict[str, Any]:
    """팀 생성 — 팀장 본인의 테넌트를 팀 공유 테넌트로 사용. 1인 1팀."""
    await ensure_schema(db)
    existing = await get_team_owned(db, owner_user_id)
    if existing:
        return existing
    tid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO teams(id, name, owner_user_id, tenant_id) VALUES (:i,:n,:o,:t)"),
        {"i": tid, "n": (name or "내 팀").strip()[:100], "o": str(owner_user_id), "t": str(owner_tenant_id)},
    )
    # 팀장 본인을 멤버(승인됨)로 등록(소유자 role).
    await db.execute(
        text("INSERT INTO team_members(team_id, user_id, status, role, origin_tenant_id, approved_at) "
             "VALUES (:tm,:u,'approved','owner',:t, now()) ON CONFLICT (team_id, user_id) DO NOTHING"),
        {"tm": tid, "u": str(owner_user_id), "t": str(owner_tenant_id)},
    )
    await db.commit()
    return {"id": tid, "name": name, "owner_user_id": str(owner_user_id), "tenant_id": str(owner_tenant_id)}


async def request_join(db: AsyncSession, user_id: Any, user_tenant_id: Any, owner_email: str) -> dict[str, Any]:
    """팀장 이메일(ID)로 가입 신청. 팀장 승인 전까지 pending."""
    await ensure_schema(db)
    owner = (await db.execute(
        text("SELECT id FROM users WHERE lower(email)=lower(:e)"), {"e": owner_email.strip()},
    )).first()
    if not owner:
        return {"ok": False, "error": "해당 ID(이메일)의 팀장을 찾을 수 없습니다."}
    team = await get_team_owned(db, owner[0])
    if not team:
        return {"ok": False, "error": "해당 사용자가 만든 팀이 없습니다."}
    if str(owner[0]) == str(user_id):
        return {"ok": False, "error": "본인 팀에는 신청할 수 없습니다."}
    await db.execute(
        text("INSERT INTO team_members(team_id, user_id, status, origin_tenant_id) "
             "VALUES (:tm,:u,'pending',:t) "
             "ON CONFLICT (team_id, user_id) DO UPDATE SET status='pending'"),
        {"tm": team["id"], "u": str(user_id), "t": str(user_tenant_id)},
    )
    await db.commit()
    return {"ok": True, "team_name": team["name"]}


async def list_members(db: AsyncSession, team_id: str) -> list[dict[str, Any]]:
    rows = (await db.execute(
        text("SELECT m.user_id, u.email, u.name, m.status, m.role, COALESCE(m.usage_limit_krw,0), "
             "m.requested_at "
             "FROM team_members m LEFT JOIN users u ON u.id=m.user_id "
             "WHERE m.team_id=:t ORDER BY m.requested_at"),
        {"t": team_id},
    )).all()
    return [
        {"user_id": str(r[0]), "email": r[1], "name": r[2], "status": r[3], "role": r[4],
         "usage_limit_krw": float(r[5] or 0), "requested_at": r[6].isoformat() if r[6] else None}
        for r in rows
    ]


async def approve_member(db: AsyncSession, team: dict, user_id: Any, approver_id: Any) -> dict[str, Any]:
    """팀장이 멤버 승인 → 멤버 tenant_id를 팀 공유 테넌트로 배정(팀 자원·quota 공유)."""
    m = (await db.execute(
        text("SELECT status FROM team_members WHERE team_id=:t AND user_id=:u"),
        {"t": team["id"], "u": str(user_id)},
    )).first()
    if not m:
        return {"ok": False, "error": "가입 신청이 없습니다."}
    await db.execute(
        text("UPDATE team_members SET status='approved', approved_at=now(), approved_by=:a "
             "WHERE team_id=:t AND user_id=:u"),
        {"a": str(approver_id), "t": team["id"], "u": str(user_id)},
    )
    # 멤버 계정을 팀 테넌트에 배정 + 역할 team_member(권한 제한). 개인 로그인은 유지.
    await db.execute(
        text("UPDATE users SET tenant_id=:tt, role='team_member' WHERE id=:u"),
        {"tt": team["tenant_id"], "u": str(user_id)},
    )
    await db.commit()
    return {"ok": True}


async def remove_member(db: AsyncSession, team: dict, user_id: Any) -> dict[str, Any]:
    """멤버 제거/거절 → 개인 테넌트로 복원(없으면 새 개인 테넌트)."""
    row = (await db.execute(
        text("SELECT origin_tenant_id, role FROM team_members WHERE team_id=:t AND user_id=:u"),
        {"t": team["id"], "u": str(user_id)},
    )).first()
    if row and row[1] == "owner":
        return {"ok": False, "error": "팀장은 제거할 수 없습니다."}
    origin = row[0] if row and row[0] else None
    if origin:
        await db.execute(text("UPDATE users SET tenant_id=:tt, role='admin' WHERE id=:u"),
                         {"tt": str(origin), "u": str(user_id)})
    await db.execute(text("DELETE FROM team_members WHERE team_id=:t AND user_id=:u"),
                     {"t": team["id"], "u": str(user_id)})
    await db.commit()
    return {"ok": True}


async def set_member_limit(db: AsyncSession, team_id: str, user_id: Any, limit_krw: float) -> dict[str, Any]:
    """멤버별 사용량 한도(원). 0=무제한. billing 게이트가 서버측 강제."""
    await db.execute(
        text("UPDATE team_members SET usage_limit_krw=:l WHERE team_id=:t AND user_id=:u AND role<>'owner'"),
        {"l": max(0.0, float(limit_krw or 0)), "t": team_id, "u": str(user_id)},
    )
    await db.commit()
    return {"ok": True}


async def member_usage(db: AsyncSession, team_id: str, days: int = 30) -> list[dict[str, Any]]:
    """팀 멤버별 LLM 사용량(원·토큰) — 팀장이 모니터링."""
    rows = (await db.execute(
        text("SELECT m.user_id, u.email, m.role, COALESCE(m.usage_limit_krw,0), "
             "COALESCE(SUM(l.input_tokens+l.output_tokens),0), COALESCE(SUM(l.cost_krw),0) "
             "FROM team_members m LEFT JOIN users u ON u.id=m.user_id "
             "LEFT JOIN llm_usage_log l ON l.user_id = m.user_id::text "
             f"  AND l.created_at >= now() - (:d || ' days')::interval "
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
             f"WHERE user_id=:u AND created_at >= now() - (:d || ' days')::interval"),
        {"u": str(user_id), "d": int(days)},
    )).first()
    used_krw = float(used[0] or 0) if used else 0.0
    return {"limited": used_krw >= limit, "limit_krw": limit, "used_krw": round(used_krw)}
