"""Phase1-E 직원관리 + 공통 구인구직 마켓플레이스 + 재사용 프로필.

분양상담사(프리랜서)가 여러 현장을 뛰며, 잡코리아/링크드인 패턴으로 프로필을 1회
작성→재사용한다. 구인/구직·현장홍보·대행모집을 플랫폼 공통(public) 컨텐츠로 운영한다.

★★격리모델 — PUBLIC/공통(현장 RLS 적용 금지)
  profiles_personal / profiles_company / job_posts / job_applications / site_promotions
  는 분양 sales 테이블(site_id RLS 대상)과 달리 site RLS 를 걸지 않는다.
  - 테이블명에 sales_ / mh_ 접두를 쓰지 않으므로 sales_rls_bootstrap.py 의 동적
    대상조회(table LIKE 'sales\\_%' OR 'mh\\_%')에서 자동 제외된다(부트스트랩 목록 미추가).
  - 격리는 애플리케이션 계층에서 소유자(user_id) + 공개범위(visibility) 로 엄격히 강제.
  - 채용확정→조직 멤버십 연결만 기존 sales 조직도(SalesOrgNode, site 격리)에 기록한다.

인증
  PUBLIC 컨텐츠이므로 sales_ctx(현장 컨텍스트) 가 아니라 get_current_user(전역 SSO)를 쓴다.

재사용(기존 무파괴)
  - 사용자        : public.users(id·email·name·role·tenant_id) + get_current_user
  - 조직도/멤버십 : sales_org_nodes(user_id·site_id·node_type·path·active) — 채용연계 훅
  - 이미지업로드  : 기존 /api/v1/uploads/image 로 업로드한 public URL 을 프로필/로고에 전달
  - 직원집계      : sales_org_nodes(멤버십) + sales_commission_* (수수료) + 출근/계약 집계 재사용

신규 PUBLIC 테이블(_ensure, 멱등, gen_random_uuid 기본)
  profiles_personal   : 개인(상담사) 재사용 프로필(user_id UNIQUE)
  profiles_company    : 회사(시행/대행) 재사용 프로필
  job_posts           : 구인/구직/현장홍보/대행모집 공고
  job_applications    : 공고 신청(프로필 불러오기)
  site_promotions     : 분양현장 홍보(B2C 고객유치 + B2B 대행유치)
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from apps.api.database.sales_market_ddl import INDEX_DDLS, TABLE_DDLS  # DDL/인덱스 SSOT(036 과 공유)

logger = logging.getLogger(__name__)

market_router = APIRouter(prefix="/api/v1/market", tags=["sales-market"])

# 채용연계(조직도 멤버십 생성) 가능 역할 — 현장 관리자
_MANAGER_ROLES = {"superadmin", "super_admin", "admin", "owner", "developer", "agency"}

# 테이블/컬럼 미존재 PostgreSQL SQLSTATE(asyncpg) — 이것만 '정상 0/스킵'(아직 안 만든 테이블)으로 본다.
# 42P01=undefined_table, 42703=undefined_column. 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).
# (app/services/sales/payment/service.py·commission/engine.py 의 검증된 분류 패턴과 동일.)
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01", "42703"})


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블/컬럼 미존재'(42P01/42703)면 해당 SQLSTATE, 아니면 None(전파신호).

    ★이 분류기는 컬럼 미존재(42703)도 '정상 스킵'으로 본다. 채용연계처럼 '조직도 자체가 미설치'를
      판별하는 곳에 쓴다(테이블/컬럼 어느 쪽이 비어도 미설치로 간주 가능).
    """
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code in _MISSING_OBJECT_SQLSTATES:
        return code
    return None


