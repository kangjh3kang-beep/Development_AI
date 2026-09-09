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

import logging
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db

# ★SSOT: 폴백 역할 집합은 deps_sales 한 곳에서만 정의(중복정의 드리프트 제거). 여기서 재정의
# 하지 않고 import 해 my_sites 가 동일 기준(_SUPERADMIN_ROLES)을 쓰게 한다.
# _node_priority 도 import 해 my_sites 의 '표시 역할' 을 resolve_site_membership 의 '적용 역할'
# 선택 기준(상위 권한 우선)과 일치시킨다(표시=적용 일관).
from app.api.deps_sales import _SUPERADMIN_ROLES, _node_priority
from app.core.config import settings

# ★진입 판정은 의존 없는 서비스 모듈에 산다 — 어디서든 태울 수 있게(2026-09-09).
from app.services.sales.site_entry import resolve_entry
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite

logger = logging.getLogger(__name__)

site_auth_router = APIRouter(tags=["sales-auth"])

# ── 역할/권한 정의 ──────────────────────────────────────────────────────────
# 현장 내 조직 node_type: AGENCY(대행본사)/SUBAGENCY(대행지사)/GM_DIRECTOR(본부장)/
#                         DIRECTOR(팀장급 이사)/TEAM_LEADER(팀장)/MEMBER(직원)
# 플랫폼 폴백: DEVELOPER(시행/현장소유), SUPERADMIN(관리자)
# (폴백 역할 집합 _SUPERADMIN_ROLES/_DEVELOPER_ROLES 는 deps_sales SSOT 사용. site_auth 의
#  과거 _DEVELOPER_ROLES 중복정의는 dead(미사용)였어 제거했다 — my_sites 는 _SUPERADMIN_ROLES
#  만 쓰고, 멤버십/폴백 판정은 resolve_site_membership 헬퍼가 담당한다.)

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


# 인증 테이블 DDL은 프로세스당 1회만 실행한다(요청마다 CREATE TABLE IF NOT EXISTS 는
# 존재해도 락을 잡아 동시성 시 지연·503 유발). 첫 성공 후 플래그로 건너뛴다.
_ENSURED = False


async def _ensure(db: AsyncSession) -> None:
    """현장 인증 테이블을 멱등 생성(프로세스 최초 1회). 기존 무파괴."""
    global _ENSURED
    if _ENSURED:
        return
    await db.execute(text(_PWD_DDL))
    await db.execute(text(_ATTEMPT_DDL))
    await db.commit()  # DDL 영속 보장(신규 DB의 GET 경로도 안전) 후에만 플래그 설정.
    _ENSURED = True


# ── 역할 해석(deps_sales 와 동일 규칙 — 단일 기준) ────────────────────────────
async def _resolve_role(db: AsyncSession, site: SalesSite, user) -> tuple[str, str]:
    """현 사용자의 그 현장 역할을 (org_path, role) 로 반환. 멤버 아니면 ('', '') 반환은 호출부에서 처리.

    ★일원화(코드로 1:1 보장): 멤버십(노드 → 플랫폼 폴백) 판정을 deps_sales 의 공용 헬퍼
    resolve_site_membership 로 위임한다(중복 SELECT 제거). 본 함수는 호출부 기존 계약을
    보존하기 위해 None → ('', '')(멤버 아님) 로만 변환한다(무회귀).
    """
    from app.api.deps_sales import resolve_site_membership  # 지연 import(순환 방지)

    membership = await resolve_site_membership(db, site, user)
    if membership is None:
        return "", ""  # 멤버 아님(호출부에서 처리)
    return membership


