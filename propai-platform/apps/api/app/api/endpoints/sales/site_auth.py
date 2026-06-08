"""Phase 1-A — 현장 2차인증 · 내 현장리스트 · 역할 게이트.

분양 현장앱의 인증 토대:
 1) site_passwords            현장별 2차 비밀번호(bcrypt 해시, 멱등 _ensure 테이블)
 2) POST /sites/{id}/password 현장 2차비번 설정/변경(관리권한 또는 admin)
 3) GET  /my-sites            내가 멤버인 현장 + 현장 내 역할 + 상태
 4) POST /sites/{id}/enter    2차비번 검증 → 현장 세션토큰(site_id+role claim, 단기 8h)
 5) GET  /sites/{id}/role     현 사용자의 현장 역할 + 허용 기능키(프론트 게이팅)

세션토큰은 deps_sales 가 X-Site-Token 헤더에서 인식해 RLS 세션변수
(app.site_id / app.org_path / app.role)를 토큰 우선으로 주입한다(기존 X-Site-Code 경로 보존).

보안: 평문저장 금지(bcrypt), 진입 실패 rate-limit(실패카운트+잠금), 토큰 만료·site 스코프,
멤버십 없는 현장 진입 차단(403), 비번 불일치(401).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite

site_auth_router = APIRouter(tags=["sales-auth"])

# ── 역할/권한 정의 ──────────────────────────────────────────────────────────
# 현장 내 조직 node_type: AGENCY(대행본사)/SUBAGENCY(대행지사)/GM_DIRECTOR(본부장)/
#                         DIRECTOR(팀장급 이사)/TEAM_LEADER(팀장)/MEMBER(직원)
# 플랫폼 폴백: DEVELOPER(시행/현장소유), SUPERADMIN(관리자)
_SUPERADMIN_ROLES = {"superadmin", "super_admin", "admin", "owner", "총괄관리자", "platform_admin"}
_DEVELOPER_ROLES = {"developer", "시행사", "dev"}

# 현장 관리권한(2차비번 설정 가능) = 시행/대행 본부장↑ 또는 admin
_MANAGE_ROLES = {"SUPERADMIN", "DEVELOPER", "AGENCY", "GM_DIRECTOR"}

# 역할 → 한글 라벨
_ROLE_LABEL = {
    "SUPERADMIN": "총괄관리자", "DEVELOPER": "시행사", "AGENCY": "대행본사",
    "SUBAGENCY": "대행지사", "GM_DIRECTOR": "본부장", "DIRECTOR": "이사",
    "TEAM_LEADER": "팀장", "MEMBER": "직원",
}

# 역할 → 허용 기능키(프론트 메뉴 게이팅). 상위 역할은 하위 기능 포함.
_FEATURE_KEYS = {
    "SUPERADMIN": ["dashboard", "org", "pricing", "units", "contracts", "commission",
                   "customers", "ads", "reports", "settings", "site_password"],
    "DEVELOPER": ["dashboard", "org", "pricing", "units", "contracts", "commission",
                  "customers", "ads", "reports", "settings", "site_password"],
    "AGENCY": ["dashboard", "org", "pricing", "units", "contracts", "commission",
               "customers", "ads", "reports", "site_password"],
    "SUBAGENCY": ["dashboard", "org", "units", "contracts", "commission", "customers", "ads", "reports"],
    "GM_DIRECTOR": ["dashboard", "org", "units", "contracts", "commission",
                    "customers", "ads", "reports", "site_password"],
    "DIRECTOR": ["dashboard", "units", "contracts", "customers", "ads"],
    "TEAM_LEADER": ["dashboard", "units", "contracts", "customers"],
    "MEMBER": ["dashboard", "units", "customers"],
}

# 진입 rate-limit
_MAX_FAILS = 5            # 잠금 임계
_LOCK_MINUTES = 15       # 잠금 시간(분)
_SITE_TOKEN_HOURS = 8    # 현장 세션토큰 만료

# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
_PWD_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_site_passwords ("
    "  site_id uuid PRIMARY KEY REFERENCES sales_sites(id) ON DELETE CASCADE,"
    "  password_hash text NOT NULL,"
    "  updated_by uuid,"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_ATTEMPT_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_site_login_attempts ("
    "  site_id uuid NOT NULL,"
    "  user_id uuid NOT NULL,"
    "  fail_count int NOT NULL DEFAULT 0,"
    "  locked_until timestamptz,"
    "  last_attempt_at timestamptz NOT NULL DEFAULT now(),"
    "  PRIMARY KEY (site_id, user_id)"
    ")"
)


async def _ensure(db: AsyncSession) -> None:
    """현장 인증 테이블을 멱등 생성(배포 후 최초 호출 시 1회). 기존 무파괴."""
    await db.execute(text(_PWD_DDL))
    await db.execute(text(_ATTEMPT_DDL))


# ── 역할 해석(deps_sales 와 동일 규칙 — 단일 기준) ────────────────────────────
async def _resolve_role(db: AsyncSession, site: SalesSite, user) -> tuple[str, str]:
    """현 사용자의 그 현장 역할을 (org_path, role) 로 반환. 멤버 아니면 ('', '') 반환은 호출부에서 처리."""
    node = (await db.execute(
        select(SalesOrgNode).where(
            SalesOrgNode.site_id == site.id,
            SalesOrgNode.user_id == user.id,
            SalesOrgNode.active.is_(True),
            SalesOrgNode.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    role_lower = (getattr(user, "role", "") or "").lower()
    user_tenant = getattr(user, "tenant_id", None)
    owns_site = bool(user_tenant) and str(getattr(site, "organization_id", "") or "") == str(user_tenant)

    if node:
        return str(node.path), node.node_type
    if role_lower in _SUPERADMIN_ROLES:
        return "", "SUPERADMIN"
    if role_lower in _DEVELOPER_ROLES or owns_site:
        return "", "DEVELOPER"
    return "", ""  # 멤버 아님


async def _get_site(db: AsyncSession, site_id) -> SalesSite:
    # site_id는 UUID 또는 사람이 읽는 현장코드(site_code) 둘 다 허용한다.
    # (현장앱 주소에 코드가 들어오거나 로컬 생성분이 비-UUID여도 422로 깨지지 않게 함.)
    sid = str(site_id).strip()
    cond = None
    try:
        cond = SalesSite.id == uuid.UUID(sid)
    except (ValueError, AttributeError, TypeError):
        cond = SalesSite.site_code == sid  # UUID가 아니면 현장코드로 조회
    site = (await db.execute(select(SalesSite).where(cond))).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "현장을 찾을 수 없습니다")
    return site


def _features(role: str) -> list[str]:
    return _FEATURE_KEYS.get(role, ["dashboard"])


def issue_site_token(user_id, tenant_id, site_id, role: str, org_path: str) -> str:
    """현장 세션토큰 발급(JWT). app.* 세션변수 주입에 필요한 site_id/role/org_path 클레임 포함.

    auth_service.get_current_user 와 호환되도록 type='access' + token_kind 를 유지하되,
    scope='sales_site' 로 일반 액세스와 구분한다(이 토큰은 site 컨텍스트 전용).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "scope": "sales_site",
        "site_id": str(site_id),
        "site_role": role,
        "org_path": org_path or "",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=_SITE_TOKEN_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_site_token(token: str) -> dict | None:
    """현장 세션토큰을 검증·디코드. scope!=sales_site 또는 무효면 None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except Exception:  # noqa: BLE001 - 만료/위조 모두 None 처리
        return None
    if payload.get("scope") != "sales_site" or not payload.get("site_id"):
        return None
    return payload


# ── 스키마 ───────────────────────────────────────────────────────────────────
class SetPasswordRequest(BaseModel):
    password: str


class EnterRequest(BaseModel):
    password: str


# ── 1) 현장 2차비번 설정/변경 ────────────────────────────────────────────────
@site_auth_router.post("/sites/{site_id}/password", summary="현장 2차비밀번호 설정/변경")
async def set_site_password(site_id: str, body: SetPasswordRequest,
                            db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    if len(body.password or "") < 4:
        raise HTTPException(400, "현장 2차비밀번호는 4자 이상이어야 합니다")
    await _ensure(db)
    site = await _get_site(db, site_id)  # UUID/현장코드 모두 허용
    sid = str(site.id)  # 이후 SQL은 반드시 해석된 실제 UUID 사용
    _, role = await _resolve_role(db, site, user)
    if role not in _MANAGE_ROLES:
        raise HTTPException(403, "현장 2차비밀번호를 설정할 권한이 없습니다(시행/대행 본부장↑ 또는 관리자)")

    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    await db.execute(text(
        "INSERT INTO sales_site_passwords (site_id, password_hash, updated_by, updated_at) "
        "VALUES (:sid, :h, :uid, now()) "
        "ON CONFLICT (site_id) DO UPDATE SET "
        "  password_hash = EXCLUDED.password_hash, updated_by = EXCLUDED.updated_by, updated_at = now()"
    ), {"sid": sid, "h": pw_hash, "uid": str(user.id)})
    # 비번 변경 시 잠금/실패카운트 리셋
    await db.execute(text("DELETE FROM sales_site_login_attempts WHERE site_id = :sid"), {"sid": sid})
    await db.commit()
    return {"ok": True, "site_id": sid}


# ── 2) 내 현장 리스트 ─────────────────────────────────────────────────────────
@site_auth_router.get("/my-sites", summary="내가 멤버인 현장 목록 + 현장 내 역할")
async def my_sites(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> list[dict]:
    """SSO 사용자가 멤버인(또는 소유/관리하는) 현장 + 현장 내 역할 + 상태."""
    role_lower = (getattr(user, "role", "") or "").lower()
    user_tenant = getattr(user, "tenant_id", None)
    is_super = role_lower in _SUPERADMIN_ROLES

    out: dict[str, dict] = {}

    # (a) 멤버십(org node) 기반 — 현장별 역할 포함
    node_rows = (await db.execute(
        select(SalesOrgNode, SalesSite).join(SalesSite, SalesSite.id == SalesOrgNode.site_id).where(
            SalesOrgNode.user_id == user.id,
            SalesOrgNode.active.is_(True),
            SalesOrgNode.deleted_at.is_(None),
            SalesSite.deleted_at.is_(None),
        )
    )).all()
    for node, site in node_rows:
        out[str(site.id)] = {
            "site_id": str(site.id), "site_code": site.site_code, "site_name": site.site_name,
            "development_type": site.development_type, "status": site.status,
            "role": node.node_type, "role_label": _ROLE_LABEL.get(node.node_type, node.node_type),
            "membership": "org",
        }

    # (b) 소유 테넌트 현장(시행) — 멤버 노드 없어도 운영자
    if user_tenant:
        owned = (await db.execute(select(SalesSite).where(
            SalesSite.organization_id == user_tenant, SalesSite.deleted_at.is_(None)))).scalars().all()
        for site in owned:
            out.setdefault(str(site.id), {
                "site_id": str(site.id), "site_code": site.site_code, "site_name": site.site_name,
                "development_type": site.development_type, "status": site.status,
                "role": "DEVELOPER", "role_label": _ROLE_LABEL["DEVELOPER"], "membership": "owner",
            })

    # (c) 관리자(superadmin) — 전체 현장 가시
    if is_super:
        allsites = (await db.execute(select(SalesSite).where(
            SalesSite.deleted_at.is_(None)).order_by(SalesSite.created_at.desc()))).scalars().all()
        for site in allsites:
            out.setdefault(str(site.id), {
                "site_id": str(site.id), "site_code": site.site_code, "site_name": site.site_name,
                "development_type": site.development_type, "status": site.status,
                "role": "SUPERADMIN", "role_label": _ROLE_LABEL["SUPERADMIN"], "membership": "admin",
            })

    return list(out.values())


# ── 3) 현장 진입(2차인증) ─────────────────────────────────────────────────────
@site_auth_router.post("/sites/{site_id}/enter", summary="현장 2차인증 → 현장 세션토큰 발급")
async def enter_site(site_id: str, body: EnterRequest,
                     db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    site = await _get_site(db, site_id)  # UUID/현장코드 모두 허용
    sid = str(site.id)  # 이후 SQL·토큰은 해석된 실제 UUID 사용

    org_path, role = await _resolve_role(db, site, user)
    if not role:
        raise HTTPException(403, "이 현장의 멤버가 아닙니다")

    now = datetime.now(timezone.utc)
    # rate-limit: 잠금 여부 확인
    att = (await db.execute(text(
        "SELECT fail_count, locked_until FROM sales_site_login_attempts WHERE site_id=:s AND user_id=:u"
    ), {"s": sid, "u": str(user.id)})).first()
    if att and att.locked_until is not None:
        locked_until = att.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            wait = int((locked_until - now).total_seconds() // 60) + 1
            raise HTTPException(429, f"진입 시도가 많아 잠겼습니다. {wait}분 후 다시 시도하세요")

    pw = (await db.execute(text(
        "SELECT password_hash FROM sales_site_passwords WHERE site_id=:s"
    ), {"s": sid})).first()
    if not pw:
        raise HTTPException(409, "현장 2차비밀번호가 아직 설정되지 않았습니다. 관리자에게 문의하세요")

    ok = False
    try:
        ok = bcrypt.checkpw((body.password or "").encode(), pw.password_hash.encode())
    except (ValueError, TypeError):
        ok = False

    if not ok:
        # 실패 누적 + 임계 도달 시 잠금
        new_fail = (att.fail_count if att else 0) + 1
        locked = now + timedelta(minutes=_LOCK_MINUTES) if new_fail >= _MAX_FAILS else None
        await db.execute(text(
            "INSERT INTO sales_site_login_attempts (site_id, user_id, fail_count, locked_until, last_attempt_at) "
            "VALUES (:s, :u, :f, :l, now()) "
            "ON CONFLICT (site_id, user_id) DO UPDATE SET "
            "  fail_count = EXCLUDED.fail_count, locked_until = EXCLUDED.locked_until, last_attempt_at = now()"
        ), {"s": sid, "u": str(user.id), "f": new_fail, "l": locked})
        await db.commit()
        remaining = max(0, _MAX_FAILS - new_fail)
        raise HTTPException(401, f"비밀번호가 일치하지 않습니다(남은 시도 {remaining}회)")

    # 성공: 실패카운트 리셋 + 세션토큰 발급
    await db.execute(text("DELETE FROM sales_site_login_attempts WHERE site_id=:s AND user_id=:u"),
                     {"s": sid, "u": str(user.id)})
    await db.commit()

    token = issue_site_token(user.id, getattr(user, "tenant_id", None), site.id, role, org_path)
    return {
        "site_token": token,
        "token_type": "bearer",
        "expires_in": _SITE_TOKEN_HOURS * 3600,
        "site_id": sid,
        "role": role,
        "role_label": _ROLE_LABEL.get(role, role),
        "features": _features(role),
    }


# ── 4) 역할 맵 ────────────────────────────────────────────────────────────────
@site_auth_router.get("/sites/{site_id}/role", summary="현 사용자의 현장 역할 + 허용 기능키")
async def site_role(site_id: str, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> dict:
    site = await _get_site(db, site_id)  # UUID/현장코드 모두 허용
    sid = str(site.id)
    org_path, role = await _resolve_role(db, site, user)
    if not role:
        raise HTTPException(403, "이 현장의 멤버가 아닙니다")
    await _ensure(db)
    has_pw = (await db.execute(text(
        "SELECT 1 FROM sales_site_passwords WHERE site_id=:s"), {"s": sid})).first() is not None
    return {
        "site_id": sid,
        "role": role,
        "role_label": _ROLE_LABEL.get(role, role),
        "org_path": org_path,
        "can_manage": role in _MANAGE_ROLES,
        "password_set": has_pw,
        "features": _features(role),
    }
