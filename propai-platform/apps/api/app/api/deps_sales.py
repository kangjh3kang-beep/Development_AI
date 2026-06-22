"""v62 sales — 테넌트/현장(site)/조직(ltree)/역할 컨텍스트 + RLS 세션변수 주입.

현장 격리는 1차로 app 계층(SalesCtx.site_id 필터)에서 강제하고,
set_config('app.site_id'|'app.org_path'|'app.role') 도 함께 주입해 RLS 활성화 시 즉시 적용되게 한다.
(RLS ENABLE+FORCE 자체는 통합검증 후 별도 단계에서 적용 — 정본=v62_2_sales_rls.py)

★세션변수 누수 방지(풀러 안전):
  - 모든 주입은 set_config(name, value, is_local=true) = SET LOCAL 의미로만 한다.
    트랜잭션 종료(commit/rollback) 시 자동 소멸하므로 pgbouncer/asyncpg 풀러에서 다음
    요청으로 누수되지 않는다(절대 is_local=false 로 주입하지 않는다).
  - 주입은 단일 헬퍼 _apply_session_ctx() 로 일원화한다(중복 set_config 산재 제거).

★commit 후 SET LOCAL 소멸 → 자동 재주입(silent 회귀 차단):
  - SET LOCAL 은 db.commit() 시 사라진다. FORCE+non-bypassrls 라이브에서 첫 commit 이후의
    RLS 쿼리는 세션변수 NULL → fail-closed 0행으로 'silent 회귀'한다.
  - 이를 엔드포인트마다 수동 재주입에 의존하지 않고, 세션 레벨 after_begin 이벤트로 자동화한다:
    한 번 _apply_session_ctx() 한 세션은 이후 모든 새 트랜잭션 시작 시(=commit/rollback 후
    첫 쿼리) 직전 컨텍스트를 자동 재주입한다. 따라서 db.commit 을 쓰는 sales 엔드포인트
    (mh/lifecycle_p5·p6/market/commission_agreement 등 10+)도 추가 코드 없이 보호된다.
  - 명시 재주입이 필요한 경우를 위해 SalesCtx.reapply(db) 도 제공한다(동일 헬퍼 경유).
  - 실풀러 누수 검증(라이브)은 deploy-pending. 코드상 SET LOCAL 일원화·is_local=true·
    commit 후 자동 재주입 보장은 본 변경으로 완료.
"""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite

# ★SSOT(단일 출처): 플랫폼 User.role → sales 폴백 역할 매핑(조직노드 없을 때).
# deps_sales 가 sales 인증의 최하위 모듈이므로 여기서 1회 정의하고, site_auth 등 상위 모듈은
# 이 집합을 import 해 재사용한다(과거 deps_sales·site_auth 중복정의로 드리프트 위험이 있었음).
_SUPERADMIN_ROLES = {"superadmin", "super_admin", "admin", "owner", "총괄관리자", "platform_admin"}
_DEVELOPER_ROLES = {"developer", "시행사", "dev"}

# 한 사용자가 같은 현장에 복수의 살아있는 조직노드를 가질 수 있다((site_id,user_id) UNIQUE 부재).
# 그때 결정적으로 '상위 권한' 노드를 고르기 위한 우선순위(작을수록 상위). 목록에 없는 값은
# 맨 뒤(낮은 우선순위)로 정렬한다. scalar_one_or_none() 의 MultipleResultsFound(500) 위험을
# scalars().first() + 이 정렬로 대체한다.
_NODE_TYPE_PRIORITY = {
    "AGENCY": 0,
    "SUBAGENCY": 1,
    "GM_DIRECTOR": 2,
    "DIRECTOR": 3,
    "TEAM_LEADER": 4,
    "MEMBER": 5,
}


def _node_priority(node_type: str) -> int:
    """조직노드 권한 우선순위(작을수록 상위). 미등록 타입은 가장 낮은 우선순위로."""
    return _NODE_TYPE_PRIORITY.get(node_type, len(_NODE_TYPE_PRIORITY))