async def _get_site(db: AsyncSession, site_id) -> SalesSite:
    # site_id는 UUID 또는 사람이 읽는 현장코드(site_code) 둘 다 허용한다.
    # (현장앱 주소에 코드가 들어오거나 로컬 생성분이 비-UUID여도 422로 깨지지 않게 함.)
    sid = str(site_id).strip()
    cond = None
    try:
        cond = SalesSite.id == uuid.UUID(sid)
    except (ValueError, AttributeError, TypeError):
        cond = SalesSite.site_code == sid  # UUID가 아니면 현장코드로 조회
    # ★삭제된 현장은 주지 않는다(2026-09-09 리뷰 M5). `SalesSite` 는 `SoftDeleteMixin` 을 달고,
    #   같은 파일의 형제 조회 **3곳**(`my_sites` (a)(b)(c))은 전부 이 필터를 건다 — **4중 1곳만**
    #   빠져 있었고, 하필 그 하나가 `enter_site`·`set_site_password`·`site_role` 이 쓰는 것이다.
    #   비번 미설정 현장이 진입 가능해지면서 «삭제된 현장에 토큰 발급» 이 열린다.
    site = (await db.execute(select(SalesSite).where(
        cond, SalesSite.deleted_at.is_(None)))).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "현장을 찾을 수 없습니다")
    return site


def _log_entry(site_id: str, user, role: str, auth: str) -> None:
    """현장 진입을 **양쪽 경로 모두** 같은 모양으로 남긴다.

    ★2026-09-09 리뷰 M4: 앞 판은 membership 진입만 로그했다. 그러면 «오늘 몇 명이 비번으로
      들어왔나» 를 셀 수 없고, 두 경로가 **로그에서 비대칭**이 된다 — 응답에 `auth` 를 실어
      «구별한다» 고 주석에 써 놓고 정작 로그에서는 하나만 보였다.
    ★한쪽만 부르면 그것이 이 결함의 재발이다 — 그래서 **헬퍼 하나**로 묶는다.
    """
    logger.info("현장 진입: site=%s user=%s role=%s auth=%s", site_id, user.id, role, auth)


def _features(role: str) -> list[str]:
    return _FEATURE_KEYS.get(role, ["dashboard"])


