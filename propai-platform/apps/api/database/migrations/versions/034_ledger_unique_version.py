"""034 — 분석 원장 체인 버전 UNIQUE 백스톱 + 기존 중복 version 결정적 정리 (P1-5)

Revision ID: 034_ledger_unique_version
Revises: 033_shadow_comparison
Create Date: 2026-07-02

배경(감사 P1-5): append_analysis 가 '최신 version 조회 → +1 INSERT'를 락 없이 수행해
동시 append 시 같은 체인에 중복 version(포크된 prev_hash)이 생길 수 있었다.
서비스에 pg_advisory_xact_lock(체인키) 직렬화를 추가했고(1차 방어), 본 마이그레이션은
 (a) 기존 중복 version 을 결정적으로 재번호 — 중복을 포함한 '체인 전체'를
     (version, created_at, id) 순으로 1..N 재부여. payload/content_hash 는 불변(원장 내용 보존),
     version 번호만 정합화(중복 체인은 이미 prev_hash 연속성이 깨져 있던 상태).
 (b) COALESCE 표현식 UNIQUE 인덱스 백스톱을 추가한다(2차 방어 — 레이스 재발 시 INSERT 가
     unique_violation 으로 실패해 침묵 포크 대신 관측 가능한 오류가 된다).

한계(정직): 체인 식별은 조회 시 pnu 우선/주소 폴백의 '유연 키'라, 같은 논리 체인이라도 저장
컬럼이 다른 행(예: 같은 pnu·다른 address_norm) 간 중복은 본 인덱스가 못 막는다 — 그 경우는
서비스 advisory lock 이 방어선이다.

★서비스 lazy-DDL(_IDX)에는 본 UNIQUE 를 넣지 않는다: 본 마이그레이션(선정리) 없이 중복을
보유한 환경에서 _ensure() 가 인덱스 생성에 실패하면 append 전체가 침묵 불능이 되기 때문.
UNIQUE 인덱스 생성 경로는 이 파일이 유일하다.
"""
from alembic import op

revision = "034_ledger_unique_version"
down_revision = "033_shadow_comparison"
branch_labels = None
depends_on = None

# 중복 version 을 가진 체인 전체를 결정적으로 재번호(테스트에서 임포트해 헤르메틱 검증).
DEDUPE_SQL = """
WITH dup_chain AS (
    SELECT DISTINCT COALESCE(tenant_id,'') AS t, COALESCE(pnu,'') AS p,
           COALESCE(address_norm,'') AS a, COALESCE(project_id,'') AS pr, analysis_type AS ty
    FROM analysis_ledger
    GROUP BY COALESCE(tenant_id,''), COALESCE(pnu,''), COALESCE(address_norm,''),
             COALESCE(project_id,''), analysis_type, version
    HAVING COUNT(*) > 1
), renum AS (
    SELECT l.id,
           ROW_NUMBER() OVER (
               PARTITION BY COALESCE(l.tenant_id,''), COALESCE(l.pnu,''),
                            COALESCE(l.address_norm,''), COALESCE(l.project_id,''), l.analysis_type
               ORDER BY l.version, l.created_at, l.id) AS new_version
    FROM analysis_ledger l
    JOIN dup_chain d
      ON COALESCE(l.tenant_id,'') = d.t AND COALESCE(l.pnu,'') = d.p
     AND COALESCE(l.address_norm,'') = d.a AND COALESCE(l.project_id,'') = d.pr
     AND l.analysis_type = d.ty
)
UPDATE analysis_ledger AS al SET version = r.new_version
FROM renum r WHERE al.id = r.id AND al.version <> r.new_version
"""

UNIQUE_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_chain_version "
    "ON analysis_ledger (COALESCE(tenant_id,''), COALESCE(pnu,''), COALESCE(address_norm,''), "
    "COALESCE(project_id,''), analysis_type, version)"
)


def upgrade() -> None:
    op.execute(DEDUPE_SQL)
    op.execute(UNIQUE_INDEX_SQL)


def downgrade() -> None:
    # 재번호는 불가역(원장 내용은 불변·번호만 정합화라 롤백 불필요). 인덱스만 제거.
    op.execute("DROP INDEX IF EXISTS uq_ledger_chain_version")