# RLS 정책이 읽는 세션변수 키(정책 USING 절과 1:1 — v62_2_sales_rls.py / sales_rls_bootstrap.py).
_CTX_SITE_KEY = "app.site_id"
_CTX_ORG_KEY = "app.org_path"
_CTX_ROLE_KEY = "app.role"

# 세션 info 에 보관하는 키: 직전 주입한 RLS 컨텍스트 + 리스너 1회 등록 가드.
_INFO_CTX_KEY = "sales_rls_ctx"
_INFO_LISTENER_KEY = "sales_rls_reapply_registered"

# ★토큰 경로 sentinel: '토큰 없음(비토큰 경로로)' 과 '토큰 유효하나 멤버십 없음(즉시 403)' 을
# 구분한다. 과거엔 둘 다 None 을 반환해 sales_ctx 가 멤버십 SELECT 를 재실행(중복 2쿼리)했다.
# - _NO_TOKEN : 유효 토큰이 없음 → sales_ctx 가 비토큰 분기에서 멤버십을 '한 번' 해석.
# - None      : 유효 토큰은 있으나 멤버십이 사라짐(해촉/soft-delete/폴백없음) → 즉시 403(재쿼리 X).
# - (org_path, role) : 토큰 유효 + 멤버십 존재.
_NO_TOKEN = object()


def _ctx_values(site_id, org_path, role) -> dict[str, str]:
    """주입할 세션변수 값 3종을 정규화해 반환(빈 입력 → '' = 정책 nullif→NULL = fail-closed)."""
    return {
        _CTX_SITE_KEY: str(site_id) if site_id else "",
        _CTX_ORG_KEY: org_path or "",
        _CTX_ROLE_KEY: role or "",
    }


def _set_config_sync(connection, values: dict[str, str]) -> None:
    """동기 Connection 으로 set_config(..., is_local=true) 3종을 재주입한다.

    after_begin 이벤트 핸들러는 동기 컨텍스트(그린렛 내부)라 await 불가 → 동기 connection
    으로 실행한다. SET LOCAL 의미(is_local=true) 유지 → 풀러 누수 없음.
    """
    for k, v in values.items():
        connection.execute(
            text("SELECT set_config(:k, :v, true)"), {"k": k, "v": v}
        )


def _register_reapply_listener(db: AsyncSession) -> None:
    """세션에 after_begin 리스너를 1회 등록한다(commit/rollback 후 자동 재주입).

    after_begin 은 새 트랜잭션이 시작될 때마다 호출된다(SET LOCAL 이 날아간 직후 첫 쿼리
    시점). 이때 세션 info 에 저장된 직전 컨텍스트를 동기 connection 으로 재주입해
    'commit 후 RLS 세션변수 소멸 → silent 0행' 회귀를 막는다.
    """
    sync_session = db.sync_session
    if sync_session.info.get(_INFO_LISTENER_KEY):
        return  # 멱등: 세션당 1회만 등록(중복 핸들러 방지).
    sync_session.info[_INFO_LISTENER_KEY] = True

    @event.listens_for(sync_session, "after_begin")
    def _reapply_on_begin(session, transaction, connection):  # noqa: ANN001
        values = session.info.get(_INFO_CTX_KEY)
        if not values:
            return  # 아직 sales 컨텍스트가 주입되지 않은 세션 → 아무것도 안 함.
        _set_config_sync(connection, values)


