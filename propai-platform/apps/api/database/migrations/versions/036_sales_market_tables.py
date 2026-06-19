"""#5 조직도·직원 — 마켓 PUBLIC 테이블 런타임 DDL 정본화(Alembic 이관).

Revision ID: 036_sales_market_tables
Revises: 035_sales_payment_loan_settlement
Create Date: 2026-06-19

#5 조직도·직원 Wave2 P1-2(5.8→8.0)의 스키마 정본.

[배경/해소]
기존에 market.py 의 _ensure() 가 '매 요청' 5개 PUBLIC 테이블을 CREATE TABLE IF NOT EXISTS 로
만들었다(런타임 DDL). 이를 본 마이그레이션으로 정본 이관한다.
대상(5개): profiles_personal, profiles_company, job_posts, job_applications, site_promotions.
  - profiles_personal/company : 재사용 개인·회사 프로필
  - job_posts                 : 구인/구직/현장홍보/대행모집 공고(kind: hire|seek|promote_site|recruit_agency)
  - job_applications          : 공고 지원(status: applied|accepted|rejected)
  - site_promotions           : 현장 홍보(B2C 고객유치 | B2B 대행유치)

런타임 _ensure() 는 마이그레이션 미적용 환경(개발/신규배포) 대비 '프로세스 1회 + advisory-lock'
부팅 안전망으로 강등된다(매 요청 DDL 제거 + 동시 부팅 race 제거). 정본은 본 마이그레이션이다.

DDL 본문은 market.py 의 *_DDL 상수와 1:1 동일하게 유지(컬럼/타입/UNIQUE/DEFAULT 정합) — 적용
환경에선 IF NOT EXISTS 라 no-op, 미적용 환경에선 런타임 안전망이 동일 스키마를 만든다(충돌 없음).
전부 additive·IF NOT EXISTS 라 기존 데이터·동작 무회귀.

★헤드: 직전 단일 헤드는 035_sales_payment_loan_settlement(035 를 단일 부모로 받아 헤드 1개 유지).
  샌드박스에선 라이브 적용 불가(deploy-pending) — 코드 정본만 추가한다.
"""
# ★[지연 import] `from alembic import op` 는 upgrade()/downgrade() 안에서 한다(최상위 아님).
#   이렇게 하면 alembic 미설치 환경(샌드박스 테스트)에서도 이 모듈을 import 할 수 있어, 런타임
#   _ensure 와 정본 마이그레이션이 같은 SSOT(sales_market_ddl) 상수를 쓰는지 단위테스트로 잠글 수
#   있다(op 는 실제 마이그레이션 실행 시점에만 필요하므로 지연 import 가 안전하다).

# ★[DDL/인덱스 SSOT] 테이블 5개 + 인덱스 3개 DDL 은 database/sales_market_ddl.py 단일 정본을 import
#   한다. 과거엔 동일 DDL 이 이 마이그레이션과 market.py 의 _ensure() 에 '복붙'으로 중복돼 드리프트
#   위험이 있었다. 두 소비자가 같은 한 부를 import 해 컬럼/타입/UNIQUE/DEFAULT/인덱스가 영원히 동일.
#   (v62_1_sales_tables.py 가 apps.api.database.models 를 import 하는 검증된 패턴과 동일.)
from apps.api.database.sales_market_ddl import INDEX_DDLS, TABLE_DDLS

revision = "036_sales_market_tables"
down_revision = "035_sales_payment_loan_settlement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op  # 지연 import — 마이그레이션 실행 시점에만 필요(상단 주석 참조).

    for ddl in TABLE_DDLS:    # 테이블 5개(IF NOT EXISTS) — PUBLIC 컨텐츠(현장 격리 대상 아님).
        op.execute(ddl)
    for idx in INDEX_DDLS:    # 조회 가속 인덱스 3개(공고 목록/지원 조회/홍보 현장).
        op.execute(idx)


def downgrade() -> None:
    from alembic import op  # 지연 import — 마이그레이션 실행 시점에만 필요(상단 주석 참조).

    # 데이터 보존: 런타임 DDL 로 만들어진 동일 테이블과 충돌하지 않게 인덱스만 되돌린다.
    # (테이블은 PUBLIC 컨텐츠 보존 — 드롭하지 않음. 런타임 안전망이 재생성하므로 무해.)
    op.execute("DROP INDEX IF EXISTS idx_site_promotions_site")
    op.execute("DROP INDEX IF EXISTS idx_job_apps_post")
    op.execute("DROP INDEX IF EXISTS idx_job_posts_kind_status")
