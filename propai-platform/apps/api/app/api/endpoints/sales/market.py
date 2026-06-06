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

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db

market_router = APIRouter(prefix="/api/v1/market", tags=["sales-market"])

# 채용연계(조직도 멤버십 생성) 가능 역할 — 현장 관리자
_MANAGER_ROLES = {"superadmin", "super_admin", "admin", "owner", "developer", "agency"}

# ── 표시광고법·개인정보 동의 고지 문구(홍보 응답에 포함) ───────────────────────
_PROMO_NOTICE = (
    "본 홍보는 표시·광고의 공정화에 관한 법률을 준수하며, 개인정보 수집·이용 동의 후 "
    "연락이 진행됩니다. 실적·정보는 작성자 자기기재이며 사실과 다를 수 있습니다."
)


# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
_PROFILE_PERSONAL_DDL = (
    "CREATE TABLE IF NOT EXISTS profiles_personal ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  user_id uuid NOT NULL UNIQUE,"
    "  full_name varchar(120),"
    "  contact varchar(120),"                    # 연락처(전화/카톡 등)
    "  region varchar(120),"                     # 활동지역
    "  specialties text[] DEFAULT '{}',"         # 전문분야
    "  experience_years int DEFAULT 0,"
    "  achievement_summary text,"                # 실적요약(자기기재)
    "  certifications text[] DEFAULT '{}',"      # 자격
    "  desired_conditions text,"                 # 희망조건
    "  photo_url text,"                          # 프로필 사진 URL
    "  visibility varchar(12) NOT NULL DEFAULT 'public',"  # public|contacts|private
    "  mask_contact boolean NOT NULL DEFAULT true,"        # 연락처 마스킹 여부
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_PROFILE_COMPANY_DDL = (
    "CREATE TABLE IF NOT EXISTS profiles_company ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  owner_user_id uuid NOT NULL UNIQUE,"
    "  org_id uuid,"                             # 연계 조직(선택)
    "  company_name varchar(200),"
    "  company_type varchar(16) NOT NULL DEFAULT 'AGENCY',"  # DEVELOPER(시행)|AGENCY(대행)
    "  company_size varchar(40),"
    "  intro text,"                              # 소개
    "  active_sites text,"                       # 진행현장(자기기재)
    "  reputation text,"                         # 평판/실적(자기기재)
    "  logo_url text,"                           # 회사 로고 URL
    "  contact varchar(120),"
    "  region varchar(120),"
    "  visibility varchar(12) NOT NULL DEFAULT 'public',"
    "  mask_contact boolean NOT NULL DEFAULT true,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_JOB_POSTS_DDL = (
    "CREATE TABLE IF NOT EXISTS job_posts ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  author_user_id uuid NOT NULL,"
    "  kind varchar(16) NOT NULL,"               # hire|seek|promote_site|recruit_agency
    "  title varchar(200) NOT NULL,"
    "  body text,"
    "  region varchar(120),"
    "  specialty text[] DEFAULT '{}',"
    "  site_id uuid,"                            # 현장연계(선택, 채용연계 훅에 사용)
    "  contact_method varchar(200),"            # 연락방식
    "  status varchar(12) NOT NULL DEFAULT 'open',"  # open|closed
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_JOB_APPLICATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS job_applications ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  post_id uuid NOT NULL,"
    "  applicant_user_id uuid NOT NULL,"
    "  profile_personal_id uuid,"               # 불러오기(개인)
    "  profile_company_id uuid,"                 # 불러오기(회사)
    "  message text,"
    "  status varchar(12) NOT NULL DEFAULT 'applied',"  # applied|accepted|rejected
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_SITE_PROMOTIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS site_promotions ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  author_user_id uuid NOT NULL,"
    "  site_id uuid,"
    "  promo_type varchar(8) NOT NULL DEFAULT 'B2C',"  # B2C(고객유치)|B2B(대행유치)
    "  title varchar(200) NOT NULL,"
    "  body text,"
    "  media_urls text[] DEFAULT '{}',"
    "  region varchar(120),"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)


async def _ensure(db: AsyncSession) -> None:
    """마켓 PUBLIC 테이블 멱등 생성(최초 호출 시 1회). 기존 sales/mh 테이블 무파괴.

    ★ 테이블명에 sales_/mh_ 접두를 쓰지 않으므로 RLS 부트스트랩 동적조회에서 자동 제외.
    """
    await db.execute(text(_PROFILE_PERSONAL_DDL))
    await db.execute(text(_PROFILE_COMPANY_DDL))
    await db.execute(text(_JOB_POSTS_DDL))
    await db.execute(text(_JOB_APPLICATIONS_DDL))
    await db.execute(text(_SITE_PROMOTIONS_DDL))


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
    except Exception:  # noqa: BLE001 — 멤버십 연결 실패는 채용결정을 막지 않음(best-effort)
        return False


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


async def _site_staff_summary(db: AsyncSession, site_id: str) -> dict:
    """현장 1곳의 멤버 실적/출근/계약/수수료 요약 — 기존 sales 집계 재사용(best-effort)."""
    member_cnt = (await db.execute(text(
        "SELECT count(*) FROM sales_org_nodes WHERE site_id = :sid AND active = true"),
        {"sid": site_id})).scalar() or 0
    site_name = (await db.execute(text(
        "SELECT site_name FROM sales_sites WHERE id = :sid"), {"sid": site_id})).scalar()

    contracts = 0
    try:
        contracts = (await db.execute(text(
            "SELECT count(*) FROM sales_contracts WHERE site_id = :sid"), {"sid": site_id})).scalar() or 0
    except Exception:  # noqa: BLE001 — 테이블/컬럼 차이 시 0
        contracts = 0

    attendance = 0
    try:
        attendance = (await db.execute(text(
            "SELECT count(*) FROM sales_staff_attendance WHERE site_id = :sid"),
            {"sid": site_id})).scalar() or 0
    except Exception:  # noqa: BLE001
        attendance = 0

    commission_gross = 0
    try:
        row = (await db.execute(text(
            "SELECT coalesce(sum(e.amount),0) FROM sales_commission_events e WHERE e.site_id = :sid"),
            {"sid": site_id})).first()
        commission_gross = int(row[0]) if row and row[0] is not None else 0
    except Exception:  # noqa: BLE001
        commission_gross = 0

    return {
        "site_id": site_id, "site_name": site_name or "-",
        "member_count": int(member_cnt), "contract_count": int(contracts),
        "attendance_count": int(attendance), "commission_gross": commission_gross,
    }


@market_router.get("/staff/overview", summary="직원관리 집계(scope=site|all)")
async def staff_overview(scope: str = Query(default="all"),
                         site_id: uuid.UUID | None = Query(default=None),
                         db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> dict:
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

    sites = [await _site_staff_summary(db, sid) for sid in target]
    totals = {
        "member_count": sum(s["member_count"] for s in sites),
        "contract_count": sum(s["contract_count"] for s in sites),
        "attendance_count": sum(s["attendance_count"] for s in sites),
        "commission_gross": sum(s["commission_gross"] for s in sites),
    }
    return {"scope": scope, "site_count": len(sites), "sites": sites, "totals": totals}