async def _apply_session_ctx(db: AsyncSession, *, site_id, org_path: str, role: str) -> None:
    """RLS 세션변수(app.site_id/app.org_path/app.role)를 트랜잭션 로컬로 주입한다.

    ★누수 방지: set_config(..., is_local=true) = SET LOCAL 로만 주입한다. 트랜잭션이
    끝나면 자동 소멸하므로 풀러에서 다음 요청으로 새지 않는다.

    ★commit 후 자동 재주입: 주입값을 세션 info 에 보관하고 after_begin 리스너를 1회 등록해,
    같은 요청 내 db.commit() 이후 새 트랜잭션에서도 동일 컨텍스트가 자동 재주입되게 한다
    (엔드포인트의 수동 재주입 의존 제거 → silent 0행 회귀 차단).

    ★fail-closed 정합: 빈 org_path 는 빈문자열('')로 주입한다. 정책의
    nullif(current_setting('app.org_path', true),'') 가 이를 NULL 로 만들어 행 비노출
    (fail-closed)이 되게 한다. (과거 'none' 센티넬은 유효 ltree 라벨이라 fail-closed 가
    아니었음 — 제거.) DEVELOPER/SUPERADMIN 처럼 org_path 가 없는 역할은 정책의 role-IN
    분기로 통과하므로 빈 org_path 가 정상이다.
    """
    values = _ctx_values(site_id, org_path, role)
    # 세션 info 에 보관 → after_begin 리스너가 commit 후 자동 재주입에 사용.
    db.sync_session.info[_INFO_CTX_KEY] = values
    _register_reapply_listener(db)
    for k, v in values.items():
        await db.execute(text("SELECT set_config(:k, :v, true)"), {"k": k, "v": v})


class SalesCtx:
    def __init__(self, site_id, org_path, role, user):
        self.site_id = site_id
        self.org_path = org_path
        self.role = role
        self.user = user

    async def reapply(self, db: AsyncSession) -> None:
        """RLS 세션변수를 현 컨텍스트로 다시 주입한다(명시 재주입용).

        after_begin 자동 재주입으로 대부분 불필요하나, 엔드포인트가 직접 재주입을 원할 때
        단일 헬퍼(_apply_session_ctx)를 경유해 동일하게 처리한다.
        """
        await _apply_session_ctx(db, site_id=self.site_id, org_path=self.org_path, role=self.role)


async def resolve_site_membership(db: AsyncSession, site, user):
    """현 사용자의 그 현장 (org_path, role) 을 단일 기준으로 해석. 권한 없으면 None.

    ★3중복 SELECT 일원화(코드로 1:1 보장): deps_sales.sales_ctx·_site_token_ctx 와
    site_auth._resolve_role 이 동일한 멤버십 판정(조직노드 → 플랫폼 폴백)을 각자 SELECT 로
    중복 수행하던 것을 본 공용 헬퍼로 모은다. '1:1 일원화'를 주석이 아닌 코드로 보장한다.
    (멤버십 SELECT 의 단일 출처 = 본 헬퍼 1곳. 호출부는 재조회하지 않는다.)

    판정 순서(단일 기준):
      1) 살아있는 조직노드(active=True, deleted_at IS NULL) → (str(node.path), node.node_type).
         강등/이동도 DB 최신값을 그대로 반영(토큰 클레임 미신뢰).
      2) 노드 없음 → 플랫폼 폴백: user.role 이 SUPERADMIN 군이면 ('', 'SUPERADMIN'),
         DEVELOPER 군 또는 owns_site(본인 테넌트 소유 현장)면 ('', 'DEVELOPER').
      3) 어느 것도 아니면 None(=멤버 아님 → 호출부가 403/거부 처리).

    ★복수 노드 안전(런타임 500 방지): (site_id,user_id) UNIQUE 가 없어 한 사용자가 같은
    현장에 살아있는 노드를 2개 이상 가질 수 있다. scalar_one_or_none() 은 그 경우
    MultipleResultsFound(=500)를 던진다. 그래서 scalars().all() 로 받고, 권한 우선순위
    (_node_priority)로 정렬해 '상위 권한' 노드를 결정적으로 선택한다(비결정 정렬 제거).

    ★결정성(이번 변경): 같은 node_type 노드가 2개 이상이면(예: MEMBER root.a / MEMBER
    root.b) priority 가 동률이라 min() 이 '입력 순서(=DB 행순)'에 의존해 비결정적이었다.
    선택된 node.path 는 RLS 세션변수 app.org_path 로 주입되므로, 동률에서 흔들리면 같은
    site/user 인데도 실행마다 RLS 가시 서브트리가 달라진다(격리 비결정). 이를 막기 위해
    ① SQL .order_by 를 (node_type, path, id) 로 의미화하고 ② 파이썬 정렬 키도
    (priority, str(path), str(id)) 튜플로 동률을 완전히 깨, 입력 순서와 무관하게 항상 같은
    노드를 고른다.
    """
    nodes = (await db.execute(
        select(SalesOrgNode).where(
            SalesOrgNode.site_id == site.id,
            SalesOrgNode.user_id == user.id,
            SalesOrgNode.active.is_(True),
            # soft-deleted 노드는 멤버십으로 인정하지 않는다(_resolve_role·my_sites 동일 기준).
            SalesOrgNode.deleted_at.is_(None),
        )
        # 상위 권한 우선 → 같은 현장 복수 노드여도 결정적으로 최상위 역할을 고른다.
        # node_type 만으론 같은 타입 복수 노드에서 행순 의존(비결정) → (path, id)까지 의미화.
        .order_by(SalesOrgNode.node_type, SalesOrgNode.path, SalesOrgNode.id)
    )).scalars().all()
    # DB order_by(node_type)는 알파벳 정렬이라 권한순이 아님 → 파이썬에서 권한 우선순위로 재정렬.
    # ★동률 결정화: priority 동률(같은 node_type)이면 (path, id)로 깨 입력 순서 무관·항상 동일 선택.
    node = (
        min(nodes, key=lambda n: (_node_priority(n.node_type), str(n.path), str(n.id)))
        if nodes else None
    )

    if node is not None:
        return str(node.path), node.node_type

    role_lower = (getattr(user, "role", "") or "").lower()
    user_tenant = getattr(user, "tenant_id", None)
    # SalesSite의 소유 테넌트는 organization_id 컬럼(=provision 시 user.tenant_id)으로 저장됨.
    owns_site = bool(user_tenant) and str(getattr(site, "organization_id", "") or "") == str(user_tenant)
    if role_lower in _SUPERADMIN_ROLES:
        return "", "SUPERADMIN"
    if role_lower in _DEVELOPER_ROLES or owns_site:
        # 본인 테넌트가 소유한 현장 → 시행사(DEVELOPER)로 인정(구독자가 만든 현장을 운영 가능).
        return "", "DEVELOPER"
    return None  # 멤버 아님 → 호출부가 거부/403 처리.