def _missing_table_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블 미존재(42P01)'면 그 SQLSTATE, 아니면 None(전파신호).

    ★[correctness — 컬럼누락 은폐 차단(iter-3)] count(*)/sum() 집계는 특정 컬럼을 지목하지 않으므로,
      여기서 42703(undefined_column=스키마 드리프트)이 나오면 그건 '정상 0'(아직 안 만든 테이블)이
      아니라 '있어야 할 컬럼이 사라진 진짜 결함'이다. 공유 _missing_object_sqlstate(42P01+42703)를
      그대로 쓰면 컬럼 드리프트를 0 으로 흡수해 '계약/매출 0' 으로 은폐된다. 그래서 집계 경로는
      이 전용 분류기로 '테이블 미존재(42P01)'만 정상 0 으로 보고, 42703 은 전파한다(은폐 금지).
    """
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code == "42P01":
        return code
    return None

# ── 표시광고법·개인정보 동의 고지 문구(홍보 응답에 포함) ───────────────────────
_PROMO_NOTICE = (
    "본 홍보는 표시·광고의 공정화에 관한 법률을 준수하며, 개인정보 수집·이용 동의 후 "
    "연락이 진행됩니다. 실적·정보는 작성자 자기기재이며 사실과 다를 수 있습니다."
)


# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
# ★[DDL/인덱스 SSOT] 5개 PUBLIC 테이블 DDL + 3개 인덱스는 database/sales_market_ddl.py 단일 정본을
#   import 한다(상단 import 참조). 과거엔 같은 DDL 이 여기와 036 마이그레이션에 '복붙'으로 중복됐고,
#   인덱스는 036 에만 있고 여기엔 없어 마이그레이션 미적용 환경에서 인덱스 없이 동작하는 드리프트가
#   있었다. 정본을 공유 모듈로 추출해 두 소비자(이 _ensure / 036)가 byte-identical 문자열을 쓰도록 강제.

# 런타임 DDL race 제거용 advisory-lock 키(임의 고유 상수, 충돌 회피). 트랜잭션 종료 시 자동 해제.
_LOCK_MARKET_TABLES = 880421036
# 프로세스 1회 게이트(읽기경로 매 요청 DDL/commit 직렬화 제거). asyncio.Lock 으로 동시 첫 호출 합류.
_MARKET_READY = False
_market_lock = asyncio.Lock()


async def _ensure(db: AsyncSession | None = None) -> None:
    """마켓 PUBLIC 테이블 멱등 보장(부팅 안전망) — 프로세스 1회만 실제 DDL 수행.

    ★정본은 Alembic 036_sales_market_tables. 여기서는 마이그레이션 미적용 환경(개발/신규배포) 대비
      테이블 5개 + 인덱스 3개를 CREATE ... IF NOT EXISTS 로 보장한다(파괴적 변경 없음). DDL/인덱스
      문자열은 database/sales_market_ddl.py 정본을 import 해 036 과 byte-identical 로 쓴다(드리프트
      제거 — 과거엔 인덱스가 036 에만 있고 여기엔 없어 미적용 환경이 인덱스 없이 동작했다). 최초 1회
      성공 후엔 즉시 반환(no-op)해 '매 요청 DDL/commit'을 없앤다(과거엔 모든 마켓 요청마다 CREATE 반복).
    동시 부팅(멀티프로세스) race 는 advisory-lock(pg_advisory_xact_lock, 트랜잭션 종료 시 자동해제)으로,
    코루틴 경합은 asyncio.Lock 으로 막는다.

    ★[부분커밋 차단] DDL+commit 은 항상 '별도 단명 세션'(async_session_factory)에서 수행한다.
      호출자 세션(db)에서 DDL/commit 하면 같은 요청 안의 호출자 미커밋 쓰기가 휩쓸려 조기 부분커밋
      되기 때문이다(commission.ensure_tax_pref 의 검증된 패턴). 인자 db 는 하위호환 위해 받지만
      사용하지 않는다(별도 세션으로 DDL 수행).

    ★ 테이블명에 sales_/mh_ 접두를 쓰지 않으므로 RLS 부트스트랩 동적조회에서 자동 제외.
    """
    global _MARKET_READY
    if _MARKET_READY:  # 이미 보장됨 → DB 왕복 없이 즉시 반환.
        return
    async with _market_lock:  # 동시 첫 호출(코루틴 경합)을 1회로 합류.
        if _MARKET_READY:
            return
        # ★별도 단명 세션 — 호출자 세션(db)의 미커밋 쓰기를 휩쓸지 않도록 DDL/commit 을 격리.
        from app.core.database import async_session_factory
        async with async_session_factory() as ddl_db:
            # advisory-lock: 트랜잭션 종료(commit/rollback) 시 자동 해제.
            await ddl_db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_MARKET_TABLES})
            for ddl in TABLE_DDLS:          # 테이블 5개(IF NOT EXISTS) — SSOT 정본.
                await ddl_db.execute(text(ddl))
            for idx in INDEX_DDLS:          # ★인덱스 3개 추가(036 과 동일) — 드리프트 해소.
                await ddl_db.execute(text(idx))
            await ddl_db.commit()
        _MARKET_READY = True  # 성공 시에만 게이트 닫음(실패 시 다음 호출이 재시도).


# ── 스키마 ───────────────────────────────────────────────────────────────────
class PersonalProfileUpsert(BaseModel):
    full_name: str | None = None
    contact: str | None = None
    region: str | None = None
    specialties: list[str] = Field(default_factory=list)
    experience_years: int = 0
    achievement_summary: str | None = None
    certifications: list[str] = Field(default_factory=list)
    desired_conditions: str | None = None
    photo_url: str | None = None
    visibility: str = "public"           # public|contacts|private
    mask_contact: bool = True


class CompanyProfileUpsert(BaseModel):
    org_id: uuid.UUID | None = None
    company_name: str | None = None
    company_type: str = "AGENCY"          # DEVELOPER|AGENCY
    company_size: str | None = None
    intro: str | None = None
    active_sites: str | None = None
    reputation: str | None = None
    logo_url: str | None = None
    contact: str | None = None
    region: str | None = None
    visibility: str = "public"
    mask_contact: bool = True


class PostCreate(BaseModel):
    kind: str                              # hire|seek|promote_site|recruit_agency
    title: str
    body: str | None = None
    region: str | None = None
    specialty: list[str] = Field(default_factory=list)
    site_id: uuid.UUID | None = None
    contact_method: str | None = None


class PostUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    region: str | None = None
    specialty: list[str] | None = None
    contact_method: str | None = None
    status: str | None = None             # open|closed


class ApplyRequest(BaseModel):
    profile_id: uuid.UUID | None = None    # 불러오기 — 개인/회사 자동판별
    message: str | None = None


class DecideRequest(BaseModel):
    accept: bool


class PromotionCreate(BaseModel):
    site_id: uuid.UUID | None = None
    promo_type: str = "B2C"                # B2C|B2B
    title: str
    body: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    region: str | None = None


# ── 직원관리 집계 응답계약(Pydantic) — 프론트 StaffOverviewPanel.tsx 와 1:1 정합 ──
# ★응답계약 SSOT(역할 분리): 본 staff_overview 는 '여러 현장의 현장 단위' 요약(현장별 멤버·계약·
#   출근·수수료gross, 다현장 union)이다. 이는 sales/org/overview.py 의 team_overview(=한 현장의
#   조직 노드 단위 로스터 TeamOverviewResponse)와 입도·범위가 다른 별개 계약으로, 두 응답을 합치지
#   않고 '명확히 분리'한다. 본 응답의 단일 소비자는 StaffOverviewPanel.tsx 하나뿐이다(이중 구현 금지).
class SiteStaffSummary(BaseModel):
    """현장 1곳의 직원관리 요약(멤버·계약·출근·수수료gross)."""
    site_id: str
    site_name: str = "-"
    member_count: int = 0
    contract_count: int = 0
    attendance_count: int = 0
    commission_gross: int = 0


class StaffOverviewTotals(BaseModel):
    """집계 대상 현장들의 합계."""
    member_count: int = 0
    contract_count: int = 0
    attendance_count: int = 0
    commission_gross: int = 0


class StaffOverviewResponse(BaseModel):
    """직원관리 집계(scope=site|all) — 현장 단위 요약 리스트 + 합계."""
    scope: str                         # 'site'(단일) | 'all'(내가 관리·소유하는 전 현장)
    site_count: int = 0
    sites: list[SiteStaffSummary] = Field(default_factory=list)
    totals: StaffOverviewTotals = Field(default_factory=StaffOverviewTotals)


_VALID_KIND = {"hire", "seek", "promote_site", "recruit_agency"}
_VALID_VIS = {"public", "contacts", "private"}


# ── 공개범위·마스킹 유틸 ──────────────────────────────────────────────────────
def _mask_contact_value(contact: str | None) -> str | None:
    """연락처 마스킹 — 뒤 4자만 가린다(전화·카톡 공통)."""
    if not contact:
        return contact
    s = str(contact)
    if len(s) <= 4:
        return "****"
    return s[:-4] + "****"


def _apply_personal_visibility(row: dict, viewer_id: str | None) -> dict | None:
    """개인 프로필 공개범위/마스킹 적용. private=본인만, contacts=연결사용자(현재=본인 폴백),
    public=공개(마스킹옵션 적용). 비공개 시 None."""
    is_owner = viewer_id is not None and row["user_id"] == str(viewer_id)
    vis = row.get("visibility") or "public"
    if is_owner:
        return {**row, "_is_owner": True}
    if vis == "private":
        return None
    # contacts: 연결(친구/멤버십) 그래프는 소셜그래프 미구축 단계 — 보수적으로 비공개 처리.
    if vis == "contacts":
        return None
    masked = dict(row)
    masked["_is_owner"] = False
    masked["_self_reported"] = True       # 실적·자격은 자기기재 표기
    if row.get("mask_contact"):
        masked["contact"] = _mask_contact_value(row.get("contact"))
    return masked


def _personal_public_dict(row) -> dict:
    return {
        "id": str(row[0]), "user_id": str(row[1]), "full_name": row[2], "contact": row[3],
        "region": row[4], "specialties": list(row[5] or []), "experience_years": int(row[6] or 0),
        "achievement_summary": row[7], "certifications": list(row[8] or []),
        "desired_conditions": row[9], "photo_url": row[10], "visibility": row[11],
        "mask_contact": bool(row[12]),
        "created_at": str(row[13]) if row[13] else None,
        "updated_at": str(row[14]) if row[14] else None,
    }


_PERSONAL_COLS = (
    "id, user_id, full_name, contact, region, specialties, experience_years,"
    " achievement_summary, certifications, desired_conditions, photo_url, visibility,"
    " mask_contact, created_at, updated_at"
)
_COMPANY_COLS = (
    "id, owner_user_id, org_id, company_name, company_type, company_size, intro,"
    " active_sites, reputation, logo_url, contact, region, visibility, mask_contact,"
    " created_at, updated_at"
)


def _company_public_dict(row) -> dict:
    return {
        "id": str(row[0]), "owner_user_id": str(row[1]),
        "org_id": str(row[2]) if row[2] else None, "company_name": row[3],
        "company_type": row[4], "company_size": row[5], "intro": row[6],
        "active_sites": row[7], "reputation": row[8], "logo_url": row[9],
        "contact": row[10], "region": row[11], "visibility": row[12],
        "mask_contact": bool(row[13]),
        "created_at": str(row[14]) if row[14] else None,
        "updated_at": str(row[15]) if row[15] else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# 1) 재사용 프로필 — 개인
# ════════════════════════════════════════════════════════════════════════════
@market_router.get("/profile/personal", summary="내 개인 프로필 조회")
async def get_my_personal(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = (await db.execute(text(
        f"SELECT {_PERSONAL_COLS} FROM profiles_personal WHERE user_id = :uid"),
        {"uid": str(user.id)})).first()
    if not row:
        return {"exists": False, "profile": None}
    return {"exists": True, "profile": _personal_public_dict(row)}


@market_router.put("/profile/personal", summary="내 개인 프로필 저장(upsert)")
async def put_my_personal(body: PersonalProfileUpsert, db: AsyncSession = Depends(get_db),
                          user=Depends(get_current_user)) -> dict:
    if body.visibility not in _VALID_VIS:
        raise HTTPException(400, "visibility 는 public|contacts|private 중 하나여야 합니다")
    await _ensure(db)
    params = {
        "uid": str(user.id), "nm": body.full_name, "ct": body.contact, "rg": body.region,
        "sp": list(body.specialties), "yr": int(body.experience_years), "ac": body.achievement_summary,
        "cf": list(body.certifications), "dc": body.desired_conditions, "ph": body.photo_url,
        "vs": body.visibility, "mk": body.mask_contact,
    }
    await db.execute(text(
        "INSERT INTO profiles_personal"
        " (user_id, full_name, contact, region, specialties, experience_years,"
        "  achievement_summary, certifications, desired_conditions, photo_url, visibility, mask_contact)"
        " VALUES (:uid,:nm,:ct,:rg,:sp,:yr,:ac,:cf,:dc,:ph,:vs,:mk)"
        " ON CONFLICT (user_id) DO UPDATE SET"
        "  full_name=excluded.full_name, contact=excluded.contact, region=excluded.region,"
        "  specialties=excluded.specialties, experience_years=excluded.experience_years,"
        "  achievement_summary=excluded.achievement_summary, certifications=excluded.certifications,"
        "  desired_conditions=excluded.desired_conditions, photo_url=excluded.photo_url,"
        "  visibility=excluded.visibility, mask_contact=excluded.mask_contact, updated_at=now()"),
        params)
    await db.commit()
    row = (await db.execute(text(
        f"SELECT {_PERSONAL_COLS} FROM profiles_personal WHERE user_id = :uid"),
        {"uid": str(user.id)})).first()
    return {"profile": _personal_public_dict(row), "self_reported_notice": "실적·자격은 자기기재 항목입니다"}


@market_router.get("/profile/personal/{user_id}", summary="타인 개인 프로필 조회(공개범위·마스킹 존중)")
async def get_personal_by_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                               user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = (await db.execute(text(
        f"SELECT {_PERSONAL_COLS} FROM profiles_personal WHERE user_id = :uid"),
        {"uid": str(user_id)})).first()
    if not row:
        raise HTTPException(404, "프로필이 없습니다")
    full = _personal_public_dict(row)
    shown = _apply_personal_visibility(full, str(user.id))
    if shown is None:
        raise HTTPException(403, "비공개 프로필이거나 열람 권한이 없습니다")
    return {"profile": shown}


# ════════════════════════════════════════════════════════════════════════════
# 2) 재사용 프로필 — 회사
# ════════════════════════════════════════════════════════════════════════════
@market_router.get("/profile/company", summary="내 회사 프로필 조회")
async def get_my_company(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = (await db.execute(text(
        f"SELECT {_COMPANY_COLS} FROM profiles_company WHERE owner_user_id = :uid"),
        {"uid": str(user.id)})).first()
    if not row:
        return {"exists": False, "profile": None}
    return {"exists": True, "profile": _company_public_dict(row)}


@market_router.put("/profile/company", summary="내 회사 프로필 저장(upsert)")
async def put_my_company(body: CompanyProfileUpsert, db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> dict:
    if body.visibility not in _VALID_VIS:
        raise HTTPException(400, "visibility 는 public|contacts|private 중 하나여야 합니다")
    if body.company_type not in {"DEVELOPER", "AGENCY"}:
        raise HTTPException(400, "company_type 는 DEVELOPER|AGENCY 중 하나여야 합니다")
    await _ensure(db)
    params = {
        "uid": str(user.id), "org": str(body.org_id) if body.org_id else None,
        "cn": body.company_name, "tp": body.company_type, "sz": body.company_size,
        "it": body.intro, "as": body.active_sites, "rp": body.reputation, "lg": body.logo_url,
        "ct": body.contact, "rg": body.region, "vs": body.visibility, "mk": body.mask_contact,
    }
    await db.execute(text(
        "INSERT INTO profiles_company"
        " (owner_user_id, org_id, company_name, company_type, company_size, intro,"
        "  active_sites, reputation, logo_url, contact, region, visibility, mask_contact)"
        " VALUES (:uid,:org,:cn,:tp,:sz,:it,:as,:rp,:lg,:ct,:rg,:vs,:mk)"
        " ON CONFLICT (owner_user_id) DO UPDATE SET"
        "  org_id=excluded.org_id, company_name=excluded.company_name, company_type=excluded.company_type,"
        "  company_size=excluded.company_size, intro=excluded.intro, active_sites=excluded.active_sites,"
        "  reputation=excluded.reputation, logo_url=excluded.logo_url, contact=excluded.contact,"
        "  region=excluded.region, visibility=excluded.visibility, mask_contact=excluded.mask_contact,"
        "  updated_at=now()"),
        params)
    await db.commit()
    row = (await db.execute(text(
        f"SELECT {_COMPANY_COLS} FROM profiles_company WHERE owner_user_id = :uid"),
        {"uid": str(user.id)})).first()
    return {"profile": _company_public_dict(row), "self_reported_notice": "진행현장·평판은 자기기재 항목입니다"}


# ════════════════════════════════════════════════════════════════════════════
# 3) 구인구직 마켓(공통) — 공고
# ════════════════════════════════════════════════════════════════════════════
def _post_dict(row) -> dict:
    return {
        "id": str(row[0]), "author_user_id": str(row[1]), "kind": row[2], "title": row[3],
        "body": row[4], "region": row[5], "specialty": list(row[6] or []),
        "site_id": str(row[7]) if row[7] else None, "contact_method": row[8], "status": row[9],
        "created_at": str(row[10]) if row[10] else None,
        "updated_at": str(row[11]) if row[11] else None,
    }


_POST_COLS = (
    "id, author_user_id, kind, title, body, region, specialty, site_id,"
    " contact_method, status, created_at, updated_at"
)


@market_router.post("/posts", summary="공고 등록(구인/구직/현장홍보/대행모집)")
async def create_post(body: PostCreate, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)) -> dict:
    if body.kind not in _VALID_KIND:
        raise HTTPException(400, "kind 는 hire|seek|promote_site|recruit_agency 중 하나여야 합니다")
    if not body.title.strip():
        raise HTTPException(400, "title 은 필수입니다")
    await _ensure(db)
    pid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO job_posts (id, author_user_id, kind, title, body, region, specialty, site_id, contact_method)"
        " VALUES (:id,:au,:kd,:tt,:bd,:rg,:sp,:sid,:cm)"),
        {"id": str(pid), "au": str(user.id), "kd": body.kind, "tt": body.title, "bd": body.body,
         "rg": body.region, "sp": list(body.specialty), "sid": str(body.site_id) if body.site_id else None,
         "cm": body.contact_method})
    await db.commit()
    row = (await db.execute(text(f"SELECT {_POST_COLS} FROM job_posts WHERE id = :id"),
                            {"id": str(pid)})).first()
    return {"post": _post_dict(row)}


@market_router.get("/posts", summary="공고 검색·필터(kind/region/specialty/q)")
async def list_posts(kind: str | None = Query(default=None),
                     region: str | None = Query(default=None),
                     specialty: str | None = Query(default=None),
                     q: str | None = Query(default=None),
                     status: str = Query(default="open"),
                     limit: int = Query(default=50, le=200),
                     db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    where = ["1=1"]
    params: dict = {"lim": limit}
    if status:
        where.append("status = :st")
        params["st"] = status
    if kind:
        if kind not in _VALID_KIND:
            raise HTTPException(400, "kind 값이 올바르지 않습니다")
        where.append("kind = :kd")
        params["kd"] = kind
    if region:
        where.append("region ILIKE :rg")
        params["rg"] = f"%{region}%"
    if specialty:
        where.append(":sp = ANY(specialty)")
        params["sp"] = specialty
    if q:
        where.append("(title ILIKE :q OR body ILIKE :q)")
        params["q"] = f"%{q}%"
    rows = (await db.execute(text(
        f"SELECT {_POST_COLS} FROM job_posts WHERE {' AND '.join(where)}"
        " ORDER BY created_at DESC LIMIT :lim"), params)).all()
    return {"items": [_post_dict(r) for r in rows], "count": len(rows)}


@market_router.get("/posts/{post_id}", summary="공고 상세")
async def get_post(post_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                   user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = (await db.execute(text(f"SELECT {_POST_COLS} FROM job_posts WHERE id = :id"),
                            {"id": str(post_id)})).first()
    if not row:
        raise HTTPException(404, "공고를 찾을 수 없습니다")
    return {"post": _post_dict(row)}


@market_router.patch("/posts/{post_id}", summary="공고 수정(작성자 본인)")
async def update_post(post_id: uuid.UUID, body: PostUpdate, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    owner = (await db.execute(text("SELECT author_user_id FROM job_posts WHERE id = :id"),
                              {"id": str(post_id)})).first()
    if not owner:
        raise HTTPException(404, "공고를 찾을 수 없습니다")
    if str(owner[0]) != str(user.id):
        raise HTTPException(403, "작성자 본인만 수정할 수 있습니다")
    sets, params = [], {"id": str(post_id)}
    if body.title is not None:
        sets.append("title = :tt"); params["tt"] = body.title
    if body.body is not None:
        sets.append("body = :bd"); params["bd"] = body.body
    if body.region is not None:
        sets.append("region = :rg"); params["rg"] = body.region
    if body.specialty is not None:
        sets.append("specialty = :sp"); params["sp"] = list(body.specialty)
    if body.contact_method is not None:
        sets.append("contact_method = :cm"); params["cm"] = body.contact_method
    if body.status is not None:
        if body.status not in {"open", "closed"}:
            raise HTTPException(400, "status 는 open|closed 여야 합니다")
        sets.append("status = :st"); params["st"] = body.status
    if not sets:
        raise HTTPException(400, "수정할 항목이 없습니다")
    sets.append("updated_at = now()")
    await db.execute(text(f"UPDATE job_posts SET {', '.join(sets)} WHERE id = :id"), params)
    await db.commit()
    row = (await db.execute(text(f"SELECT {_POST_COLS} FROM job_posts WHERE id = :id"),
                            {"id": str(post_id)})).first()
    return {"post": _post_dict(row)}


# ── 신청(불러오기) ────────────────────────────────────────────────────────────
@market_router.post("/posts/{post_id}/apply", summary="공고 신청(프로필 불러오기)")
async def apply_post(post_id: uuid.UUID, body: ApplyRequest, db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    post = (await db.execute(text("SELECT author_user_id, status FROM job_posts WHERE id = :id"),
                             {"id": str(post_id)})).first()
    if not post:
        raise HTTPException(404, "공고를 찾을 수 없습니다")
    if str(post[0]) == str(user.id):
        raise HTTPException(400, "본인 공고에는 신청할 수 없습니다")
    if post[1] != "open":
        raise HTTPException(400, "마감된 공고입니다")

    # 불러오기 — profile_id 를 개인/회사 프로필 중 어느 쪽인지 본인 소유로 검증
    profile_personal_id: str | None = None
    profile_company_id: str | None = None
    if body.profile_id is not None:
        pp = (await db.execute(text(
            "SELECT id FROM profiles_personal WHERE id = :id AND user_id = :uid"),
            {"id": str(body.profile_id), "uid": str(user.id)})).first()
        if pp:
            profile_personal_id = str(pp[0])
        else:
            cp = (await db.execute(text(
                "SELECT id FROM profiles_company WHERE id = :id AND owner_user_id = :uid"),
                {"id": str(body.profile_id), "uid": str(user.id)})).first()
            if cp:
                profile_company_id = str(cp[0])
            else:
                raise HTTPException(403, "본인 소유 프로필만 불러올 수 있습니다")

    app_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO job_applications"
        " (id, post_id, applicant_user_id, profile_personal_id, profile_company_id, message)"
        " VALUES (:id,:pid,:uid,:pp,:cp,:msg)"),
        {"id": str(app_id), "pid": str(post_id), "uid": str(user.id),
         "pp": profile_personal_id, "cp": profile_company_id, "msg": body.message})
    await db.commit()
    return {"id": str(app_id), "post_id": str(post_id), "status": "applied",
            "profile_personal_id": profile_personal_id, "profile_company_id": profile_company_id}


@market_router.get("/posts/{post_id}/applications", summary="공고 신청자 목록(작성자)")
async def list_applications(post_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    post = (await db.execute(text("SELECT author_user_id FROM job_posts WHERE id = :id"),
                             {"id": str(post_id)})).first()
    if not post:
        raise HTTPException(404, "공고를 찾을 수 없습니다")
    if str(post[0]) != str(user.id):
        raise HTTPException(403, "작성자 본인만 신청자를 볼 수 있습니다")
    rows = (await db.execute(text(
        "SELECT a.id, a.applicant_user_id, a.profile_personal_id, a.profile_company_id,"
        "       a.message, a.status, a.created_at, u.name, u.email"
        "  FROM job_applications a LEFT JOIN users u ON u.id = a.applicant_user_id"
        " WHERE a.post_id = :pid ORDER BY a.created_at DESC"),
        {"pid": str(post_id)})).all()
    items = [{
        "id": str(r[0]), "applicant_user_id": str(r[1]),
        "profile_personal_id": str(r[2]) if r[2] else None,
        "profile_company_id": str(r[3]) if r[3] else None,
        "message": r[4], "status": r[5], "created_at": str(r[6]) if r[6] else None,
        "applicant_name": r[7], "applicant_email": r[8],
    } for r in rows]
    return {"items": items, "count": len(items)}


@market_router.post("/applications/{application_id}/decide", summary="신청 수락/거절(작성자) — 멱등")
async def decide_application(application_id: uuid.UUID, body: DecideRequest,
                            db: AsyncSession = Depends(get_db),
                            user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT a.id, a.post_id, a.applicant_user_id, a.status, p.author_user_id, p.site_id, p.kind"
        "  FROM job_applications a JOIN job_posts p ON p.id = a.post_id"
        " WHERE a.id = :id"), {"id": str(application_id)})).first()
    if not row:
        raise HTTPException(404, "신청을 찾을 수 없습니다")
    if str(row[4]) != str(user.id):
        raise HTTPException(403, "공고 작성자만 결정할 수 있습니다")
    new_status = "accepted" if body.accept else "rejected"
    # 멱등 — 이미 동일 상태면 재실행해도 부작용 없이 현재 상태 반환
    if row[3] == new_status:
        return {"id": str(application_id), "status": new_status, "idempotent": True, "membership_linked": False}

    await db.execute(text(
        "UPDATE job_applications SET status = :st, updated_at = now() WHERE id = :id"),
        {"st": new_status, "id": str(application_id)})

    membership_linked = False
    if body.accept:
        membership_linked = await _link_membership_on_accept(
            db, site_id=row[5], applicant_user_id=row[2], post_kind=row[6], decider=user)
    await db.commit()
    return {"id": str(application_id), "status": new_status, "idempotent": False,
            "membership_linked": membership_linked}


async def _link_membership_on_accept(db: AsyncSession, site_id, applicant_user_id,
                                     post_kind: str, decider) -> bool:
    """채용연계 — accept 시 기존 조직도(SalesOrgNode)에 멤버십을 best-effort 연결.

    안전조건(모두 충족해야 연결, 아니면 noop):
      - 공고에 site_id 가 있고(현장연계 공고)
      - 결정자(공고작성자)가 해당 현장의 관리자 역할이며
      - 지원자가 아직 그 현장에 active 멤버가 아닐 때
    추천코드 귀속·소셜그래프 자동연결은 별도 로직 부재 시 TODO(과설계 금지).

    ★[silent-fail 제거] 과거엔 모든 예외를 무시하고 False 를 돌려, '채용은 accepted 인데 조직노드는
      안 생긴' 유령 상태(데이터 불일치)를 은폐했다(테이블 부재·권한·구문·연결 오류가 전부 동일하게
      삼켜짐). 이제 SQLSTATE 로 분류한다:
        - 조직 테이블 미존재(42P01/42703) → '아직 조직도 미설치' 정상 noop(로그 info + False).
          이 현장은 조직도를 안 쓰므로 연결할 노드 자체가 없다(채용결정은 정상 진행).
        - 그 외 DB 오류(권한·연결·구문 등) → 분류 로깅 후 전파(raise). 멤버십 INSERT 가 실제로
          실패했는데 'accepted' 만 커밋되는 은폐를 막는다(운영자가 실패를 인지하도록).
    """
    if site_id is None or post_kind not in {"hire", "recruit_agency"}:
        return False
    try:
        # 결정자가 해당 현장의 관리자(노드 또는 플랫폼 역할)인지 확인
        decider_role = (getattr(decider, "role", "") or "").lower()
        is_admin = decider_role in _MANAGER_ROLES
        if not is_admin:
            mgr = (await db.execute(text(
                "SELECT node_type FROM sales_org_nodes"
                " WHERE site_id = :sid AND user_id = :uid AND active = true"),
                {"sid": str(site_id), "uid": str(decider.id)})).first()
            is_admin = bool(mgr and str(mgr[0]) in {
                "AGENCY", "SUBAGENCY", "GM_DIRECTOR", "DIRECTOR", "TEAM_LEADER"})
        if not is_admin:
            return False

        # 이미 멤버면 noop(멱등)
        existing = (await db.execute(text(
            "SELECT id FROM sales_org_nodes WHERE site_id = :sid AND user_id = :uid AND active = true"),
            {"sid": str(site_id), "uid": str(applicant_user_id)})).first()
        if existing:
            return True

        # 신규 MEMBER 노드 생성 — ltree path 는 현장 루트 하위 단순경로(고유 라벨).
        # ★라벨은 영문 'm' 접두(영숫자) — 숫자 시작 라벨은 text2ltree 캐스트가 거부하므로 접두로 방지.
        node_id = uuid.uuid4()
        label = f"m{str(node_id).replace('-', '')[:16]}"
        name_row = (await db.execute(text("SELECT name FROM users WHERE id = :uid"),
                                     {"uid": str(applicant_user_id)})).first()
        display = name_row[0] if name_row else None
        await db.execute(text(
            "INSERT INTO sales_org_nodes (id, site_id, node_type, path, user_id, display_name, active)"
            " VALUES (:id, :sid, 'MEMBER', :path::ltree, :uid, :nm, true)"),
            {"id": str(node_id), "sid": str(site_id), "path": label,
             "uid": str(applicant_user_id), "nm": display})
        # MGM 추천코드 귀속은 Phase1-C referral 모듈로 구현됨(고객 방문/계약 경로에서 귀속).
        # 채용(B2B)은 고객귀속과 별개 흐름이므로 여기서는 멤버십 연결만 수행한다.
        return True
    except Exception as e:  # noqa: BLE001 — 분류: 정상 noop(테이블부재)만 흡수, 실오류는 전파
        code = _missing_object_sqlstate(e)
        if code:
            logger.info("채용연계: 조직 테이블 미존재(%s) — 조직도 미설치 현장, 멤버십 연결 noop", code)
            return False
        logger.exception("채용연계: 멤버십 연결 실패(테이블부재 외 오류 — 전파, 채용결정과 함께 롤백)")
        raise


# ════════════════════════════════════════════════════════════════════════════
# 4) 현장 홍보(B2C 고객유치 + B2B 대행유치)
# ════════════════════════════════════════════════════════════════════════════
def _promo_dict(row) -> dict:
    return {
        "id": str(row[0]), "author_user_id": str(row[1]),
        "site_id": str(row[2]) if row[2] else None, "promo_type": row[3], "title": row[4],
        "body": row[5], "media_urls": list(row[6] or []), "region": row[7],
        "created_at": str(row[8]) if row[8] else None,
        "updated_at": str(row[9]) if row[9] else None,
    }


_PROMO_COLS = (
    "id, author_user_id, site_id, promo_type, title, body, media_urls, region,"
    " created_at, updated_at"
)


@market_router.post("/promotions", summary="현장 홍보 등록(B2C/B2B)")
async def create_promotion(body: PromotionCreate, db: AsyncSession = Depends(get_db),
                           user=Depends(get_current_user)) -> dict:
    if body.promo_type not in {"B2C", "B2B"}:
        raise HTTPException(400, "promo_type 은 B2C|B2B 중 하나여야 합니다")
    if not body.title.strip():
        raise HTTPException(400, "title 은 필수입니다")
    await _ensure(db)
    pid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO site_promotions (id, author_user_id, site_id, promo_type, title, body, media_urls, region)"
        " VALUES (:id,:au,:sid,:tp,:tt,:bd,:md,:rg)"),
        {"id": str(pid), "au": str(user.id), "sid": str(body.site_id) if body.site_id else None,
         "tp": body.promo_type, "tt": body.title, "bd": body.body,
         "md": list(body.media_urls), "rg": body.region})
    await db.commit()
    row = (await db.execute(text(f"SELECT {_PROMO_COLS} FROM site_promotions WHERE id = :id"),
                            {"id": str(pid)})).first()
    return {"promotion": _promo_dict(row), "notice": _PROMO_NOTICE}


@market_router.get("/promotions", summary="현장 홍보 목록(region/type)")
async def list_promotions(region: str | None = Query(default=None),
                          type: str | None = Query(default=None, alias="type"),
                          limit: int = Query(default=50, le=200),
                          db: AsyncSession = Depends(get_db),
                          user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    where = ["1=1"]
    params: dict = {"lim": limit}
    if region:
        where.append("region ILIKE :rg")
        params["rg"] = f"%{region}%"
    if type:
        if type not in {"B2C", "B2B"}:
            raise HTTPException(400, "type 은 B2C|B2B 여야 합니다")
        where.append("promo_type = :tp")
        params["tp"] = type
    rows = (await db.execute(text(
        f"SELECT {_PROMO_COLS} FROM site_promotions WHERE {' AND '.join(where)}"
        " ORDER BY created_at DESC LIMIT :lim"), params)).all()
    return {"items": [_promo_dict(r) for r in rows], "count": len(rows), "notice": _PROMO_NOTICE}


# ════════════════════════════════════════════════════════════════════════════
# 5) 직원관리 집계 — 본인이 관리하는 현장(들)의 멤버 실적/출근/계약/수수료 요약
#    scope=site : 단일 현장(site_id 필수) / scope=all : 내 멤버십 전 현장 union
# ════════════════════════════════════════════════════════════════════════════
async def _managed_site_ids(db: AsyncSession, user) -> list[str]:
    """내가 관리(또는 멤버)하는 현장 목록 — 조직도 노드 + 소유 현장(테넌트) union."""
    sids: set[str] = set()
    rows = (await db.execute(text(
        "SELECT DISTINCT site_id FROM sales_org_nodes WHERE user_id = :uid AND active = true"),
        {"uid": str(user.id)})).all()
    for r in rows:
        if r[0]:
            sids.add(str(r[0]))
    # 본인 테넌트 소유 현장(organization_id == user.tenant_id)
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id:
        owned = (await db.execute(text(
            "SELECT id FROM sales_sites WHERE organization_id = :tid"),
            {"tid": str(tenant_id)})).all()
        for r in owned:
            sids.add(str(r[0]))
    return list(sids)


async def _site_staff_summary(db: AsyncSession, site_id: str) -> SiteStaffSummary:
    """현장 1곳의 멤버 실적/출근/계약/수수료 요약 — 기존 sales 집계 재사용.

    ★[silent-fail 제거] 계약·출근·수수료 집계의 예외를 무조건 0으로 삼던 것을 SQLSTATE 분류로
      바꾼다. 집계는 count(*)/sum() 이라 특정 컬럼을 지목하지 않으므로, '테이블 미존재(42P01)'만
      '정상 0(아직 안 만든 집계 대상)'으로 보고 0 을 쓰고, 컬럼 미존재(42703=스키마 드리프트)를
      포함한 그 외 DB 오류(권한·연결·구문 등)는 분류 로깅 후 전파한다(은폐 금지). 공유
      _missing_object_sqlstate(42P01+42703) 대신 _missing_table_sqlstate(42P01만)를 쓰는 이유:
      42703 까지 흡수하면 '있어야 할 컬럼이 사라진' 진짜 결함이 '계약/매출 0' 으로 은폐된다.
    """
    member_cnt = (await db.execute(text(
        "SELECT count(*) FROM sales_org_nodes WHERE site_id = :sid AND active = true"),
        {"sid": site_id})).scalar() or 0
    site_name = (await db.execute(text(
        "SELECT site_name FROM sales_sites WHERE id = :sid"), {"sid": site_id})).scalar()

    contracts = 0
    try:
        contracts = (await db.execute(text(
            "SELECT count(*) FROM sales_contracts WHERE site_id = :sid"), {"sid": site_id})).scalar() or 0
    except Exception as e:  # noqa: BLE001 — 테이블부재(42P01)만 정상0, 컬럼누락(42703)·실오류는 전파
        if _missing_table_sqlstate(e):
            logger.info("staff_summary: sales_contracts 미존재(42P01) — 계약 0")
            contracts = 0
        else:
            logger.exception("staff_summary: 계약 집계 실패(테이블부재 외 오류 — 전파)")
            raise

    attendance = 0
    try:
        attendance = (await db.execute(text(
            "SELECT count(*) FROM sales_staff_attendance WHERE site_id = :sid"),
            {"sid": site_id})).scalar() or 0
    except Exception as e:  # noqa: BLE001 — 테이블부재(42P01)만 정상0, 컬럼누락(42703)·실오류는 전파
        if _missing_table_sqlstate(e):
            logger.info("staff_summary: sales_staff_attendance 미존재(42P01) — 출근 0")
            attendance = 0
        else:
            logger.exception("staff_summary: 출근 집계 실패(테이블부재 외 오류 — 전파)")
            raise

    commission_gross = 0
    try:
        # ★[HIGH·correctness(iter-6)] 과거 'sum(e.amount)' 는 sales_commission_events 에 없는 컬럼을
        #   지목했다(events 엔 base_amount 만 있고 amount 는 sales_commission_splits 의 컬럼이다 —
        #   commission_mh_harness.py 의 SalesCommissionEvent.base_amount / SalesCommissionSplit.amount).
        #   iter-3 가 42703(컬럼누락)을 더 이상 흡수하지 않게 바꾸면서, 테이블이 존재하는 모든 라이브
        #   DB 에서 이 집계가 42703 으로 전파돼 staff_overview 가 500 이 됐다. base_amount(수수료
        #   베이스액=현장 gross 의미) 로 교정한다 — 컬럼 계약은 test_sales_commission_event_column_contract
        #   로 고정(ORM introspection 으로 컬럼명 드리프트 차단).
        row = (await db.execute(text(
            "SELECT coalesce(sum(e.base_amount),0) FROM sales_commission_events e WHERE e.site_id = :sid"),
            {"sid": site_id})).first()
        commission_gross = int(row[0]) if row and row[0] is not None else 0
    except Exception as e:  # noqa: BLE001 — 테이블부재(42P01)만 정상0, 컬럼누락(42703)·실오류는 전파
        if _missing_table_sqlstate(e):
            logger.info("staff_summary: sales_commission_events 미존재(42P01) — 수수료 0")
            commission_gross = 0
        else:
            logger.exception("staff_summary: 수수료 집계 실패(테이블부재 외 오류 — 전파)")
            raise

    return SiteStaffSummary(
        site_id=site_id, site_name=site_name or "-",
        member_count=int(member_cnt), contract_count=int(contracts),
        attendance_count=int(attendance), commission_gross=commission_gross,
    )


@market_router.get("/staff/overview", summary="직원관리 집계(scope=site|all)",
                   response_model=StaffOverviewResponse)
async def staff_overview(scope: str = Query(default="all"),
                         site_id: uuid.UUID | None = Query(default=None),
                         db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> StaffOverviewResponse:
    if scope not in {"site", "all"}:
        raise HTTPException(400, "scope 는 site|all 중 하나여야 합니다")
    await _ensure(db)  # market 테이블 보장(혼합 호출 안전)

    managed = await _managed_site_ids(db, user)
    if scope == "site":
        if site_id is None:
            raise HTTPException(400, "scope=site 는 site_id 가 필요합니다")
        if str(site_id) not in managed:
            raise HTTPException(403, "관리(멤버) 권한이 있는 현장만 조회할 수 있습니다")
        target = [str(site_id)]
    else:
        target = managed

    # 현장 N개를 호출자 요청세션(db) 하나로 순차 집계한다. _ensure 와 동일 엔진(app.core.database)을
    # 재사용해 엔진 혼용(core 5432 vs apps.api 5444)을 원천 차단한다 — _ensure 가 만든 테이블을 같은
    # 엔진으로 읽으므로 SSOT 일관성이 보장된다.
    # backlog: 다현장 N+1 직렬 라운드트립은 정확·유계지만, 추후 '동일 엔진' 세마포어 병렬화로 최적화
    #          (별도 엔진 팬아웃 금지 — SSOT 위반). 이번엔 정확성 우선으로 직렬 유지.
    sites = [await _site_staff_summary(db, sid) for sid in target]
    totals = StaffOverviewTotals(
        member_count=sum(s.member_count for s in sites),
        contract_count=sum(s.contract_count for s in sites),
        attendance_count=sum(s.attendance_count for s in sites),
        commission_gross=sum(s.commission_gross for s in sites),
    )
    return StaffOverviewResponse(scope=scope, site_count=len(sites), sites=sites, totals=totals)
