"""#5 조직도·직원 — 마켓 PUBLIC 테이블 DDL/인덱스 SSOT(단일 정본).

★왜 이 모듈이 있나(드리프트 제거)
  과거엔 같은 5개 테이블 DDL 이 두 곳(런타임 _ensure(): market.py / 정본 마이그레이션: 036)에
  '복붙'으로 존재했고, 인덱스는 036 에만 있고 _ensure() 엔 없어 마이그레이션 미적용 환경(개발/신규
  배포)에서는 인덱스 없이 동작하는 '드리프트'가 있었다. 두 소비자가 '같은 한 부'를 import 하도록
  여기로 추출해(SSOT) 컬럼/타입/UNIQUE/DEFAULT/인덱스가 영원히 동일하게 유지되도록 한다.

  - market.py 의 _ensure() = 부팅 안전망(advisory-lock·프로세스 1회). 마이그레이션 미적용 환경 대비.
  - versions/036_sales_market_tables.py = 라이브 정본(Alembic). 둘 다 이 상수를 그대로 쓴다.

  테이블명에 sales_/mh_ 접두를 쓰지 않으므로 RLS 부트스트랩 동적조회에서 자동 제외(PUBLIC 컨텐츠).
  전부 IF NOT EXISTS 라 additive·무회귀(적용 환경에선 no-op, 미적용 환경에선 안전망이 동일 생성).
"""
from __future__ import annotations

# ── 5개 PUBLIC 테이블 DDL(IF NOT EXISTS, gen_random_uuid 기본) ──────────────────
PROFILE_PERSONAL_DDL = (
    "CREATE TABLE IF NOT EXISTS profiles_personal ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  user_id uuid NOT NULL UNIQUE,"
    "  full_name varchar(120),"
    "  contact varchar(120),"
    "  region varchar(120),"
    "  specialties text[] DEFAULT '{}',"
    "  experience_years int DEFAULT 0,"
    "  achievement_summary text,"
    "  certifications text[] DEFAULT '{}',"
    "  desired_conditions text,"
    "  photo_url text,"
    "  visibility varchar(12) NOT NULL DEFAULT 'public',"
    "  mask_contact boolean NOT NULL DEFAULT true,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
PROFILE_COMPANY_DDL = (
    "CREATE TABLE IF NOT EXISTS profiles_company ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  owner_user_id uuid NOT NULL UNIQUE,"
    "  org_id uuid,"
    "  company_name varchar(200),"
    "  company_type varchar(16) NOT NULL DEFAULT 'AGENCY',"
    "  company_size varchar(40),"
    "  intro text,"
    "  active_sites text,"
    "  reputation text,"
    "  logo_url text,"
    "  contact varchar(120),"
    "  region varchar(120),"
    "  visibility varchar(12) NOT NULL DEFAULT 'public',"
    "  mask_contact boolean NOT NULL DEFAULT true,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
JOB_POSTS_DDL = (
    "CREATE TABLE IF NOT EXISTS job_posts ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  author_user_id uuid NOT NULL,"
    "  kind varchar(16) NOT NULL,"
    "  title varchar(200) NOT NULL,"
    "  body text,"
    "  region varchar(120),"
    "  specialty text[] DEFAULT '{}',"
    "  site_id uuid,"
    "  contact_method varchar(200),"
    "  status varchar(12) NOT NULL DEFAULT 'open',"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
JOB_APPLICATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS job_applications ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  post_id uuid NOT NULL,"
    "  applicant_user_id uuid NOT NULL,"
    "  profile_personal_id uuid,"
    "  profile_company_id uuid,"
    "  message text,"
    "  status varchar(12) NOT NULL DEFAULT 'applied',"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
SITE_PROMOTIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS site_promotions ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  author_user_id uuid NOT NULL,"
    "  site_id uuid,"
    "  promo_type varchar(8) NOT NULL DEFAULT 'B2C',"
    "  title varchar(200) NOT NULL,"
    "  body text,"
    "  media_urls text[] DEFAULT '{}',"
    "  region varchar(120),"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)

# ── 조회 가속 인덱스(IF NOT EXISTS) — 공고 목록/지원 조회/홍보 현장 ───────────────
INDEX_JOB_POSTS_KIND_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_job_posts_kind_status ON job_posts (kind, status)"
)
INDEX_JOB_APPS_POST = (
    "CREATE INDEX IF NOT EXISTS idx_job_apps_post ON job_applications (post_id)"
)
INDEX_SITE_PROMOTIONS_SITE = (
    "CREATE INDEX IF NOT EXISTS idx_site_promotions_site ON site_promotions (site_id)"
)

# 소비자가 순서대로 실행하면 되도록 묶음 제공(테이블 5개 → 인덱스 3개).
TABLE_DDLS: tuple[str, ...] = (
    PROFILE_PERSONAL_DDL,
    PROFILE_COMPANY_DDL,
    JOB_POSTS_DDL,
    JOB_APPLICATIONS_DDL,
    SITE_PROMOTIONS_DDL,
)
INDEX_DDLS: tuple[str, ...] = (
    INDEX_JOB_POSTS_KIND_STATUS,
    INDEX_JOB_APPS_POST,
    INDEX_SITE_PROMOTIONS_SITE,
)