async def resolve_site(request: Request, db: AsyncSession) -> SalesSite:
    """우선순위: 경로변수 site_id → 헤더 X-Site-Code → 서브도메인(host). site_code 또는 UUID 허용."""
    site_code = request.path_params.get("site_id") or request.headers.get("x-site-code")
    if not site_code:
        host = request.headers.get("host", "")
        if ".sales." in host or ".desk." in host:
            site_code = host.split(".")[0]
    if not site_code:
        raise HTTPException(400, "site context missing (X-Site-Code 헤더 또는 경로 site_id 필요)")

    # UUID 우선 시도, 실패 시 site_code 로 조회
    try:
        site = (await db.execute(select(SalesSite).where(SalesSite.id == uuid.UUID(str(site_code))))).scalar_one_or_none()
    except (ValueError, TypeError):
        site = None
    if site is None:
        site = (await db.execute(select(SalesSite).where(SalesSite.site_code == str(site_code)))).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "site not found")
    return site


async def _site_token_ctx(request: Request, db: AsyncSession, user, site):
    """X-Site-Token(현장 세션토큰) 경로 해석. 반환은 3치(_NO_TOKEN / None / (org_path, role)).

    Phase1-A 현장 2차인증으로 발급된 단기 토큰(8h). 토큰에는 발급 시점의 멤버십·역할이
    담겨 있지만, 그 자체만 신뢰하면 해촉/강등/soft-delete 된 직원이 토큰 만료(8h)까지
    권한을 유지하는 '8h 권한지연' 위험이 있다(deleted_at 게이트 우회).

    ★그래서 토큰 디코드 직후에도 멤버십을 DB로 1쿼리 재검증한다(가벼운 검증). 판정은 공용
    헬퍼 resolve_site_membership 로 일원화한다(비토큰 경로와 동일 기준).
    - 살아있는 조직노드(active=True, deleted_at IS NULL)가 있으면 그 노드의 최신
      (path, node_type) 을 사용한다 → 강등(역할 변경)도 즉시 반영된다.
    - 노드가 없으면(=해촉/삭제) 헬퍼가 플랫폼 폴백(SUPERADMIN/DEVELOPER/owns_site)을 판정한다.

    ★반환 sentinel 구분(중복 SELECT 제거 = 정확성):
      - _NO_TOKEN : 유효한 토큰이 없음(헤더 무·디코드 실패·site/user 불일치). sales_ctx 는
        비토큰 분기에서 멤버십을 '한 번' 해석한다(여기서는 멤버십 SELECT 미수행).
      - None      : 토큰은 유효하나 멤버십이 사라짐(헬퍼가 None) → sales_ctx 가 '즉시 403'.
        과거엔 이 경우도 None 을 돌려줘 sales_ctx 가 동일 멤버십 SELECT 를 '한 번 더' 실행
        (중복 2쿼리)했다. sentinel 로 '토큰 없음' 과 분리해 재쿼리를 제거한다.
      - (org_path, role) : 토큰 유효 + 멤버십 존재.
    토큰 클레임(org_path/site_role)은 신뢰하지 않고 DB 최신 멤버십/폴백만 사용한다.
    """
    raw = request.headers.get("x-site-token")
    if not raw:
        return _NO_TOKEN
    from app.api.endpoints.sales.site_auth import decode_site_token  # 지연 import(순환 방지)
    payload = decode_site_token(raw)
    if not payload:
        return _NO_TOKEN
    # 토큰의 site/사용자 정합 — 다른 현장·다른 사용자 토큰 차단(유효 토큰 아님 → 비토큰 경로로).
    if str(payload.get("site_id")) != str(site.id):
        return _NO_TOKEN
    if str(payload.get("sub")) != str(getattr(user, "id", "")):
        return _NO_TOKEN

    # ★멤버십 DB 재검증(8h 권한지연 제거) — 멤버십 SELECT 단일 출처(공용 헬퍼) 1회.
    # 토큰 유효 + 멤버십 없음이면 헬퍼가 None → 그대로 None 반환(sales_ctx 즉시 403, 재쿼리 X).
    return await resolve_site_membership(db, site, user)