def issue_site_token(user_id, tenant_id, site_id, role: str, org_path: str) -> str:
    """현장 세션토큰 발급(JWT). app.* 세션변수 주입에 필요한 site_id/role/org_path 클레임 포함.

    auth_service.get_current_user 와 호환되도록 type='access' + token_kind 를 유지하되,
    scope='sales_site' 로 일반 액세스와 구분한다(이 토큰은 site 컨텍스트 전용).
    """
    now = datetime.now(UTC)
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
    """★`password` 는 **선택**이다(2026-09-09).

    승인된 멤버십이 곧 인증이다 — 아래 `enter_site` 독스트링 참조.
    현장이 2차비번을 **설정해 둔 경우에만** 이 값이 검증된다.
    """

    password: str | None = None


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
    # ★표시=적용 일관: 한 사용자가 같은 현장에 복수 노드를 가지면(과거엔 루프 마지막 노드가
    #   덮어써져 '표시 역할' 이 임의였다), resolve_site_membership 과 동일하게 '상위 권한' 노드를
    #   결정적으로 골라 표시한다. 동률(같은 node_type)은 (path, id)로 깨 입력 순서와 무관.
    best_node: dict[str, SalesOrgNode] = {}
    site_by_id: dict[str, SalesSite] = {}
    for node, site in node_rows:
        sid = str(site.id)
        site_by_id[sid] = site
        cur = best_node.get(sid)
        if cur is None or (
            _node_priority(node.node_type), str(node.path), str(node.id)
        ) < (
            _node_priority(cur.node_type), str(cur.path), str(cur.id)
        ):
            best_node[sid] = node
    for sid, node in best_node.items():
        site = site_by_id[sid]
        out[sid] = {
            "site_id": sid, "site_code": site.site_code, "site_name": site.site_name,
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

    # ★★현장마다 «2차 비밀번호가 설정돼 있나» 를 **한 쿼리로** 싣는다(2026-09-09 리뷰 C1).
    #
    #   【왜】「승인이 곧 인증」 뒤에는 **비번 미설정 현장이 다수**다(라이브 실측 14 중 11).
    #     그런데 목록 카드는 진입 전 현장 전부에 «2차 비밀번호» 라벨을 무조건 그리고 있었고
    #     (`SiteListClient.tsx`), 그 라벨은 11현장에서 **거짓**이 된다.
    #   【그리고 이 필드가 게이팅을 만든다】진입 모달은 열리면 비번 없이 조용히 먼저 시도하는데,
    #     비번이 **설정된** 현장에서 그 시도를 하면 잠금 카운터를 향해 노크하는 셈이다.
    #     서버가 카운터 앞에서 400 으로 막지만(`resolve_entry` → `no_secret_supplied`),
    #     **애초에 두드리지 않는 것**이 옳다 — 그 판정에 이 필드가 쓰인다.
    #   ★N+1 이 되지 않게 `IN` 한 번으로 받는다. 목록이 비면 쿼리 자체를 건너뛴다.
    if out:
        await _ensure(db)
        pw_rows = (await db.execute(
            text("SELECT site_id::text FROM sales_site_passwords WHERE site_id = ANY(:ids)"),
            {"ids": list(out.keys())},
        )).all()
        with_pw = {r[0] for r in pw_rows}
        for sid, item in out.items():
            item["password_set"] = sid in with_pw

    return list(out.values())


# ── 3) 현장 진입(2차인증) ─────────────────────────────────────────────────────
@site_auth_router.post("/sites/{site_id}/enter", summary="현장 2차인증 → 현장 세션토큰 발급")
async def enter_site(site_id: str, body: EnterRequest,
                     db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    site = await _get_site(db, site_id)  # UUID/현장코드 모두 허용
    sid = str(site.id)  # 이후 SQL·토큰은 해석된 실제 UUID 사용

    org_path, role = await _resolve_role(db, site, user)
    # ★★멤버십 거부도 **판정 값**으로 받는다(2026-09-09 리뷰 C2).
    #   종전엔 `if not role:` **한 줄**에만 살아서 `if role is None:` 로 바꿔도
    #   (비멤버는 `""` 를 받으므로 **영원히 거짓**) 락 11건이 전부 초록이었다 —
    #   그 변이는 **인증된 아무나 아무 현장에** 진입시킨다. 판정이 값이어야 태울 수 있다.
    if resolve_entry(role, None, None) == "forbidden":
        raise HTTPException(403, "이 현장의 멤버가 아닙니다")

    now = datetime.now(UTC)
    # ★★**승인이 곧 인증이다**(2026-09-09). 위 `_resolve_role` 이 이미 «이 현장의 멤버인가» 를
    #   물었고, 멤버십은 **관리자·상위 레벨이 승인해야** 생긴다(`sales_org_nodes`).
    #
    #   ★라이브 실측(2026-09-09 · 읽기 전용 프로브): **14현장 중 11현장이 비번 미설정**이라
    #     그 현장들은 «2차비밀번호가 아직 설정되지 않았습니다» 409 로 **멤버여도 진입이 막혀
    #     있었다.** 워크스페이스 전체와 등록신청 승인 화면이 그 뒤에 있다.
    #
    #   ★볼트 R5(채택 · Zoom 벤치마킹): *"passcode(공유 설계) ↔ password(공유 금지) 구분 —
    #     우리는 **공유되도록 설계된 값을 비밀번호로 저장 중**"*. 현장 2차비번은 그 현장 사람
    #     모두가 아는 **공유 비밀**이고 회전되지 않는다. 「관리자가 개인에게 부여한 멤버십」보다
    #     약한 인증을 그 위에 강제하고 있었던 셈이다.
    #
    #   ⇒ **설정돼 있으면 요구하고, 없으면 멤버십으로 충분하다.** 비번을 지우지는 않는다 —
    #     이미 설정한 현장(실측 3곳)의 2차 요소를 **조용히 걷어내지 않기** 위해서다.
    # rate-limit: 잠금 여부 확인
    att = (await db.execute(text(
        "SELECT fail_count, locked_until FROM sales_site_login_attempts WHERE site_id=:s AND user_id=:u"
    ), {"s": sid, "u": str(user.id)})).first()
    if att and att.locked_until is not None:
        locked_until = att.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until > now:
            wait = int((locked_until - now).total_seconds() // 60) + 1
            raise HTTPException(429, f"진입 시도가 많아 잠겼습니다. {wait}분 후 다시 시도하세요")

    pw = (await db.execute(text(
        "SELECT password_hash FROM sales_site_passwords WHERE site_id=:s"
    ), {"s": sid})).first()
    if not pw:
        # ★비번 미설정 현장 — **승인된 멤버십으로 진입한다**(종전엔 409 로 막혔다).
        #   passwordless 진입은 감사에 남긴다(누가 무엇으로 들어왔는지 구별 가능해야 한다).
        await db.execute(text(
            "DELETE FROM sales_site_login_attempts WHERE site_id=:s AND user_id=:u"),
            {"s": sid, "u": str(user.id)})
        await db.commit()
        _log_entry(sid, user, role, "membership")
        token = issue_site_token(user.id, getattr(user, "tenant_id", None), site.id, role, org_path)
        return {
            "site_token": token,
            "token_type": "bearer",
            "expires_in": _SITE_TOKEN_HOURS * 3600,
            "site_id": sid,
            "role": role,
            "role_label": _ROLE_LABEL.get(role, role),
            "features": _features(role),
            # ★어떤 인증으로 들어왔는지 **말한다** — 두 경로가 같은 응답이면 진단이 불가능하다.
            "auth": "membership",
        }

    # ★판정은 **서비스 층**이 한다(`site_entry.verify_site_secret`) — 라우터는 3.10 에서
    #   임포트조차 안 돼(PEP 695 의존) 여기 두면 **CI 에서 처음 실행되는 락**만 남는다.
    outcome = resolve_entry(role, pw.password_hash, body.password)
    if outcome == "no_secret_supplied":
        # ★**실패 카운트를 올리지 않는다**(리뷰 C1). 「안 보냈다」와 「틀렸다」는 다른 사건이고,
        #   전자가 후자의 예산을 쓰면 모달을 몇 번 여는 것만으로 계정이 잠긴다.
        raise HTTPException(400, "이 현장은 2차 비밀번호가 필요합니다")

    if outcome != "password":
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

    _log_entry(sid, user, role, "password")
    token = issue_site_token(user.id, getattr(user, "tenant_id", None), site.id, role, org_path)
    return {
        "site_token": token,
        "token_type": "bearer",
        "expires_in": _SITE_TOKEN_HOURS * 3600,
        "site_id": sid,
        "role": role,
        "role_label": _ROLE_LABEL.get(role, role),
        "features": _features(role),
        "auth": "password",
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
    # ★★잠금 상태를 **볼 수 있게** 한다(2026-09-09 리뷰 «잠금 해제/조회 수단이 없다»).
    #   종전에는 `fail_count`·`locked_until` 이 **오직 401/429 응답에만** 드러나서,
    #   잠긴 사용자는 «틀렸다» 와 «잠겼다» 를 구별하려면 **또 시도해야** 했고
    #   관리자는 그 상태를 조회할 방법이 아예 없었다(유일한 해제 수단이 비번 재설정의 부작용).
    #   ★이 값은 **자기 자신의 상태**다 — 남의 잠금을 보여 주지 않는다.
    att = (await db.execute(text(
        "SELECT fail_count, locked_until FROM sales_site_login_attempts "
        "WHERE site_id=:s AND user_id=:u"), {"s": sid, "u": str(user.id)})).first()
    locked_until = att.locked_until if att else None
    return {
        "site_id": sid,
        "role": role,
        "role_label": _ROLE_LABEL.get(role, role),
        "org_path": org_path,
        "can_manage": role in _MANAGE_ROLES,
        "password_set": has_pw,
        # ★진단 불가는 그 자체로 장애다 — 「몇 번 남았나」와 「언제 풀리나」를 말한다.
        "fail_count": (att.fail_count if att else 0),
        "locked_until": (locked_until.isoformat() if locked_until is not None else None),
        "features": _features(role),
    }