async def sales_ctx(request: Request, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> SalesCtx:
    site = await resolve_site(request, db)
    site_id = site.id

    # ── 토큰 우선: 현장 세션토큰(X-Site-Token) + 멤버십 DB 재검증(8h 권한지연 제거) ──
    # 멤버십 SELECT 는 토큰/비토큰 어느 경로든 '정확히 1회'만 수행한다(중복 2쿼리 제거):
    #  - _NO_TOKEN : 토큰 없음 → 비토큰 분기에서 멤버십을 1회 해석.
    #  - None      : 토큰 유효하나 멤버십 없음 → 즉시 403(재쿼리하지 않음).
    #  - (op, role): 토큰 유효 + 멤버십 존재 → 그대로 사용.
    tok = await _site_token_ctx(request, db, user, site)
    if tok is _NO_TOKEN:
        # 비토큰 경로도 토큰 경로와 동일한 공용 헬퍼로 멤버십(노드 → 폴백)을 판정한다(1:1 일원화).
        membership = await resolve_site_membership(db, site, user)
        if membership is None:
            raise HTTPException(403, "이 현장에 대한 분양(sales) 권한이 없습니다")
        org_path, role = membership
    elif tok is None:
        # 토큰은 유효했으나 멤버십이 사라짐(해촉/soft-delete/폴백없음) → 즉시 거부(재쿼리 없음).
        raise HTTPException(403, "이 현장에 대한 분양(sales) 권한이 없습니다")
    else:
        org_path, role = tok

    # RLS 세션변수 주입(트랜잭션 로컬·단일 헬퍼) — 활성화 시 즉시 적용, 풀러 누수 없음
    await _apply_session_ctx(db, site_id=site_id, org_path=org_path, role=role)
    return SalesCtx(site_id, org_path, role, user)


def require_role(*allowed):
    async def _dep(ctx: SalesCtx = Depends(sales_ctx)):
        if ctx.role not in allowed and ctx.role != "SUPERADMIN":
            raise HTTPException(403, f"role {ctx.role} not permitted")
        return ctx
    return _dep
